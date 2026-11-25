"""Evidence-state vocabulary: AUTHORIZED / ATTEMPTED / CONSEQUENCE UNKNOWN.

v9.1 review section 6a: no single three-state vocabulary existed -- AUTHORIZED
lived in kernel decisions, ATTEMPTED only in custody/budget state, and
CONSEQUENCE UNKNOWN only in proof modules. These tests pin the unified
vocabulary in pulpo/evidence_observation.py and its projection in
pulpo/evidence_export.py: an EvidenceEvent can express attempted and unknown
outcomes, the mapping agrees with the custody lifecycle and the
effect-reconciliation vocabulary, and an unknown outcome is never silently
coerced to success or failure by projection or reconciliation.
"""
import hashlib
from pathlib import Path
import tempfile
import unittest

from pulpo import GovernanceKernel, Intent, Policy, PulpoOrchestrator, SQLiteKernelState
from pulpo.custody import SQLiteGovernanceCustody
from pulpo.effect_reconcile import (
    EffectEnvelope,
    ExecutionIdentity,
    SurfaceSpec,
    capture_envelope_surfaces,
    reconcile_effects,
)
from pulpo.evidence_export import export_evidence_observation, freeze_evidence_observation
from pulpo.evidence_observation import (
    EVENT_NAMES,
    OUTCOMES,
    STATE_OUTCOMES,
    EvidenceEvent,
    EvidenceObservation,
    load_observation,
)


class EvidenceVocabularyTests(unittest.TestCase):
    def test_attempted_and_unknown_are_valid_evidence_outcomes(self):
        for outcome in ("attempted", "unknown"):
            event = EvidenceEvent(123, "decision", outcome, "0" * 64)
            self.assertEqual(outcome, event.outcome)
        for outcome in ("succeeded", "failed", "pending"):
            with self.assertRaises(ValueError):
                EvidenceEvent(123, "decision", outcome, "0" * 64)

    def test_observation_with_attempted_and_unknown_events_is_valid(self):
        events = (EvidenceEvent(100, "decision", "allowed", "a" * 64),
                  EvidenceEvent(200, "reconciliation_required", "attempted", "b" * 64),
                  EvidenceEvent(300, "unresolved", "unknown", "c" * 64))
        observation = EvidenceObservation("d" * 32, 400, True, 3, events=events)
        self.assertEqual(events, observation.events)

    def test_audit_event_names_recognize_reconciliation_events(self):
        self.assertIn("reconciliation_required", EVENT_NAMES)
        self.assertIn("unresolved", EVENT_NAMES)

    def test_mapping_matches_custody_attempt_lifecycle(self):
        custody = SQLiteGovernanceCustody
        for state in (custody.ATTEMPT_AUTHORIZED, custody.ATTEMPT_CLAIMED,
                      custody.REQUEST_TRANSMITTED, custody.RECONCILIATION_REQUIRED):
            self.assertEqual("attempted", STATE_OUTCOMES[state])
        self.assertEqual("unknown", STATE_OUTCOMES[custody.UNRESOLVED])
        # The custody strings themselves are the mapping keys: renaming one
        # side without the other fails here, not silently in production.
        self.assertEqual("reconciliation_required", custody.RECONCILIATION_REQUIRED)
        self.assertEqual("unresolved", custody.UNRESOLVED)

    def test_mapping_matches_effect_reconciliation_uncertain(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        protected = base / "protected"
        writable = base / "runtime"
        evidence = base / "evidence"
        for directory in (protected, writable, evidence):
            directory.mkdir()
        (protected / "source.txt").write_text("canonical\n", encoding="utf-8")
        executable = base / "codex"
        executable.write_bytes(b"pinned-codex")
        digest = hashlib.sha256(executable.read_bytes()).hexdigest()
        envelope = EffectEnvelope(
            executable_path=str(executable),
            executable_sha256=digest,
            argv=(str(executable), "--sandbox", "read-only"),
            workdir=str(protected),
            source_sha="2bad0db3675f0ea8ccdc0a1188be576f1a59e4e8",
            profile="permit-bound-local-intelligence-v1",
            expires_at_ns=10_000,
            surfaces=(SurfaceSpec(str(protected), "protected"),
                      SurfaceSpec(str(writable), "writable"),
                      SurfaceSpec(str(evidence), "evidence")),
        )
        identity = ExecutionIdentity(
            executable_path=str(executable),
            executable_sha256=digest,
            argv=envelope.argv,
            workdir=str(protected),
            source_sha=envelope.source_sha,
            profile=envelope.profile,
        )
        before = capture_envelope_surfaces(envelope)
        after = capture_envelope_surfaces(envelope)
        result = reconcile_effects(envelope, identity, before, after,
                                   execution_started_ns=9_000, observation_complete=False)
        self.assertEqual("uncertain", result.status)
        self.assertIn("observation_incomplete", result.reason)
        self.assertEqual("unknown", STATE_OUTCOMES[result.status])

    def test_reconciled_terminal_states_are_not_rewritten_as_allowed_or_denied(self):
        custody = SQLiteGovernanceCustody
        # Reconciliation resolves an unknown; it does not rewrite it, and
        # "allowed" means authorized, not succeeded.
        self.assertNotIn(custody.RECONCILED_SUCCESS, STATE_OUTCOMES)
        self.assertNotIn(custody.RECONCILED_FAILURE, STATE_OUTCOMES)


class EvidenceVocabularyProjectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "state.sqlite"
        self.path = Path(self.temp.name) / "observation.json"
        self.backend = SQLiteKernelState(self.db)
        self.addCleanup(self.backend.close)
        self.kernel = GovernanceKernel(Policy(frozenset({"read"}), 0), secret=b"test-only", state=self.backend)
        self.owner = PulpoOrchestrator(self.kernel)

    def consume_once(self):
        intent = Intent("agent:test", "read", "fixture-private", 0)
        decision = self.kernel.evaluate(intent)
        self.assertTrue(self.kernel.consume(decision.permit, intent))

    def test_projection_preserves_attempted_and_unknown_outcomes(self):
        self.consume_once()
        # Attempt / unknown audit events, as the live path will emit them
        # once wired; this slice defines the vocabulary and the projection.
        self.backend.append("reconciliation_required",
                            {"reason": "external_consequence_not_yet_verified"}, 200)
        self.backend.append("unresolved", {"reason": "provider_status_unknown"}, 300)
        snapshot = freeze_evidence_observation(self.owner)
        by_event = {event.event: event for event in snapshot.events}
        self.assertEqual("attempted", by_event["reconciliation_required"].outcome)
        self.assertEqual("unknown", by_event["unresolved"].outcome)
        for outcome in ("allowed", "denied", "rejected", "recorded"):
            self.assertNotEqual(outcome, by_event["reconciliation_required"].outcome)
            self.assertNotEqual(outcome, by_event["unresolved"].outcome)
        # An unknown consequence is not counted as a success.
        self.assertEqual(1, snapshot.allowed)
        self.assertEqual(1, snapshot.permit_consumed)

    def test_unknown_survives_export_load_round_trip_unchanged(self):
        self.consume_once()
        self.backend.append("unresolved", {"reason": "provider_status_unknown"}, 300)
        snapshot = export_evidence_observation(self.owner, self.path)
        reloaded = load_observation(self.path)
        self.assertEqual(snapshot, reloaded)
        unknown = [event for event in reloaded.events if event.event == "unresolved"]
        self.assertEqual(["unknown"], [event.outcome for event in unknown])

    def test_unknown_is_not_upgraded_by_a_neighboring_success(self):
        self.backend.append("unresolved", {"reason": "provider_status_unknown"}, 100)
        self.consume_once()
        snapshot = freeze_evidence_observation(self.owner)
        unresolved = [event for event in snapshot.events if event.event == "unresolved"]
        self.assertEqual(["unknown"], [event.outcome for event in unresolved])


if __name__ == "__main__":
    unittest.main()
