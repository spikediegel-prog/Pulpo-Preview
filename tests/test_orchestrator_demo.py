import contextlib
from dataclasses import replace
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import demo_orchestrator as demo


class OrchestratorDemoTests(unittest.TestCase):
    def test_demo_exercises_must_fix_boundaries(self):
        result = demo.run_demo()
        self.assertEqual("target_hash_mismatch", result["target_mismatch_denied"])
        self.assertEqual(0, result["authority_polls_after_tamper"])
        self.assertTrue(result["first_permit_consume"])
        self.assertFalse(result["replay_permit_consume"])
        self.assertFalse(result["revoked_preissued_directive_permit"])
        self.assertTrue(result["audit_valid"])
        self.assertEqual(22, result["audit_records"])

    def test_plain_language_output_and_json_use_same_checked_results(self):
        text = io.StringIO()
        with contextlib.redirect_stdout(text):
            self.assertEqual(0, demo.main([]))
        for expected in ("Changed target blocked", "Permit replay blocked",
                         "Revoked permission blocked", "22 records", "test-only authority",
                         "production readiness"):
            self.assertIn(expected, text.getvalue())
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(0, demo.main(["--json"]))
        self.assertEqual(demo.run_demo(), json.loads(output.getvalue()))

    def test_replay_acceptance_fails_without_success_output(self):
        for options in ([], ["--json"]):
            output, errors = io.StringIO(), io.StringIO()
            with (patch.object(demo.PulpoOrchestrator, "consume_authorized_target", return_value=True),
                  contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors)):
                self.assertEqual(1, demo.main(options))
            self.assertEqual("", output.getvalue())
            self.assertIn("Permit replay was not blocked", errors.getvalue())

    def test_invalid_audit_fails_without_success_output(self):
        snapshot = demo.PulpoOrchestrator.evidence_snapshot

        def invalid(orchestrator):
            return replace(snapshot(orchestrator), audit_valid=False)

        with (patch.object(demo.PulpoOrchestrator, "evidence_snapshot", invalid),
              contextlib.redirect_stdout(io.StringIO()) as output,
              contextlib.redirect_stderr(io.StringIO()) as errors):
            self.assertEqual(1, demo.main([]))
        self.assertEqual("", output.getvalue())
        self.assertIn("Demo audit did not verify", errors.getvalue())

    def test_normal_and_optimized_runs_preserve_same_transitions_without_files(self):
        script = str(Path(demo.__file__).resolve())
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        with tempfile.TemporaryDirectory() as directory:
            results = []
            for flags in ([], ["-O"], ["-O"]):
                result = subprocess.run([sys.executable, "-B", *flags, script, "--json"],
                                        cwd=directory, env=env, capture_output=True, text=True)
                self.assertEqual(0, result.returncode, result.stderr)
                results.append(json.loads(result.stdout))
            self.assertTrue(all(item == results[0] for item in results))
            self.assertEqual(22, results[0]["audit_records"])
            self.assertEqual([], list(Path(directory).iterdir()))

    def test_optimized_run_still_rejects_replay_acceptance(self):
        root = str(Path(demo.__file__).resolve().parents[1])
        code = (
            "from unittest.mock import patch; from scripts import demo_orchestrator as d; "
            "p=patch.object(d.PulpoOrchestrator, 'consume_authorized_target', return_value=True); "
            "p.start(); raise SystemExit(d.main(['--json']))"
        )
        result = subprocess.run([sys.executable, "-B", "-O", "-c", code],
                                cwd=root, capture_output=True, text=True)
        self.assertEqual(1, result.returncode)
        self.assertEqual("", result.stdout)
        self.assertIn("Permit replay was not blocked", result.stderr)

    def test_unknown_arguments_stop_before_demo_runs(self):
        with (patch.object(demo, "run_demo") as run, contextlib.redirect_stderr(io.StringIO()),
              self.assertRaises(SystemExit) as error):
            demo.main(["--execute", "production"])
        self.assertEqual(2, error.exception.code)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
