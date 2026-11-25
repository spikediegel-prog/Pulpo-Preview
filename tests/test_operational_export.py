from dataclasses import asdict, replace
import json
import sqlite3
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pulpo import GovernanceKernel, Intent, Policy, PulpoOrchestrator, SQLiteKernelState
from pulpo.custody import SQLiteGovernanceCustody
from pulpo.custody_evidence import SQLiteCustodyEvidenceConvergence
from pulpo.operational_export import export_operational_observation, freeze_operational_observation
from pulpo.operational_observation import parse_operational


class OperationalExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "synthetic.sqlite3"
        self.state = SQLiteKernelState(self.path)
        self.addCleanup(self.state.close)
        self.kernel = GovernanceKernel(Policy(allowed_actions=frozenset({"read"}), max_cost=1), state=self.state)
        self.owner = PulpoOrchestrator(self.kernel)

    def test_existing_owner_only_no_database_open_or_canonical_mutation(self):
        audit = self.kernel.audit
        changes = self.state._connection.total_changes
        with patch("sqlite3.connect", side_effect=AssertionError("No new database connection")), \
             patch.object(GovernanceKernel, "__init__", side_effect=AssertionError("No new kernel/writer")):
            observations = [freeze_operational_observation(self.owner, check_database=True) for _ in range(3)]
        self.assertEqual(changes, self.state._connection.total_changes)
        self.assertEqual(audit, self.kernel.audit)
        self.assertTrue(all(value.audit_valid and value.database_health == "ok" for value in observations))
        self.assertTrue(all(value.pending_evidence_obligations is None for value in observations))
        encoded = json.dumps(asdict(observations[0]))
        self.assertNotIn(str(self.path), encoded)
        self.assertEqual(parse_operational(json.loads(encoded)), observations[0])

    def test_actual_outbox_zero_pending_then_projected_without_observer_draining(self):
        custody = SQLiteGovernanceCustody(self.path, signing_secret=b"E2-synthetic-fixture-only", clock=lambda: 81_000_000)
        convergence = SQLiteCustodyEvidenceConvergence(custody)
        self.assertEqual(0, freeze_operational_observation(self.owner).pending_evidence_obligations)
        head = custody.snapshot()
        custody.authorize_attempt(expected_epoch=head.epoch, expected_state_root=head.state_root,
            object_hash="1" * 64, target_hash="2" * 64, permit_hash="3" * 64, authorization_hash="4" * 64)
        for _ in range(3):
            self.assertEqual(1, freeze_operational_observation(self.owner).pending_evidence_obligations)
            self.assertEqual(1, convergence.pending_count())
        convergence.project_all()  # Existing canonical owner operation, not an observer action.
        snapshot = freeze_operational_observation(self.owner)
        self.assertEqual(0, snapshot.pending_evidence_obligations)
        self.assertTrue(snapshot.audit_valid)

    def test_transaction_options_and_missing_owner_reject_without_writes(self):
        for value in (object(), None):
            with self.assertRaises(TypeError):
                freeze_operational_observation(value)
        with self.assertRaises(TypeError):
            freeze_operational_observation(self.owner, check_database=1)
        self.state._connection.execute("BEGIN")
        with self.assertRaises(ValueError):
            freeze_operational_observation(self.owner)
        self.state._connection.rollback()
        self.assertEqual([], self.kernel.audit)

    def test_export_is_public_private_file_and_policy_change_is_visible(self):
        target = Path(self.temp.name) / "operations.json"
        before = freeze_operational_observation(self.owner)
        snapshot = export_operational_observation(self.owner, target, check_database=True)
        self.assertEqual(parse_operational(json.loads(target.read_text())), snapshot)
        self.assertEqual(0o600, target.stat().st_mode & 0o777)
        changed = PulpoOrchestrator(GovernanceKernel(Policy(allowed_actions=frozenset({"read"}), max_cost=2), state=self.state))
        after = freeze_operational_observation(changed)
        self.assertEqual(before.source_id, after.source_id)
        self.assertNotEqual(before.policy_hash, after.policy_hash)
        self.assertEqual([], self.kernel.audit)

    def test_contract_rejects_extra_private_fields_bool_counters_and_bad_schema(self):
        value = freeze_operational_observation(self.owner)
        for changes in ({"pending_evidence_obligations": True}, {"observed_at_ns": False},
                        {"policy_hash": "PRIVATE"}, {"schema": "future"}):
            with self.assertRaises((ValueError, TypeError)):
                replace(value, **changes)
        with self.assertRaises(ValueError):
            parse_operational(dict(asdict(value), credential="PRIVATE"))

    def test_absent_destination_never_creates_directories_or_mutates_state(self):
        target = Path(self.temp.name) / "absent" / "operations.json"
        with self.assertRaises(ValueError):
            export_operational_observation(self.owner, target)
        self.assertFalse(target.parent.exists())
        self.assertEqual([], self.kernel.audit)

    def test_unavailable_dependency_and_counter_are_unknown_not_zero(self):
        custody = SQLiteGovernanceCustody(self.path, signing_secret=b"E2-synthetic-fixture-only", clock=lambda: 81_000_000)
        convergence = SQLiteCustodyEvidenceConvergence(custody)
        def deny_status(action, first, second, _database, _trigger):
            if action == sqlite3.SQLITE_READ and first == "custody_evidence_outbox" or action == sqlite3.SQLITE_PRAGMA and first == "quick_check":
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        self.state._connection.set_authorizer(deny_status)
        try:
            snapshot = freeze_operational_observation(self.owner, check_database=True)
        finally:
            self.state._connection.set_authorizer(None)
        self.assertIsNone(snapshot.pending_evidence_obligations)
        self.assertEqual("unavailable", snapshot.database_health)
        self.assertEqual(0, convergence.pending_count())

    def test_audit_corruption_is_reported_without_repair(self):
        self.kernel.evaluate(Intent("fixture", "read", "fixture", cost=0))
        self.state._connection.execute("UPDATE audit SET hash = ?", ("0" * 64,))
        self.state._connection.commit()
        changes = self.state._connection.total_changes
        snapshot = freeze_operational_observation(self.owner)
        self.assertFalse(snapshot.audit_valid)
        self.assertEqual(changes, self.state._connection.total_changes)
