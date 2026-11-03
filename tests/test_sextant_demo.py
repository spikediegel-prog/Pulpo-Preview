import unittest
import time

from pulpo.sextant_demo import build_synthetic_observation
from pulpo.sextant_observation import replay


class SyntheticSextantDemoTests(unittest.TestCase):
    def test_scenario_is_bounded_and_produces_an_investigation_signal(self):
        now_ns = time.time_ns()
        observation = build_synthetic_observation(now_ns)
        result = replay(observation)

        self.assertEqual("synthetic-inference-scenario", observation.calibration.workload_id)
        self.assertEqual(10, observation.event_count)
        self.assertEqual(now_ns, observation.observed_at_ns)
        self.assertEqual("Investigate", result.drift.status)
        self.assertEqual(8, result.accuracy.reviewed_sample_count)
        self.assertEqual(6, result.accuracy.correct_count)
        self.assertEqual("recent source timestamp", result.freshness)
        self.assertTrue(all(event.evidence_ref for event in observation.events))

    def test_invalid_demo_time_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid_synthetic_demo_time"):
            build_synthetic_observation(1)


if __name__ == "__main__":
    unittest.main()
