"""Synthetic SQLite upgrade, head reconciliation and failure-boundary proofs."""
from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from pulpo import GovernanceKernel, Policy, SQLiteKernelState, StateIntegrityError
import pulpo.state as state_module


class AuditIntegrityMigrationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "disposable.sqlite3"

    def state(self):
        state = SQLiteKernelState(self.path)
        self.addCleanup(state.close)
        return state

    def kernel(self, state):
        return GovernanceKernel(Policy(frozenset(), 0), secret=b"fixture", state=state)

    def seed(self):
        state = self.state()
        for i, timestamp in enumerate((100, 10, 10, -1)):
            state.append("fixture", {"i": i}, timestamp)
        self.assertTrue(self.kernel(state).verify_audit())
        records = state.audit
        state.close()
        return records

    def legacy(self):
        records = self.seed()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            for name in ("audit_head_check_insert", "audit_head_advance"):
                connection.execute(f"DROP TRIGGER IF EXISTS {name}")
            connection.execute("DROP TABLE IF EXISTS audit_integrity_schema")
            connection.execute("DROP TABLE IF EXISTS audit_head")
        return records

    def snapshot(self):
        with closing(sqlite3.connect(self.path)) as connection:
            return tuple(connection.iterdump())

    def test_legacy_adoption_preserves_bytes_clock_rollback_and_restart(self):
        records = self.legacy()
        state = self.state()
        self.assertEqual(records, state.audit)
        self.assertTrue(self.kernel(state).verify_audit())
        state.append("after", {}, -100)
        state.close()
        reopened = self.state()
        self.assertEqual(records, reopened.audit[:4])
        self.assertTrue(self.kernel(reopened).verify_audit())

    def test_failed_alter_rolls_back_all_schema_changes(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("CREATE TABLE permit_directives (permit TEXT PRIMARY KEY)")
        before = self.snapshot()
        original = sqlite3.connect
        def connect(*args, **kwargs):
            connection = original(*args, **kwargs)
            connection.set_authorizer(lambda action, *unused: sqlite3.SQLITE_DENY
                                      if action == sqlite3.SQLITE_ALTER_TABLE else sqlite3.SQLITE_OK)
            return connection
        with patch.object(state_module.sqlite3, "connect", connect):
            with self.assertRaises(sqlite3.DatabaseError):
                self.state()
        self.assertEqual(before, self.snapshot())

    def test_failed_head_publication_rolls_back_upgrade(self):
        self.legacy()
        before = self.snapshot()
        original = sqlite3.connect
        def connect(*args, **kwargs):
            connection = original(*args, **kwargs)
            connection.set_authorizer(lambda action, table, *unused: sqlite3.SQLITE_DENY
                                      if action == sqlite3.SQLITE_INSERT and table == "audit_integrity_schema"
                                      else sqlite3.SQLITE_OK)
            return connection
        with patch.object(state_module.sqlite3, "connect", connect):
            with self.assertRaises(sqlite3.DatabaseError):
                self.state()
        self.assertEqual(before, self.snapshot())

    def test_failed_migration_commit_rolls_back_all_changes(self):
        self.legacy()
        before = self.snapshot()
        original = sqlite3.connect
        def connect(*args, **kwargs):
            kwargs["timeout"] = 0.01
            return original(*args, **kwargs)
        with closing(original(self.path)) as reader:
            reader.execute("BEGIN")
            reader.execute("SELECT COUNT(*) FROM audit").fetchone()
            with patch.object(state_module.sqlite3, "connect", connect):
                with self.assertRaisesRegex(sqlite3.OperationalError, "locked"):
                    self.state()
            reader.rollback()
        self.assertEqual(before, self.snapshot())

    def test_separate_process_restart_preserves_head_and_chain(self):
        records = self.seed()
        code = """
import sys
sys.path.insert(0, sys.argv[1])
from pulpo import GovernanceKernel, Policy, SQLiteKernelState
with SQLiteKernelState(sys.argv[2]) as state:
    kernel = GovernanceKernel(Policy(frozenset(), 0), secret=b'fixture', state=state)
    if len(state.audit) != 4 or not kernel.verify_audit():
        raise RuntimeError('restart verification failed')
    state.append('child', {}, -100)
    if not kernel.verify_audit():
        raise RuntimeError('child append verification failed')
"""
        result = subprocess.run([sys.executable, "-B", "-c", code,
                                 str(Path(state_module.__file__).resolve().parent.parent), str(self.path)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(0, result.returncode, result.stderr)
        state = self.state()
        self.assertEqual(records, state.audit[:4])
        self.assertEqual("child", state.audit[-1]["event"])
        self.assertTrue(self.kernel(state).verify_audit())

    def test_corrupt_legacy_chain_does_not_publish_schema_or_head(self):
        self.legacy()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE audit SET payload_json='{}' WHERE sequence=2")
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "audit"):
            self.state()
        self.assertEqual(before, self.snapshot())

    def test_preexisting_matching_head_is_reconciled_without_overwrite(self):
        records = self.legacy()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("CREATE TABLE audit_head (id INTEGER PRIMARY KEY, sequence INTEGER NOT NULL, hash TEXT NOT NULL)")
            connection.execute("INSERT INTO audit_head VALUES (1,4,?)", (records[-1]["hash"],))
            connection.execute("CREATE TRIGGER no_head_replacement BEFORE UPDATE ON audit_head BEGIN SELECT RAISE(ABORT, 'must not overwrite'); END")
        state = self.state()
        self.assertTrue(self.kernel(state).verify_audit())

    def test_preexisting_mismatched_head_rejects_and_rolls_back(self):
        self.legacy()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("CREATE TABLE audit_head (id INTEGER PRIMARY KEY, sequence INTEGER NOT NULL, hash TEXT NOT NULL)")
            connection.execute("INSERT INTO audit_head VALUES (1,4,?)", ("f" * 64,))
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "audit head"):
            self.state()
        self.assertEqual(before, self.snapshot())

    def test_missing_head_row_and_table_fail_closed_without_recreation(self):
        for drop in (False, True):
            with self.subTest(drop=drop):
                self.seed()
                with closing(sqlite3.connect(self.path)) as connection, connection:
                    connection.execute("DELETE FROM audit_head")
                    if drop:
                        connection.execute("DROP TABLE audit_head")
                before = self.snapshot()
                with self.assertRaisesRegex(ValueError, "audit head"):
                    self.state()
                self.assertEqual(before, self.snapshot())
                # Restore a disposable fixture for the next variant only.
                with closing(sqlite3.connect(self.path)) as connection, connection:
                    for name in ("audit_head_check_insert", "audit_head_advance"):
                        connection.execute(f"DROP TRIGGER IF EXISTS {name}")
                    connection.execute("DROP TABLE audit_integrity_schema")
                    connection.execute("DROP TABLE IF EXISTS audit_head")

    def test_tail_deletion_rejects_before_restart_or_another_append(self):
        self.seed()
        state = self.state()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("DELETE FROM audit WHERE sequence=4")
        with self.assertRaises(StateIntegrityError):
            self.kernel(state)
        before = self.snapshot()
        with self.assertRaises(sqlite3.IntegrityError):
            state.append("must not heal", {}, 1)
        self.assertEqual(before, self.snapshot())
        state.close()
        with self.assertRaisesRegex(ValueError, "audit head"):
            self.state()

    def test_head_update_failure_rolls_back_audit_insert(self):
        self.seed()
        state = self.state()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("CREATE TRIGGER reject_head_update BEFORE UPDATE ON audit_head BEGIN SELECT RAISE(ABORT, 'head update failure'); END")
        before = self.snapshot()
        with self.assertRaisesRegex(sqlite3.IntegrityError, "head update failure"):
            state.append("not committed", {}, 1)
        self.assertEqual(before, self.snapshot())


if __name__ == "__main__":
    unittest.main()
