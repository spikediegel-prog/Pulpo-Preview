"""Capability-free evidence telemetry contract and bounded rate history.

Evidence-state vocabulary (v9.1 review section 6a): AUTHORIZED / ATTEMPTED /
CONSEQUENCE UNKNOWN is one vocabulary across the kernel decision outcomes,
the custody attempt lifecycle, and the canonical audit chain -- not three
separate names for the same states.

    AUTHORIZED          -> outcome "allowed"
                           Kernel Decision("allow", ...) and the permit it
                           issues; audit event "permit_consumed".
    ATTEMPTED           -> outcome "attempted"
                           An authorized attempt is in flight. Custody
                           lifecycle states (pulpo/custody.py):
                           attempt_authorized, attempt_claimed,
                           request_transmitted, reconciliation_required;
                           audit event "reconciliation_required".
    CONSEQUENCE UNKNOWN -> outcome "unknown"
                           The consequence of an attempt is not yet
                           verified. Custody UNRESOLVED ("unresolved"),
                           effect-reconcile "uncertain"
                           (pulpo/effect_reconcile.py), and
                           ExternalConsequenceUnknown
                           (pulpo/custody_executor.py); audit event
                           "unresolved".

STATE_OUTCOMES maps each name the custody and effect-reconciliation layers
already use onto the one canonical outcome, so the projection in
pulpo/evidence_export.py and any later emitter agree on what a name means.
"unknown" is a terminal recorded state, never a synonym for success or
failure: projection preserves it, and only a later, separately recorded
event may supersede it. A reconciled terminal state ("reconciled_success" /
"reconciled_failure") is deliberately NOT mapped: reconciliation resolves
an unknown, it does not rewrite it, and "allowed" means authorized, not
succeeded.
"""
from collections import deque
from dataclasses import dataclass, fields
import time


MAX_COUNTER = 2**63 - 1
COUNTERS = ("reads", "writes", "commits", "rollbacks", "errors", "database_bytes", "wal_bytes",
            "volume_total", "volume_free", "allowed", "denied", "approval_required", "permit_consumed",
            "permit_rejected", "approval_rejected", "approval_expired", "approval_replayed")
EVENT_NAMES = {"decision", "approval_verified", "approval_rejected", "permit_consumed", "permit_rejected",
               "directive_activated", "directive_revoked", "reconciliation_required", "unresolved", "other"}
OUTCOMES = {"allowed", "denied", "blocked_by_policy", "approval_required", "rejected", "recorded",
            "attempted", "unknown"}
# Custody attempt-lifecycle and effect-reconciliation state names mapped onto
# the canonical evidence outcomes above. Keys are the exact strings already
# used by pulpo/custody.py (ATTEMPT_*, RECONCILIATION_REQUIRED, UNRESOLVED)
# and pulpo/effect_reconcile.py ("uncertain"); "reconciliation_required" and
# "unresolved" double as audit event names, which is how the projection in
# pulpo/evidence_export.py carries them into EvidenceEvent outcomes.
STATE_OUTCOMES = {"attempt_authorized": "attempted",
                  "attempt_claimed": "attempted",
                  "request_transmitted": "attempted",
                  "reconciliation_required": "attempted",
                  "unresolved": "unknown",
                  "uncertain": "unknown"}


def number(value, optional=True):
    return (optional and value is None) or (type(value) is int and 0 <= value <= MAX_COUNTER)


@dataclass(frozen=True, slots=True)
class AIUsage:
    provider: str = "Unknown"
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_microusd: int | None = None
    scope: str = "unavailable"

    def __post_init__(self):
        if (self.provider not in {"Unknown", "Ollama", "OpenAI", "Other"}
                or self.scope not in {"unavailable", "latest_completed_request"}
                or any(not number(getattr(self, key)) for key in ("input_tokens", "output_tokens", "cost_microusd"))):
            raise ValueError("invalid_ai_usage")


@dataclass(frozen=True, slots=True)
class EvidenceEvent:
    timestamp_ns: int
    event: str
    outcome: str
    record_hash: str

    def __post_init__(self):
        if (not number(self.timestamp_ns, False) or self.event not in EVENT_NAMES or self.outcome not in OUTCOMES
                or type(self.record_hash) is not str or len(self.record_hash) != 64
                or any(c not in "0123456789abcdef" for c in self.record_hash)):
            raise ValueError("invalid_event")


@dataclass(frozen=True, slots=True)
class EvidenceObservation:
    source_id: str
    observed_at_ns: int
    audit_valid: bool
    audit_records: int
    health: str = "not_checked"
    reads: int | None = None
    writes: int | None = None
    commits: int | None = None
    rollbacks: int | None = None
    errors: int | None = None
    database_bytes: int | None = None
    wal_bytes: int | None = None
    volume_total: int | None = None
    volume_free: int | None = None
    allowed: int | None = None
    denied: int | None = None
    approval_required: int | None = None
    permit_consumed: int | None = None
    permit_rejected: int | None = None
    approval_rejected: int | None = None
    approval_expired: int | None = None
    approval_replayed: int | None = None
    ai: AIUsage = AIUsage()
    events: tuple[EvidenceEvent, ...] = ()
    schema: str = "pulpo.evidence-observation.v1"

    def __post_init__(self):
        if (self.schema != "pulpo.evidence-observation.v1" or type(self.source_id) is not str
                or len(self.source_id) != 32 or any(c not in "0123456789abcdef" for c in self.source_id)
                or not number(self.observed_at_ns, False) or type(self.audit_valid) is not bool
                or not number(self.audit_records, False) or self.health not in {"ok", "failed", "not_checked", "unavailable"}
                or any(not number(getattr(self, key)) for key in COUNTERS)
                or type(self.ai) is not AIUsage or type(self.events) is not tuple or len(self.events) > 24
                or any(type(event) is not EvidenceEvent for event in self.events)
                or self.audit_records < len(self.events)):
            raise ValueError("invalid_evidence_observation")
        if (self.volume_total is None) != (self.volume_free is None):
            raise ValueError("incomplete_capacity")
        if self.volume_total is not None and (self.volume_total == 0 or self.volume_free > self.volume_total):
            raise ValueError("invalid_capacity")


def load_observation(path):
    from .mcp_plugin import read_snapshot_document
    value = read_snapshot_document(path)
    if set(value) != {f.name for f in fields(EvidenceObservation)}:
        raise ValueError("snapshot_fields_invalid")
    if (type(value["ai"]) is not dict or set(value["ai"]) != {f.name for f in fields(AIUsage)}
            or type(value["events"]) is not list or len(value["events"]) > 24
            or any(type(event) is not dict or set(event) != {f.name for f in fields(EvidenceEvent)} for event in value["events"])):
        raise ValueError("snapshot_nested_invalid")
    value["ai"] = AIUsage(**value["ai"])
    value["events"] = tuple(EvidenceEvent(**event) for event in value["events"])
    return EvidenceObservation(**value)


def freshness(snapshot, now_ns=None):
    age = ((time.time_ns() if now_ns is None else now_ns) - snapshot.observed_at_ns) / 1e9
    return "clock mismatch" if age < -5 else "stale" if age > 15 else "recent source timestamp"


class ActivityHistory:
    def __init__(self):
        self.points = deque(maxlen=1801)
        self.previous = None

    def clear(self):
        self.points.clear()
        self.previous = None

    def add(self, snapshot):
        previous = self.previous
        if previous and snapshot.source_id == previous.source_id and snapshot.observed_at_ns == previous.observed_at_ns:
            # A changed payload at the same sample identity is not new activity.
            if snapshot != previous:
                raise ValueError("sample_identity_changed")
            return False
        if previous and snapshot.source_id != previous.source_id:
            self.clear()
            previous = None
        rates = {key: None for key in ("reads", "writes", "commits")}
        delta = (snapshot.observed_at_ns - previous.observed_at_ns) / 1e9 if previous else 0
        if previous and delta <= 0:
            raise ValueError("snapshot_replayed")
        if previous and 0 < delta <= 15:
            for key in rates:
                new, old = getattr(snapshot, key), getattr(previous, key)
                if new is not None and old is not None and new >= old:
                    rates[key] = (new - old) / delta
        self.points.append((snapshot.observed_at_ns / 1e9, rates))
        self.previous = snapshot
        return True
