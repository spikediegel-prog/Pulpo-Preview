import math
import unittest

from pulpo.local_resources import Metric, ResourceSample
from pulpo.resource_status import duration, status_text


class ResourceStatusTests(unittest.TestCase):
    def test_real_cached_time_span_and_paused_age_are_distinct(self):
        sample = ResourceSample(1000, 250, "Linux / WSL", "/", Metric(), Metric(), Metric())
        self.assertEqual("3m 12s", duration(192))
        self.assertEqual("1h 1m 1s", duration(3661))
        self.assertIn("Updated 2s ago · 3m 12s history", status_text(sample, 58, now=252))
        self.assertIn("Paused · Updated 10s ago", status_text(sample, 58, now=260, paused=True))
        self.assertIn("Updated just now", status_text(sample, 250, now=250))

    def test_missing_and_invalid_time_do_not_become_zero_or_current(self):
        self.assertIn("Awaiting readings · History unknown", status_text(None, None))
        sample = ResourceSample(1000, 250, "Linux / WSL", "/", Metric(), Metric(), Metric())
        self.assertIn("Update time unknown", status_text(sample, 251, now=249))
        self.assertIn("Unknown history", status_text(sample, 251, now=249))
        for value in (-1, math.nan, math.inf): self.assertEqual("Unknown", duration(value))


if __name__ == "__main__":
    unittest.main()
