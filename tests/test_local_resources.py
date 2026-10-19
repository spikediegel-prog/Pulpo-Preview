import io
import math
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pulpo.local_resources import (Metric, ResourceHistory, ResourceSample, ResourceSampler,
                                   level, linux_cpu, linux_memory, utilization)


def sample(at, cpu=20, memory=30, storage=40):
    return ResourceSample(at, at, "test fixture", "/fixture", Metric(cpu), Metric(memory), Metric(storage))


class ResourceParsingTests(unittest.TestCase):
    def test_cpu_excludes_guest_double_counting_and_includes_iowait(self):
        self.assertEqual((240, 120), linux_cpu("cpu 50 10 30 100 20 10 10 10 15 5\n"))

    def test_cpu_rejects_invalid_aggregate(self):
        for raw in ("", "cpu0 1 2 3 4", "cpu 1 2", "cpu 1 2 3 -4", "cpu a 2 3 4"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                linux_cpu(raw)

    def test_memory_uses_available_not_free(self):
        result = linux_memory("MemTotal: 1000 kB\nMemFree: 10 kB\nMemAvailable: 400 kB\n")
        self.assertEqual((60, 600 * 1024, 1000 * 1024), (result.percent, result.used, result.total))

    def test_missing_malformed_or_impossible_memory_is_not_zero_usage(self):
        for raw in ("", "MemTotal: 100 kB", "MemTotal: 100 kB\nMemAvailable: 200 kB",
                    "MemTotal: 100 bytes\nMemAvailable: 20 kB",
                    "MemTotal: 100 kB\nMemTotal: 100 kB\nMemAvailable: 20 kB"):
            with self.subTest(raw=raw), self.assertRaises((ValueError, KeyError)):
                linux_memory(raw)

    def test_capacity_invalid_values_and_zero_total_rejected(self):
        for used, total in ((1, 0), (-1, 100), (101, 100), (True, 100), (50, math.inf)):
            with self.subTest(values=(used, total)), self.assertRaises(ValueError):
                utilization(used, total)
        self.assertEqual(0, utilization(0, 100).percent)
        self.assertEqual(100, utilization(100, 100).percent)

    def test_attention_thresholds_do_not_treat_unknown_as_success(self):
        for value in (None, math.nan, math.inf, -1, 101):
            self.assertEqual("Unknown", level(value))
        for value, expected in ((0, "Normal"), (74.9, "Normal"), (75, "Elevated"),
                                (89.9, "Elevated"), (90, "Attention"), (100, "Attention")):
            self.assertEqual(expected, level(value))


class ResourceSamplerTests(unittest.TestCase):
    def run_samples(self, cpu_rows, memory="MemTotal: 1000 kB\nMemAvailable: 400 kB\n", disk_error=False):
        def opened(path, **kwargs):
            if path == "/proc/stat":
                value = cpu_rows.pop(0)
                if isinstance(value, Exception):
                    raise value
                return io.StringIO(value)
            if path == "/proc/meminfo":
                return io.StringIO(memory)
            self.fail("Unexpected read: " + str(path))
        count = len(cpu_rows)
        disk = OSError("unavailable") if disk_error else SimpleNamespace(used=25, total=100)
        with patch("pulpo.local_resources.platform.system", return_value="Linux"), \
             patch("pulpo.local_resources.open", side_effect=opened, create=True), \
             patch("pulpo.local_resources.shutil.disk_usage", side_effect=disk if disk_error else None,
                   return_value=None if disk_error else disk):
            sampler = ResourceSampler()
            return [sampler.sample() for _ in range(count)]

    def test_first_cpu_sample_is_unknown_then_observed_delta(self):
        first, second = self.run_samples(["cpu 10 0 0 90\n", "cpu 30 0 0 170\n"])
        self.assertIsNone(first.cpu.percent)
        self.assertIn("first", first.cpu.reason)
        self.assertEqual(20, second.cpu.percent)
        self.assertEqual(60, second.memory.percent)
        self.assertEqual(25, second.storage.percent)

    def test_counter_reset_and_zero_interval_do_not_fabricate_cpu(self):
        results = self.run_samples(["cpu 10 0 0 90", "cpu 10 0 0 90", "cpu 1 0 0 9", "cpu 11 0 0 99"])
        self.assertIsNone(results[1].cpu.percent)
        self.assertIsNone(results[2].cpu.percent)
        self.assertEqual(10, results[3].cpu.percent)

    def test_failed_cpu_read_resets_baseline_without_hiding_other_metrics(self):
        results = self.run_samples(["cpu 10 0 0 90", OSError("unavailable"), "cpu 30 0 0 170"])
        self.assertIsNone(results[1].cpu.percent)
        self.assertIsNone(results[2].cpu.percent)
        self.assertEqual(60, results[1].memory.percent)

    def test_unavailable_memory_and_storage_are_unknown(self):
        result = self.run_samples(["cpu 10 0 0 90"], memory="malformed", disk_error=True)[0]
        self.assertIsNone(result.memory.percent)
        self.assertIsNone(result.storage.percent)

    def test_oversized_cpu_input_is_rejected(self):
        result = self.run_samples(["cpu " + "1 " * 2200])[0]
        self.assertIsNone(result.cpu.percent)


class ResourceHistoryTests(unittest.TestCase):
    def test_history_never_fills_unknown_or_paused_intervals(self):
        history = ResourceHistory()
        for item in (sample(10, cpu=None), sample(12, cpu=30), sample(40, cpu=20)):
            history.append(item)
        self.assertEqual([(10, None), (12, 30), (40, 20)], history.points("cpu", 60, 40))
        self.assertEqual([], history.points("cpu", 60, 200))
        with self.assertRaises(ValueError):
            history.append(sample(39))

    def test_hour_history_is_bounded_and_scoped(self):
        history = ResourceHistory()
        for at in range(2000):
            history.append(sample(at))
        self.assertEqual(1801, len(history.samples))
        self.assertEqual(61, len(history.points("cpu", 60, 1999)))
        for name, seconds in (("authority", 60), ("cpu", 120)):
            with self.assertRaises(ValueError):
                history.points(name, seconds, 1999)


if __name__ == "__main__":
    unittest.main()
