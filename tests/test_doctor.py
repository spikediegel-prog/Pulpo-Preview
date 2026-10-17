import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from pulpo.cli import build_parser
from pulpo.setup import run_doctor


class DoctorTests(unittest.TestCase):
    def test_real_self_check_passes_without_profile_operations(self):
        with (
            patch("pulpo.setup.AuditPerformanceTuner.load", side_effect=AssertionError("load")),
            patch("pulpo.setup.AuditPerformanceTuner.save", side_effect=AssertionError("save")),
            patch("pulpo.setup.AuditPerformanceTuner.calibrate", side_effect=AssertionError("calibrate")),
        ):
            report = run_doctor()
        self.assertTrue(report["ready_for_test_use"])
        self.assertEqual("PASS", report["audit_verification"]["status"])
        self.assertEqual("none", report["authority_effect"])
        self.assertEqual("none", report["governance_changes"])
        self.assertFalse(report["production_readiness_claim"])

    def test_valid_rejected_or_tamper_accepted_fails_closed_and_closes_engine(self):
        for results in ([False], [True, True]):
            with self.subTest(results=results), patch("pulpo.setup.AdaptiveAuditVerificationEngine") as engine:
                engine.return_value.verify_rows.side_effect = results
                report = run_doctor()
                self.assertFalse(report["ready_for_test_use"])
                self.assertEqual("FAIL", report["audit_verification"]["status"])
                engine.return_value.close.assert_called_once()

    def test_verifier_exception_closes_engine(self):
        with patch("pulpo.setup.AdaptiveAuditVerificationEngine") as engine:
            engine.return_value.verify_rows.side_effect = ValueError("bad audit")
            with self.assertRaisesRegex(ValueError, "bad audit"):
                run_doctor()
            engine.return_value.close.assert_called_once()

    def test_json_is_parseable_and_failure_returns_one(self):
        parser = build_parser()
        args = parser.parse_args(["doctor", "--json"])
        report = run_doctor()
        report["ready_for_test_use"] = False
        report["audit_verification"]["status"] = "FAIL"
        output = io.StringIO()
        with patch("pulpo.cli.run_doctor", return_value=report), contextlib.redirect_stdout(output):
            self.assertEqual(1, args.func(args))
        self.assertEqual(report, json.loads(output.getvalue()))

    def test_human_output_gives_next_step_only_on_success(self):
        args = build_parser().parse_args(["doctor"])
        for ready in (True, False):
            report = run_doctor()
            report["ready_for_test_use"] = ready
            report["audit_verification"]["status"] = "PASS" if ready else "FAIL"
            output = io.StringIO()
            with patch("pulpo.cli.run_doctor", return_value=report), contextlib.redirect_stdout(output):
                self.assertEqual(0 if ready else 1, args.func(args))
            self.assertEqual(ready, "Next:" in output.getvalue())
            self.assertIn("no live state or deployment validation", output.getvalue())

    def test_repeated_and_substituted_cli_calls_preserve_working_directory(self):
        source = str(Path(__file__).resolve().parents[1])
        env = dict(os.environ, PYTHONPATH=source, PYTHONDONTWRITEBYTECODE="1")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = root / ".pulpo" / "audit-performance-profile.json"
            profile.parent.mkdir()
            profile.write_text("malformed profile must remain untouched", encoding="utf-8")
            before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            for options, expected in ((["--json"], 0), (["--json"], 0),
                                      (["--benchmark", "fake.json"], 2),
                                      (["--evidence-install", "recommended"], 2),
                                      (["--profile", str(profile)], 2)):
                result = subprocess.run(
                    [sys.executable, "-B", "-m", "pulpo.cli", "doctor", *options],
                    cwd=root, env=env, capture_output=True, text=True, check=False,
                )
                self.assertEqual(expected, result.returncode, result.stderr)
                if expected == 0:
                    self.assertTrue(json.loads(result.stdout)["ready_for_test_use"])
            after = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
