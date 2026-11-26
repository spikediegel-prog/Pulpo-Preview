"""Regression tests for the Gladiator verdict echo.

Covers proposal section 8.5: PASS (qualified vs Pwned), breach, UNKNOWN,
duplicate emission, forged success attempts, line-level evidence, and the
CLI runner-failure guards. Also covers the 2026-11-25 hardening: operator
booleans alone never establish a verified consequence, breach needs
verified transfer evidence, changed evidence supersedes explicitly, and
tampered receipts are refused. The echo is presentation only; these tests
prove what it renders, not that any network enforcement exists.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pulpo import GovernanceKernel, Policy
from pulpo.gladiator_gate import GladiatorRecord, completion_eligible
from pulpo.gladiator_audit_projection import audit_references_present
from pulpo.gladiator_verdict_echo import (
    EnforcementEvidence,
    TransferEvidence,
    emit,
    render,
    verify_enforcement_evidence,
    verify_transfer_evidence,
)

ROLES = (
    "pulpo_assessment",
    "gladiator_tournament",
    "gladiator_battle",
    "independent_verdict",
    "reconciliation",
    "held_out_evaluation",
)


def build_kernel(object_id, revision, verdict="PASS", state="COMPLETE"):
    """Kernel with one audit event per Gladiator role, as the projection tests do."""
    kernel = GovernanceKernel(Policy(frozenset({"read"}), 0))
    hashes = []
    for role in ROLES:
        payload = {
            "object_id": object_id,
            "source_revision": revision,
            "authority_effect": "none",
        }
        if role == "independent_verdict":
            payload["verdict"] = verdict
        if role == "reconciliation":
            payload["state"] = state
        kernel._state.append(role, payload, 1)
        hashes.append(kernel.audit[-1]["hash"])
    return kernel, hashes


def build_record(hashes, *, object_id="assessment:fixture",
                 revision="sha256:fixture", verdict="PASS",
                 state="COMPLETE", claim="VERIFIED"):
    return GladiatorRecord(
        object_id=object_id, source_revision=revision,
        pulpo_assessment_ref=hashes[0], tournament_ref=hashes[1],
        teams=("attack", "defend"), battle_refs=(hashes[2],),
        independent_verdict_ref=hashes[3], reconciliation_ref=hashes[4],
        unresolved_risks=(), held_out_ref=hashes[5],
        independent_verdict=verdict, reconciliation_state=state,
        completion_claim=claim,
    )


def full_evidence(hashes):
    """Pre-verified full evidence, corroborated by the fixture audit.

    Unit tests supply pre-verified evidence directly; the CLI path verifies
    refs instead (see the verify tests and the CLI tests). The refs are
    structural corroboration against the fixture audit, not proof that a
    boundary did anything.
    """
    return EnforcementEvidence(
        consequence_established=True,
        attempt_detected=True,
        boundary_held=True,
        authority_revoked=True,
        containment_verified=True,
        source="boundary",
        refs={"attempt": hashes[2], "boundary": hashes[1],
              "revocation": hashes[4], "containment": hashes[5]},
        verified=True,
    )


OPERATOR_EVIDENCE = EnforcementEvidence(
    consequence_established=True,
    attempt_detected=True,
    boundary_held=True,
    authority_revoked=True,
    containment_verified=True,
    source="operator-supplied",
)


class VerdictEchoTests(unittest.TestCase):
    def setUp(self):
        self.object_id = "assessment:fixture"
        self.revision = "sha256:fixture"
        self.kernel, self.hashes = build_kernel(self.object_id, self.revision)
        self.record = build_record(self.hashes)
        self.timestamp = "2026-11-25T16:00:00+00:00"

    def assess(self, record=None):
        record = self.record if record is None else record
        eligible = completion_eligible(
            record, expected_object=self.object_id,
            expected_revision=self.revision)
        projection = audit_references_present(
            self.kernel, record, expected_object=self.object_id,
            expected_revision=self.revision)
        return eligible, projection

    def render_assessed(self, record=None, enforcement=None, breach=None,
                        audit_provenance=None):
        eligible, projection = self.assess(record)
        return render(
            self.record if record is None else record,
            eligible=eligible, projection_passed=projection,
            enforcement=enforcement, breach=breach,
            audit_provenance=audit_provenance, timestamp=self.timestamp)

    def verify(self, evidence, kernel=None, record=None):
        return verify_enforcement_evidence(
            self.kernel if kernel is None else kernel,
            self.record if record is None else record,
            evidence, expected_object=self.object_id,
            expected_revision=self.revision)

    def test_verified_without_enforcement_renders_qualified_not_pwned(self):
        echo = self.render_assessed()
        self.assertEqual(echo.display_verdict, "PASS")
        self.assertEqual(echo.record_verdict, "PASS")
        self.assertEqual(
            echo.text,
            "GLADIATOR ASSESSMENT: PASS\n"
            "Audit projection: structurally verified\n"
            "External enforcement consequence: NOT ESTABLISHED")
        self.assertNotIn("PWNED", echo.text)
        self.assertFalse(echo.enforcement_consequence_established)
        self.assertIn(
            "External enforcement consequence: NOT ESTABLISHED",
            echo.evidence_scope_and_limitations)

    def test_verified_with_enforcement_renders_pwned(self):
        echo = self.render_assessed(enforcement=full_evidence(self.hashes))
        self.assertIn("YOU'VE BEEN PWNED BY GLADIATOR", echo.text)
        self.assertIn("Attack attempt detected.", echo.text)
        self.assertIn("Enforcement boundary held.", echo.text)
        self.assertIn("Authority revoked.", echo.text)
        self.assertIn("Containment verified.", echo.text)
        self.assertIn("VERDICT: PASS", echo.text)
        self.assertTrue(echo.enforcement_consequence_established)
        # Banner lines are all the same width: a well-formed box.
        widths = {len(line) for line in echo.text.splitlines()}
        self.assertEqual(len(widths), 1)

    def test_operator_booleans_without_verification_never_pwn(self):
        # Issue 1: operator-authored JSON booleans, with no verification
        # against the audit, must not establish a verified consequence or
        # trigger the Pwned banner.
        echo = self.render_assessed(enforcement=OPERATOR_EVIDENCE)
        self.assertEqual(echo.display_verdict, "PASS")
        self.assertNotIn("PWNED", echo.text)
        self.assertFalse(echo.enforcement_consequence_established)
        self.assertIn(
            "Pwned banner withheld: enforcement consequence asserted "
            "but not verified against the kernel audit.",
            echo.evidence_scope_and_limitations)

    def test_verify_enforcement_evidence_requires_resolving_refs(self):
        # Refs that resolve to audit entries with the same object and
        # revision corroborate the consequence.
        verified = self.verify(full_evidence(self.hashes))
        self.assertTrue(verified.verified)
        self.assertTrue(verified.consequence_established)
        self.assertEqual(verified.dropped_steps, ())
        # Booleans with no refs: every claim is dropped.
        dropped = self.verify(OPERATOR_EVIDENCE)
        self.assertFalse(dropped.verified)
        self.assertFalse(dropped.consequence_established)
        self.assertEqual(
            dropped.dropped_steps,
            ("attempt", "boundary", "revocation", "containment"))
        # Refs that do not exist in the audit: dropped.
        missing = replace(
            full_evidence(self.hashes),
            refs={"attempt": "0" * 64, "boundary": "0" * 64,
                  "revocation": "0" * 64, "containment": "0" * 64},
            verified=False)
        self.assertFalse(self.verify(missing).verified)
        # Refs from another object's audit: dropped (cross-object).
        other_kernel, other_hashes = build_kernel(
            "assessment:other", self.revision)
        cross = replace(
            full_evidence(self.hashes),
            refs={"attempt": other_hashes[2], "boundary": other_hashes[1],
                  "revocation": other_hashes[4], "containment": other_hashes[5]},
            verified=False)
        self.assertFalse(self.verify(cross).verified)
        self.assertEqual(
            self.verify(cross).dropped_steps,
            ("attempt", "boundary", "revocation", "containment"))
        # A tampered audit chain verifies nothing.
        self.kernel.audit[0]["payload"]["object_id"] = "tampered"
        self.assertFalse(self.verify(full_evidence(self.hashes)).verified)

    def test_pwned_lines_gated_on_their_own_evidence(self):
        partial = EnforcementEvidence(
            consequence_established=True, attempt_detected=True,
            boundary_held=True, source="boundary", verified=True)
        echo = self.render_assessed(enforcement=partial)
        self.assertIn("YOU'VE BEEN PWNED BY GLADIATOR", echo.text)
        self.assertIn("Attack attempt detected.", echo.text)
        self.assertIn("Enforcement boundary held.", echo.text)
        self.assertNotIn("Authority revoked.", echo.text)
        self.assertNotIn("Containment verified.", echo.text)

    def _deny_record(self):
        kernel, hashes = build_kernel(
            self.object_id, self.revision, verdict="DENY", state="COMPLETE")
        record = build_record(
            hashes, verdict="DENY", state="COMPLETE", claim="CLOSED_DENIED")
        eligible = completion_eligible(
            record, expected_object=self.object_id,
            expected_revision=self.revision)
        projection = audit_references_present(
            kernel, record, expected_object=self.object_id,
            expected_revision=self.revision)
        self.assertTrue(eligible)
        self.assertTrue(projection)
        return kernel, record, eligible, projection

    def test_breach_renders_fail_display_with_deny_record(self):
        kernel, record, eligible, projection = self._deny_record()
        kernel._state.append("decision", {
            "object_id": self.object_id,
            "source_revision": self.revision,
            "authority_effect": "none"}, 1)
        transfer = verify_transfer_evidence(
            kernel, record,
            TransferEvidence(transfer_observed=True,
                             refs=(kernel.audit[-1]["hash"],),
                             source="boundary"),
            expected_object=self.object_id,
            expected_revision=self.revision)
        self.assertTrue(transfer.verified)
        echo = render(record, eligible=eligible, projection_passed=projection,
                      breach=transfer, timestamp=self.timestamp)
        self.assertEqual(echo.display_verdict, "FAIL")
        self.assertEqual(echo.record_verdict, "DENY")
        self.assertIn("GLADIATOR: DEFENSE BREACHED", echo.text)
        self.assertIn("VERDICT: FAIL", echo.text)
        self.assertNotIn("PWNED", echo.text)

    def test_denied_without_transfer_evidence_renders_unverified(self):
        # Issue 2: CLOSED_DENIED must not claim an unauthorized transfer
        # or boundary failure without transfer evidence.
        kernel, record, eligible, projection = self._deny_record()
        echo = render(record, eligible=eligible, projection_passed=projection,
                      timestamp=self.timestamp)
        self.assertEqual(echo.display_verdict, "UNKNOWN")
        self.assertNotIn("DEFENSE BREACHED", echo.text)
        self.assertNotIn("Unauthorized transfer observed.", echo.text)
        self.assertIn(
            "Breach claim withheld: no transfer evidence supplied.",
            echo.evidence_scope_and_limitations)

    def test_denied_with_operator_transfer_claim_only_renders_unverified(self):
        kernel, record, eligible, projection = self._deny_record()
        transfer = verify_transfer_evidence(
            kernel, record, TransferEvidence(transfer_observed=True),
            expected_object=self.object_id,
            expected_revision=self.revision)
        self.assertFalse(transfer.verified)
        self.assertTrue(transfer.claim_dropped)
        echo = render(record, eligible=eligible, projection_passed=projection,
                      breach=transfer, timestamp=self.timestamp)
        self.assertEqual(echo.display_verdict, "UNKNOWN")
        self.assertNotIn("DEFENSE BREACHED", echo.text)
        self.assertIn(
            "Breach claim withheld: transfer claim uncorroborated by "
            "the kernel audit.",
            echo.evidence_scope_and_limitations)

    def test_denied_with_cross_object_transfer_ref_renders_unverified(self):
        kernel, record, eligible, projection = self._deny_record()
        other_kernel, other_hashes = build_kernel(
            "assessment:other", self.revision)
        transfer = verify_transfer_evidence(
            kernel, record,
            TransferEvidence(transfer_observed=True,
                             refs=(other_hashes[2],), source="boundary"),
            expected_object=self.object_id,
            expected_revision=self.revision)
        self.assertFalse(transfer.verified)
        self.assertTrue(transfer.claim_dropped)
        echo = render(record, eligible=eligible, projection_passed=projection,
                      breach=transfer, timestamp=self.timestamp)
        self.assertEqual(echo.display_verdict, "UNKNOWN")
        self.assertNotIn("DEFENSE BREACHED", echo.text)

    def test_closed_unknown_renders_unverified(self):
        kernel, hashes = build_kernel(
            self.object_id, self.revision, verdict="UNKNOWN", state="COMPLETE")
        record = build_record(
            hashes, verdict="UNKNOWN", state="COMPLETE", claim="CLOSED_UNKNOWN")
        eligible = completion_eligible(
            record, expected_object=self.object_id,
            expected_revision=self.revision)
        projection = audit_references_present(
            kernel, record, expected_object=self.object_id,
            expected_revision=self.revision)
        echo = render(record, eligible=eligible, projection_passed=projection,
                      timestamp=self.timestamp)
        self.assertEqual(echo.display_verdict, "UNKNOWN")
        self.assertIn("GLADIATOR: CONTAINMENT UNVERIFIED", echo.text)
        self.assertNotIn("PWNED", echo.text)

    def test_pending_reconciliation_renders_unverified_never_pwned(self):
        record = replace(self.record, reconciliation_state="PENDING",
                         completion_claim="REVIEW_PENDING")
        echo = self.render_assessed(record, enforcement=full_evidence(self.hashes))
        self.assertEqual(echo.display_verdict, "UNKNOWN")
        self.assertNotIn("PWNED", echo.text)

    def test_ineligible_record_renders_unverified_never_pwned(self):
        # Substituted object: eligibility fails, so no Pwned banner even
        # with full enforcement evidence asserted.
        record = replace(self.record, object_id="assessment:other")
        echo = self.render_assessed(record, enforcement=full_evidence(self.hashes))
        self.assertEqual(echo.display_verdict, "UNKNOWN")
        self.assertNotIn("PWNED", echo.text)

    def test_projection_failure_renders_unverified_never_pwned(self):
        record = replace(
            self.record, independent_verdict_ref="self:asserted")
        echo = self.render_assessed(record, enforcement=full_evidence(self.hashes))
        self.assertEqual(echo.display_verdict, "UNKNOWN")
        self.assertNotIn("PWNED", echo.text)

    def test_non_record_input_raises_no_echo(self):
        with self.assertRaises(TypeError):
            render(None, eligible=True, projection_passed=True)
        with self.assertRaises(TypeError):
            render("VERIFIED", eligible=True, projection_passed=True)

    def test_structured_event_distinguishes_fields(self):
        echo = self.render_assessed(enforcement=full_evidence(self.hashes))
        event = echo.to_event()
        self.assertEqual(event["test_id"], "assessment:fixture")
        self.assertEqual(event["record_verdict"], "PASS")
        self.assertEqual(event["display_verdict"], "PASS")
        self.assertEqual(event["audit_projection_result"], "pass")
        self.assertTrue(event["enforcement_consequence_established"])
        self.assertIn(
            "External enforcement consequence: established",
            event["evidence_scope_and_limitations"])
        self.assertEqual(event["receipt"]["object_id"], "assessment:fixture")
        self.assertEqual(event["receipt"]["completion_claim"], "VERIFIED")
        self.assertEqual(event["timestamp"], self.timestamp)
        self.assertEqual(event["text"], echo.text)

    def test_qualified_event_states_consequence_not_established(self):
        echo = self.render_assessed()
        event = echo.to_event()
        self.assertFalse(event["enforcement_consequence_established"])
        self.assertIn(
            "External enforcement consequence: NOT ESTABLISHED",
            event["evidence_scope_and_limitations"])

    def test_render_does_not_mutate_record_or_audit(self):
        before_audit = tuple(entry["hash"] for entry in self.kernel.audit)
        before_record = self.record
        self.render_assessed(enforcement=full_evidence(self.hashes))
        self.assertEqual(before_audit, tuple(entry["hash"] for entry in self.kernel.audit))
        self.assertEqual(before_record, self.record)

    def test_duplicate_emission_writes_once(self):
        eligible, projection = self.assess()
        with tempfile.TemporaryDirectory() as tmp:
            first = emit(self.record, eligible=eligible,
                         projection_passed=projection,
                         enforcement=full_evidence(self.hashes), output_dir=tmp,
                         timestamp=self.timestamp)
            self.assertTrue(first.emitted)
            self.assertTrue(first.path.exists())
            content = first.path.read_text(encoding="utf-8")
            second = emit(self.record, eligible=eligible,
                          projection_passed=projection,
                          enforcement=full_evidence(self.hashes), output_dir=tmp,
                          timestamp=self.timestamp)
            self.assertFalse(second.emitted)
            self.assertEqual(second.path, first.path)
            self.assertEqual(first.path.read_text(encoding="utf-8"), content)
            self.assertEqual(second.event, first.event)

    def test_conflicting_emission_refused(self):
        eligible, projection = self.assess()
        with tempfile.TemporaryDirectory() as tmp:
            first = emit(self.record, eligible=eligible,
                         projection_passed=projection,
                         enforcement=full_evidence(self.hashes), output_dir=tmp,
                         timestamp=self.timestamp)
            first.path.write_text(
                json.dumps({"emission_key": "tampered"}),
                encoding="utf-8")
            with self.assertRaises(ValueError):
                emit(self.record, eligible=eligible,
                     projection_passed=projection,
                     enforcement=full_evidence(self.hashes), output_dir=tmp,
                     timestamp=self.timestamp)

    def test_changed_evidence_supersedes_explicitly(self):
        # Issue 3: changed evidence is detected, not hidden behind the
        # old emission key. The new event names the superseded key and
        # the earlier file stays intact.
        eligible, projection = self.assess()
        with tempfile.TemporaryDirectory() as tmp:
            first = emit(self.record, eligible=eligible,
                         projection_passed=projection,
                         output_dir=tmp, timestamp=self.timestamp)
            self.assertTrue(first.emitted)
            self.assertEqual(first.event["supersedes"], [])
            second = emit(self.record, eligible=eligible,
                          projection_passed=projection,
                          enforcement=full_evidence(self.hashes),
                          output_dir=tmp, timestamp=self.timestamp)
            self.assertTrue(second.emitted)
            self.assertNotEqual(second.path, first.path)
            self.assertEqual(
                second.event["supersedes"],
                [first.event["emission_key"]])
            self.assertIn("PWNED", second.text)
            self.assertTrue(first.path.exists())
            self.assertEqual(
                json.loads(first.path.read_text(encoding="utf-8")),
                first.event)
            self.assertEqual(len(list(Path(tmp).glob("*.json"))), 2)

    def test_tampered_receipt_refused(self):
        # Issue 3: a receipt changed after it was written is refused,
        # whether the text, a reference, or the hash itself was changed.
        eligible, projection = self.assess()
        with tempfile.TemporaryDirectory() as tmp:
            first = emit(self.record, eligible=eligible,
                         projection_passed=projection,
                         enforcement=full_evidence(self.hashes),
                         output_dir=tmp, timestamp=self.timestamp)
            event = json.loads(first.path.read_text(encoding="utf-8"))
            tampered_text = dict(event)
            tampered_text["text"] = tampered_text["text"].replace(
                "VERDICT: PASS", "VERDICT: PWNED")
            first.path.write_text(
                json.dumps(tampered_text, indent=2, sort_keys=True),
                encoding="utf-8")
            with self.assertRaises(ValueError):
                emit(self.record, eligible=eligible,
                     projection_passed=projection,
                     enforcement=full_evidence(self.hashes),
                     output_dir=tmp, timestamp=self.timestamp)
            tampered_ref = dict(event)
            tampered_ref["receipt"] = dict(event["receipt"])
            tampered_ref["receipt"]["independent_verdict_ref"] = "0" * 64
            first.path.write_text(
                json.dumps(tampered_ref, indent=2, sort_keys=True),
                encoding="utf-8")
            with self.assertRaises(ValueError):
                emit(self.record, eligible=eligible,
                     projection_passed=projection,
                     enforcement=full_evidence(self.hashes),
                     output_dir=tmp, timestamp=self.timestamp)
            tampered_hash = dict(event)
            tampered_hash["event_hash"] = "0" * 64
            first.path.write_text(
                json.dumps(tampered_hash, indent=2, sort_keys=True),
                encoding="utf-8")
            with self.assertRaises(ValueError):
                emit(self.record, eligible=eligible,
                     projection_passed=projection,
                     enforcement=full_evidence(self.hashes),
                     output_dir=tmp, timestamp=self.timestamp)

    def test_event_hash_is_self_consistent(self):
        eligible, projection = self.assess()
        with tempfile.TemporaryDirectory() as tmp:
            first = emit(self.record, eligible=eligible,
                         projection_passed=projection,
                         enforcement=full_evidence(self.hashes),
                         output_dir=tmp, timestamp=self.timestamp)
            event = first.event
            body = {key: value for key, value in event.items()
                    if key != "event_hash"}
            digest = sha256(
                json.dumps(body, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")).hexdigest()
            self.assertEqual(digest, event["event_hash"])
            self.assertEqual(event["supersedes"], [])
            self.assertTrue(event["evidence_fingerprint"])

    def test_audit_provenance_recorded_in_event(self):
        # Issue 4: the provenance limit travels with the event.
        provenance = ("caller-supplied reconstruction — structural "
                      "membership only, not authenticated provenance")
        echo = self.render_assessed(audit_provenance=provenance)
        self.assertEqual(echo.audit_provenance, provenance)
        self.assertIn("Audit provenance: " + provenance,
                      echo.evidence_scope_and_limitations)
        self.assertEqual(echo.to_event()["audit_provenance"], provenance)


class VerdictEchoCliTests(unittest.TestCase):
    def _make_repo(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email",
                        "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name",
                        "Test"], check=True)
        (repo / "probe.txt").write_text("probe\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-qm", "probe"],
                       check=True)
        revision = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
        return repo, revision

    def _write_fixture(self, inputs, revision, *, evidence=None, transfer=None,
                       verdict="PASS", state="COMPLETE", claim="VERIFIED"):
        inputs.mkdir(parents=True, exist_ok=True)
        object_id = "assessment:cli"
        kernel, hashes = build_kernel(object_id, revision,
                                      verdict=verdict, state=state)
        record = build_record(
            hashes, object_id=object_id, revision=revision,
            verdict=verdict, state=state, claim=claim)
        entries = []
        for role in ROLES:
            payload = {
                "object_id": object_id,
                "source_revision": revision,
                "authority_effect": "none",
            }
            if role == "independent_verdict":
                payload["verdict"] = verdict
            if role == "reconciliation":
                payload["state"] = state
            entries.append({"event": role, "payload": payload,
                            "timestamp_ns": 1})
        (inputs / "record.json").write_text(
            json.dumps({
                "object_id": record.object_id,
                "source_revision": record.source_revision,
                "pulpo_assessment_ref": record.pulpo_assessment_ref,
                "tournament_ref": record.tournament_ref,
                "teams": list(record.teams),
                "battle_refs": list(record.battle_refs),
                "independent_verdict_ref": record.independent_verdict_ref,
                "reconciliation_ref": record.reconciliation_ref,
                "unresolved_risks": [],
                "held_out_ref": record.held_out_ref,
                "independent_verdict": verdict,
                "reconciliation_state": state,
                "completion_claim": claim,
            }, indent=2), encoding="utf-8")
        (inputs / "audit.json").write_text(
            json.dumps(entries, indent=2), encoding="utf-8")
        evidence_path = None
        if evidence is not None:
            evidence_path = inputs / "evidence.json"
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        transfer_path = None
        if transfer is not None:
            transfer_path = inputs / "transfer.json"
            transfer_path.write_text(json.dumps(transfer), encoding="utf-8")
        return record, evidence_path, transfer_path, hashes

    def _run_cli(self, repo, out, record, audit, evidence, revision,
                 transfer=None):
        script = Path(__file__).resolve().parent.parent / "scripts" / "echo_gladiator_verdict.py"
        cmd = [sys.executable, str(script), "--repo", str(repo),
               "--record", str(record), "--audit", str(audit),
               "--output", str(out), "--expected-revision", revision,
               "--timestamp", "2026-11-25T16:00:00+00:00"]
        if evidence is not None:
            cmd += ["--evidence", str(evidence)]
        if transfer is not None:
            cmd += ["--transfer-evidence", str(transfer)]
        return subprocess.run(cmd, text=True, capture_output=True, timeout=60)

    def test_cli_qualified_then_duplicate_then_revision_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            repo = tmp_path / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email",
                            "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name",
                            "Test"], check=True)
            (repo / "probe.txt").write_text("probe\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-qm", "probe"],
                           check=True)
            revision = subprocess.check_output(
                ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
            out = tmp_path / "out"
            inputs = tmp_path / "inputs"
            record, evidence_path, _, _ = self._write_fixture(inputs, revision)
            audit = inputs / "audit.json"
            # First run: qualified echo, event written.
            first = self._run_cli(repo, out, inputs / "record.json", audit,
                                  None, revision)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertIn("GLADIATOR ASSESSMENT: PASS", first.stdout)
            self.assertNotIn("PWNED", first.stdout)
            # Issue 4: the CLI states the reconstructed-audit limit.
            self.assertIn("Audit provenance: caller-supplied reconstruction",
                          first.stderr)
            self.assertIn("structural membership only, not authenticated provenance",
                          first.stderr)
            self.assertEqual(len(list(out.glob("*.json"))), 1)
            event = json.loads(next(out.glob("*.json")).read_text(encoding="utf-8"))
            self.assertIn("structural membership only, not authenticated provenance",
                          event["audit_provenance"])
            # Second run: already emitted, nothing re-printed.
            second = self._run_cli(repo, out, inputs / "record.json", audit,
                                   None, revision)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertNotIn("GLADIATOR ASSESSMENT", second.stdout)
            self.assertIn("already emitted", second.stderr)
            self.assertEqual(len(list(out.glob("*.json"))), 1)
            # Wrong revision: runner failure, nothing emitted.
            out2 = tmp_path / "out2"
            wrong = self._run_cli(repo, out2, inputs / "record.json", audit,
                                  None, "0" * 40)
            self.assertEqual(wrong.returncode, 2)
            self.assertFalse(out2.exists())
            # Dirty tree: runner failure, nothing emitted.
            (repo / "probe.txt").write_text("dirty\n", encoding="utf-8")
            out3 = tmp_path / "out3"
            dirty = self._run_cli(repo, out3, inputs / "record.json", audit,
                                  None, revision)
            self.assertEqual(dirty.returncode, 3)
            self.assertFalse(out3.exists())

    def test_cli_pwned_with_full_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            repo = tmp_path / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email",
                            "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name",
                            "Test"], check=True)
            (repo / "probe.txt").write_text("probe\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-qm", "probe"],
                           check=True)
            revision = subprocess.check_output(
                ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
            out = tmp_path / "out"
            inputs = tmp_path / "inputs"
            _, _, _, hashes = self._write_fixture(inputs, revision)
            evidence_path = inputs / "evidence.json"
            evidence_path.write_text(json.dumps({
                "consequence_established": True,
                "attempt_detected": True,
                "boundary_held": True,
                "authority_revoked": True,
                "containment_verified": True,
                "source": "boundary",
                "refs": {"attempt": hashes[2], "boundary": hashes[1],
                         "revocation": hashes[4], "containment": hashes[5]},
            }), encoding="utf-8")
            result = self._run_cli(repo, out, inputs / "record.json",
                                   inputs / "audit.json", evidence_path, revision)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("YOU'VE BEEN PWNED BY GLADIATOR", result.stdout)
            event = json.loads(next(out.glob("*.json")).read_text(encoding="utf-8"))
            self.assertTrue(event["enforcement_consequence_established"])
            self.assertEqual(event["record_verdict"], "PASS")

    def test_cli_operator_booleans_without_refs_never_pwn(self):
        # Issue 1 via the CLI: all booleans true, no refs -> qualified.
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            repo, revision = self._make_repo(tmp_path)
            out = tmp_path / "out"
            inputs = tmp_path / "inputs"
            _, evidence_path, _, _ = self._write_fixture(inputs, revision, evidence={
                "consequence_established": True,
                "attempt_detected": True,
                "boundary_held": True,
                "authority_revoked": True,
                "containment_verified": True,
                "source": "operator-supplied",
            })
            result = self._run_cli(repo, out, inputs / "record.json",
                                   inputs / "audit.json", evidence_path, revision)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("GLADIATOR ASSESSMENT: PASS", result.stdout)
            self.assertNotIn("PWNED", result.stdout)
            event = json.loads(next(out.glob("*.json")).read_text(encoding="utf-8"))
            self.assertFalse(event["enforcement_consequence_established"])
            self.assertIn("Uncorroborated enforcement claims ignored",
                          " ".join(event["evidence_scope_and_limitations"]))

    def test_cli_evidence_asserting_verified_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            repo, revision = self._make_repo(tmp_path)
            out = tmp_path / "out"
            inputs = tmp_path / "inputs"
            _, evidence_path, _, _ = self._write_fixture(inputs, revision, evidence={
                "consequence_established": True,
                "attempt_detected": True,
                "boundary_held": True,
                "authority_revoked": True,
                "containment_verified": True,
                "verified": True,
            })
            result = self._run_cli(repo, out, inputs / "record.json",
                                   inputs / "audit.json", evidence_path, revision)
            self.assertEqual(result.returncode, 4)
            self.assertFalse(out.exists())

    def test_cli_breach_needs_verified_transfer_evidence(self):
        # Issue 2 via the CLI: CLOSED_DENIED without transfer evidence
        # renders UNVERIFIED; with a verifying ref it renders the breach.
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            repo, revision = self._make_repo(tmp_path)
            inputs = tmp_path / "inputs"
            _, _, _, hashes = self._write_fixture(
                inputs, revision, verdict="DENY", state="COMPLETE",
                claim="CLOSED_DENIED")
            out = tmp_path / "out"
            result = self._run_cli(repo, out, inputs / "record.json",
                                   inputs / "audit.json", None, revision)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("GLADIATOR: CONTAINMENT UNVERIFIED", result.stdout)
            self.assertNotIn("DEFENSE BREACHED", result.stdout)
            transfer_path = inputs / "transfer.json"
            transfer_path.write_text(json.dumps({
                "transfer_observed": True,
                "refs": [hashes[2]],
                "source": "boundary",
            }), encoding="utf-8")
            out2 = tmp_path / "out2"
            breached = self._run_cli(repo, out2, inputs / "record.json",
                                     inputs / "audit.json", None, revision,
                                     transfer=transfer_path)
            self.assertEqual(breached.returncode, 0, breached.stderr)
            self.assertIn("GLADIATOR: DEFENSE BREACHED", breached.stdout)


if __name__ == "__main__":
    unittest.main()
