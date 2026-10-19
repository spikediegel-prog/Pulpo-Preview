import json
import unittest
from unittest.mock import patch

from pulpo.activity_model import SessionActivity


class ActivityModelTests(unittest.TestCase):
    def test_bounds_review_retention_and_safe_export(self):
        model = SessionActivity()
        event = model.add("token=PRIVATE /private/file\x1b" + "x" * 9000, action="benchmark", outcome="Failed", severity="Error")
        self.assertEqual(8191, len(event.detail))
        self.assertNotIn("\x1b", event.detail)
        self.assertNotIn("PRIVATE", json.dumps(event.public()))
        self.assertNotIn("detail", event.public())
        self.assertEqual((event,), model.select(attention=True))
        model.review(event.sequence)
        self.assertFalse(model.select(attention=True))
        self.assertEqual("Failed", event.outcome)
        for _ in range(600): model.add("local")
        self.assertEqual(500, len(model.events))
        self.assertEqual(101, model.dropped)
        self.assertFalse(model.reviewed)

    def test_search_filters_timestamp_order_and_invalid_metadata(self):
        model = SessionActivity()
        with patch("pulpo.activity_model.time.time_ns", return_value=10):
            first = model.add("fixture cancelled", category="System", action="benchmark", outcome="Cancelled")
        with patch("pulpo.activity_model.time.time_ns", return_value=20):
            second = model.add("fixture failed", category="Evidence", action="source", outcome="Failed", severity="Warning")
        self.assertEqual((second, first), model.select(search="FIXTURE"))
        self.assertEqual((second,), model.select(category="Evidence", outcome="Failed", severity="Warning", since_ns=15))
        self.assertFalse(model.select(category="AI"))
        for key, value in (("category", "execute"), ("action", "grant"), ("outcome", "Verified"), ("severity", "trusted")):
            with self.assertRaises(ValueError): model.add("bad", **{key: value})
        with self.assertRaises(ValueError): model.add({"token": "PRIVATE"})
        self.assertEqual(2, model.sequence)

    def test_histogram_counts_retained_samples_only_without_future_events(self):
        model = SessionActivity()
        minute = 60_000_000_000
        for stamp, severity in ((10 * minute, "Info"), (11 * minute, "Warning"), (20 * minute, "Error")):
            with patch("pulpo.activity_model.time.time_ns", return_value=stamp):
                model.add("local", severity=severity)
        bins = model.histogram(11 * minute)
        self.assertEqual(1, bins[-2]["Info"])
        self.assertEqual(1, bins[-1]["Warning"])
        self.assertEqual(0, sum(row["Error"] for row in bins))


if __name__ == "__main__":
    unittest.main()
