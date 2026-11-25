"""Isolated checks for the kernel's canonical audit-chain verifier."""

from __future__ import annotations

from ..kernel import GovernanceKernel, Intent, Policy
from .report import CheckStatus, VerificationCheck


def audit_checks() -> tuple[VerificationCheck, ...]:
    kernel = GovernanceKernel(Policy(frozenset({"read"}), max_cost=1))
    kernel.evaluate(Intent("agent:verifier", "read", "repo:audit-probe"))
    valid_before_tamper = kernel.verify_audit()
    return (
        VerificationCheck(
            check_id="audit-chain-integrity",
            category="audit",
            status=CheckStatus.PASS if valid_before_tamper else CheckStatus.FAIL,
            summary=(
                "The isolated kernel audit chain verified."
                if valid_before_tamper
                else "The isolated kernel audit chain failed verification before tampering."
            ),
            evidence=(f"valid_chain={valid_before_tamper}",),
            claim_classification="Verified",
        ),
        VerificationCheck(
            check_id="audit-tamper-detection",
            category="audit",
            status=CheckStatus.UNVERIFIABLE,
            summary="The verifier does not mutate audit state to create a tamper fixture.",
            evidence=("Tamper detection is covered by kernel tests, not by this report run.",),
            claim_classification="Unknown",
        ),
        VerificationCheck(
            check_id="audit-event-completeness",
            category="audit",
            status=CheckStatus.UNVERIFIABLE,
            summary="The verifier has no independent event source for detecting missing audit events.",
            evidence=("Hash-chain integrity cannot establish that every consequential event was recorded.",),
            claim_classification="Unknown",
        ),
    )
