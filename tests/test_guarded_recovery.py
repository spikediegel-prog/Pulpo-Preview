"""Only synthetic state; a checkpoint never grants authority or proves freshness."""
from contextlib import closing
import hashlib
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from pulpo import GovernanceKernel, Intent, Policy, SQLiteKernelState, StateRecoveryError
import pulpo.state as state_module


class GuardedRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.path = self.folder / 'live.sqlite3'
        self.state = SQLiteKernelState(self.path)
        self.addCleanup(self.state.close)
        self.intent = Intent('agent:fixture', 'read', 'local:fixture', 0, 'recovery-test')
        self.kernel = self.make_kernel(self.state)

    def make_kernel(self, state):
        return GovernanceKernel(Policy(frozenset({'read'}), 100, frozenset()),
                secret=b'recovery-test-only', clock=lambda: 1_000_000, state=state)

    def backup(self, name):
        path = self.folder / name
        with closing(sqlite3.connect(self.path)) as source, closing(sqlite3.connect(path)) as target:
            source.backup(target)
        return path

    def test_current_backup_restart_preserves_spent_permit_and_fresh_execution(self):
        decision = self.kernel.evaluate(self.intent)
        self.assertTrue(self.kernel.consume(decision.permit, self.intent))
        pin = self.state.recovery_checkpoint()
        backup = self.backup('current.sqlite3')
        with SQLiteKernelState.recover(backup, expected_checkpoint=pin) as recovered:
            app = self.make_kernel(recovered)
            self.assertTrue(app.verify_audit())
            self.assertFalse(app.consume(decision.permit, self.intent))
            fresh = app.evaluate(self.intent)
            self.assertTrue(app.consume(fresh.permit, self.intent))

    def test_stale_valid_backup_rejected_before_initialization_or_any_write(self):
        decision = self.kernel.evaluate(self.intent)
        backup = self.backup('stale.sqlite3')
        self.assertTrue(self.kernel.consume(decision.permit, self.intent))
        pin = self.state.recovery_checkpoint()
        before = backup.read_bytes()
        with patch.object(SQLiteKernelState, '_initialize_transaction') as initialize:
            with self.assertRaises(StateRecoveryError):
                SQLiteKernelState.recover(backup, expected_checkpoint=pin)
            initialize.assert_not_called()
        self.assertEqual(before, backup.read_bytes())

    def test_same_audit_tip_with_changed_spent_or_approval_metadata_is_rejected(self):
        decision = self.kernel.evaluate(self.intent)
        self.assertTrue(self.kernel.consume(decision.permit, self.intent))
        pin = self.state.recovery_checkpoint()
        for sql in ['UPDATE permits SET spent=0',
                    "INSERT INTO approvals VALUES ('substituted', 'substituted')",
                    "INSERT INTO directives VALUES ('revoked-state-substitute', 1, 'hash', 0)"]:
            with self.subTest(sql=sql):
                backup = self.backup('changed-' + hashlib.sha256(sql.encode()).hexdigest() + '.sqlite3')
                with closing(sqlite3.connect(backup)) as connection, connection:
                    connection.execute(sql)
                with self.assertRaises(StateRecoveryError):
                    SQLiteKernelState.recover(backup, expected_checkpoint=pin)

    def test_malformed_missing_checkpoint_never_opens_or_creates_database(self):
        absent = self.folder / 'missing.sqlite3'
        for pin in [None, '', 1, True, '0' * 64, 'pulpo.sqlite.recovery.v1:' + 'G' * 64]:
            with self.subTest(pin=pin), self.assertRaises(StateRecoveryError):
                SQLiteKernelState.recover(absent, expected_checkpoint=pin)
        self.assertFalse(absent.exists())
        with self.assertRaises(sqlite3.OperationalError):
            SQLiteKernelState.recover(absent, expected_checkpoint=self.state.recovery_checkpoint())
        self.assertFalse(absent.exists())

    def test_incomplete_or_extra_schema_rejected_without_migration(self):
        pin = self.state.recovery_checkpoint()
        for sql in ['DROP TABLE approvals', 'CREATE TABLE alternate_authority (value TEXT)',
                    'CREATE TRIGGER cache_side_effect AFTER INSERT ON audit_verification_checkpoint BEGIN UPDATE permits SET spent=0; END']:
            with self.subTest(sql=sql):
                backup = self.backup('schema-' + hashlib.sha256(sql.encode()).hexdigest() + '.sqlite3')
                with closing(sqlite3.connect(backup)) as connection, connection:
                    connection.execute(sql)
                before = backup.read_bytes()
                with self.assertRaises(StateRecoveryError):
                    SQLiteKernelState.recover(backup, expected_checkpoint=pin)
                self.assertEqual(before, backup.read_bytes())

    def test_cache_content_does_not_become_recovery_authority(self):
        pin = self.state.recovery_checkpoint()
        backup = self.backup('cache.sqlite3')
        with closing(sqlite3.connect(backup)) as connection, connection:
            connection.execute("UPDATE audit_verification_checkpoint SET checkpoint_json='untrusted cache'")
        with SQLiteKernelState.recover(backup, expected_checkpoint=pin) as recovered:
            self.assertTrue(self.make_kernel(recovered).verify_audit())

    def test_capture_is_read_only_and_pending_transaction_is_not_committed(self):
        before = self.path.read_bytes()
        self.state.recovery_checkpoint()
        self.assertEqual(before, self.path.read_bytes())
        self.state._connection.execute('BEGIN IMMEDIATE')
        self.state._connection.execute("INSERT INTO approvals VALUES ('pending', 'pending')")
        with self.assertRaises(StateRecoveryError):
            self.state.recovery_checkpoint()
        self.assertTrue(self.state._connection.in_transaction)
        self.state._connection.rollback()

    def test_checkpoint_comparison_holds_writer_lock(self):
        pin = self.state.recovery_checkpoint()
        backup = self.backup('locked.sqlite3')
        original = state_module._recovery_checkpoint
        def competing_writer(connection):
            with closing(sqlite3.connect(backup, timeout=0)) as competitor:
                with self.assertRaisesRegex(sqlite3.OperationalError, 'locked'):
                    competitor.execute('BEGIN IMMEDIATE')
            return original(connection)
        with patch.object(state_module, '_recovery_checkpoint', side_effect=competing_writer):
            with SQLiteKernelState.recover(backup, expected_checkpoint=pin):
                pass

    def test_corrupt_truncated_and_foreign_database_fail_closed(self):
        pin = self.state.recovery_checkpoint()
        for payload in [b'not a database', self.path.read_bytes()[:128]]:
            backup = self.folder / 'corrupt.sqlite3'
            backup.write_bytes(payload)
            with self.assertRaises((sqlite3.DatabaseError, StateRecoveryError)):
                SQLiteKernelState.recover(backup, expected_checkpoint=pin)
        foreign = self.folder / 'foreign.sqlite3'
        with SQLiteKernelState(foreign) as state:
            self.make_kernel(state).evaluate(self.intent)
        with self.assertRaises(StateRecoveryError):
            SQLiteKernelState.recover(foreign, expected_checkpoint=pin)

    def test_co_rolled_back_checkpoint_is_explicitly_outside_this_protection(self):
        decision = self.kernel.evaluate(self.intent)
        stale_pin = self.state.recovery_checkpoint()
        backup = self.backup('co-rollback.sqlite3')
        self.assertTrue(self.kernel.consume(decision.permit, self.intent))
        # Demonstrates why deriving a pin from the backup or retaining it beside
        # the rolled-back database MUST NOT be advertised as rollback protection.
        with SQLiteKernelState.recover(backup, expected_checkpoint=stale_pin) as recovered:
            self.assertTrue(self.make_kernel(recovered).consume(decision.permit, self.intent))


if __name__ == '__main__':
    unittest.main()
