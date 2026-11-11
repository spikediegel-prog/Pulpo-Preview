"""Open/close lifecycle for the incident channel (slice (c) of PR #119 leftovers).

Tests pin the state machine in pulpo/incident_channel.py: lifecycle states
are derived from `incident_lifecycle` audit events (never stored beside the
record), transitions are attributable to an explicit actor, closing an
incident whose resolution is still `unresolved` requires a reason recorded
as an override, near-misses carry no lifecycle, and a kind flip retires the
incident record (its lifecycle history stays in the audit).
"""
import json
import tempfile
import unittest
from pathlib import Path

from pulpo import GovernanceKernel, Policy, PulpoOrchestrator, SQLiteKernelState
from pulpo.custody import SQLiteGovernanceCustody
from pulpo.incident_channel import (
    INCIDENT_SCHEMA,
    REPORT_SCHEMA,
    IncidentRecord,
    export_incident_report,
    freeze_incident_report,
    list_incidents,
    load_incident_report,
    transition_incident,
)

NOW = 8_000_000
OPERATOR = "operator:owner"


def audit_events(kernel, event):
    return [record for record in kernel.audit if record.get("event") == event]


class LifecycleRecordValidationTests(unittest.TestCase):
    def valid_kwargs(self):
        return {
            "record_id": "incident:" + "a" * 64,
            "kind": "incident",
            "source": "canonical_audit",
            "source_detail": "purchase_consequence_unknown",
            "first_seen_ns": 100,
            "last_seen_ns": 100,
            "anchors": (("audit_record", "a" * 64),),
            "reason": "external_consequence_not_yet_verified",
            "resolution": "unresolved",
            "anchor_hash": "a" * 64,
            "lifecycle": "open",
            "lifecycle_at_ns": 100,
            "lifecycle_actor": "",
        }

    def test_valid_record(self):
        record = IncidentRecord(**self.valid_kwargs())
        self.assertEqual("open", record.lifecycle)

    def test_bad_lifecycle_rejected(self):
        with self.assertRaises(ValueError):
            IncidentRecord(**{**self.valid_kwargs(), "lifecycle": "triaged"})

    def test_incident_with_not_applicable_rejected(self):
        with self.assertRaises(ValueError):
            IncidentRecord(**{**self.valid_kwargs(), "lifecycle": "not_applicable"})

    def test_near_miss_with_open_rejected(self):
        with self.assertRaises(ValueError):
            IncidentRecord(**{**self.valid_kwargs(), "kind": "near_miss",
                              "record_id": "near-miss:" + "a" * 64})

    def test_near_miss_with_not_applicable_valid(self):
        record = IncidentRecord(**{**self.valid_kwargs(), "kind": "near_miss",
                                   "record_id": "near-miss:" + "a" * 64,
                                   "lifecycle": "not_applicable"})
        self.assertEqual("not_applicable", record.lifecycle)

    def test_bad_lifecycle_at_ns_rejected(self):
        with self.assertRaises(ValueError):
            IncidentRecord(**{**self.valid_kwargs(), "lifecycle_at_ns": -1})
        with self.assertRaises(ValueError):
            IncidentRecord(**{**self.valid_kwargs(), "lifecycle_at_ns": "100"})

    def test_bad_lifecycle_actor_rejected(self):
        with self.assertRaises(ValueError):
            IncidentRecord(**{**self.valid_kwargs(), "lifecycle_actor": 7})


class LifecycleDerivationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "state.sqlite"
        self.backend = SQLiteKernelState(self.db)
        self.addCleanup(self.backend.close)
        self.kernel = GovernanceKernel(Policy(frozenset({"read"}), 0), secret=b"test-only", state=self.backend)
        self.owner = PulpoOrchestrator(self.kernel)

    def unknown_record(self, timestamp=100):
        self.backend.append("purchase_consequence_unknown",
                            {"order_hash": "a" * 64, "intent_hash": "b" * 64,
                             "permit_hash": "c" * 64,
                             "reason": "external_consequence_not_yet_verified"}, timestamp)
        (record,) = freeze_incident_report(self.owner).records
        return record

    def test_new_incident_starts_open(self):
        record = self.unknown_record()
        self.assertEqual("open", record.lifecycle)
        self.assertEqual(100, record.lifecycle_at_ns)
        self.assertEqual("", record.lifecycle_actor)

    def test_near_miss_has_no_lifecycle(self):
        self.backend.append("permit_rejected", {"reason": "permit_clock_invalid"}, 100)
        (record,) = freeze_incident_report(self.owner).records
        self.assertEqual("near_miss", record.kind)
        self.assertEqual("not_applicable", record.lifecycle)
        self.assertEqual(100, record.lifecycle_at_ns)
        self.assertEqual("", record.lifecycle_actor)

    def test_hand_appended_valid_event_is_derived(self):
        record = self.unknown_record()
        self.backend.append("incident_lifecycle",
                            {"record_id": record.record_id, "anchor_hash": record.anchor_hash,
                             "transition": "acknowledge", "from_state": "open",
                             "to_state": "acknowledged", "actor": OPERATOR,
                             "reason": "", "override": False}, 200)
        (derived,) = freeze_incident_report(self.owner).records
        self.assertEqual("acknowledged", derived.lifecycle)
        self.assertEqual(200, derived.lifecycle_at_ns)
        self.assertEqual(OPERATOR, derived.lifecycle_actor)

    def test_hand_appended_invalid_transition_is_ignored(self):
        record = self.unknown_record()
        self.backend.append("incident_lifecycle",
                            {"record_id": record.record_id, "anchor_hash": record.anchor_hash,
                             "transition": "acknowledge", "from_state": "open",
                             "to_state": "acknowledged", "actor": OPERATOR,
                             "reason": "", "override": False}, 200)
        # Second acknowledge: from_state no longer matches the derived state.
        self.backend.append("incident_lifecycle",
                            {"record_id": record.record_id, "anchor_hash": record.anchor_hash,
                             "transition": "acknowledge", "from_state": "open",
                             "to_state": "acknowledged", "actor": OPERATOR,
                             "reason": "", "override": False}, 300)
        # Unknown record id and unknown transition are ignored, not crashes.
        self.backend.append("incident_lifecycle",
                            {"record_id": "incident:" + "f" * 64, "anchor_hash": "f" * 64,
                             "transition": "acknowledge", "from_state": "open",
                             "to_state": "acknowledged", "actor": OPERATOR,
                             "reason": "", "override": False}, 400)
        self.backend.append("incident_lifecycle",
                            {"record_id": record.record_id, "anchor_hash": record.anchor_hash,
                             "transition": "teleport", "from_state": "acknowledged",
                             "to_state": "closed", "actor": OPERATOR,
                             "reason": "", "override": False}, 500)
        (derived,) = freeze_incident_report(self.owner).records
        self.assertEqual("acknowledged", derived.lifecycle)
        self.assertEqual(200, derived.lifecycle_at_ns)
        self.assertTrue(self.kernel.verify_audit())


class TransitionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "state.sqlite"
        self.backend = SQLiteKernelState(self.db)
        self.addCleanup(self.backend.close)
        self.kernel = GovernanceKernel(Policy(frozenset({"read"}), 0), secret=b"test-only", state=self.backend)
        self.owner = PulpoOrchestrator(self.kernel)
        self.backend.append("purchase_consequence_unknown",
                            {"order_hash": "a" * 64, "intent_hash": "b" * 64,
                             "permit_hash": "c" * 64,
                             "reason": "external_consequence_not_yet_verified"}, 100)
        (self.record,) = freeze_incident_report(self.owner).records

    def test_acknowledge_resolve_close_happy_path(self):
        record = transition_incident(self.owner, self.record.record_id,
                                     "acknowledge", actor=OPERATOR)
        self.assertEqual("acknowledged", record.lifecycle)
        self.assertEqual(OPERATOR, record.lifecycle_actor)
        record = transition_incident(self.owner, self.record.record_id,
                                     "resolve", actor=OPERATOR, reason="checked with registrar")
        self.assertEqual("resolved", record.lifecycle)
        record = transition_incident(self.owner, self.record.record_id,
                                     "close", actor=OPERATOR, reason="provider confirms no charge")
        self.assertEqual("closed", record.lifecycle)
        self.assertEqual(OPERATOR, record.lifecycle_actor)
        events = audit_events(self.kernel, "incident_lifecycle")
        self.assertEqual(["acknowledge", "resolve", "close"],
                         [event["payload"]["transition"] for event in events])
        self.assertEqual(["open", "acknowledged", "resolved"],
                         [event["payload"]["from_state"] for event in events])
        self.assertEqual(["acknowledged", "resolved", "closed"],
                         [event["payload"]["to_state"] for event in events])
        for event in events:
            self.assertEqual(self.record.record_id, event["payload"]["record_id"])
            self.assertEqual(self.record.anchor_hash, event["payload"]["anchor_hash"])
            self.assertEqual(OPERATOR, event["payload"]["actor"])
        self.assertFalse(events[0]["payload"]["override"])
        self.assertFalse(events[1]["payload"]["override"])
        self.assertTrue(events[2]["payload"]["override"])
        self.assertEqual("provider confirms no charge", events[2]["payload"]["reason"])
        self.assertTrue(self.kernel.verify_audit())

    def test_invalid_transitions_refused_and_append_nothing(self):
        before = len(self.kernel.audit)
        for transition in ("resolve", "close", "reopen"):
            with self.assertRaises(ValueError):
                transition_incident(self.owner, self.record.record_id,
                                    transition, actor=OPERATOR, reason="x")
        self.assertEqual(before, len(self.kernel.audit))
        transition_incident(self.owner, self.record.record_id, "acknowledge", actor=OPERATOR)
        for transition in ("acknowledge", "close", "reopen"):
            with self.assertRaises(ValueError):
                transition_incident(self.owner, self.record.record_id,
                                    transition, actor=OPERATOR, reason="x")
        self.assertEqual(before + 1, len(self.kernel.audit))

    def test_close_unresolved_requires_reason(self):
        transition_incident(self.owner, self.record.record_id, "acknowledge", actor=OPERATOR)
        transition_incident(self.owner, self.record.record_id, "resolve", actor=OPERATOR)
        before = len(self.kernel.audit)
        with self.assertRaises(ValueError):
            transition_incident(self.owner, self.record.record_id, "close", actor=OPERATOR)
        with self.assertRaises(ValueError):
            transition_incident(self.owner, self.record.record_id, "close",
                                actor=OPERATOR, reason="")
        self.assertEqual(before, len(self.kernel.audit))
        record = transition_incident(self.owner, self.record.record_id, "close",
                                     actor=OPERATOR, reason="provider gone, outcome unknowable")
        self.assertEqual("closed", record.lifecycle)
        event = audit_events(self.kernel, "incident_lifecycle")[-1]
        self.assertTrue(event["payload"]["override"])
        self.assertEqual("provider gone, outcome unknowable", event["payload"]["reason"])

    def test_reopen_from_resolved_and_closed(self):
        transition_incident(self.owner, self.record.record_id, "acknowledge", actor=OPERATOR)
        transition_incident(self.owner, self.record.record_id, "resolve", actor=OPERATOR)
        record = transition_incident(self.owner, self.record.record_id, "reopen",
                                     actor=OPERATOR, reason="registrar called back")
        self.assertEqual("open", record.lifecycle)
        record = transition_incident(self.owner, self.record.record_id, "acknowledge", actor=OPERATOR)
        self.assertEqual("acknowledged", record.lifecycle)
        transition_incident(self.owner, self.record.record_id, "resolve", actor=OPERATOR)
        transition_incident(self.owner, self.record.record_id, "close",
                            actor=OPERATOR, reason="confirmed no charge")
        record = transition_incident(self.owner, self.record.record_id, "reopen",
                                     actor=OPERATOR, reason="charge appeared after all")
        self.assertEqual("open", record.lifecycle)
        self.assertTrue(self.kernel.verify_audit())

    def test_near_miss_transition_refused(self):
        self.backend.append("permit_rejected", {"reason": "permit_clock_invalid"}, 200)
        (near_miss,) = [record for record in freeze_incident_report(self.owner).records
                        if record.kind == "near_miss"]
        before = len(self.kernel.audit)
        with self.assertRaises(ValueError):
            transition_incident(self.owner, near_miss.record_id, "acknowledge", actor=OPERATOR)
        self.assertEqual(before, len(self.kernel.audit))

    def test_unknown_record_and_bad_inputs_refused(self):
        with self.assertRaises(ValueError):
            transition_incident(self.owner, "incident:" + "f" * 64, "acknowledge", actor=OPERATOR)
        with self.assertRaises(ValueError):
            transition_incident(self.owner, self.record.record_id, "teleport", actor=OPERATOR)
        with self.assertRaises(ValueError):
            transition_incident(self.owner, self.record.record_id, "acknowledge", actor="")
        with self.assertRaises(ValueError):
            transition_incident(self.owner, self.record.record_id, "acknowledge", actor=7)
        with self.assertRaises(ValueError):
            transition_incident(self.owner, self.record.record_id, "acknowledge",
                                actor=OPERATOR, reason=7)
        with self.assertRaises(TypeError):
            transition_incident(self.kernel, self.record.record_id, "acknowledge", actor=OPERATOR)
        with self.assertRaises(ValueError):
            transition_incident(self.owner, "", "acknowledge", actor=OPERATOR)


class CustodyLifecycleTests(unittest.TestCase):
    def custody(self, directory):
        path = Path(directory) / "custody.sqlite3"
        return SQLiteGovernanceCustody(path, signing_secret=b"test-only-custody-secret",
                                       clock=lambda: NOW)

    def head(self, store):
        snapshot = store.snapshot()
        return snapshot.epoch, snapshot.state_root

    def authorize(self, store, *, object_hash="a" * 64, target_hash="b" * 64,
                  permit_hash="c" * 64, authorization_hash="d" * 64):
        epoch, root = self.head(store)
        authorization = store.authorize_attempt(
            expected_epoch=epoch, expected_state_root=root,
            object_hash=object_hash, target_hash=target_hash,
            permit_hash=permit_hash, authorization_hash=authorization_hash,
        )
        return authorization.attempt_id

    def drive_to(self, store, attempt_id, *states):
        for state in states:
            epoch, root = self.head(store)
            if state == "attempt_claimed":
                store.claim_attempt(expected_epoch=epoch, expected_state_root=root,
                                    attempt_id=attempt_id, executor_id="executor:test")
            elif state == "request_transmitted":
                store.authorize_transmission(expected_epoch=epoch, expected_state_root=root,
                                             attempt_id=attempt_id)
            elif state == "reconciliation_required":
                store.require_reconciliation(expected_epoch=epoch, expected_state_root=root,
                                             attempt_id=attempt_id)
            elif state in ("reconciled_success", "reconciled_failure"):
                outcome = {"reconciled_success": "success",
                           "reconciled_failure": "failure"}[state]
                store.reconcile_observed(expected_epoch=epoch, expected_state_root=root,
                                         attempt_id=attempt_id, outcome=outcome,
                                         observation_hash="e" * 64, observer_id="observer:test")
            else:  # pragma: no cover - test helper guard
                raise AssertionError(state)

    def owner_for(self, directory):
        db = Path(directory) / "state.sqlite"
        backend = SQLiteKernelState(db)
        self.addCleanup(backend.close)
        kernel = GovernanceKernel(Policy(frozenset({"read"}), 0), secret=b"test-only", state=backend)
        return PulpoOrchestrator(kernel), backend, kernel

    def test_confirmed_wrong_close_needs_no_reason(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.custody(directory)
            owner, backend, kernel = self.owner_for(directory)
            attempt_id = self.authorize(store)
            self.drive_to(store, attempt_id, "attempt_claimed", "request_transmitted",
                          "reconciliation_required", "reconciled_failure")
            (record,) = freeze_incident_report(owner, custody=store).records
            self.assertEqual("incident", record.kind)
            self.assertEqual("confirmed_wrong", record.resolution)
            self.assertEqual("open", record.lifecycle)
            transition_incident(owner, record.record_id, "acknowledge", actor=OPERATOR, custody=store)
            transition_incident(owner, record.record_id, "resolve", actor=OPERATOR, custody=store)
            closed = transition_incident(owner, record.record_id, "close",
                                         actor=OPERATOR, custody=store)
            self.assertEqual("closed", closed.lifecycle)
            event = audit_events(kernel, "incident_lifecycle")[-1]
            self.assertFalse(event["payload"]["override"])
            self.assertEqual("", event["payload"]["reason"])

    def test_kind_flip_retires_lifecycle(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.custody(directory)
            owner, backend, kernel = self.owner_for(directory)
            attempt_id = self.authorize(store)
            backend.append("purchase_consequence_unknown",
                           {"order_hash": "a" * 64, "custody_attempt_id": attempt_id,
                            "reason": "external_consequence_not_yet_verified"}, 100)
            (record,) = freeze_incident_report(owner, custody=store).records
            self.assertEqual("incident", record.kind)
            transition_incident(owner, record.record_id, "acknowledge",
                                actor=OPERATOR, custody=store)
            self.drive_to(store, attempt_id, "attempt_claimed", "request_transmitted",
                          "reconciliation_required", "reconciled_success")
            (flipped,) = freeze_incident_report(owner, custody=store).records
            self.assertEqual("near_miss", flipped.kind)
            self.assertEqual("resolved_cleanly", flipped.resolution)
            self.assertEqual("not_applicable", flipped.lifecycle)
            # The acknowledgement history stays in the audit even though the
            # incident record it belonged to no longer exists.
            self.assertEqual(1, len(audit_events(kernel, "incident_lifecycle")))
            self.assertTrue(kernel.verify_audit())


class LifecycleQueryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "state.sqlite"
        self.backend = SQLiteKernelState(self.db)
        self.addCleanup(self.backend.close)
        self.kernel = GovernanceKernel(Policy(frozenset({"read"}), 0), secret=b"test-only", state=self.backend)
        self.owner = PulpoOrchestrator(self.kernel)
        self.backend.append("purchase_consequence_unknown",
                            {"reason": "external_consequence_not_yet_verified"}, 100)
        self.backend.append("purchase_consequence_unknown",
                            {"reason": "external_consequence_not_yet_verified"}, 200)
        self.backend.append("permit_rejected", {"reason": "permit_clock_invalid"}, 300)
        (first, second, _) = freeze_incident_report(self.owner).records
        transition_incident(self.owner, first.record_id, "acknowledge", actor=OPERATOR)

    def test_lifecycle_filter(self):
        self.assertEqual(1, len(list_incidents(self.owner, lifecycle="open")))
        self.assertEqual(1, len(list_incidents(self.owner, lifecycle="acknowledged")))
        self.assertEqual(1, len(list_incidents(self.owner, lifecycle="not_applicable")))
        self.assertEqual(0, len(list_incidents(self.owner, lifecycle="closed")))
        self.assertEqual(1, len(list_incidents(self.owner, kind="incident", lifecycle="open")))

    def test_invalid_lifecycle_filter_raises(self):
        with self.assertRaises(ValueError):
            list_incidents(self.owner, lifecycle="triaged")


class LifecycleSchemaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "state.sqlite"
        self.path = Path(self.temp.name) / "incident-report.json"
        self.backend = SQLiteKernelState(self.db)
        self.addCleanup(self.backend.close)
        self.kernel = GovernanceKernel(Policy(frozenset({"read"}), 0), secret=b"test-only", state=self.backend)
        self.owner = PulpoOrchestrator(self.kernel)

    def test_schemas_are_v2(self):
        self.assertEqual("pulpo.incident-record.v2", INCIDENT_SCHEMA)
        self.assertEqual("pulpo.incident-report.v2", REPORT_SCHEMA)

    def test_export_load_round_trip_preserves_lifecycle(self):
        self.backend.append("purchase_consequence_unknown",
                            {"reason": "external_consequence_not_yet_verified"}, 100)
        (record,) = freeze_incident_report(self.owner).records
        transition_incident(self.owner, record.record_id, "acknowledge", actor=OPERATOR)
        snapshot = export_incident_report(self.owner, self.path)
        reloaded = load_incident_report(self.path)
        self.assertEqual(snapshot, reloaded)
        (loaded,) = reloaded.records
        self.assertEqual("acknowledged", loaded.lifecycle)
        self.assertEqual(OPERATOR, loaded.lifecycle_actor)
        self.assertGreaterEqual(loaded.lifecycle_at_ns, 100)

    def test_v1_snapshot_is_rejected(self):
        self.backend.append("purchase_consequence_unknown",
                            {"reason": "external_consequence_not_yet_verified"}, 100)
        snapshot = export_incident_report(self.owner, self.path)
        document = json.loads(self.path.read_text())
        document["schema"] = "pulpo.incident-report.v1"
        for record in document["records"]:
            record["schema"] = "pulpo.incident-record.v1"
            del record["lifecycle"]
            del record["lifecycle_at_ns"]
            del record["lifecycle_actor"]
        self.path.write_text(json.dumps(document))
        with self.assertRaises(ValueError):
            load_incident_report(self.path)


if __name__ == "__main__":
    unittest.main()
