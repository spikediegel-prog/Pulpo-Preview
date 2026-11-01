"""Checks for approval-gated authority without creating an approval credential."""

from __future__ import annotations

from ..authority import AuthorityTrust
from ..kernel import GovernanceKernel, Intent, Policy
from .report import CheckStatus, VerificationCheck


def check_mutation_approval_gate() -> VerificationCheck:
    trust = AuthorityTrust(
        authority_id="authority:unconfigured",
        verifier_id="verifier:unconfigured",
        key_id="key:unconfigured",
        algorithm="ed25519",
        key_fingerprint="0" * 64,
        deployment_id="deployment:unconfigured",
        max_approval_ttl_ns=1,
    )
    kernel = GovernanceKernel(
        Policy(
            frozenset({"write"}),
            max_cost=1,
            approval_actions=frozenset({"write"}),
            authority_trust=trust,
        )
    )
    decision = kernel.evaluate(Intent("agent:verifier", "write", "repo:mutation-probe", 0))
    passed = decision.outcome == "require_approval" and decision.permit is None
    return VerificationCheck(
        check_id="mutation-approval-gate",
        category="authority",
        status=CheckStatus.PASS if passed else CheckStatus.FAIL,
        summary=(
            "The approval-gated mutation received no permit without approval."
            if passed
            else "The approval-gated mutation was not stopped before permit issuance."
        ),
        evidence=(f"decision={decision.outcome}:{decision.reason}", f"permit_issued={decision.permit is not None}"),
        claim_classification="Verified",
    )


def check_authority_separation() -> VerificationCheck:
    check = check_mutation_approval_gate()
    return VerificationCheck(
        check_id="authority-separation",
        category="authority",
        status=check.status,
        summary=(
            "The unapproved evaluator did not grant mutation authority."
            if check.status is CheckStatus.PASS
            else "The unapproved evaluator granted or failed to deny mutation authority."
        ),
        evidence=check.evidence,
        claim_classification=check.claim_classification,
    )


def check_independent_approval() -> VerificationCheck:
    return VerificationCheck(
        check_id="independent-approval",
        category="authority",
        status=CheckStatus.UNVERIFIABLE,
        summary="No trusted external verifier or approver identity was configured.",
        evidence=(
            "No signature was generated, accepted, or attributed to a human.",
            "Self-approval and signer/principal separation cannot be established from an isolated policy probe.",
        ),
        claim_classification="Unknown",
    )


def check_signature_validation() -> VerificationCheck:
    return VerificationCheck(
        check_id="approval-signature-validation",
        category="authority",
        status=CheckStatus.UNVERIFIABLE,
        summary="No deployment-pinned public verifier or signed approval envelope was supplied.",
        evidence=(
            "The verifier creates no signature fixture and cannot claim external signature validity.",
            "Approval-gate behavior was checked without issuing a permit.",
        ),
        claim_classification="Unknown",
    )


def check_direct_execution_boundary() -> VerificationCheck:
    return VerificationCheck(
        check_id="direct-execution-boundary",
        category="authority",
        status=CheckStatus.UNVERIFIABLE,
        summary="No executor or deployed execution boundary was supplied.",
        evidence=("Permit-gating behavior does not prove that an external executor requires the permit.",),
        claim_classification="Unknown",
    )
