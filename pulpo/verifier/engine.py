"""Orchestrate bounded, isolated verifier probes."""

from __future__ import annotations

from . import audit, authority, custody
from . import constitutional
from .report import VerificationCheck, VerificationReport, build_report


def run_verification() -> VerificationReport:
    """Run probes against fresh in-memory kernel instances only."""

    checks: tuple[VerificationCheck, ...] = (
        constitutional.check_policy_constraints(),
        constitutional.check_target_binding(),
        constitutional.check_permit_replay(),
        constitutional.check_durable_replay_protection(),
        constitutional.check_revocation_enforcement(),
        constitutional.check_constitutional_artifact(),
        constitutional.check_unauthorized_mutation(),
        authority.check_mutation_approval_gate(),
        authority.check_authority_separation(),
        authority.check_independent_approval(),
        authority.check_signature_validation(),
        authority.check_direct_execution_boundary(),
        *custody.custody_checks(),
        *audit.audit_checks(),
    )
    return build_report(checks)
