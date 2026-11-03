"""Explicitly synthetic Sextant inputs for local UI demonstrations."""
import hashlib
import time

from .sextant_observation import (
    SextantCalibration,
    SextantEvent,
    SextantObservation,
)


_DAY_NS = 24 * 60 * 60 * 1_000_000_000
_SAMPLES = (
    (29, 98.0, True),
    (22, 101.0, True),
    (15, 99.0, False),
    (9, 102.0, True),
    (6, 100.0, None),
    (3, 138.0, True),
    (1, 145.0, False),
    (0.5, 141.0, True),
    (0.25, 147.0, None),
    (0.04, 143.0, True),
)


def build_synthetic_observation(now_ns=None):
    """Build a bounded demonstration scenario without executing or persisting work."""
    now = time.time_ns() if now_ns is None else now_ns
    if type(now) is not int or now < 30 * _DAY_NS:
        raise ValueError("invalid_synthetic_demo_time")

    calibration = SextantCalibration(
        calibration_id="synthetic-demo-calibration",
        version="1",
        workload_id="synthetic-inference-scenario",
        metric_id="latency-ms",
        baseline_workload_version="synthetic-baseline-v1",
        baseline_model_version="synthetic-model-v1",
        baseline_sample_count=100,
        baseline_mean=100.0,
        baseline_stddev=8.0,
        investigate_z_threshold=2.0,
        checkpoint_ref="synthetic-demo-checkpoint",
        evidence_ref=hashlib.sha256(b"pulpo-sextant-synthetic-demo-calibration").hexdigest(),
    )
    events = tuple(
        SextantEvent(
            sequence=index,
            timestamp_ns=now - int(days_ago * _DAY_NS),
            workload_id=calibration.workload_id,
            workload_version="synthetic-workload-v2",
            model_version="synthetic-model-v2",
            metric_id=calibration.metric_id,
            metric_value=value,
            checkpoint_ref="synthetic-demo-checkpoint",
            evidence_ref=hashlib.sha256(
                f"pulpo-sextant-synthetic-demo-event-{index}".encode("ascii")
            ).hexdigest(),
            reviewed_correct=reviewed_correct,
        )
        for index, (days_ago, value, reviewed_correct) in enumerate(_SAMPLES, 1)
    )
    return SextantObservation(
        source_id="e" * 32,
        observed_at_ns=now,
        first_sequence=1,
        event_count=len(events),
        calibration=calibration,
        events=events,
    )
