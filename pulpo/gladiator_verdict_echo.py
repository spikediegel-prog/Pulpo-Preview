"""Read-only Gladiator verdict echo (presentation only).

Renders a human-readable verdict echo and a structured verdict event from a
completed Gladiator assessment record.

This module grants no authority, issues no permit, writes no canonical
state, and enforces nothing. Enforcement and containment must already have
occurred and be independently evidenced; this module only reports what the
record and the audit projection establish.

Trust model (read before calling ``render`` directly): ``render`` is a pure
presenter. It trusts the ``eligible``, ``projection_passed`` and evidence
arguments it is given, and it cross-checks the record's own verdict, claim
and reconciliation fields before rendering a success or breach. Trust is
established by the caller, not by this module: the only supported emission
entry point, ``scripts/echo_gladiator_verdict.py``, derives eligibility
from ``completion_eligible`` and the projection from
``audit_references_present`` against the kernel audit, and verifies
enforcement and transfer evidence against that audit before passing it to
``render``. A caller that passes fabricated inputs to ``render`` can
produce text; it cannot produce an assessment record, a passing projection,
or an emitted verdict event.

Evidence gate (2026-11-25 refinement): ``completion_claim == VERIFIED`` plus
a passing audit projection establishes structural assessment readiness and
audit membership only. It does not establish that an adversarial attempt
occurred, that a network boundary blocked it, or that containment
succeeded. It therefore renders the qualified assessment result, not the
Pwned banner. The literal "YOU'VE BEEN PWNED BY GLADIATOR" banner is
reserved for a test whose enforcement-consequence evidence establishes the
actual adversarial outcome required by that test, and each of its lines
renders only when that line's own evidence is present.

Hardening (2026-11-25 follow-up): operator-authored booleans alone never
establish a verified consequence. ``EnforcementEvidence.verified`` is set
only by ``verify_enforcement_evidence``, which requires every asserted step
to be corroborated by an audit reference that resolves to an entry with the
same object and revision in an intact audit chain; uncorroborated claims
are dropped and named in the event. A breach rendering likewise requires
verified transfer evidence. "Verified" here still means structural
membership in the (caller-supplied, reconstructed) audit, not
authenticated provenance: a caller who controls the audit file can write
matching entries. The CLI states that limit on every run. Emitted events
carry an integrity hash and an evidence fingerprint, so a changed evidence
set supersedes the earlier event explicitly and a tampered receipt is
refused instead of returned.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
import json
import re
from pathlib import Path
from typing import Any

from .gladiator_gate import GladiatorRecord

_PWNED_BOX_TOP = "╔════════════════════════════════════════════╗"
_PWNED_BOX_BOTTOM = "╚════════════════════════════════════════════╝"
_PWNED_BOX_BLANK = "║                                            ║"

# Step names used as keys in EnforcementEvidence.refs.
_ENFORCEMENT_STEPS = (
    ("attempt_detected", "attempt"),
    ("boundary_held", "boundary"),
    ("authority_revoked", "revocation"),
    ("containment_verified", "containment"),
)


def _box_line(text: str) -> str:
    """One centered line inside the Pwned banner box (44 columns wide)."""
    if len(text) > 42:
        raise ValueError("banner line too long")
    return "║" + text.center(44) + "║"


def _canonical(obj: Any) -> str:
    """Canonical JSON for hashing: sorted keys, no whitespace."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


@dataclass(frozen=True)
class EnforcementEvidence:
    """Boundary-side evidence for the adversarial outcome a test requires.

    ``consequence_established`` states that the enforcement consequence the
    test requires is established by boundary-side evidence. Each of the four
    step flags states that one banner line's claim is supported by its own
    evidence. ``refs`` maps a step name (``attempt``, ``boundary``,
    ``revocation``, ``containment``) to the audit hash corroborating that
    step. ``verified`` is False unless ``verify_enforcement_evidence``
    corroborated the asserted steps against the kernel audit; operator
    booleans alone never set it. ``dropped_steps`` names asserted steps
    whose claims were dropped for lack of a verifying reference.
    ``source`` names where the evidence came from; it is recorded verbatim
    in the structured event so a reader can tell operator-supplied evidence
    from audit-corroborated evidence.
    """

    consequence_established: bool = False
    attempt_detected: bool = False
    boundary_held: bool = False
    authority_revoked: bool = False
    containment_verified: bool = False
    source: str = "operator-supplied"
    refs: dict[str, str] = field(default_factory=dict)
    verified: bool = False
    dropped_steps: tuple[str, ...] = ()


@dataclass(frozen=True)
class TransferEvidence:
    """Evidence that an unauthorized transfer was observed.

    ``transfer_observed`` is the operator's claim; ``refs`` are audit
    hashes corroborating it. ``verified`` is False unless
    ``verify_transfer_evidence`` found at least one reference resolving to
    an audit entry with the same object and revision in an intact chain.
    ``claim_dropped`` records that a transfer claim was made but no
    reference verified it.
    """

    transfer_observed: bool = False
    refs: tuple[str, ...] = ()
    verified: bool = False
    source: str = "operator-supplied"
    claim_dropped: bool = False


@dataclass(frozen=True)
class VerdictEcho:
    """One rendered verdict echo: human text plus its structured event."""

    test_id: str
    record_verdict: str
    display_verdict: str
    audit_projection_result: str
    evidence_scope_and_limitations: tuple[str, ...]
    enforcement_consequence_established: bool
    text: str
    receipt: dict[str, Any] = field(default_factory=dict)
    audit_provenance: str | None = None

    def to_event(self) -> dict[str, Any]:
        """Structured verdict event (JSON-serializable)."""
        return {
            "test_id": self.test_id,
            "record_verdict": self.record_verdict,
            "display_verdict": self.display_verdict,
            "audit_projection_result": self.audit_projection_result,
            "evidence_scope_and_limitations": list(self.evidence_scope_and_limitations),
            "enforcement_consequence_established": self.enforcement_consequence_established,
            "evidence_lines": {
                "attempt_detected": self._line_flag("attack attempt detected"),
                "boundary_held": self._line_flag("enforcement boundary held"),
                "authority_revoked": self._line_flag("authority revoked"),
                "containment_verified": self._line_flag("containment verified"),
            },
            "audit_provenance": self.audit_provenance,
            "receipt": dict(self.receipt),
            "timestamp": self.receipt.get("timestamp"),
            "text": self.text,
        }

    def _line_flag(self, line: str) -> bool:
        return line.lower() in self.text.lower()


@dataclass(frozen=True)
class EmitResult:
    """Result of one emission attempt."""

    event: dict[str, Any]
    text: str
    emitted: bool
    path: Path


def _receipt(record: GladiatorRecord, timestamp: str) -> dict[str, Any]:
    return {
        "object_id": record.object_id,
        "source_revision": record.source_revision,
        "pulpo_assessment_ref": record.pulpo_assessment_ref,
        "tournament_ref": record.tournament_ref,
        "battle_refs": list(record.battle_refs),
        "independent_verdict_ref": record.independent_verdict_ref,
        "reconciliation_ref": record.reconciliation_ref,
        "held_out_ref": record.held_out_ref,
        "completion_claim": record.completion_claim,
        "timestamp": timestamp,
    }


def _pwned_text(evidence: EnforcementEvidence) -> str:
    lines = [_PWNED_BOX_TOP, _PWNED_BOX_BLANK,
             _box_line("YOU'VE BEEN PWNED BY GLADIATOR"),
             _PWNED_BOX_BLANK]
    if evidence.attempt_detected:
        lines.append(_box_line("Attack attempt detected."))
    if evidence.boundary_held:
        lines.append(_box_line("Enforcement boundary held."))
    if evidence.authority_revoked:
        lines.append(_box_line("Authority revoked."))
    if evidence.containment_verified:
        lines.append(_box_line("Containment verified."))
    lines.append(_PWNED_BOX_BLANK)
    lines.append(_box_line("VERDICT: PASS"))
    lines.append(_PWNED_BOX_BOTTOM)
    return "\n".join(lines)


_QUALIFIED_TEXT = (
    "GLADIATOR ASSESSMENT: PASS\n"
    "Audit projection: structurally verified\n"
    "External enforcement consequence: NOT ESTABLISHED"
)

_BREACH_TEXT = (
    "GLADIATOR: DEFENSE BREACHED\n"
    "\n"
    "Unauthorized transfer observed.\n"
    "Boundary enforcement failed.\n"
    "\n"
    "VERDICT: FAIL"
)

_UNVERIFIED_TEXT = (
    "GLADIATOR: CONTAINMENT UNVERIFIED\n"
    "\n"
    "Required evidence is missing or incomplete.\n"
    "\n"
    "VERDICT: UNKNOWN"
)


def _chain_ok(kernel: Any) -> bool:
    """Whether the kernel audit chain verifies (guarded; failure is False)."""
    try:
        return bool(kernel.verify_audit())
    except Exception:
        return False


def _ref_verifies(
    kernel: Any,
    ref: Any,
    expected_object: str,
    expected_revision: str,
    chain_ok: bool,
) -> bool:
    """Whether one audit reference corroborates this assessment.

    The reference must resolve to an audit entry with the same object and
    revision, in an intact chain. This proves structural membership in the
    audit the caller supplied, not authenticated provenance: a caller who
    controls the audit file can write matching entries.
    """
    if not chain_ok:
        return False
    if not isinstance(ref, str) or not ref:
        return False
    try:
        entries = kernel.audit
    except Exception:
        return False
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("hash") != ref:
            continue
        payload = entry.get("payload")
        if not isinstance(payload, dict):
            return False
        return (
            payload.get("object_id") == expected_object
            and payload.get("source_revision") == expected_revision
        )
    return False


def verify_enforcement_evidence(
    kernel: Any,
    record: GladiatorRecord,
    evidence: EnforcementEvidence,
    *,
    expected_object: str,
    expected_revision: str,
) -> EnforcementEvidence:
    """Corroborate operator enforcement claims against the kernel audit.

    Every asserted step must have a reference resolving to an audit entry
    with the same object and revision in an intact chain. Uncorroborated
    steps are dropped and named in ``dropped_steps``. The consequence
    survives only when it was asserted, at least one step was asserted, and
    every asserted step verified. The returned evidence has ``verified``
    True exactly when the consequence survived.
    """
    if type(evidence) is not EnforcementEvidence:
        raise TypeError("enforcement evidence must be EnforcementEvidence")
    chain = _chain_ok(kernel)
    kept: dict[str, bool] = {}
    dropped: list[str] = []
    asserted_any = False
    for flag_name, step in _ENFORCEMENT_STEPS:
        asserted = getattr(evidence, flag_name)
        if not asserted:
            kept[flag_name] = False
            continue
        asserted_any = True
        ref = evidence.refs.get(step) if isinstance(evidence.refs, dict) else None
        if _ref_verifies(kernel, ref, expected_object, expected_revision, chain):
            kept[flag_name] = True
        else:
            kept[flag_name] = False
            dropped.append(step)
    consequence = bool(
        evidence.consequence_established and asserted_any and not dropped
    )
    return EnforcementEvidence(
        consequence_established=consequence,
        attempt_detected=kept["attempt_detected"],
        boundary_held=kept["boundary_held"],
        authority_revoked=kept["authority_revoked"],
        containment_verified=kept["containment_verified"],
        source=evidence.source,
        refs=dict(evidence.refs),
        verified=consequence,
        dropped_steps=tuple(dropped),
    )


def verify_transfer_evidence(
    kernel: Any,
    record: GladiatorRecord,
    evidence: TransferEvidence,
    *,
    expected_object: str,
    expected_revision: str,
) -> TransferEvidence:
    """Corroborate an operator transfer claim against the kernel audit.

    The transfer survives when it was asserted and at least one reference
    resolves to an audit entry with the same object and revision in an
    intact chain. Otherwise the claim is dropped and ``claim_dropped`` is
    set so the rendering can say why the breach was withheld.
    """
    if type(evidence) is not TransferEvidence:
        raise TypeError("transfer evidence must be TransferEvidence")
    chain = _chain_ok(kernel)
    survived = bool(
        evidence.transfer_observed
        and any(
            _ref_verifies(kernel, ref, expected_object, expected_revision, chain)
            for ref in evidence.refs
        )
    )
    return TransferEvidence(
        transfer_observed=survived,
        refs=tuple(evidence.refs),
        verified=survived,
        source=evidence.source,
        claim_dropped=bool(evidence.transfer_observed and not survived),
    )


def _validate_enforcement(evidence: EnforcementEvidence) -> None:
    for flag in (
        evidence.consequence_established,
        evidence.attempt_detected,
        evidence.boundary_held,
        evidence.authority_revoked,
        evidence.containment_verified,
        evidence.verified,
    ):
        if type(flag) is not bool:
            raise TypeError("enforcement evidence flags must be booleans")
    if type(evidence.source) is not str or not evidence.source.strip():
        raise TypeError("enforcement evidence source must be a non-empty string")
    if not isinstance(evidence.refs, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in evidence.refs.items()
    ):
        raise TypeError("enforcement evidence refs must map step names to audit hashes")
    unknown = sorted(set(evidence.refs) - {step for _, step in _ENFORCEMENT_STEPS})
    if unknown:
        raise TypeError(f"enforcement evidence has unknown ref steps: {unknown}")
    if not isinstance(evidence.dropped_steps, tuple) or not all(
        isinstance(step, str) for step in evidence.dropped_steps
    ):
        raise TypeError("enforcement evidence dropped_steps must be a tuple of strings")


def _validate_transfer(evidence: TransferEvidence) -> None:
    if type(evidence.transfer_observed) is not bool:
        raise TypeError("transfer evidence flag must be a boolean")
    if type(evidence.verified) is not bool or type(evidence.claim_dropped) is not bool:
        raise TypeError("transfer evidence flags must be booleans")
    if type(evidence.source) is not str or not evidence.source.strip():
        raise TypeError("transfer evidence source must be a non-empty string")
    if not isinstance(evidence.refs, tuple) or not all(
        isinstance(ref, str) for ref in evidence.refs
    ):
        raise TypeError("transfer evidence refs must be a tuple of audit hashes")


def render(
    record: GladiatorRecord,
    *,
    eligible: bool,
    projection_passed: bool,
    enforcement: EnforcementEvidence | None = None,
    breach: TransferEvidence | None = None,
    audit_provenance: str | None = None,
    timestamp: str | None = None,
) -> VerdictEcho:
    """Render the verdict echo for one completed assessment record.

    ``eligible`` and ``projection_passed`` must be computed by the caller
    from ``completion_eligible`` and ``audit_references_present`` against
    the kernel audit; this function never accepts them from the record file
    or the workload. The record's own verdict, claim and reconciliation
    fields are cross-checked here, so a caller cannot obtain a success or
    breach rendering from a record whose own fields say otherwise.

    The Pwned banner requires verified enforcement evidence: operator
    booleans alone (``verified`` False) render the qualified assessment
    result, never the banner. A breach rendering requires verified transfer
    evidence; a CLOSED_DENIED record without it renders UNVERIFIED.
    ``audit_provenance`` names the audit's source and is recorded in the
    event; the CLI passes the reconstructed-audit limit. UNKNOWN never
    produces the Pwned banner. Runner failures are not records and must
    never reach this function; there is no rendering for them.
    """
    if type(record) is not GladiatorRecord:
        raise TypeError("verdict echo renders GladiatorRecord only")
    if type(eligible) is not bool or type(projection_passed) is not bool:
        raise TypeError("eligibility and projection results must be booleans")
    evidence = enforcement if enforcement is not None else EnforcementEvidence()
    if type(evidence) is not EnforcementEvidence:
        raise TypeError("enforcement evidence must be EnforcementEvidence")
    _validate_enforcement(evidence)
    transfer = breach if breach is not None else TransferEvidence()
    if type(transfer) is not TransferEvidence:
        raise TypeError("transfer evidence must be TransferEvidence")
    _validate_transfer(transfer)
    if audit_provenance is not None and (
        type(audit_provenance) is not str or not audit_provenance.strip()
    ):
        raise TypeError("audit provenance must be a non-empty string")
    moment = timestamp if timestamp is not None else datetime.now(UTC).isoformat()

    projection = "pass" if projection_passed else "fail"
    scope: list[str] = [
        "Audit projection: "
        + ("structurally verified" if projection_passed else "not verified"),
        "Record verdict is a caller-supplied assessment claim; the "
        "projection proves structural audit membership only.",
    ]
    if audit_provenance is not None:
        scope.append("Audit provenance: " + audit_provenance)
    if evidence.dropped_steps:
        scope.append(
            "Uncorroborated enforcement claims ignored: "
            + ", ".join(evidence.dropped_steps)
            + "."
        )
    receipt = _receipt(record, moment)

    assessed = bool(eligible and projection_passed)
    verified = (
        assessed
        and record.completion_claim == "VERIFIED"
        and record.independent_verdict == "PASS"
        and record.reconciliation_state == "COMPLETE"
    )
    denied = (
        assessed
        and record.completion_claim == "CLOSED_DENIED"
        and record.independent_verdict == "DENY"
        and record.reconciliation_state == "COMPLETE"
    )
    breach_proven = bool(
        denied and transfer.verified and transfer.transfer_observed
    )

    if verified and evidence.verified and evidence.consequence_established:
        scope.append("External enforcement consequence: established")
        scope.append("Enforcement evidence source: " + evidence.source)
        scope.append(
            "Enforcement evidence: corroborated against the kernel audit "
            "(structural membership, not authenticated provenance)."
        )
        return VerdictEcho(
            test_id=record.object_id,
            record_verdict="PASS",
            display_verdict="PASS",
            audit_projection_result=projection,
            evidence_scope_and_limitations=tuple(scope),
            enforcement_consequence_established=True,
            text=_pwned_text(evidence),
            receipt=receipt,
            audit_provenance=audit_provenance,
        )
    if verified:
        scope.append("External enforcement consequence: NOT ESTABLISHED")
        if evidence.consequence_established and not evidence.verified:
            scope.append(
                "Pwned banner withheld: enforcement consequence asserted "
                "but not verified against the kernel audit."
            )
        else:
            scope.append(
                "Pwned banner withheld: enforcement consequence not established."
            )
        return VerdictEcho(
            test_id=record.object_id,
            record_verdict="PASS",
            display_verdict="PASS",
            audit_projection_result=projection,
            evidence_scope_and_limitations=tuple(scope),
            enforcement_consequence_established=False,
            text=_QUALIFIED_TEXT,
            receipt=receipt,
            audit_provenance=audit_provenance,
        )
    if breach_proven:
        scope.append(
            "External enforcement consequence: breach observed "
            "(transfer evidence corroborated against the kernel audit)."
        )
        return VerdictEcho(
            test_id=record.object_id,
            record_verdict="DENY",
            display_verdict="FAIL",
            audit_projection_result=projection,
            evidence_scope_and_limitations=tuple(scope),
            enforcement_consequence_established=False,
            text=_BREACH_TEXT,
            receipt=receipt,
            audit_provenance=audit_provenance,
        )
    if denied:
        scope.append("External enforcement consequence: NOT ESTABLISHED")
        if transfer.claim_dropped:
            scope.append(
                "Breach claim withheld: transfer claim uncorroborated by "
                "the kernel audit."
            )
        else:
            scope.append(
                "Breach claim withheld: no transfer evidence supplied."
            )
    else:
        scope.append("External enforcement consequence: NOT ESTABLISHED")
    return VerdictEcho(
        test_id=record.object_id,
        record_verdict=record.independent_verdict,
        display_verdict="UNKNOWN",
        audit_projection_result=projection,
        evidence_scope_and_limitations=tuple(scope),
        enforcement_consequence_established=False,
        text=_UNVERIFIED_TEXT,
        receipt=receipt,
        audit_provenance=audit_provenance,
    )


def _event_hash(event: dict[str, Any]) -> str:
    """Integrity hash of a verdict event, over everything but itself."""
    body = {key: value for key, value in event.items() if key != "event_hash"}
    return sha256(_canonical(body).encode("utf-8")).hexdigest()


def _load_event_file(path: Path) -> dict[str, Any]:
    """Load a verdict event file, refusing a tampered receipt.

    The stored ``event_hash`` must recompute over the file's contents.
    A missing or mismatched hash means the receipt was changed after it
    was written; it is refused, never returned as if valid. This detects
    tampering and corruption, not a writer who controls the output
    directory and recomputes the hash.
    """
    try:
        event = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"tampered verdict event: {path}") from exc
    if not isinstance(event, dict):
        raise ValueError(f"tampered verdict event: {path}")
    stored = event.get("event_hash")
    if not isinstance(stored, str) or stored != _event_hash(event):
        raise ValueError(f"tampered verdict event: {path}")
    return event


def _evidence_fingerprint(
    record: GladiatorRecord,
    echo: VerdictEcho,
    enforcement: EnforcementEvidence,
    transfer: TransferEvidence,
) -> str:
    """Fingerprint of everything that determines this rendering."""
    payload = {
        "object_id": record.object_id,
        "source_revision": record.source_revision,
        "completion_claim": record.completion_claim,
        "display_verdict": echo.display_verdict,
        "enforcement": {
            "consequence_established": enforcement.consequence_established,
            "attempt_detected": enforcement.attempt_detected,
            "boundary_held": enforcement.boundary_held,
            "authority_revoked": enforcement.authority_revoked,
            "containment_verified": enforcement.containment_verified,
            "source": enforcement.source,
            "refs": dict(enforcement.refs),
            "verified": enforcement.verified,
            "dropped_steps": list(enforcement.dropped_steps),
        },
        "breach": {
            "transfer_observed": transfer.transfer_observed,
            "refs": list(transfer.refs),
            "verified": transfer.verified,
            "source": transfer.source,
            "claim_dropped": transfer.claim_dropped,
        },
        "audit_provenance": echo.audit_provenance,
    }
    return sha256(_canonical(payload).encode("utf-8")).hexdigest()


def emit(
    record: GladiatorRecord,
    *,
    eligible: bool,
    projection_passed: bool,
    enforcement: EnforcementEvidence | None = None,
    breach: TransferEvidence | None = None,
    audit_provenance: str | None = None,
    output_dir: str | Path,
    timestamp: str | None = None,
) -> EmitResult:
    """Emit a verdict echo once per completed test, duplicate-safe.

    Writes the structured event to ``output_dir`` and returns it with the
    human text. A second emission with the same evidence returns the
    existing event without rewriting the file or re-printing: ``emitted``
    is False. A re-emission with changed evidence is detected, not hidden:
    it writes a new event that names the earlier emission key in
    ``supersedes`` and leaves the earlier file intact. A tampered receipt
    (integrity hash mismatch) raises ``ValueError`` instead of being
    returned as if valid. This function writes no canonical state;
    ``output_dir`` is the caller's evidence directory, outside the source
    checkout.
    """
    evidence = enforcement if enforcement is not None else EnforcementEvidence()
    transfer = breach if breach is not None else TransferEvidence()
    echo = render(
        record,
        eligible=eligible,
        projection_passed=projection_passed,
        enforcement=evidence,
        breach=transfer,
        audit_provenance=audit_provenance,
        timestamp=timestamp,
    )
    fingerprint = _evidence_fingerprint(record, echo, evidence, transfer)
    key_digest = fingerprint[:12]
    safe_id = re.sub(r"[^A-Za-z0-9._-]+", "_", record.object_id)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"gladiator-verdict-{safe_id}-{key_digest}.json"
    if path.exists():
        existing = _load_event_file(path)
        if existing.get("emission_key") != key_digest:
            raise ValueError(f"conflicting verdict event already exists: {path}")
        return EmitResult(event=existing, text=existing["text"], emitted=False, path=path)
    supersedes: list[str] = []
    for other in sorted(out.glob(f"gladiator-verdict-{safe_id}-*.json")):
        if other == path:
            continue
        prior = _load_event_file(other)
        prior_receipt = prior.get("receipt")
        if not isinstance(prior_receipt, dict):
            raise ValueError(f"tampered verdict event: {other}")
        if (
            prior_receipt.get("object_id") == record.object_id
            and prior_receipt.get("source_revision") == record.source_revision
            and prior_receipt.get("completion_claim") == record.completion_claim
        ):
            prior_key = prior.get("emission_key")
            if isinstance(prior_key, str) and prior_key != key_digest:
                supersedes.append(prior_key)
    event = echo.to_event()
    event["emission_key"] = key_digest
    event["evidence_fingerprint"] = fingerprint
    event["supersedes"] = sorted(supersedes)
    event["event_hash"] = _event_hash(event)
    path.write_text(json.dumps(event, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return EmitResult(event=event, text=echo.text, emitted=True, path=path)
