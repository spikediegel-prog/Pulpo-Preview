"""Deployment-scoped custody checks that cannot be inferred from kernel probes."""

from .report import CheckStatus, VerificationCheck


def custody_checks() -> tuple[VerificationCheck, ...]:
    return (
        VerificationCheck(
            check_id="custody-approval-binding",
            category="custody",
            status=CheckStatus.UNVERIFIABLE,
            summary="No live custody receipt or approval evidence was supplied.",
            evidence=(
                "Approval recorded, signed, intent-linked, and unexpired were not assessed.",
                "The verifier does not load custody signing material or a custody store.",
            ),
            claim_classification="Unknown",
        ),
        VerificationCheck(
            check_id="custody-required-for-execution",
            category="custody",
            status=CheckStatus.UNVERIFIABLE,
            summary="No deployed execution handoff was available to verify custody enforcement.",
            evidence=(
                "An isolated kernel permit probe cannot prove that a provider call is custody-gated.",
                "No executor or provider was invoked.",
            ),
            claim_classification="Unknown",
        ),
    )
