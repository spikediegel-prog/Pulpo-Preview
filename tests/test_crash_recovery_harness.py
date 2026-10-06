"""Negative controls for the crash harness's independent recovery oracle."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('crash_harness', ROOT/'scripts/test_crash_recovery.py')
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)


class CrashRecoveryOracleTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.path = self.directory/'state.sqlite3'

    def test_partial_issuance_is_rejected_even_with_valid_empty_audit(self):
        harness.prepare(harness.SQLiteKernelState, self.path, 'issue')
        state = harness.SQLiteKernelState(self.path)
        try:
            with state._connection:
                state._connection.execute("INSERT INTO permits (permit, intent_hash) VALUES ('permit', 'intent')")
        finally:
            state.close()
        with self.assertRaisesRegex(RuntimeError, 'partial issuance'):
            harness.recovered(harness.SQLiteKernelState, self.path, 'issue', 'either')

    def test_spent_without_consumption_audit_is_rejected(self):
        harness.prepare(harness.SQLiteKernelState, self.path, 'consume')
        state = harness.SQLiteKernelState(self.path)
        try:
            with state._connection:
                state._connection.execute("UPDATE permits SET spent=1 WHERE permit='permit'")
        finally:
            state.close()
        with self.assertRaisesRegex(RuntimeError, 'partial consumption'):
            harness.recovered(harness.SQLiteKernelState, self.path, 'consume', 'either')

    def test_missing_acknowledged_commit_is_rejected(self):
        harness.prepare(harness.SQLiteKernelState, self.path, 'unique')
        with self.assertRaisesRegex(RuntimeError, 'acknowledgment/transaction boundary'):
            harness.recovered(harness.SQLiteKernelState, self.path, 'unique', 'committed')

    def test_storage_faults_really_fire_and_roll_back(self):
        results = harness.storage_faults(harness.SQLiteKernelState, self.directory)
        self.assertEqual(9, len(results))
        self.assertTrue(all(result['passed'] for result in results))

    def test_tamper_controls_are_rejected_at_restart(self):
        results = harness.tamper_controls(harness.SQLiteKernelState, self.directory)
        self.assertEqual(3, len(results))
        self.assertTrue(all(result['rejected'] for result in results))
