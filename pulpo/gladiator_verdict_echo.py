"""Read-only Gladiator verdict echo (presentation only).

Renders a human-readable verdict echo and a structured verdict event from a
completed Gladiator assessment record.

This module grants no authority, issues no permit, writes no canonical
state, and enforces nothing. Enforcement and containment must already have
occurred and be independently evidenced; this module only reports what the
record and the audit projection establish.

Trust model (read before calling ``render`` directly): ``render`` is a pure
presenter. It trusts the ``eligible``, ``projection_passed`` and
``enforcement`` arguments it is given, and it cross-checks the record's own
verdict, claim and reconciliation fields before rendering a success or
breach. Trust is established by the caller, not by this module: the only
supported emission entry point, ``scripts/echo_gladiator_verdict.py``,
derives eligibility from ``completion_eligible`` and the projection from
``audit_references_present`` against the kernel audit, and never accepts
those booleans from the record file or the workload. A caller that passes
fabricated inputs to ``render`` can produce text; it cannot produce an
assessment record, a passing projection, or an emitted verdict event.

Evidence gate (2026-11-25 refinement): ``completion_claim == VERIFIED`` plus
a passing audit projection establishes structural assessment readiness and
audit membership only. It does not establish that an adversarial attempt
occurred, that a network boundary blocked it, or that containment
succeeded. It therefore renders the qualified assessment result, not the
Pwned banner. The literal "YOU'VE BEEN PWNED BY GLADIATOR" banner is
reserved for a test whose enforcement-consequence evidence establishes the
actual adversarial outcome required by that test, and each of its lines
renders only when that line's own evidence is present.
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


def _box_line(text: str) -> str:
    """One centered line inside the Pwned banner box (44 columns wide)."""
    if len(text) > 42:
        raise ValueError("banner line too long")
    return "║" + text.center(44) + "║"


@dataclass(frozen=True)
class EnforcementEvidence:
    """Boundary-side evidence for the adversarial outcome a test requires.

    ``consequence_established`` states that the enforcement consequence the
    test requires is established by boundary-side evidence. Each of the four
    step flags states that one banner line's claim is supported by its own
    evidence. ``source`` names where the evidence came from; it is recorded
    verbatim in the structured event so a reader can tell operator-supplied
    evidence from boundary-verified evidence.
    """

    consequence_established: bool = False
    attempt_detected: bool = False
    boundary_held: bool = False
    authority_revoked: bool = False
    containment_verified: bool = False
    source: str = "operator-supplied"


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


def render(
    record: GladiatorRecord,
    *,
    eligible: bool,
    projection_passed: bool,
    enforcement: EnforcementEvidence | None = None,
    timestamp: str | None = None,
) -> VerdictEcho:
    """Render the verdict echo for one completed assessment record.

    ``eligible`` and ``projection_passed`` must be computed by the caller
    from ``completion_eligible`` and ``audit_references_present`` against
    the kernel audit; this function never accepts them from the record file
    or the workload. The record's own verdict, claim and reconciliation
    fields are cross-checked here, so a caller cannot obtain a success or
    breach rendering from a record whose own fields say otherwise.

    UNKNOWN never produces the Pwned banner. A VERIFIED record without
    enforcement-consequence evidence renders the qualified assessment
    result. Runner failures are not records and must never reach this
    function; there is no rendering for them.
    """
    if type(record) is not GladiatorRecord:
        raise TypeError("verdict echo renders GladiatorRecord only")
    if type(eligible) is not bool or type(projection_passed) is not bool:
        raise TypeError("eligibility and projection results must be booleans")
    evidence = enforcement if enforcement is not None else EnforcementEvidence()
    if type(evidence) is not EnforcementEvidence:
        raise TypeError("enforcement evidence must be EnforcementEvidence")
    for flag in (
        evidence.consequence_established,
        evidence.attempt_detected,
        evidence.boundary_held,
        evidence.authority_revoked,
        evidence.containment_verified,
    ):
        if type(flag) is not bool:
            raise TypeError("enforcement evidence flags must be booleans")
    if type(evidence.source) is not str or not evidence.source.strip():
        raise TypeError("enforcement evidence source must be a non-empty string")
    moment = timestamp if timestamp is not None else datetime.now(UTC).isoformat()

    projection = "pass" if projection_passed else "fail"
    scope: list[str] = [
        "Audit projection: "
        + ("structurally verified" if projection_passed else "not verified"),
        "Record verdict is a caller-supplied assessment claim; the "
        "projection proves structural audit membership only.",
    ]
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

    if verified and evidence.consequence_established:
        scope.append("External enforcement consequence: established")
        scope.append("Enforcement evidence source: " + evidence.source)
        return VerdictEcho(
            test_id=record.object_id,
            record_verdict="PASS",
            display_verdict="PASS",
            audit_projection_result=projection,
            evidence_scope_and_limitations=tuple(scope),
            enforcement_consequence_established=True,
            text=_pwned_text(evidence),
            receipt=receipt,
        )
    if verified:
        scope.append("External enforcement consequence: NOT ESTABLISHED")
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
        )
    if denied:
        scope.append("External enforcement consequence: breach observed")
        return VerdictEcho(
            test_id=record.object_id,
            record_verdict="DENY",
            display_verdict="FAIL",
            audit_projection_result=projection,
            evidence_scope_and_limitations=tuple(scope),
            enforcement_consequence_established=False,
            text=_BREACH_TEXT,
            receipt=receipt,
        )
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
    )


def emit(
    record: GladiatorRecord,
    *,
    eligible: bool,
    projection_passed: bool,
    enforcement: EnforcementEvidence | None = None,
    output_dir: str | Path,
    timestamp: str | None = None,
) -> EmitResult:
    """Emit a verdict echo once per completed test, duplicate-safe.

    Writes the structured event to ``output_dir`` and returns it with the
    human text. A second emission of the same record, claim, display
    verdict and enforcement-consequence outcome returns the existing event
    without rewriting the file or re-printing: ``emitted`` is False. An
    existing file under the same emission key whose content differs is a
    conflict and raises ``ValueError`` instead of overwriting an assessment
    record. This function writes no canonical state; ``output_dir`` is the
    caller's evidence directory, outside the source checkout.
    """
    echo = render(
        record,
        eligible=eligible,
        projection_passed=projection_passed,
        enforcement=enforcement,
        timestamp=timestamp,
    )
    key = (
        record.object_id,
        record.source_revision,
        record.completion_claim,
        echo.display_verdict,
        echo.enforcement_consequence_established,
    )
    key_digest = sha256(repr(key).encode("utf-8")).hexdigest()[:12]
    safe_id = re.sub(r"[^A-Za-z0-9._-]+", "_", record.object_id)
    out = Path(output_dir)
    path = out / f"gladiator-verdict-{safe_id}-{key_digest}.json"
    event = echo.to_event()
    event["emission_key"] = key_digest
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(
                f"conflicting verdict event already exists: {path}"
            ) from exc
        if existing.get("emission_key") != key_digest:
            raise ValueError(
                f"conflicting verdict event already exists: {path}"
            )
        return EmitResult(event=existing, text=existing["text"], emitted=False, path=path)
    out.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(event, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return EmitResult(event=event, text=echo.text, emitted=True, path=path)
