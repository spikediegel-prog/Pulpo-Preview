from copy import deepcopy
from pathlib import Path
import os
import tempfile
import threading
import unittest
from unittest.mock import patch

from pulpo import evidence_tuning as tuning
from pulpo import system_benchmark as benchmark
from pulpo.configuration_comparison import applicability, candidate_workers, collector_mode, inspect_configuration


class ConfigurationComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.profile = Path(self.temporary.name) / "profile.json"

    def report(self):
        from tests.test_system_benchmark import SystemBenchmarkTests
        helper = SystemBenchmarkTests()
        with patch.object(benchmark, "measure_case", side_effect=lambda workers, *_: helper.row(workers)):
            return benchmark.compare_settings(self.profile, 1, threading.Event(), lambda text: None)

    def test_missing_profile_is_default_without_fabricated_history_or_writes(self):
        current = inspect_configuration(self.profile)
        self.assertEqual(0, current.workers)
        self.assertEqual("missing", current.profile_token)
        self.assertIsNone(current.previous_workers)
        self.assertIn("serial default", current.status)
        self.assertFalse(self.profile.exists())
        self.assertEqual("Serial", collector_mode(0))
        self.assertEqual("Serial", collector_mode(1))
        self.assertEqual("Threads", collector_mode(2))
        self.assertEqual("Unknown", collector_mode(None))

    def test_accepted_profile_and_recorded_rollback_value(self):
        tuning.save_settings(tuning.EvidenceSettings(0), self.profile)
        tuning.save_settings(tuning.EvidenceSettings(1), self.profile)
        before = self.profile.read_bytes()
        current = inspect_configuration(self.profile)
        self.assertEqual((1, 0), (current.workers, current.previous_workers))
        self.assertEqual("Saved profile accepted", current.status)
        self.assertEqual(before, self.profile.read_bytes())

    def test_invalid_profile_falls_back_without_echo_and_oversized_is_unavailable(self):
        self.profile.write_text('PRIVATE credential /path')
        current = inspect_configuration(self.profile)
        self.assertEqual(0, current.workers)
        self.assertIn("serial fallback", current.status)
        self.assertNotIn("PRIVATE", str(current))
        self.profile.write_bytes(b"x" * 16385)
        self.assertIsNone(inspect_configuration(self.profile).workers)
        self.assertEqual(b"x" * 16385, self.profile.read_bytes())

    def test_non_regular_and_changed_during_check_are_unavailable(self):
        self.assertIsNone(inspect_configuration(self.profile.parent).profile_token)
        if hasattr(os, "mkfifo"):
            os.mkfifo(self.profile)
            self.assertIsNone(inspect_configuration(self.profile).profile_token)
            self.profile.unlink()
        with patch.object(benchmark, "profile_token", side_effect=["missing", "changed"]):
            self.assertIsNone(inspect_configuration(self.profile).profile_token)

    def test_only_exact_pair_and_last_checked_context_apply(self):
        report = self.report()
        current = inspect_configuration(self.profile)
        self.assertEqual("Applicable to last checked context", applicability(current, 1, report))
        self.assertEqual("Inconclusive", report["classification"])  # 0 and 1 are both serial
        self.assertIn("Candidate changed", applicability(current, 2, report))
        self.assertIn("No worker-count change", applicability(current, 0, report))
        tuning.save_settings(tuning.EvidenceSettings(0), self.profile)
        self.assertIn("Current profile changed", applicability(inspect_configuration(self.profile), 1, report))

    def test_expired_future_machine_source_and_malformed_reports_cannot_apply(self):
        report = self.report()
        current = inspect_configuration(self.profile)
        self.assertIn("expired", applicability(current, 1, report, now=report["completed_at"] + 901))
        self.assertIn("Clock mismatch", applicability(current, 1, report, now=report["completed_at"] - 1))
        for key, value in (("source_sha256", "changed"), ("machine", {}), ("schema", "unknown"),
                ("correctness", "FAIL"), ("completed_at", float("nan")), ("completed_at", True),
                ("classification", "Verified"), ("authority_effect", "grant"), ("repetitions", 1)):
            changed = deepcopy(report)
            changed[key] = value
            self.assertNotEqual("Applicable to last checked context", applicability(current, 1, changed))
        changed = deepcopy(report)
        changed["candidate"]["median_ms"] = float("inf")
        self.assertIn("invalid", applicability(current, 1, changed))
        self.assertIn("invalid", applicability(current, 1, {}))
        self.assertIn("invalid", applicability(current, 1, "PRIVATE"))

    def test_missing_checks_invalid_candidates_and_no_report_are_explicit(self):
        current = inspect_configuration(self.profile)
        self.assertIn("Unknown", applicability(None, 1, None))
        self.assertIn("No comparison", applicability(current, 1, None))
        self.assertIn("Invalid proposal", applicability(current, None, None))
        for value in ("PRIVATE secret", "1.5", "-1", "999999999999", ""):
            self.assertIsNone(candidate_workers(value))
        self.assertEqual(1, candidate_workers("1"))


if __name__ == "__main__":
    unittest.main()
