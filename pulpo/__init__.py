"""Pulpo governed-execution kernel."""

__version__ = "0.1.0"

from .accountability import AccountableContext, AccountableContextObservation, AccountableGovernance

from .authority import (
    ApprovalEnvelope,
    ApprovalVerifier,
    AuthorityTrust,
    DualControlTrust,
    Ed25519ApprovalVerifier,
    EnrolledKeyTrust,
    EnvelopeSignature,
    P256ApprovalVerifier,
    PolicyEnvelope,
    PolicyEnvelopeV2,
    PolicyVeto,
)
from .authority_client import AuthorityApprovalRequest, AuthorityClient, AuthorityPoll
from .audit_parallel import AuditDigestCache, AuditVerificationEngine
from .ceremony import (
    CeremonyEvidence,
    CeremonyTrust,
    CeremonyVerifier,
    Ed25519CeremonyVerifier,
    P256CeremonyVerifier,
)
from .commerce import SQLiteBudgetAccount
from .kernel import (
    AgentGrant,
    AuthorityTrustError,
    Decision,
    GovernanceKernel,
    Intent,
    LockedTarget,
    Policy,
    PolicyEnvelopeError,
    PolicyVetoError,
    PresenterVerifier,
    StateIntegrityError,
    TargetResolution,
    policy_hash_for,
)
from .namecom import NameComCoreAdapter
from .permit_gate import PermitGate, PermitRefused, require_permit, spend_permit
from .performance_tuning import (
    AdaptiveAuditVerificationEngine,
    AuditPerformanceTuner,
    PerformanceProfile,
    SystemFingerprint,
)
from .provenance import SemanticProvenance, artifact_hash
from .orchestrator import (
    ApprovalHandle,
    AuthorizationAttempt,
    EvidenceSnapshot,
    OrchestrationError,
    PulpoOrchestrator,
)
from .state import InMemoryKernelState, KernelState, SQLiteKernelState, StateClockError, StateRecoveryError, capture_recovery_pin
from .resources import ResourceScope
from .target_reconcile import (
    ArtifactCompletionEvidence,
    GovernedTargetReconciliation,
    TargetObligationStatus,
)
from .targets import evaluate_locked_target_with_approval

__all__ = [
    "StateRecoveryError",
    "StateClockError",
    "capture_recovery_pin",
    "ResourceScope",
    "AdaptiveAuditVerificationEngine",
    "AccountableContext",
    "AccountableContextObservation",
    "AccountableGovernance",
    "AgentGrant",
    "ApprovalEnvelope",
    "ApprovalHandle",
    "ArtifactCompletionEvidence",
    "AuthorityApprovalRequest",
    "AuthorityClient",
    "AuthorityPoll",
    "ApprovalVerifier",
    "AuthorityTrust",
    "AuthorityTrustError",
    "CeremonyEvidence",
    "CeremonyTrust",
    "CeremonyVerifier",
    "AuditDigestCache",
    "AuditVerificationEngine",
    "AuditPerformanceTuner",
    "AuthorizationAttempt",
    "Decision",
    "DualControlTrust",
    "Ed25519ApprovalVerifier",
    "EnrolledKeyTrust",
    "EnvelopeSignature",
    "Ed25519CeremonyVerifier",
    "EvidenceSnapshot",
    "GovernanceKernel",
    "GovernedTargetReconciliation",
    "InMemoryKernelState",
    "Intent",
    "KernelState",
    "LockedTarget",
    "NameComCoreAdapter",
    "OrchestrationError",
    "P256ApprovalVerifier",
    "P256CeremonyVerifier",
    "PerformanceProfile",
    "PermitGate",
    "PermitRefused",
    "Policy",
    "PolicyEnvelope",
    "PolicyEnvelopeError",
    "PolicyEnvelopeV2",
    "PolicyVeto",
    "PolicyVetoError",
    "PresenterVerifier",
    "PulpoOrchestrator",
    "policy_hash_for",
    "SQLiteBudgetAccount",
    "SQLiteKernelState",
    "SemanticProvenance",
    "StateIntegrityError",
    "SystemFingerprint",
    "TargetObligationStatus",
    "TargetResolution",
    "artifact_hash",
    "evaluate_locked_target_with_approval",
    "require_permit",
    "spend_permit",
]
