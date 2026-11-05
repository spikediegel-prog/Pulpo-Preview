import unittest
from dataclasses import replace
import json
import math
from pathlib import Path
import tempfile
import time

from pulpo.sextant_observation import (
    SCHEMA,
    SYNTHETIC_SCENARIO_SCHEMA,
    SextantCalibration,
    SextantEvent,
    SextantObservation,
    SextantReplayGuard,
    SextantSyntheticScenario,
    freshness,
    load_sextant_observation,
    load_sextant_synthetic_scenario,
    replay,
)


class SextantReplayTests(unittest.TestCase):
    def setUp(self):
        self.calibration = SextantCalibration(
            calibration_id="cal-v1",
            version="1",
            workload_id="fixture-workload",
            metric_id="latency-ms",
            baseline_workload_version="workload-1",
            baseline_model_version="model-1",
            baseline_sample_count=100,
            baseline_mean=10.0,
            baseline_stddev=1.0,
            investigate_z_threshold=2.0,
            checkpoint_ref="fixture-checkpoint",
            evidence_ref="a" * 64,
        )
        self.events = tuple(
            SextantEvent(
                sequence=index,
                timestamp_ns=index * 1_000_000_000,
                workload_id="fixture-workload",
                workload_version="workload-2",
                model_version="model-2",
                metric_id="latency-ms",
                metric_value=value,
                checkpoint_ref="fixture-checkpoint",
                evidence_ref=hex(index)[2:].rjust(64, "0"),
                reviewed_correct=reviewed,
            )
            for index, value, reviewed in (
                (1, 13.0, True),
                (2, 13.0, True),
                (3, 13.0, False),
                (4, 13.0, None),
            )
        )

    def observation(self, events=None):
        rows = self.events if events is None else tuple(events)
        return SextantObservation(
            source_id="b" * 32,
            observed_at_ns=time.time_ns(),
            first_sequence=rows[0].sequence if rows else 1,
            event_count=len(rows),
            calibration=self.calibration,
            events=rows,
        )

    def test_controlled_drift_is_an_investigate_signal_with_counts_and_uncertainty(self):
        result = replay(self.observation())
        self.assertEqual("Investigate", result.drift.status)
        self.assertEqual(4, result.drift.sample_count)
        self.assertEqual(100, result.drift.baseline_sample_count)
        self.assertEqual(13.0, result.drift.observed_mean)
        self.assertAlmostEqual(0.1, result.drift.standard_error)
        self.assertAlmostEqual(30.0, result.drift.standardized_delta)
        self.assertEqual("cal-v1", result.drift.calibration_id)
        self.assertEqual("1", result.drift.calibration_version)
        self.assertEqual("workload-1", result.drift.baseline_workload_version)
        self.assertEqual("model-1", result.drift.baseline_model_version)
        self.assertEqual("workload-2", result.drift.workload_version)
        self.assertEqual("model-2", result.drift.model_version)
        self.assertEqual(5, len(result.checkpoint_refs))
        self.assertEqual(5, len(result.evidence_refs))
        self.assertEqual(3, result.accuracy.reviewed_sample_count)
        self.assertEqual(2, result.accuracy.correct_count)
        self.assertAlmostEqual(2 / 3, result.accuracy.accuracy)
        self.assertLess(result.accuracy.wilson_95_low, result.accuracy.accuracy)
        self.assertGreater(result.accuracy.wilson_95_high, result.accuracy.accuracy)
        self.assertEqual("Recorded", result.accuracy.classification)
        self.assertEqual("Recorded", result.drift.classification)
        self.assertEqual("recent source timestamp", result.freshness)

    def test_baseline_like_samples_stay_below_investigate_threshold(self):
        baseline_like = tuple(
            replace(event, metric_value=value)
            for event, value in zip(self.events, (10.0, 10.1, 9.9, 10.0))
        )
        result = replay(self.observation(baseline_like))
        self.assertEqual("Below investigate threshold", result.drift.status)
        self.assertAlmostEqual(10.0, result.drift.observed_mean)
        self.assertLess(abs(result.drift.standardized_delta), result.drift.investigate_z_threshold)

    def test_missing_and_reordered_events_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "sequence_gap_or_reordering"):
            self.observation((self.events[0], self.events[2], self.events[3]))
        with self.assertRaisesRegex(ValueError, "sequence_gap_or_reordering"):
            self.observation((self.events[1], self.events[0], self.events[2], self.events[3]))
        with self.assertRaisesRegex(ValueError, "invalid_event_batch"):
            replace(self.observation(), event_count=3)

    def test_reordered_timestamps_and_corrupted_reference_are_rejected(self):
        reordered = (self.events[0], replace(self.events[1], timestamp_ns=0), *self.events[2:])
        with self.assertRaisesRegex(ValueError, "event_timestamp_reordered"):
            self.observation(reordered)
        with self.assertRaisesRegex(ValueError, "invalid_event_evidence_ref"):
            replace(self.events[0], evidence_ref="z" * 64)
        with self.assertRaisesRegex(ValueError, "invalid_metric_value"):
            replace(self.events[0], metric_value=float("nan"))
        with self.assertRaisesRegex(ValueError, "invalid_metric_value"):
            replace(self.events[0], metric_value=10**1000)

    def test_unreviewed_outcomes_are_excluded_and_small_batches_stay_unknown(self):
        one_reviewed = tuple(replace(event, reviewed_correct=None) for event in self.events)
        result = replay(self.observation(one_reviewed))
        self.assertEqual(0, result.accuracy.reviewed_sample_count)
        self.assertIsNone(result.accuracy.accuracy)
        self.assertEqual("Investigate", result.drift.status)
        one_event = replay(self.observation(self.events[:1]))
        self.assertEqual("Unknown", one_event.drift.status)
        self.assertEqual(1, one_event.drift.sample_count)
        self.assertIsNone(one_event.drift.standard_error)

    def test_zero_uncertainty_does_not_divide_or_claim_a_drift_score(self):
        calibration = replace(self.calibration, baseline_stddev=0.0, baseline_mean=13.0)
        events = tuple(replace(event, metric_value=13.0) for event in self.events)
        observation = replace(self.observation(events), calibration=calibration)
        result = replay(observation)
        self.assertEqual("Unknown", result.drift.status)
        self.assertEqual(0.0, result.drift.standard_error)
        self.assertIsNone(result.drift.standardized_delta)

    def test_large_finite_measurements_keep_finite_drift_outputs(self):
        calibration = replace(self.calibration, baseline_mean=-1e100, baseline_stddev=1e100)
        events = tuple(replace(event, metric_value=1e100) for event in self.events)
        observation = replace(self.observation(events), calibration=calibration)
        result = replay(observation)
        self.assertEqual("Investigate", result.drift.status)
        self.assertTrue(math.isfinite(result.drift.standard_error))
        self.assertTrue(math.isfinite(result.drift.standardized_delta))

    def test_versioned_document_parser_is_strict_and_keeps_transport_out_of_contract(self):
        from dataclasses import asdict

        observation = self.observation()
        document = {
            "schema": SCHEMA,
            "source_id": observation.source_id,
            "observed_at_ns": observation.observed_at_ns,
            "first_sequence": observation.first_sequence,
            "event_count": observation.event_count,
            "calibration": asdict(self.calibration),
            "events": [asdict(event) for event in self.events],
        }
        self.assertEqual(observation, SextantObservation.from_dict(document))
        with self.assertRaisesRegex(ValueError, "fields_invalid"):
            SextantObservation.from_dict({**document, "p3_verified": True})
        with self.assertRaisesRegex(ValueError, "unsupported_sextant_schema"):
            SextantObservation.from_dict({**document, "schema": "pulpo.sextant-observation.v0"})

    def test_stale_and_future_source_timestamps_are_distinguished(self):
        observation = self.observation()
        self.assertEqual("recent source timestamp", freshness(observation, observation.observed_at_ns))
        self.assertEqual("stale", freshness(observation, observation.observed_at_ns + 30_000_000_001))
        self.assertEqual("clock mismatch", freshness(observation, observation.observed_at_ns - 5_000_000_001))
        self.assertEqual("stale", replay(replace(
            observation, observed_at_ns=observation.observed_at_ns - 30_000_000_001
        )).freshness)

    def test_replay_guard_rejects_repeated_overlapping_and_gapped_batches(self):
        guard = SextantReplayGuard()
        first = self.observation(self.events[:2])
        guard.accept(first)
        with self.assertRaisesRegex(ValueError, "replay_or_overlap"):
            guard.accept(first)
        overlapping = replace(
            self.observation(self.events[1:3]),
            first_sequence=2,
            event_count=2,
        )
        with self.assertRaisesRegex(ValueError, "replay_or_overlap"):
            guard.accept(overlapping)
        gap = replace(
            self.observation(tuple(replace(event, sequence=event.sequence + 2)
                                   for event in self.events[2:])),
        )
        with self.assertRaisesRegex(ValueError, "sequence_gap"):
            guard.accept(gap)
        guard.reset()
        self.assertTrue(guard.accept(first))

    def test_protected_reader_rejects_bad_file_and_documents_valid_field_substitution_limit(self):
        from dataclasses import asdict

        observation = self.observation()
        document = {
            "schema": SCHEMA,
            "source_id": observation.source_id,
            "observed_at_ns": observation.observed_at_ns,
            "first_sequence": observation.first_sequence,
            "event_count": observation.event_count,
            "calibration": asdict(self.calibration),
            "events": [asdict(event) for event in observation.events],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sextant.json"
            path.write_text(json.dumps(document))
            path.chmod(0o600)
            self.assertEqual(observation, load_sextant_observation(path))
            path.write_text("{malformed")
            with self.assertRaises(ValueError):
                load_sextant_observation(path)
            path.write_text(json.dumps(document) + (" " * 16_384))
            with self.assertRaises(ValueError):
                load_sextant_observation(path)
            duplicate_key_document = json.dumps(document)[:-1] + ',"schema":"pulpo.sextant-observation.v1"}'
            path.write_text(duplicate_key_document)
            with self.assertRaises(ValueError):
                load_sextant_observation(path)
            substituted = {**document, "events": [dict(row) for row in document["events"]]}
            substituted["events"][0]["metric_value"] = 9999.0
            path.write_text(json.dumps(substituted))
            # A private transport file and valid shape do not authenticate content.
            self.assertEqual(9999.0, load_sextant_observation(path).events[0].metric_value)


class SyntheticScenarioTests(unittest.TestCase):
    """Synthetic scenario envelopes: loading, strict validation, and replay."""

    def setUp(self):
        # Reuse the replay fixture observation rather than duplicating it.
        replay_tests = SextantReplayTests()
        replay_tests.setUp()
        self.observation = replay_tests.observation()

    def scenario_document(self, observation=None, *, name="Fixture scenario", target=95.0):
        from dataclasses import asdict

        observation = self.observation if observation is None else observation
        return {
            "schema": SYNTHETIC_SCENARIO_SCHEMA,
            "scenario_name": name,
            "accuracy_target_percent": target,
            "observation": {
                "schema": SCHEMA,
                "source_id": observation.source_id,
                "observed_at_ns": observation.observed_at_ns,
                "first_sequence": observation.first_sequence,
                "event_count": observation.event_count,
                "calibration": asdict(observation.calibration),
                "events": [asdict(event) for event in observation.events],
            },
        }

    def observation_document(self, observation=None):
        return self.scenario_document(observation)["observation"]

    def write_document(self, directory, document, name="scenario.json"):
        path = Path(directory) / name
        path.write_text(json.dumps(document))
        path.chmod(0o600)
        return path

    def test_valid_synthetic_envelope_loads_with_name_target_and_replayable_observation(self):
        document = self.scenario_document()
        scenario = SextantSyntheticScenario.from_dict(document)
        self.assertEqual("Fixture scenario", scenario.name)
        self.assertEqual(95.0, scenario.accuracy_target_percent)
        self.assertEqual(self.observation, scenario.observation)
        result = replay(scenario.observation)
        self.assertEqual(3, result.accuracy.reviewed_sample_count)
        self.assertEqual(2, result.accuracy.correct_count)
        self.assertAlmostEqual(2 / 3, result.accuracy.accuracy)
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_document(directory, document)
            loaded = load_sextant_synthetic_scenario(path)
            self.assertEqual(scenario, loaded)
            self.assertEqual(95.0, loaded.accuracy_target_percent)

    def test_ordinary_observation_file_returns_none(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_document(
                directory, self.observation_document(), name="observation.json"
            )
            self.assertIsNone(load_sextant_synthetic_scenario(path))
            self.assertEqual(self.observation, load_sextant_observation(path))

    def test_synthetic_envelope_with_invalid_fields_is_rejected(self):
        document = self.scenario_document()
        del document["scenario_name"]
        with self.assertRaisesRegex(
            ValueError, "sextant_synthetic_scenario_fields_invalid"
        ):
            SextantSyntheticScenario.from_dict(document)
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_document(directory, document)
            with self.assertRaisesRegex(
                ValueError, "sextant_synthetic_scenario_fields_invalid"
            ):
                load_sextant_synthetic_scenario(path)

    def test_synthetic_envelope_with_wrong_schema_is_rejected(self):
        document = self.scenario_document()
        document["schema"] = "pulpo.sextant-synthetic-scenario.v0"
        with self.assertRaisesRegex(
            ValueError, "unsupported_sextant_synthetic_scenario_schema"
        ):
            SextantSyntheticScenario.from_dict(document)

    def test_accuracy_target_above_100_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid_accuracy_target_percent"):
            SextantSyntheticScenario.from_dict(self.scenario_document(target=100.5))
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_document(directory, self.scenario_document(target=101))
            with self.assertRaisesRegex(ValueError, "invalid_accuracy_target_percent"):
                load_sextant_synthetic_scenario(path)

    def test_negative_accuracy_target_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid_accuracy_target_percent"):
            SextantSyntheticScenario.from_dict(self.scenario_document(target=-1))


if __name__ == "__main__":
    unittest.main()
