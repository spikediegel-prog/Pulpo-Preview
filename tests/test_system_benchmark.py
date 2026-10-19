from pathlib import Path
import queue
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from pulpo import evidence_tuning as tuning
from pulpo import system_benchmark as benchmark


class SystemBenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.profile = Path(self.temp.name) / "profile.json"

    def row(self, workers=0, seconds=.01):
        return {"workers": workers, "samples_seconds": [seconds], "process_cpu_seconds": seconds / 2,
                "peak_process_rss_bytes": 30 * 1024**2, "files": 64, "fixture_bytes": 4 * 1024**2,
                "correctness": "PASS"}

    def test_alternating_order_summary_and_no_automatic_save(self):
        order = []
        def measure(workers, stop, deadline):
            order.append(workers)
            return self.row(workers, .02 if workers == 0 else .01)
        with patch.object(tuning, "thread_limit", return_value=4), patch.object(benchmark, "measure_case", side_effect=measure):
            report = benchmark.compare_settings(self.profile, 2, threading.Event(), lambda text: None)
        self.assertEqual([0, 2, 2, 0, 0, 2, 2, 0, 0, 2], order)
        self.assertEqual("Faster", report["classification"])
        self.assertEqual(6400, report["candidate"]["files_per_second"])
        self.assertEqual(50, report["candidate"]["cpu_core_percent"])
        self.assertFalse(self.profile.exists())

    def test_same_serial_mode_and_overlapping_ranges_are_inconclusive(self):
        with patch.object(benchmark, "measure_case", side_effect=lambda workers, *_: self.row(workers, .02 if workers == 0 else .01)):
            report = benchmark.compare_settings(self.profile, 1, threading.Event(), lambda text: None)
        self.assertEqual("Inconclusive", report["classification"])
        self.assertEqual("Inconclusive", benchmark.classify({"median_ms": 10, "min_ms": 5, "max_ms": 15},
                                                           {"median_ms": 8, "min_ms": 6, "max_ms": 10}))

    def test_failed_correctness_cancel_timeout_and_stale_profile_cannot_save(self):
        stop = threading.Event()
        stop.set()
        with self.assertRaises(benchmark.BenchmarkCancelled):
            benchmark.compare_settings(self.profile, 1, stop, lambda text: None)
        with self.assertRaises(TimeoutError):
            benchmark.measure_case(0, threading.Event(), time.monotonic() - 1)
        messages = queue.Queue()
        with patch.object(benchmark, "compare_settings", side_effect=ValueError("Correctness failed")):
            benchmark.run_task("compare", (self.profile, 1), messages, threading.Event())
        self.assertEqual(["error", "done"], [messages.get()[0], messages.get()[0]])
        self.assertFalse(self.profile.exists())
        with patch.object(benchmark, "measure_case", side_effect=lambda workers, *_: self.row(workers)):
            report = benchmark.compare_settings(self.profile, 1, threading.Event(), lambda text: None)
        self.profile.write_text("{}")
        before = self.profile.read_bytes()
        with self.assertRaises(ValueError): benchmark.save_candidate(report, self.profile)
        self.assertEqual(before, self.profile.read_bytes())

    def test_save_rechecks_correctness_and_restore_uses_existing_path(self):
        tuning.save_settings(tuning.EvidenceSettings(0), self.profile)
        with patch.object(benchmark, "measure_case", side_effect=lambda workers, *_: self.row(workers)):
            report = benchmark.compare_settings(self.profile, 1, threading.Event(), lambda text: None)
        with patch.object(tuning, "check_settings", side_effect=ValueError("fresh check failed")):
            before = self.profile.read_bytes()
            with self.assertRaises(ValueError): benchmark.save_candidate(report, self.profile)
            self.assertEqual(before, self.profile.read_bytes())
        benchmark.save_candidate(report, self.profile)
        self.assertEqual(1, tuning.load_settings(self.profile).workers)
        tuning.restore_previous(self.profile)
        self.assertEqual(0, tuning.load_settings(self.profile).workers)

    def test_real_spawned_worker_returns_metrics_and_cleanup_on_cancel(self):
        row = benchmark.measure_case(0, threading.Event(), time.monotonic() + 30)
        self.assertEqual("PASS", row["correctness"])
        self.assertEqual(4 * 1024**2, row["fixture_bytes"])
        self.assertGreater(row["process_cpu_seconds"], 0)
        stop = threading.Event()
        timer = threading.Timer(.02, stop.set)
        timer.start()
        try:
            with self.assertRaises(benchmark.BenchmarkCancelled):
                benchmark.measure_case(0, stop, time.monotonic() + 30)
        finally:
            timer.join()

    def test_schema_limits_missing_measurements_and_expired_report(self):
        with self.assertRaises(ValueError): tuning.EvidenceSettings(True).validate()
        rows = [self.row() for _ in range(5)]
        rows[0]["peak_process_rss_bytes"] = None
        self.assertIsNone(benchmark.summarize(rows)["peak_process_rss_bytes"])
        with self.assertRaises(ValueError): benchmark.summarize(rows[:2])
        with patch.object(benchmark, "measure_case", side_effect=lambda workers, *_: self.row(workers)):
            report = benchmark.compare_settings(self.profile, 1, threading.Event(), lambda text: None)
        report["completed_at"] = time.time() - 901
        with self.assertRaises(ValueError): benchmark.save_candidate(report, self.profile)


if __name__ == "__main__":
    unittest.main()
