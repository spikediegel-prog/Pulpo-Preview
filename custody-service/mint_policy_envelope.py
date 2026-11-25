"""Mint a signed policy envelope for the custody-service sandbox policy.

Test/proof tooling only. Generates a fresh Ed25519 issuer keypair, builds the
exact service policy ``build_service`` constructs from the same configuration
values, signs its versioned hash, and prints the public key and the envelope
JSON for the caller to pass to the service as ``PULPO_AUTHORITY_PUBLIC_KEY_HEX``
and ``PULPO_POLICY_ENVELOPE_JSON``.

The service holds only the public key and cannot sign a policy itself; whoever
runs this script plays the issuing authority for one disposable proof run.
The keypair is fresh per run: nothing here is a standing credential.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, replace

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from pulpo import AuthorityTrust, Policy, PolicyEnvelope
from pulpo.kernel import policy_hash_for


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authority-id", required=True)
    parser.add_argument("--verifier-id", required=True)
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--deployment-id", required=True)
    parser.add_argument("--max-ttl-seconds", type=int, required=True)
    parser.add_argument("--budget-cents", type=int, required=True)
    args = parser.parse_args()

    private_key = Ed25519PrivateKey.generate()
    public = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    trust = AuthorityTrust(
        authority_id=args.authority_id,
        verifier_id=args.verifier_id,
        key_id=args.key_id,
        algorithm="ed25519",
        key_fingerprint=hashlib.sha256(public).hexdigest(),
        deployment_id=args.deployment_id,
        max_approval_ttl_ns=args.max_ttl_seconds * 1_000_000_000,
    )
    policy = Policy(
        frozenset({"purchase_domain"}),
        args.budget_cents,
        frozenset({"purchase_domain"}),
        authority_trust=trust,
    )
    unsigned = PolicyEnvelope(
        policy_hash=policy_hash_for(policy),
        version=policy.version,
        previous_policy_hash=policy.previous_policy_hash,
        authority_id=args.authority_id,
        verifier_id=args.verifier_id,
        key_id=args.key_id,
        deployment_id=args.deployment_id,
        trust_hash=trust.trust_hash,
        signature="",
    )
    envelope = replace(
        unsigned, signature=private_key.sign(unsigned.signing_bytes()).hex()
    )
    print(f"PULPO_AUTHORITY_PUBLIC_KEY_HEX={public.hex()}")
    print(
        "PULPO_POLICY_ENVELOPE_JSON="
        + json.dumps(asdict(envelope), sort_keys=True, separators=(",", ":"))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
