"""Shared exact-action construction for the GitHub Actions custody proof."""

from __future__ import annotations

import base64
from dataclasses import asdict, replace
from hashlib import sha256
import json

from pulpo import (
    AuthorityTrust,
    Ed25519ApprovalVerifier,
    GovernanceKernel,
    Intent,
    Policy,
    PolicyEnvelope,
)
from pulpo.kernel import policy_hash_for

ACTION = "create_proof_artifact"
PRINCIPAL = "github-actions:executor"
AUTHORITY_ID = "authority:github-environment-owner"
VERIFIER_ID = "verifier:github-actions-ed25519"
KEY_ID = "key:github-actions-custody:v1"
DEPLOYMENT_ID = "deployment:github-actions-custody:v1"
TTL_NS = 300_000_000_000


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def build_action(repository: str, ref: str, sha: str, run_id: str, run_attempt: str):
    artifact_name = f"pulpo-custody-{run_id}-{run_attempt}"
    receipt = {
        "schema": "pulpo.github-actions-custody.receipt.v1",
        "repository": repository,
        "ref": ref,
        "sha": sha,
        "run_id": run_id,
        "run_attempt": run_attempt,
        "artifact_name": artifact_name,
    }
    payload = canonical(receipt)
    payload_hash = sha256(payload).hexdigest()
    session_id = f"github-run:{run_id}:{run_attempt}"
    resource = ":".join(
        ("github-actions-artifact", repository, sha, run_id, run_attempt, artifact_name, payload_hash)
    )
    return Intent(PRINCIPAL, ACTION, resource, 0, session_id), artifact_name, payload


def build_policy(public_key: bytes):
    """The exact policy the authority signs envelopes for; deterministic."""

    verifier = Ed25519ApprovalVerifier(
        authority_id=AUTHORITY_ID,
        verifier_id=VERIFIER_ID,
        key_id=KEY_ID,
        public_key=public_key,
    )
    trust = AuthorityTrust(
        authority_id=AUTHORITY_ID,
        verifier_id=VERIFIER_ID,
        key_id=KEY_ID,
        algorithm=verifier.algorithm,
        key_fingerprint=verifier.key_fingerprint,
        deployment_id=DEPLOYMENT_ID,
        max_approval_ttl_ns=TTL_NS,
    )
    policy = Policy(frozenset({ACTION}), 0, frozenset({ACTION}), authority_trust=trust)
    return verifier, trust, policy


def sign_policy_envelope(policy, trust, sign):
    """Sign the policy's versioned hash; the signer holds the issuer key."""

    unsigned = PolicyEnvelope(
        policy_hash=policy_hash_for(policy),
        version=policy.version,
        previous_policy_hash=policy.previous_policy_hash,
        authority_id=trust.authority_id,
        verifier_id=trust.verifier_id,
        key_id=trust.key_id,
        deployment_id=trust.deployment_id,
        trust_hash=trust.trust_hash,
        signature="",
    )
    return replace(unsigned, signature=sign(unsigned.signing_bytes()))


def build_kernel(public_key: bytes, now_ns: int, *, policy_envelope=None):
    verifier, _trust, policy = build_policy(public_key)
    return GovernanceKernel(
        policy,
        approval_verifier=verifier,
        clock=lambda: now_ns,
        policy_envelope=policy_envelope,
    ), _trust


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def unb64(value: str) -> bytes:
    return base64.b64decode(value.encode(), validate=True)


def envelope_json(envelope) -> bytes:
    return canonical(asdict(envelope))
