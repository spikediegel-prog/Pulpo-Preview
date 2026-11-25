import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from pulpo.cli import main
from pulpo.verifier import CheckStatus, run_verification
from pulpo.verifier.evidence import write_report
from pulpo.verifier.report import CheckStatus, VerificationCheck, build_report


class VerifierTests(unittest.TestCase):
    def test_isolated_harness_reports_observed_checks_and_unknown_boundaries(self):
        report = run_verification()
        checks = {check.check_id: check for check in report.checks}

        self.assertEqual("UNVERIFIABLE", report.status.value)
        self.assertTrue(
            {
                "permit-replay-protection",
                "directive-revocation",
                "target-binding",
                "authority-separation",
                "custody-required-for-execution",
                "mutation-approval-gate",
                "approval-signature-validation",
                "durable-permit-replay-protection",
            }.issubset(checks)
        )
        self.assertEqual(CheckStatus.PASS, checks["permit-replay-protection"].status)
        self.assertEqual(CheckStatus.PASS, checks["target-binding"].status)
        self.assertEqual(CheckStatus.PASS, checks["authority-separation"].status)
        self.assertEqual(CheckStatus.PASS, checks["mutation-approval-gate"].status)
        self.assertEqual(CheckStatus.UNVERIFIABLE, checks["directive-revocation"].status)
        self.assertEqual(CheckStatus.UNVERIFIABLE, checks["custody-required-for-execution"].status)
        self.assertEqual(
            CheckStatus.UNVERIFIABLE,
            checks["audit-tamper-detection"].status,
        )
        self.assertTrue(report.scope["authority_effect"].startswith("none_outside_ephemeral_probe"))
        self.assertIn("ephemeral", report.scope["canonical_state_mutation"])
        self.assertIn("audit writes", report.scope["governed_effect"])
        self.assertEqual(
            round(report.check_counts["pass"] / report.check_counts["total"] * 100, 1),
            report.governance_score["percentage"],
        )

    def test_report_writer_emits_versioned_machine_readable_evidence(self):
        report = run_verification()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "verifier_report.json"
            self.assertEqual(path, write_report(report, path))
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual("pulpo.verifier-report.v1", payload["schema"])
        self.assertEqual("0.1.0", payload["version"])
        self.assertEqual(report.status.value, payload["status"])
        self.assertEqual(report.check_counts, payload["check_counts"])
        self.assertTrue(payload["generated_at"].endswith("+00:00"))

    def test_cli_writes_report_and_returns_nonzero_for_unverifiable_claims(self):
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.json"
            output = StringIO()
            with patch("sys.argv", ["pulpo", "verify", "--report", str(report_path)]):
                with redirect_stdout(output):
                    result = main()

            self.assertEqual(1, result)
            self.assertTrue(report_path.is_file())
            self.assertIn("Governance score", output.getvalue())
            self.assertIn("UNVERIFIABLE", output.getvalue())

    def test_cli_requires_complete_external_integrity_configuration(self):
        with patch(
            "sys.argv",
            ["pulpo", "verify", "--integrity-manifest-url", "https://integrity.example.test"],
        ):
            with self.assertRaises(SystemExit) as error:
                main()
        self.assertEqual(2, error.exception.code)

    def test_cli_includes_configured_external_integrity_result(self):
        integrity_check = VerificationCheck(
            "external-verifier-integrity",
            "integrity",
            CheckStatus.PASS,
            "Signed source matched.",
            ("challenge_matched=true",),
            "Verified",
        )
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.json"
            arguments = [
                "pulpo",
                "verify",
                "--report",
                str(report_path),
                "--integrity-manifest-url",
                "https://integrity.example.test/manifest",
                "--integrity-public-key",
                str(Path(directory) / "trusted.pub"),
                "--integrity-key-sha256",
                "a" * 64,
            ]
            with (
                patch("sys.argv", arguments),
                patch(
                    "pulpo.verifier.external_integrity.check_external_integrity",
                    return_value=integrity_check,
                ) as external_check,
                redirect_stdout(StringIO()),
            ):
                result = main()

            payload = json.loads(report_path.read_text(encoding="utf-8"))
        external_check.assert_called_once()
        self.assertEqual(1, result)
        self.assertEqual("UNVERIFIABLE", payload["status"])
        self.assertTrue(
            any(check["check_id"] == "external-verifier-integrity" for check in payload["checks"])
        )
        self.assertIn("running process", payload["scope"]["external_integrity_boundary"])

    def test_failed_checks_take_precedence_in_report_status(self):
        checks = (
            VerificationCheck(
                "probe-passed",
                "test",
                CheckStatus.PASS,
                "Observed a pass.",
                (),
                "Verified",
            ),
            VerificationCheck(
                "probe-failed",
                "test",
                CheckStatus.FAIL,
                "Observed a failure.",
                (),
                "Verified",
            ),
            VerificationCheck(
                "probe-unknown",
                "test",
                CheckStatus.UNVERIFIABLE,
                "No evidence.",
                (),
                "Unknown",
            ),
        )
        report = build_report(checks)
        self.assertEqual(CheckStatus.FAIL, report.status)
        self.assertEqual(33.3, report.governance_score["percentage"])


if __name__ == "__main__":
    unittest.main()
