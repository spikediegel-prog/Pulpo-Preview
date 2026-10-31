"""Isolated probes for the kernel's observable policy and permit contracts."""

from __future__ import annotations

from ..kernel import GovernanceKernel, Intent, Policy
from .report import CheckStatus, VerificationCheck


def check_policy_constraints() -> VerificationCheck:
    kernel = GovernanceKernel(Policy(frozenset({"read"}), max_cost=5))
    allowed = kernel.evaluate(Intent("agent:verifier", "read", "repo:item", 5))
    over_budget = kernel.evaluate(Intent("agent:verifier", "read", "repo:item", 6))
    unknown_action = kernel.evaluate(Intent("agent:verifier", "write", "repo:item", 0))
    passed = (
        allowed.outcome == "allow"
        and over_budget.outcome == "deny"
        and over_budget.reason == "budget_exceeded"
        and unknown_action.outcome == "deny"
        and unknown_action.reason == "action_not_allowed"
    )
    return VerificationCheck(
        check_id="policy-constraints",
        category="constitutional",
        status=CheckStatus.PASS if passed else CheckStatus.FAIL,
        summary=(
            "Configured action and cost constraints were enforced."
            if passed
            else "A sample intent crossed a configured action or cost boundary."
        ),
        evidence=(
            f"allowed_at_limit={allowed.outcome}",
            f"over_budget={over_budget.outcome}:{over_budget.reason}",
            f"unknown_action={unknown_action.outcome}:{unknown_action.reason}",
        ),
        claim_classification="Verified",
    )


def check_target_binding() -> VerificationCheck:
    kernel = GovernanceKernel(Policy(frozenset({"read"}), max_cost=5))
    intent = Intent("agent:verifier", "read", "repo:exact-target", 1, "verifier-session")
    target = kernel.lock_target("verifier-target", intent)
    exact = kernel.resolve_locked_target("verifier-target", target.target_hash)
    substitute_hash = ("0" if target.target_hash[0] != "0" else "1") + target.target_hash[1:]
    substituted = kernel.resolve_locked_target("verifier-target", substitute_hash)
    passed = (
        exact.outcome == "match"
        and exact.target == target
        and substituted.outcome == "deny"
        and substituted.reason == "target_hash_mismatch"
        and substituted.target is None
    )
    return VerificationCheck(
        check_id="target-binding",
        category="constitutional",
        status=CheckStatus.PASS if passed else CheckStatus.FAIL,
        summary=(
            "Only the exact locked target resolved."
            if passed
            else "A substituted target reference was not rejected."
        ),
        evidence=(
            f"exact_target={exact.outcome}:{exact.reason}",
            f"substituted_hash={substituted.outcome}:{substituted.reason}",
        ),
        claim_classification="Verified",
    )


def check_permit_replay() -> VerificationCheck:
    kernel = GovernanceKernel(Policy(frozenset({"read"}), max_cost=5))
    intent = Intent("agent:verifier", "read", "repo:replay-probe", 1)
    decision = kernel.evaluate(intent)
    first_use = (
        kernel.consume(decision.permit, intent)
        if decision.outcome == "allow" and decision.permit is not None
        else False
    )
    replay = (
        kernel.consume(decision.permit, intent)
        if decision.permit is not None
        else False
    )
    passed = first_use and not replay
    return VerificationCheck(
        check_id="permit-replay-protection",
        category="replay",
        status=CheckStatus.PASS if passed else CheckStatus.FAIL,
        summary=(
            "The isolated one-use permit was consumed once and replay was denied."
            if passed
            else "The isolated permit was missing, unusable, or accepted more than once."
        ),
        evidence=(
            f"issuance={decision.outcome}:{decision.reason}",
            f"first_use={first_use}",
            f"second_use={replay}",
        ),
        claim_classification="Verified",
    )


def check_revocation_enforcement() -> VerificationCheck:
    return VerificationCheck(
        check_id="directive-revocation",
        category="replay",
        status=CheckStatus.UNVERIFIABLE,
        summary="No deployment authority verifier or live directive state was supplied.",
        evidence=(
            "The verifier does not activate or revoke canonical directives.",
            "The repository's governed directive path requires external approval; this probe does not synthesize it.",
        ),
        claim_classification="Unknown",
    )


def check_durable_replay_protection() -> VerificationCheck:
    return VerificationCheck(
        check_id="durable-permit-replay-protection",
        category="replay",
        status=CheckStatus.UNVERIFIABLE,
        summary="No configured persistent kernel state was supplied.",
        evidence=(
            "The one-use replay probe used fresh in-memory state.",
            "Restart and storage-backend guarantees were not inferred.",
        ),
        claim_classification="Unknown",
    )


def check_constitutional_artifact() -> VerificationCheck:
    return VerificationCheck(
        check_id="constitution-signature",
        category="constitutional",
        status=CheckStatus.UNVERIFIABLE,
        summary="No separately signed constitutional artifact is exposed to this verifier.",
        evidence=("Policy behavior was probed; signature validity for a deployment constitution was not assessed.",),
        claim_classification="Unknown",
    )


def check_unauthorized_mutation() -> VerificationCheck:
    return VerificationCheck(
        check_id="unauthorized-policy-mutation",
        category="constitutional",
        status=CheckStatus.UNVERIFIABLE,
        summary="The verifier is not connected to a deployed policy-mutation boundary.",
        evidence=("Isolated policy fixtures do not establish which principals can mutate deployed policy.",),
        claim_classification="Unknown",
    )
