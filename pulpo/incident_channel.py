"""Incident-reporting + near-miss channel: a derived, read-only projection.

WIC *Frontier AI Safety and Governance 2026*, indicator 3.2 (risk incident
reporting and near-miss sharing): Pulpo recorded the unknown an incident
report would cite, but had no reporting channel and no near-miss log. This
module is that channel's first half -- the record, derived from outcomes
Pulpo already records. It reports to nobody by itself: there is no external
reporting, no sharing, no notification, no network call here. A human (or a
later, separately governed step) reads the frozen report and decides what
leaves the machine.

Definitions (from the audit's framing):

    Incident  -- a consequential effect that was executed, or may have been
                 executed, whose outcome is unknown or wrong.
    Near-miss -- a governed action refused or caught before any consequential
                 effect, OR an unknown that later resolved cleanly. No effect
                 happened, or the effect is verified fine.

Both are derived, read-only projections of the canonical audit chain and the
custody store. An incident record also carries a handling lifecycle -- open,
acknowledged, resolved, closed -- recorded as `incident_lifecycle` audit
events, never as a mutation: the current state is derived from the audit
chain, so a reader can replay exactly who did what, when. Near-misses carry
no lifecycle (`not_applicable`): refused before any effect, or an unknown
that resolved cleanly, there is nothing to work. The state machine lives in
docs/incident-channel.md.

Feeds (see docs/incident-channel.md for the full table):

    canonical audit -- purchase_consequence_unknown is an incident until a
        custody record for the same custody_attempt_id resolves it;
        purchase_revalidation_failed, permit_rejected, decision/deny and
        approval_rejected are near-misses (refused before any effect). A
        revalidation refusal consumes its custody attempt (by attempt id,
        else by order hash), so a refusal yields exactly one near-miss.
    custody store  -- one record per attempt_id, from the attempt's latest
        state: unresolved / reconciliation_required / attempt_authorized /
        attempt_claimed / request_transmitted are incidents, unresolved;
        reconciled_failure is an incident, confirmed_wrong;
        reconciled_success emits no record by itself -- it is a resolver
        for an earlier unknown.

Custody transitions reach the canonical audit only where an evidence
projector is wired: DomainCommerceExecutor takes one and, when supplied,
projects every transition (SQLiteCustodyEvidenceConvergence.project_all)
into `custody_transition` audit events; the TrustedDomainExecutor's
projector is only wired in tests. The custody feed therefore still reads
the custody store directly (SQLiteGovernanceCustody.attempts), and the
channel says so on every record via its source field.

Integrity levels -- a record's anchor is only as strong as its source:

    canonical_audit -- anchored by the audit record hash and the hash chain
        (kernel.verify_audit); the report carries audit_valid and derives
        regardless, flagging a broken chain rather than hiding it.
    custody_store  -- anchored by the attempt authorization_hash and the
        HMAC-signed transition receipts; NOT hash-chained to the canonical
        audit. Custody-derived records are never presented as audit-backed.

Custody time -- the custody store records NO per-attempt timestamp.
created_epoch / updated_epoch are head-epoch counters (1, 2, 3, ...), not
seconds, so there is no epoch-to-nanosecond conversion to apply; converting
one would fabricate a time. A custody-sourced record instead carries the
store head's custody_time_ns at freeze time as both first_seen_ns and
last_seen_ns: the time of the store's latest transition, an upper bound on
the attempt's last transition, not the attempt's own time. A merged record
(audit event + custody resolution) keeps the audit timestamp as
first_seen_ns and takes last_seen_ns as the later of the audit timestamp
and the custody head time.

No cap on records: incidents are rare, and silently dropping one would be
worse than a large report.
"""

from dataclasses import dataclass, fields
import hashlib
import os
import time

from .custody import SQLiteGovernanceCustody
from .mcp_boundary import _publish_snapshot
from .orchestrator import PulpoOrchestrator
from .state import SQLiteKernelState

KINDS = frozenset({"incident", "near_miss"})
SOURCES = frozenset({"canonical_audit", "custody_store"})
RESOLUTIONS = frozenset({"unresolved", "resolved_cleanly", "confirmed_wrong", "not_applicable"})
# Handling lifecycle states. `not_applicable` is for near-misses only: a
# record that is already terminal needs no handling state.
LIFECYCLES = frozenset({"open", "acknowledged", "resolved", "closed", "not_applicable"})
LIFECYCLE_EVENT = "incident_lifecycle"
# transition -> {from_state: to_state}. `reopen` is the only way back, from
# resolved or closed to open.
_TRANSITION_TARGETS = {
    "acknowledge": {"open": "acknowledged"},
    "resolve": {"acknowledged": "resolved"},
    "close": {"resolved": "closed"},
    "reopen": {"resolved": "open", "closed": "open"},
}
INCIDENT_SCHEMA = "pulpo.incident-record.v2"
REPORT_SCHEMA = "pulpo.incident-report.v2"

# Audit events that are refusals: caught before any consequential effect.
_AUDIT_NEAR_MISS_EVENTS = frozenset({"purchase_revalidation_failed", "permit_rejected", "approval_rejected"})
# Custody states that emit a record, and the (kind, resolution) each maps to.
# reconciled_success resolves an earlier unknown into a near-miss; it emits
# no record by itself (see _derive_records).
_CUSTODY_OUTCOMES = {
    "unresolved": ("incident", "unresolved"),
    "reconciliation_required": ("incident", "unresolved"),
    "attempt_authorized": ("incident", "unresolved"),
    "attempt_claimed": ("incident", "unresolved"),
    "request_transmitted": ("incident", "unresolved"),
    "reconciled_failure": ("incident", "confirmed_wrong"),
    "reconciled_success": ("near_miss", "resolved_cleanly"),
}
# Payload hash keys carried into anchors, in fixed order. Hashes only, never
# authority material: the permit itself never appears, only its hash, exactly
# as the canonical audit already records it.
_ANCHOR_HASH_KEYS = ("order_hash", "intent_hash", "permit_hash")


def _is_hex(value, length):
    return (type(value) is str and len(value) == length
            and all(character in "0123456789abcdef" for character in value))


def _is_hash(value):
    return _is_hex(value, 64)


def _number(value):
    return type(value) is int and value >= 0


@dataclass(frozen=True, slots=True)
class IncidentRecord:
    record_id: str
    kind: str
    source: str
    source_detail: str
    first_seen_ns: int
    last_seen_ns: int
    anchors: tuple
    reason: str
    resolution: str
    anchor_hash: str
    lifecycle: str
    lifecycle_at_ns: int
    lifecycle_actor: str
    schema: str = INCIDENT_SCHEMA

    def __post_init__(self):
        if (self.schema != INCIDENT_SCHEMA or type(self.record_id) is not str or not self.record_id
                or self.kind not in KINDS or self.source not in SOURCES
                or type(self.source_detail) is not str or not self.source_detail
                or not _number(self.first_seen_ns) or not _number(self.last_seen_ns)
                or self.last_seen_ns < self.first_seen_ns
                or type(self.anchors) is not tuple or not self.anchors
                or any(type(anchor) is not tuple or len(anchor) != 2
                       or type(anchor[0]) is not str or not anchor[0]
                       or not _is_hash(anchor[1]) for anchor in self.anchors)
                or type(self.reason) is not str or not self.reason
                or self.resolution not in RESOLUTIONS or not _is_hash(self.anchor_hash)
                or self.anchor_hash not in {anchor[1] for anchor in self.anchors}
                or (self.record_id.startswith("incident:") != (self.kind == "incident"))
                or (self.record_id.startswith("near-miss:") != (self.kind == "near_miss"))
                or self.lifecycle not in LIFECYCLES
                or (self.lifecycle == "not_applicable") != (self.kind == "near_miss")
                or not _number(self.lifecycle_at_ns)
                or type(self.lifecycle_actor) is not str):
            raise ValueError("invalid_incident_record")


@dataclass(frozen=True, slots=True)
class IncidentReport:
    source_id: str
    observed_at_ns: int
    audit_valid: bool
    audit_records: int
    incidents: int
    near_misses: int
    unresolved: int
    resolved_cleanly: int
    confirmed_wrong: int
    records: tuple
    schema: str = REPORT_SCHEMA

    def __post_init__(self):
        if (self.schema != REPORT_SCHEMA or not _is_hex(self.source_id, 32)
                or not _number(self.observed_at_ns) or type(self.audit_valid) is not bool
                or not _number(self.audit_records)
                or any(not _number(getattr(self, key)) for key in
                       ("incidents", "near_misses", "unresolved", "resolved_cleanly", "confirmed_wrong"))
                or type(self.records) is not tuple
                or any(type(record) is not IncidentRecord for record in self.records)
                or [record.record_id for record in self.records] != [record.record_id for record in sorted(
                    self.records, key=lambda record: (record.first_seen_ns, record.record_id))]
                or self.incidents != sum(1 for record in self.records if record.kind == "incident")
                or self.near_misses != sum(1 for record in self.records if record.kind == "near_miss")
                or self.unresolved != sum(1 for record in self.records if record.resolution == "unresolved")
                or self.resolved_cleanly != sum(1 for record in self.records if record.resolution == "resolved_cleanly")
                or self.confirmed_wrong != sum(1 for record in self.records if record.resolution == "confirmed_wrong")):
            raise ValueError("invalid_incident_report")


def _audit_anchors(record_hash, payload):
    anchors = [("audit_record", record_hash)]
    for key in _ANCHOR_HASH_KEYS:
        value = payload.get(key)
        if _is_hash(value):
            anchors.append((key, value))
    return tuple(anchors)


def _custody_resolution(state):
    # Unknown custody state fails closed toward reporting: an attempt whose
    # state the channel does not recognise is an unresolved incident, never
    # silently dropped.
    return _CUSTODY_OUTCOMES.get(state, ("incident", "unresolved"))


def _lifecycle_states(audit):
    """Fold `incident_lifecycle` audit events into current state per record.

    Deterministic from the audit alone: events are applied in audit order,
    and only a transition valid from the record's current derived state
    takes effect. An event for an unknown record id, for a near-miss
    (whose lifecycle is `not_applicable`), or with a from_state that does
    not match the current state is ignored -- it stays in the audit as
    history, but it cannot corrupt the derived state. Write-time validation
    lives in `transition_incident`; this is the derivation's own guard.
    Returns {record_id: (state, at_ns, actor)}.
    """
    states = {}
    for record in audit:
        if record["event"] != LIFECYCLE_EVENT:
            continue
        payload = record["payload"] if isinstance(record["payload"], dict) else {}
        record_id = payload.get("record_id")
        transition = payload.get("transition")
        if (type(record_id) is not str or not record_id
                or type(transition) is not str or transition not in _TRANSITION_TARGETS):
            continue
        if not record_id.startswith("incident:"):
            continue
        from_state = payload.get("from_state")
        to_state = payload.get("to_state")
        actor = payload.get("actor")
        if (type(from_state) is not str or type(to_state) is not str
                or type(actor) is not str):
            continue
        current = states.get(record_id, ("open", None, ""))
        if (_TRANSITION_TARGETS[transition].get(current[0]) != to_state
                or from_state != current[0]):
            continue
        states[record_id] = (to_state, record["timestamp_ns"], actor)
    return states


def _record_lifecycle(lifecycle_states, record_id, kind, first_seen_ns):
    """Lifecycle fields for one derived record.

    A record with no lifecycle events starts `open` (incident) or
    `not_applicable` (near-miss), current since it was first seen.
    """
    state, at_ns, actor = lifecycle_states.get(record_id, (None, None, ""))
    if state is None:
        return (("open", first_seen_ns, "") if kind == "incident"
                else ("not_applicable", first_seen_ns, ""))
    return state, at_ns, actor


def _derive_records(audit, custody):
    attempts = {}
    attempts_by_object = {}
    custody_time_ns = None
    if custody is not None:
        for snapshot in custody.attempts():
            attempts[snapshot.attempt_id] = snapshot
            attempts_by_object[snapshot.object_hash] = snapshot
        custody_time_ns = custody.snapshot().custody_time_ns
    records = []
    lifecycle_states = _lifecycle_states(audit)
    consumed_attempts = set()
    for record in audit:
        event = record["event"]
        payload = record["payload"] if isinstance(record["payload"], dict) else {}
        timestamp_ns = record["timestamp_ns"]
        record_hash = record["hash"]
        if event == "purchase_consequence_unknown":
            attempt_id = payload.get("custody_attempt_id")
            snapshot = attempts.get(attempt_id) if type(attempt_id) is str else None
            if snapshot is not None:
                # One record, anchored on the audit event, resolution taken
                # from the custody attempt's latest state.
                consumed_attempts.add(attempt_id)
                kind, resolution = _custody_resolution(snapshot.state)
                anchors = _audit_anchors(record_hash, payload) + (
                    ("custody_authorization", snapshot.authorization_hash),)
                last_seen_ns = max(timestamp_ns, custody_time_ns)
            else:
                kind, resolution = "incident", "unresolved"
                anchors = _audit_anchors(record_hash, payload)
                last_seen_ns = timestamp_ns
            reason = payload.get("reason") or "external_consequence_not_yet_verified"
            prefix = "incident" if kind == "incident" else "near-miss"
            record_id = f"{prefix}:{record_hash}"
            lifecycle, lifecycle_at_ns, lifecycle_actor = _record_lifecycle(
                lifecycle_states, record_id, kind, timestamp_ns)
            records.append(IncidentRecord(
                record_id, kind, "canonical_audit", event,
                timestamp_ns, last_seen_ns, anchors, reason, resolution, record_hash,
                lifecycle, lifecycle_at_ns, lifecycle_actor))
        elif event == "purchase_revalidation_failed":
            # A refusal is the terminal record for its custody attempt: no
            # effect happened, so the attempt must not also surface as an
            # unresolved custody incident. Consume it here -- by attempt id
            # when the payload carries one, else by order hash (the attempt
            # object hash IS the order hash, unique per attempt) -- and
            # anchor the near-miss on the custody authorization as well.
            # The attempt itself stays attempt_authorized in the store: the
            # custody vocabulary has no cancel/refuse transition, so the
            # channel consumes it rather than the store resolving it.
            attempt_id = payload.get("custody_attempt_id")
            snapshot = attempts.get(attempt_id) if type(attempt_id) is str else None
            if snapshot is None:
                order_hash = payload.get("order_hash")
                snapshot = attempts_by_object.get(order_hash) if type(order_hash) is str else None
            if snapshot is not None:
                consumed_attempts.add(snapshot.attempt_id)
                anchors = _audit_anchors(record_hash, payload) + (
                    ("custody_authorization", snapshot.authorization_hash),)
                last_seen_ns = max(timestamp_ns, custody_time_ns)
            else:
                anchors = _audit_anchors(record_hash, payload)
                last_seen_ns = timestamp_ns
            reason = payload.get("reason") or event
            record_id = f"near-miss:{record_hash}"
            lifecycle, lifecycle_at_ns, lifecycle_actor = _record_lifecycle(
                lifecycle_states, record_id, "near_miss", timestamp_ns)
            records.append(IncidentRecord(
                record_id, "near_miss", "canonical_audit", event,
                timestamp_ns, last_seen_ns, anchors,
                reason, "not_applicable", record_hash,
                lifecycle, lifecycle_at_ns, lifecycle_actor))
        elif event in _AUDIT_NEAR_MISS_EVENTS:
            reason = payload.get("reason") or event
            record_id = f"near-miss:{record_hash}"
            lifecycle, lifecycle_at_ns, lifecycle_actor = _record_lifecycle(
                lifecycle_states, record_id, "near_miss", timestamp_ns)
            records.append(IncidentRecord(
                record_id, "near_miss", "canonical_audit", event,
                timestamp_ns, timestamp_ns, _audit_anchors(record_hash, payload),
                reason, "not_applicable", record_hash,
                lifecycle, lifecycle_at_ns, lifecycle_actor))
        elif event == "decision" and payload.get("outcome") == "deny":
            reason = payload.get("reason") or "denied"
            record_id = f"near-miss:{record_hash}"
            lifecycle, lifecycle_at_ns, lifecycle_actor = _record_lifecycle(
                lifecycle_states, record_id, "near_miss", timestamp_ns)
            records.append(IncidentRecord(
                record_id, "near_miss", "canonical_audit", event,
                timestamp_ns, timestamp_ns, _audit_anchors(record_hash, payload),
                reason, "not_applicable", record_hash,
                lifecycle, lifecycle_at_ns, lifecycle_actor))
    if custody is not None:
        for attempt_id, snapshot in attempts.items():
            if attempt_id in consumed_attempts:
                continue
            if snapshot.state == "reconciled_success":
                # A resolver only: no record by itself.
                continue
            kind, resolution = _custody_resolution(snapshot.state)
            anchors = (
                ("custody_authorization", snapshot.authorization_hash),
                ("object_hash", snapshot.object_hash),
                ("target_hash", snapshot.target_hash),
                ("permit_hash", snapshot.permit_hash),
            )
            record_id = f"incident:custody:{attempt_id}"
            lifecycle, lifecycle_at_ns, lifecycle_actor = _record_lifecycle(
                lifecycle_states, record_id, kind, custody_time_ns)
            records.append(IncidentRecord(
                record_id, kind, "custody_store", snapshot.state,
                custody_time_ns, custody_time_ns, anchors,
                f"custody_attempt_{snapshot.state}", resolution,
                snapshot.authorization_hash, lifecycle, lifecycle_at_ns, lifecycle_actor))
    records.sort(key=lambda record: (record.first_seen_ns, record.record_id))
    return records


def freeze_incident_report(orchestrator, *, custody=None):
    """Derive the incident report from the canonical audit (+ custody store).

    Read-only: nothing is appended to the audit and nothing is written to
    the custody store. With custody=None the feed is audit-only; custody
    resolution of an unknown needs the store passed in.
    """
    if type(orchestrator) is not PulpoOrchestrator:
        raise TypeError("canonical PulpoOrchestrator required")
    if custody is not None and type(custody) is not SQLiteGovernanceCustody:
        raise TypeError("invalid custody store")
    kernel = orchestrator.kernel
    backend = kernel._state
    source_id = hashlib.sha256(f"{os.getpid()}:{id(backend)}".encode()).hexdigest()[:32]
    if type(backend) is SQLiteKernelState:
        source_id = backend._connection.activity_id
    audit = kernel.audit
    valid = kernel.verify_audit()
    records = _derive_records(audit, custody)
    return IncidentReport(
        source_id, time.time_ns(), valid, len(audit),
        incidents=sum(1 for record in records if record.kind == "incident"),
        near_misses=sum(1 for record in records if record.kind == "near_miss"),
        unresolved=sum(1 for record in records if record.resolution == "unresolved"),
        resolved_cleanly=sum(1 for record in records if record.resolution == "resolved_cleanly"),
        confirmed_wrong=sum(1 for record in records if record.resolution == "confirmed_wrong"),
        records=tuple(records),
    )


def export_incident_report(orchestrator, destination, *, custody=None):
    """Explicit owner-side export; does not install a timer or alter authority."""
    snapshot = freeze_incident_report(orchestrator, custody=custody)
    return _publish_snapshot(snapshot, destination)


def list_incidents(orchestrator, *, kind=None, resolution=None, lifecycle=None, since_ns=None, until_ns=None, custody=None):
    """Pure query over the frozen derivation; the time window applies to first_seen_ns."""
    if kind is not None and kind not in KINDS:
        raise ValueError("invalid incident kind")
    if resolution is not None and resolution not in RESOLUTIONS:
        raise ValueError("invalid incident resolution")
    if lifecycle is not None and lifecycle not in LIFECYCLES:
        raise ValueError("invalid incident lifecycle")
    if since_ns is not None and not _number(since_ns):
        raise ValueError("invalid since_ns")
    if until_ns is not None and not _number(until_ns):
        raise ValueError("invalid until_ns")
    if since_ns is not None and until_ns is not None and since_ns > until_ns:
        raise ValueError("invalid incident time window")
    report = freeze_incident_report(orchestrator, custody=custody)
    return tuple(
        record for record in report.records
        if (kind is None or record.kind == kind)
        and (resolution is None or record.resolution == resolution)
        and (lifecycle is None or record.lifecycle == lifecycle)
        and (since_ns is None or record.first_seen_ns >= since_ns)
        and (until_ns is None or record.first_seen_ns <= until_ns)
    )


def transition_incident(orchestrator, record_id, transition, *, actor, reason=None, custody=None):
    """Append a lifecycle transition for one incident record to the canonical audit.

    Handling status only: the transition changes how the record is reported,
    never what the kernel, the custody coordinator, or any permit will do.
    The transition is itself evidence -- it is appended to the hash-chained
    audit (event `incident_lifecycle`), and the record's current lifecycle
    state is derived from the audit on the next freeze, never stored beside
    it. Returns the updated record, re-derived after the append.

    `actor` is an explicit attribution string, conventionally
    `operator:<name>` for a human or `process:<name>` for automation; it is
    recorded, not authenticated -- there is no credential check here.
    `reason` is optional, except when closing an incident whose resolution
    is still `unresolved`: then it is required and the event is recorded as
    an explicit override, so a permanently unknown outcome can still be
    closed without pretending it was resolved. A failed append raises --
    unlike the purchase-outcome record, which is best-effort so a failed
    projection never masks the outcome the caller must reconcile, a
    lifecycle transition is an explicit operator action, and silent failure
    would leave the operator believing the incident is closed when it is not.
    """
    if type(orchestrator) is not PulpoOrchestrator:
        raise TypeError("canonical PulpoOrchestrator required")
    if type(record_id) is not str or not record_id:
        raise ValueError("invalid incident record_id")
    if type(transition) is not str or transition not in _TRANSITION_TARGETS:
        raise ValueError("invalid incident transition")
    if type(actor) is not str or not actor:
        raise ValueError("invalid incident actor")
    if reason is not None and type(reason) is not str:
        raise ValueError("invalid incident reason")
    if custody is not None and type(custody) is not SQLiteGovernanceCustody:
        raise TypeError("invalid custody store")
    report = freeze_incident_report(orchestrator, custody=custody)
    record = next((item for item in report.records if item.record_id == record_id), None)
    if record is None:
        raise ValueError("incident_record_not_found")
    if record.kind != "incident":
        raise ValueError("incident_lifecycle_not_applicable")
    targets = _TRANSITION_TARGETS[transition]
    if record.lifecycle not in targets:
        raise ValueError("invalid_incident_transition")
    to_state = targets[record.lifecycle]
    override = False
    if transition == "close" and record.resolution == "unresolved":
        if not reason:
            raise ValueError("incident_close_requires_reason")
        override = True
    kernel = orchestrator.kernel
    kernel._state.append(  # noqa: SLF001 - existing canonical audit seam
        LIFECYCLE_EVENT,
        {
            "record_id": record_id,
            "anchor_hash": record.anchor_hash,
            "transition": transition,
            "from_state": record.lifecycle,
            "to_state": to_state,
            "actor": actor,
            "reason": reason or "",
            "override": override,
        },
        time.time_ns(),
    )
    updated = freeze_incident_report(orchestrator, custody=custody)
    for item in updated.records:
        if item.record_id == record_id or item.anchor_hash == record.anchor_hash:
            return item
    raise ValueError("incident_record_not_found")


def load_incident_report(path):
    from .mcp_plugin import read_snapshot_document
    value = read_snapshot_document(path)
    if set(value) != {field.name for field in fields(IncidentReport)}:
        raise ValueError("snapshot_fields_invalid")
    if (type(value["records"]) is not list
            or any(type(record) is not dict
                   or set(record) != {field.name for field in fields(IncidentRecord)}
                   for record in value["records"])):
        raise ValueError("snapshot_nested_invalid")
    records = []
    for record in value["records"]:
        anchors = record["anchors"]
        if (type(anchors) is not list
                or any(type(anchor) is not list or len(anchor) != 2 for anchor in anchors)):
            raise ValueError("snapshot_nested_invalid")
        records.append(IncidentRecord(
            **{**record, "anchors": tuple((anchor[0], anchor[1]) for anchor in anchors)}))
    value["records"] = tuple(records)
    return IncidentReport(**value)
