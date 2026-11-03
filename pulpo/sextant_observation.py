"""Offline, read-only Sextant workload event contract and bounded replay."""
from dataclasses import dataclass
import math
from statistics import fmean, variance
import time


SCHEMA = "pulpo.sextant-observation.v1"
MAX_EVENTS = 16
MAX_METRIC_MAGNITUDE = 1e100
MAX_SEQUENCE = 2**63 - 1
MAX_FRESH_AGE_NS = 30_000_000_000
MAX_FUTURE_SKEW_NS = 5_000_000_000
_HEX = frozenset("0123456789abcdef")


def _text(value, maximum, field):
    if (type(value) is not str or not value or len(value) > maximum
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise ValueError(f"invalid_{field}")
    return value


def _number(value, field, *, minimum=None):
    if type(value) not in (int, float):
        raise ValueError(f"invalid_{field}")
    try:
        result = float(value)
    except OverflowError as exc:
        raise ValueError(f"invalid_{field}") from exc
    if not math.isfinite(result) or abs(result) > MAX_METRIC_MAGNITUDE:
        raise ValueError(f"invalid_{field}")
    if minimum is not None and result < minimum:
        raise ValueError(f"invalid_{field}")
    return result


def _reference(value, field):
    if (type(value) is not str or len(value) != 64
            or any(char not in _HEX for char in value)):
        raise ValueError(f"invalid_{field}")
    return value


@dataclass(frozen=True, slots=True)
class SextantCalibration:
    calibration_id: str
    version: str
    workload_id: str
    metric_id: str
    baseline_workload_version: str
    baseline_model_version: str
    baseline_sample_count: int
    baseline_mean: float
    baseline_stddev: float
    investigate_z_threshold: float
    checkpoint_ref: str
    evidence_ref: str

    def __post_init__(self):
        for field in ("calibration_id", "version", "workload_id", "metric_id",
                      "baseline_workload_version", "baseline_model_version"):
            _text(getattr(self, field), 128, field)
        if (type(self.baseline_sample_count) is not int or self.baseline_sample_count < 2
                or self.baseline_sample_count > MAX_SEQUENCE):
            raise ValueError("invalid_baseline_sample_count")
        _number(self.baseline_mean, "baseline_mean")
        _number(self.baseline_stddev, "baseline_stddev", minimum=0)
        _number(self.investigate_z_threshold, "investigate_z_threshold", minimum=0)
        if self.investigate_z_threshold == 0:
            raise ValueError("invalid_investigate_z_threshold")
        _text(self.checkpoint_ref, 128, "checkpoint_ref")
        _reference(self.evidence_ref, "calibration_evidence_ref")


@dataclass(frozen=True, slots=True)
class SextantEvent:
    sequence: int
    timestamp_ns: int
    workload_id: str
    workload_version: str
    model_version: str
    metric_id: str
    metric_value: float
    checkpoint_ref: str
    evidence_ref: str
    reviewed_correct: bool | None = None

    def __post_init__(self):
        if type(self.sequence) is not int or not 1 <= self.sequence <= MAX_SEQUENCE:
            raise ValueError("invalid_event_sequence")
        if type(self.timestamp_ns) is not int or not 0 <= self.timestamp_ns <= MAX_SEQUENCE:
            raise ValueError("invalid_event_timestamp")
        for field in ("workload_id", "workload_version", "model_version", "metric_id"):
            _text(getattr(self, field), 128, field)
        _number(self.metric_value, "metric_value")
        _text(self.checkpoint_ref, 128, "checkpoint_ref")
        _reference(self.evidence_ref, "event_evidence_ref")
        if self.reviewed_correct is not None and type(self.reviewed_correct) is not bool:
            raise ValueError("invalid_reviewed_outcome")


@dataclass(frozen=True, slots=True)
class SextantObservation:
    source_id: str
    observed_at_ns: int
    first_sequence: int
    event_count: int
    calibration: SextantCalibration
    events: tuple[SextantEvent, ...]
    schema: str = SCHEMA

    def __post_init__(self):
        if self.schema != SCHEMA:
            raise ValueError("unsupported_sextant_schema")
        if (type(self.source_id) is not str or len(self.source_id) != 32
                or any(char not in _HEX for char in self.source_id)):
            raise ValueError("invalid_source_id")
        if type(self.observed_at_ns) is not int or not 0 <= self.observed_at_ns <= MAX_SEQUENCE:
            raise ValueError("invalid_observed_at")
        if type(self.first_sequence) is not int or not 1 <= self.first_sequence <= MAX_SEQUENCE:
            raise ValueError("invalid_first_sequence")
        if type(self.event_count) is not int or not 1 <= self.event_count <= MAX_EVENTS:
            raise ValueError("invalid_event_count")
        if type(self.calibration) is not SextantCalibration:
            raise ValueError("invalid_calibration")
        if type(self.events) is not tuple or len(self.events) != self.event_count:
            raise ValueError("invalid_event_batch")
        if self.events and self.first_sequence + len(self.events) - 1 > MAX_SEQUENCE:
            raise ValueError("invalid_event_batch_range")
        previous_timestamp = -1
        for index, event in enumerate(self.events):
            if type(event) is not SextantEvent:
                raise ValueError("invalid_event")
            if event.sequence != self.first_sequence + index:
                raise ValueError("event_sequence_gap_or_reordering")
            if event.timestamp_ns < previous_timestamp:
                raise ValueError("event_timestamp_reordered")
            if (event.workload_id != self.calibration.workload_id
                    or event.metric_id != self.calibration.metric_id):
                raise ValueError("event_calibration_scope_mismatch")
            previous_timestamp = event.timestamp_ns
        cohort = {(event.workload_version, event.model_version) for event in self.events}
        if len(cohort) > 1:
            raise ValueError("mixed_event_cohort")

    @classmethod
    def from_dict(cls, value):
        fields = {"schema", "source_id", "observed_at_ns", "first_sequence", "event_count",
                  "calibration", "events"}
        calibration_fields = {field for field in SextantCalibration.__dataclass_fields__}
        event_fields = {field for field in SextantEvent.__dataclass_fields__}
        if type(value) is not dict or set(value) != fields:
            raise ValueError("sextant_observation_fields_invalid")
        calibration = value["calibration"]
        events = value["events"]
        if type(calibration) is not dict or set(calibration) != calibration_fields:
            raise ValueError("sextant_calibration_fields_invalid")
        if type(events) is not list or len(events) > MAX_EVENTS:
            raise ValueError("sextant_events_invalid")
        if any(type(event) is not dict or set(event) != event_fields for event in events):
            raise ValueError("sextant_event_fields_invalid")
        return cls(
            source_id=value["source_id"],
            observed_at_ns=value["observed_at_ns"],
            first_sequence=value["first_sequence"],
            event_count=value["event_count"],
            calibration=SextantCalibration(**calibration),
            events=tuple(SextantEvent(**event) for event in events),
            schema=value["schema"],
        )


def load_sextant_observation(path):
    """Read a private frozen contract document without adding a source/transport."""
    from .mcp_plugin import read_snapshot_document

    return SextantObservation.from_dict(read_snapshot_document(path))


@dataclass(frozen=True, slots=True)
class AccuracyAssessment:
    reviewed_sample_count: int
    correct_count: int
    accuracy: float | None
    wilson_95_low: float | None
    wilson_95_high: float | None
    classification: str = "Recorded"


@dataclass(frozen=True, slots=True)
class DriftAssessment:
    status: str
    sample_count: int
    baseline_sample_count: int
    observed_mean: float | None
    baseline_mean: float
    standard_error: float | None
    standardized_delta: float | None
    investigate_z_threshold: float
    baseline_workload_version: str
    baseline_model_version: str
    workload_version: str | None
    model_version: str | None
    calibration_id: str
    calibration_version: str
    classification: str = "Recorded"


@dataclass(frozen=True, slots=True)
class SextantReplay:
    accuracy: AccuracyAssessment
    drift: DriftAssessment
    freshness: str
    first_sequence: int
    last_sequence: int | None
    checkpoint_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]


def _accuracy(events):
    outcomes = [event.reviewed_correct for event in events if event.reviewed_correct is not None]
    count = len(outcomes)
    correct = sum(outcomes)
    if not count:
        return AccuracyAssessment(0, 0, None, None, None)
    estimate = correct / count
    z = 1.959963984540054
    denominator = 1 + z * z / count
    center = (estimate + z * z / (2 * count)) / denominator
    margin = z * math.sqrt(estimate * (1 - estimate) / count + z * z / (4 * count * count)) / denominator
    return AccuracyAssessment(count, correct, estimate, max(0.0, center - margin), min(1.0, center + margin))


def replay(observation):
    """Summarize one validated batch; results are reported signals, never proof."""
    if type(observation) is not SextantObservation:
        raise TypeError("SextantObservation required")
    calibration = observation.calibration
    events = observation.events
    cohort = next(iter(events), None)
    if len(events) < 2:
        drift = DriftAssessment(
            "Unknown", len(events), calibration.baseline_sample_count,
            fmean(event.metric_value for event in events) if events else None,
            calibration.baseline_mean, None, None, calibration.investigate_z_threshold,
            calibration.baseline_workload_version, calibration.baseline_model_version,
            cohort.workload_version if cohort else None, cohort.model_version if cohort else None,
            calibration.calibration_id, calibration.version,
        )
    else:
        values = [event.metric_value for event in events]
        observed_mean = fmean(values)
        observed_variance = variance(values)
        standard_error = math.sqrt(
            calibration.baseline_stddev ** 2 / calibration.baseline_sample_count
            + observed_variance / len(values)
        )
        if standard_error == 0 or not math.isfinite(standard_error):
            standardized_delta = None
            status = "Unknown"
            if not math.isfinite(standard_error):
                standard_error = None
        else:
            standardized_delta = (observed_mean - calibration.baseline_mean) / standard_error
            if not math.isfinite(standardized_delta):
                standardized_delta = None
                status = "Unknown"
            else:
                status = ("Investigate" if abs(standardized_delta) >= calibration.investigate_z_threshold
                          else "Below investigate threshold")
        drift = DriftAssessment(
            status, len(values), calibration.baseline_sample_count, observed_mean,
            calibration.baseline_mean, standard_error, standardized_delta,
            calibration.investigate_z_threshold,
            calibration.baseline_workload_version, calibration.baseline_model_version,
            cohort.workload_version, cohort.model_version,
            calibration.calibration_id, calibration.version,
        )
    return SextantReplay(
        accuracy=_accuracy(events),
        drift=drift,
        freshness=freshness(observation),
        first_sequence=observation.first_sequence,
        last_sequence=events[-1].sequence if events else None,
        checkpoint_refs=(calibration.checkpoint_ref, *(event.checkpoint_ref for event in events)),
        evidence_refs=(calibration.evidence_ref, *(event.evidence_ref for event in events)),
    )


def freshness(observation, now_ns=None):
    """Classify producer-supplied snapshot time; it does not authenticate it."""
    if type(observation) is not SextantObservation:
        raise TypeError("SextantObservation required")
    now = time.time_ns() if now_ns is None else now_ns
    if type(now) is not int or now < 0:
        raise ValueError("invalid_current_time")
    age = now - observation.observed_at_ns
    if age < -MAX_FUTURE_SKEW_NS:
        return "clock mismatch"
    if age > MAX_FRESH_AGE_NS:
        return "stale"
    return "recent source timestamp"


class SextantReplayGuard:
    """Ephemeral cursor against duplicate/overlapping batches in one view."""
    def __init__(self):
        self.source_id = None
        self.last_sequence = None

    def reset(self):
        self.source_id = None
        self.last_sequence = None

    def accept(self, observation):
        if type(observation) is not SextantObservation:
            raise TypeError("SextantObservation required")
        last_sequence = observation.first_sequence + observation.event_count - 1
        if self.source_id is None:
            self.source_id = observation.source_id
        elif observation.source_id != self.source_id:
            raise ValueError("sextant_source_changed")
        if self.last_sequence is not None:
            if observation.first_sequence <= self.last_sequence:
                raise ValueError("sextant_replay_or_overlap")
            if observation.first_sequence != self.last_sequence + 1:
                raise ValueError("sextant_sequence_gap")
        self.last_sequence = last_sequence
        return True
