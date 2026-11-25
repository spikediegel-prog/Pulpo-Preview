"""Regression tests for the Gladiator verdict echo.

Covers proposal section 8.5: PASS (qualified vs Pwned), breach, UNKNOWN,
duplicate emission, forged success attempts, line-level evidence, and the
CLI runner-failure guards. The echo is presentation only; these tests prove
what it renders, not that any network enforcement exists.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pulpo import GovernanceKernel, Policy
from pulpo.gladiator_gate import GladiatorRecord, completion_eligible
from pulpo.gladiator_audit_projection import audit_references_present
from pulpo.gladiator_verdict_echo import (
    EnforcementEvidence,
    emit,
    render,
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


FULL_EVIDENCE = EnforcementEvidence(
    consequence_established=True,
    attempt_detected=True,
    boundary_held=True,
    authority_revoked=True,
    containment_verified=True,
    source="boundary",
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

    def render_assessed(self, record=None, enforcement=None):
        eligible, projection = self.assess(record)
        return render(
            self.record if record is None else record,
            eligible=eligible, projection_passed=projection,
            enforcement=enforcement, timestamp=self.timestamp)

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
        echo = self.render_assessed(enforcement=FULL_EVIDENCE)
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

    def test_pwned_lines_gated_on_their_own_evidence(self):
        partial = EnforcementEvidence(
            consequence_established=True, attempt_detected=True,
            boundary_held=True, source="boundary")
        echo = self.render_assessed(enforcement=partial)
        self.assertIn("YOU'VE BEEN PWNED BY GLADIATOR", echo.text)
        self.assertIn("Attack attempt detected.", echo.text)
        self.assertIn("Enforcement boundary held.", echo.text)
        self.assertNotIn("Authority revoked.", echo.text)
        self.assertNotIn("Containment verified.", echo.text)

    def test_breach_renders_fail_display_with_deny_record(self):
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
        echo = render(record, eligible=eligible, projection_passed=projection,
                      timestamp=self.timestamp)
        self.assertEqual(echo.display_verdict, "FAIL")
        self.assertEqual(echo.record_verdict, "DENY")
        self.assertIn("GLADIATOR: DEFENSE BREACHED", echo.text)
        self.assertIn("VERDICT: FAIL", echo.text)
        self.assertNotIn("PWNED", echo.text)

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
        echo = self.render_assessed(record, enforcement=FULL_EVIDENCE)
        self.assertEqual(echo.display_verdict, "UNKNOWN")
        self.assertNotIn("PWNED", echo.text)

    def test_ineligible_record_renders_unverified_never_pwned(self):
        # Substituted object: eligibility fails, so no Pwned banner even
        # with full enforcement evidence asserted.
        record = replace(self.record, object_id="assessment:other")
        echo = self.render_assessed(record, enforcement=FULL_EVIDENCE)
        self.assertEqual(echo.display_verdict, "UNKNOWN")
        self.assertNotIn("PWNED", echo.text)

    def test_projection_failure_renders_unverified_never_pwned(self):
        record = replace(
            self.record, independent_verdict_ref="self:asserted")
        echo = self.render_assessed(record, enforcement=FULL_EVIDENCE)
        self.assertEqual(echo.display_verdict, "UNKNOWN")
        self.assertNotIn("PWNED", echo.text)

    def test_non_record_input_raises_no_echo(self):
        with self.assertRaises(TypeError):
            render(None, eligible=True, projection_passed=True)
        with self.assertRaises(TypeError):
            render("VERIFIED", eligible=True, projection_passed=True)

    def test_structured_event_distinguishes_fields(self):
        echo = self.render_assessed(enforcement=FULL_EVIDENCE)
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
        self.render_assessed(enforcement=FULL_EVIDENCE)
        self.assertEqual(before_audit, tuple(entry["hash"] for entry in self.kernel.audit))
        self.assertEqual(before_record, self.record)

    def test_duplicate_emission_writes_once(self):
        eligible, projection = self.assess()
        with tempfile.TemporaryDirectory() as tmp:
            first = emit(self.record, eligible=eligible,
                         projection_passed=projection,
                         enforcement=FULL_EVIDENCE, output_dir=tmp,
                         timestamp=self.timestamp)
            self.assertTrue(first.emitted)
            self.assertTrue(first.path.exists())
            content = first.path.read_text(encoding="utf-8")
            second = emit(self.record, eligible=eligible,
                          projection_passed=projection,
                          enforcement=FULL_EVIDENCE, output_dir=tmp,
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
                         enforcement=FULL_EVIDENCE, output_dir=tmp,
                         timestamp=self.timestamp)
            first.path.write_text(
                json.dumps({"emission_key": "tampered"}),
                encoding="utf-8")
            with self.assertRaises(ValueError):
                emit(self.record, eligible=eligible,
                     projection_passed=projection,
                     enforcement=FULL_EVIDENCE, output_dir=tmp,
                     timestamp=self.timestamp)


class VerdictEchoCliTests(unittest.TestCase):
    def _write_fixture(self, inputs, revision, *, evidence=None):
        inputs.mkdir(parents=True, exist_ok=True)
        object_id = "assessment:cli"
        kernel, hashes = build_kernel(object_id, revision)
        record = build_record(
            hashes, object_id=object_id, revision=revision)
        entries = []
        for role in ROLES:
            payload = {
                "object_id": object_id,
                "source_revision": revision,
                "authority_effect": "none",
            }
            if role == "independent_verdict":
                payload["verdict"] = "PASS"
            if role == "reconciliation":
                payload["state"] = "COMPLETE"
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
                "independent_verdict": "PASS",
                "reconciliation_state": "COMPLETE",
                "completion_claim": "VERIFIED",
            }, indent=2), encoding="utf-8")
        (inputs / "audit.json").write_text(
            json.dumps(entries, indent=2), encoding="utf-8")
        evidence_path = None
        if evidence is not None:
            evidence_path = inputs / "evidence.json"
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        return record, evidence_path

    def _run_cli(self, repo, out, record, audit, evidence, revision):
        script = Path(__file__).resolve().parent.parent / "scripts" / "echo_gladiator_verdict.py"
        cmd = [sys.executable, str(script), "--repo", str(repo),
               "--record", str(record), "--audit", str(audit),
               "--output", str(out), "--expected-revision", revision,
               "--timestamp", "2026-11-25T16:00:00+00:00"]
        if evidence is not None:
            cmd += ["--evidence", str(evidence)]
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
            record, evidence_path = self._write_fixture(inputs, revision)
            audit = inputs / "audit.json"
            # First run: qualified echo, event written.
            first = self._run_cli(repo, out, inputs / "record.json", audit,
                                  None, revision)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertIn("GLADIATOR ASSESSMENT: PASS", first.stdout)
            self.assertNotIn("PWNED", first.stdout)
            self.assertEqual(len(list(out.glob("*.json"))), 1)
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
            _, evidence_path = self._write_fixture(inputs, revision, evidence={
                "consequence_established": True,
                "attempt_detected": True,
                "boundary_held": True,
                "authority_revoked": True,
                "containment_verified": True,
                "source": "boundary",
            })
            result = self._run_cli(repo, out, inputs / "record.json",
                                   inputs / "audit.json", evidence_path, revision)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("YOU'VE BEEN PWNED BY GLADIATOR", result.stdout)
            event = json.loads(next(out.glob("*.json")).read_text(encoding="utf-8"))
            self.assertTrue(event["enforcement_consequence_established"])
            self.assertEqual(event["record_verdict"], "PASS")


if __name__ == "__main__":
    unittest.main()
