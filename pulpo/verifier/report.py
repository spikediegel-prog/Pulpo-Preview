"""Structured, explicitly scoped results for Pulpo verifier runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from .. import __version__

ClaimClassification = Literal["Verified", "Recorded", "Inferred", "Proposed", "Unknown"]


class CheckStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNVERIFIABLE = "UNVERIFIABLE"


@dataclass(frozen=True)
class VerificationCheck:
    check_id: str
    category: str
    status: CheckStatus
    summary: str
    evidence: tuple[str, ...]
    claim_classification: ClaimClassification


@dataclass(frozen=True)
class VerificationReport:
    schema: str
    generated_at: str
    version: str
    status: CheckStatus
    check_counts: dict[str, int]
    governance_score: dict[str, int | float]
    scope: dict[str, str]
    checks: tuple[VerificationCheck, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "generated_at": self.generated_at,
            "version": self.version,
            "status": self.status.value,
            "check_counts": self.check_counts,
            "governance_score": self.governance_score,
            "scope": self.scope,
            "checks": [
                {
                    **asdict(check),
                    "status": check.status.value,
                    "evidence": list(check.evidence),
                }
                for check in self.checks
            ],
        }


def build_report(checks: tuple[VerificationCheck, ...]) -> VerificationReport:
    passed = sum(check.status is CheckStatus.PASS for check in checks)
    failed = sum(check.status is CheckStatus.FAIL for check in checks)
    unverifiable = sum(check.status is CheckStatus.UNVERIFIABLE for check in checks)
    total = len(checks)
    status = (
        CheckStatus.FAIL
        if failed
        else CheckStatus.UNVERIFIABLE
        if unverifiable
        else CheckStatus.PASS
    )
    score = round((passed / total) * 100, 1) if total else 0.0
    return VerificationReport(
        schema="pulpo.verifier-report.v1",
        generated_at=datetime.now(timezone.utc).isoformat(),
        version=__version__,
        status=status,
        check_counts={
            "total": total,
            "pass": passed,
            "fail": failed,
            "unverifiable": unverifiable,
        },
        governance_score={"passed": passed, "total": total, "percentage": score},
        scope={
            "execution": "isolated in-memory kernel probes",
            "live_system": "not connected to a configured deployment or canonical state store",
            "authority_effect": "none_outside_ephemeral_probe; no permit leaves the probe scope",
            "governed_effect": "ephemeral kernel decisions, permit consumption, target, and audit writes",
            "canonical_state_mutation": "ephemeral probe state only; no live canonical state is read or changed",
            "boundary": (
                "External approval signatures, custody receipts, executor behavior, and event completeness "
                "require deployment evidence and are not inferred by these probes."
            ),
            "temporal_replay": (
                "not performed; this report makes no claim that a lesson transfers across historical checkpoints"
            ),
        },
        checks=checks,
    )
