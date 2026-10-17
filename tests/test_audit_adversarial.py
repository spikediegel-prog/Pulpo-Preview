"""Disposable adversarial fixtures; no production paths or external services."""
from contextlib import closing
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest

from pulpo import GovernanceKernel, Policy, SQLiteKernelState, StateIntegrityError
from pulpo.state import ApprovalUse


ROOT = Path(__file__).resolve().parents[1]
CHILD = r'''
import sys,time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from pulpo import SQLiteKernelState
path, operation, ready = sys.argv[2:5]
def pause():
    Path(ready).write_text('ready')
    sys.stdin.readline()
    return 0
if operation == 'migrate-before':
    original = SQLiteKernelState._initialize_transaction
    def initialize(self, **kw):
        original(self, **kw)
        pause()
    SQLiteKernelState._initialize_transaction = initialize
if operation == 'race':
    sys.stdin.readline()
with SQLiteKernelState(path) as state:
    if operation == 'append-before':
        state._connection.create_function('pause_fixture', 0, pause)
        state._connection.execute('CREATE TEMP TRIGGER pause_insert AFTER INSERT ON main.audit BEGIN SELECT pause_fixture(); END')
        state.append('child', {}, -100)
    elif operation == 'append-after':
        state.append('child', {}, -100)
        pause()
    elif operation == 'migrate-after':
        pause()
    elif operation == 'race':
        state.append(ready, {}, -100)
    else:
        pass
'''


class AuditAdversarialTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="pulpo-extra-disposable-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.path = self.root / "fixture.sqlite3"

    def state(self):
        state = SQLiteKernelState(self.path)
        self.addCleanup(state.close)
        return state

    def kernel(self, state):
        return GovernanceKernel(Policy(frozenset(), 0), secret=b"synthetic-only", state=state)

    def seed(self, mode="DELETE"):
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(mode.lower(), connection.execute("PRAGMA journal_mode=" + mode).fetchone()[0])
        state = self.state()
        for i, timestamp in enumerate((100, 10, 10, -1)):
            state.append("fixture", {"i": i}, timestamp)
        records = state.audit
        self.assertTrue(self.kernel(state).verify_audit())
        state.close()
        return records

    def legacy(self, mode="DELETE"):
        records = self.seed(mode)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("DROP TRIGGER audit_head_check_insert")
            connection.execute("DROP TRIGGER audit_head_advance")
            connection.execute("DROP TABLE audit_head")
            connection.execute("DROP TABLE audit_integrity_schema")
        return records

    def dump(self):
        with closing(sqlite3.connect(self.path)) as connection:
            return tuple(connection.iterdump())

    def test_same_name_trigger_substitution_is_rejected(self):
        for name in ("audit_head_check_insert", "audit_head_advance"):
            with self.subTest(trigger=name):
                self.path = self.root / (name + ".sqlite3")
                self.seed()
                with closing(sqlite3.connect(self.path)) as connection, connection:
                    connection.execute("DROP TRIGGER " + name)
                    connection.execute("CREATE TRIGGER " + name + " AFTER INSERT ON audit BEGIN SELECT 1; END")
                before = self.dump()
                with self.assertRaisesRegex(ValueError, "audit head trigger"):
                    self.state()
                self.assertEqual(before, self.dump())

    def test_malformed_preexisting_heads_fail_without_mutation(self):
        variants = {
            "duplicate": [(1, 4, None), (1, 4, None)],
            "wrong_id": [(2, 4, None)],
            "float_sequence": [(1, 4.0, None)],
            "text_sequence": [(1, "4", None)],
            "float_id": [(1.0, 4, None)],
            "ahead": [(1, 5, None)],
            "behind": [(1, 3, None)],
            "wrong_hash": [(1, 4, "f" * 64)],
            "blob_hash": [(1, 4, b"f" * 64)],
            "null_hash": [(1, 4, "NULL")],
        }
        for label, values in variants.items():
            with self.subTest(case=label):
                self.path = self.root / (label + ".sqlite3")
                records = self.legacy()
                with closing(sqlite3.connect(self.path)) as connection, connection:
                    connection.execute("CREATE TABLE audit_head (id, sequence, hash)")
                    connection.executemany("INSERT INTO audit_head VALUES (?,?,?)", [
                        (i, seq, records[-1]["hash"] if digest is None else None if digest == "NULL" else digest)
                        for i, seq, digest in values])
                before = self.dump()
                with self.assertRaisesRegex(ValueError, "audit head"):
                    self.state()
                self.assertEqual(before, self.dump())

    def test_float_schema_marker_is_rejected_without_mutation(self):
        self.seed()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("DROP TABLE audit_integrity_schema")
            connection.execute("CREATE TABLE audit_integrity_schema (id, version)")
            connection.execute("INSERT INTO audit_integrity_schema VALUES (1.0,1.0)")
        before = self.dump()
        with self.assertRaisesRegex(ValueError, "audit head schema"):
            self.state()
        self.assertEqual(before, self.dump())

    def test_delete_all_audit_rows_and_checkpoint_cannot_reset_history(self):
        self.seed()
        state = self.state()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("DELETE FROM audit")
            connection.execute("DELETE FROM audit_verification_checkpoint")
        before = self.dump()
        with self.assertRaises(StateIntegrityError):
            self.kernel(state)
        with self.assertRaises(sqlite3.IntegrityError):
            state.append("cannot reset", {}, 1)
        state.close()
        with self.assertRaisesRegex(ValueError, "audit head"):
            self.state()
        self.assertEqual(before, self.dump())

    def test_page_quota_failure_rolls_back_issuance_and_allows_exact_retry(self):
        for mode in ("DELETE", "WAL"):
            with self.subTest(mode=mode):
                self.path = self.root / (mode + ".sqlite3")
                self.seed(mode)
                state = self.state()
                pages = state._connection.execute("PRAGMA page_count").fetchone()[0]
                state._connection.execute("PRAGMA max_page_count=" + str(pages))
                approval = ApprovalUse("approval", "nonce", {"large": "x" * 200000})
                before = self.dump()
                with self.assertRaisesRegex(sqlite3.OperationalError, "full"):
                    state.issue_permit("permit", "intent", "fixture", 1, approval)
                self.assertFalse(state._connection.in_transaction)
                self.assertEqual(before, self.dump())
                self.assertEqual("ok", state._connection.execute("PRAGMA integrity_check").fetchone()[0])
                state._connection.execute("PRAGMA max_page_count=" + str(pages + 1000))
                self.assertIsNone(state.issue_permit("permit", "intent", "fixture", 1, approval))
                self.assertEqual("approval_id_replayed", state.issue_permit("other", "intent", "fixture", 1, approval))
                self.assertTrue(self.kernel(state).verify_audit())

    def test_repeated_head_failures_then_retry_issue_exactly_once(self):
        self.seed()
        state = self.state()
        state._connection.execute("CREATE TRIGGER reject_tip BEFORE UPDATE ON audit_head BEGIN SELECT RAISE(ABORT, 'retry fixture'); END")
        before = self.dump()
        approval = ApprovalUse("approval", "nonce", {"fixture": True})
        for _ in range(5):
            with self.assertRaisesRegex(sqlite3.IntegrityError, "retry fixture"):
                state.issue_permit("permit", "intent", "fixture", 1, approval)
            self.assertFalse(state._connection.in_transaction)
            self.assertEqual(before, self.dump())
        state._connection.execute("DROP TRIGGER reject_tip")
        self.assertIsNone(state.issue_permit("permit", "intent", "fixture", 1, approval))
        self.assertEqual("approval_id_replayed", state.issue_permit("other", "intent", "fixture", 1, approval))
        self.assertTrue(self.kernel(state).verify_audit())

    def test_legacy_upgrade_replay_and_restart_in_both_journal_modes(self):
        for mode in ("DELETE", "WAL"):
            with self.subTest(mode=mode):
                self.path = self.root / (mode + ".sqlite3")
                records = self.legacy(mode)
                state = self.state()
                self.assertEqual(records, state.audit)
                self.assertEqual(mode.lower(), state._connection.execute("PRAGMA journal_mode").fetchone()[0])
                self.assertEqual(2, state._connection.execute("PRAGMA synchronous").fetchone()[0])
                state.issue_permit("permit", "intent", "fixture", 1)
                state.close()
                state = self.state()
                self.assertTrue(state.consume_permit("permit", "intent", 1))
                state.close()
                state = self.state()
                self.assertFalse(state.consume_permit("permit", "intent", 1))
                self.assertTrue(self.kernel(state).verify_audit())

    def test_two_processes_upgrade_and_append_without_forking(self):
        for mode in ("DELETE", "WAL"):
            with self.subTest(mode=mode):
                self.path = self.root / (mode + ".sqlite3")
                records = self.legacy(mode)
                workers = []
                try:
                    for event in ("first", "second"):
                        workers.append(subprocess.Popen([sys.executable, "-B", "-c", CHILD, str(ROOT), str(self.path), "race", event],
                                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
                    for worker in workers:
                        worker.stdin.write("go\n")
                        worker.stdin.flush()
                    for worker in workers:
                        stdout, stderr = worker.communicate(timeout=20)
                        self.assertEqual(0, worker.returncode, stdout + stderr)
                finally:
                    for worker in workers:
                        if worker.poll() is None:
                            worker.kill()
                            worker.communicate()
                state = self.state()
                self.assertEqual(records, state.audit[:4])
                self.assertEqual({"first", "second"}, {r["event"] for r in state.audit[4:]})
                self.assertEqual(6, len(state.audit))
                self.assertTrue(self.kernel(state).verify_audit())

    def test_process_kill_before_and_after_commit_in_both_journal_modes(self):
        for mode in ("DELETE", "WAL"):
            for operation in ("migrate-before", "migrate-after", "append-before", "append-after"):
                with self.subTest(mode=mode, operation=operation):
                    self.path = self.root / (mode + operation + ".sqlite3")
                    records = self.legacy(mode) if operation.startswith("migrate") else self.seed(mode)
                    before = self.dump()
                    marker = self.root / (mode + operation + ".ready")
                    worker = subprocess.Popen([sys.executable, "-B", "-c", CHILD, str(ROOT), str(self.path), operation, str(marker)],
                                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    try:
                        deadline = time.monotonic() + 15
                        while not marker.exists() and worker.poll() is None and time.monotonic() < deadline:
                            time.sleep(0.01)
                        if not marker.exists():
                            worker.kill()
                            stdout, stderr = worker.communicate()
                            self.fail("child did not reach kill point: " + stdout + stderr)
                        worker.kill()
                        worker.communicate(timeout=10)
                    finally:
                        if worker.poll() is None:
                            worker.kill()
                            worker.communicate()
                    if operation.endswith("before"):
                        self.assertEqual(before, self.dump())
                    state = self.state()
                    self.assertEqual("ok", state._connection.execute("PRAGMA integrity_check").fetchone()[0])
                    self.assertEqual(records, state.audit[:4])
                    self.assertEqual(5 if operation == "append-after" else 4, len(state.audit))
                    self.assertTrue(self.kernel(state).verify_audit())

    def test_boundary_complete_database_rollback_is_not_detected(self):
        self.seed()
        saved = self.root / "saved.sqlite3"
        shutil.copyfile(self.path, saved)
        state = self.state()
        state.append("later", {}, 1)
        state.close()
        shutil.copyfile(saved, self.path)
        state = self.state()
        self.assertEqual(4, len(state.audit))
        self.assertTrue(self.kernel(state).verify_audit())

    def test_boundary_copied_descendants_can_each_consume_same_permit(self):
        self.seed()
        state = self.state()
        state.issue_permit("permit", "intent", "fixture", 1)
        state.close()
        sibling = self.root / "sibling.sqlite3"
        shutil.copyfile(self.path, sibling)
        first = self.state()
        with SQLiteKernelState(sibling) as second:
            self.assertTrue(first.consume_permit("permit", "intent", 1))
            self.assertTrue(second.consume_permit("permit", "intent", 1))
            self.assertTrue(self.kernel(first).verify_audit())
            self.assertTrue(self.kernel(second).verify_audit())


if __name__ == "__main__":
    unittest.main()
