# Pinned external approval authority

## Implemented contract

`AuthorityTrust` defines public trust fixed in policy before governed work
begins: authority, verifier, key identifier, algorithm, public-key fingerprint,
deployment identifier, and maximum approval lifetime. The complete descriptor
is hash-bound into canonical policy.

Approval envelope v2 defines the exact material an external human-approval
service must sign:

- schema, authority, verifier, key, deployment, and trust hash;
- approval and session identifiers;
- principal;
- exact intent hash;
- exact canonical policy hash;
- nonce, issue time, and expiration.

`GovernanceKernel` receives an `ApprovalVerifier` when the trusted kernel is
constructed. Its metadata must match policy trust at bootstrap and evaluation.
The governed caller cannot supply a verifier to `evaluate_with_approval()`.
The caller-controlled approval boolean has been removed from `evaluate()` for
every kernel, including kernels with no verifier. Approval-gated actions
therefore have no alternate permit-issuance path.

The session is part of canonical `Intent`. The kernel checks issue time,
maximum lifetime, expiry, and rollback using its bootstrapped clock before and
after verification. The approval call accepts neither a session override nor a
timestamp override. Domain-purchase intents derive their session from the
bounded request identifier.

The optional verification-only `Ed25519ApprovalVerifier` accepts one raw public
key and exposes no signer or private-key API. It uses the reviewed
`cryptography` package through the optional `pulpo[authority]` extra; the base
kernel remains dependency-free.

Approval IDs and nonces are consumed atomically when a permit is issued. With
`SQLiteKernelState`, those replay guards, the permit, and the canonical audit
records survive restart together. Signature failure, trust/key/deployment
mismatch, issue-time or lifetime failure, expiry, replay, missing or untrusted
verifier, non-boolean verification, clock rollback, and verifier exceptions all
fail closed and append public approval evidence to the same audit chain.

## Optional ceremony-evidence gate

Policies may opt selected approval-gated actions into a second, independent
evidence check with `ceremony_actions` and a pinned `CeremonyTrust`. Ceremony
actions must be a subset of approval actions, and the ceremony public-key
fingerprint must differ from the approval key fingerprint. Opt-in policy fields
are included in the policy hash; legacy policies without them retain their
existing hash.

For an opted-in action, the kernel requires separately signed
`CeremonyEvidence` binding the exact approval envelope hash and ID, intent and
policy hashes, principal, session, approval nonce, ceremony trust, method, and
bounded issue/expiry times. The kernel verifies this evidence before issuing a
permit. Evidence IDs are replay-checked and recorded atomically with the
existing `approval_verified` event and permit issuance; this adds no state
backend, ledger, or alternate authority route. Missing or invalid ceremony
evidence denies the action. Non-opted actions retain the existing approval
path.

`AuthorityClient` transports optional `ceremony_evidence` returned with an
approved poll, and the orchestrator passes it to the kernel without
interpreting it. The external service in this repository is only a contract:
there is no production ceremony issuer or verified WebAuthn integration. An
opt-in action therefore remains unavailable until deployment supplies evidence
signed by the independently pinned ceremony key. This verifies a configured
signature and its bindings; it does not prove that a human ceremony occurred.

## What this proves

The tests prove trust and public-key pinning, envelope binding, configured-
verifier routing, Ed25519 verification, key substitution denial, replay
rejection, permit issuance after successful verification, removal of the
boolean bypass, bounded trusted-clock semantics, and malformed-envelope denial.
The SQLite proof reopens the same state and proves consumed approval IDs,
nonces, and permits remain unusable, while persisted audit tampering blocks
kernel bootstrap. Concurrent presentation of one approval allows exactly once.
The ceremony tests additionally cover separate trust, exact evidence binding,
signature and expiry failures, legacy policy-hash compatibility, evidence
replay across SQLite restart and concurrent issuance, and verification-only
Ed25519/P-256 public-key verifiers. These are synthetic software tests, not
evidence of a production human ceremony.
The commerce proof uses this path and can place its bounded budget state in the
optional `SQLiteBudgetAccount`. That backend preserves reservations, attempted
orders, reconciliation evidence, and spend across ordinary restart; it does not
protect its database from a worker or host with file mutation or rollback
authority.

## Adversarial transformation review

For the opt-in ceremony gate:

| Pass | Assessment |
|---|---|
| Flip | A compromised caller can omit or substitute evidence; the kernel rejects missing or mismatched evidence. Trust in the configured verifier and bootstrap remains a deployment dependency. |
| Reverse | An unauthorized permit would require approval and ceremony evidence accepted by the kernel; the earliest blocking boundary is the kernel's policy, pinned verifiers, bindings, and atomic replay check. |
| Invert | A consequential outcome alone is not success; only a permit issued after both configured verifications is classified as governed. External effects remain outside this proof. |
| Inside-Out | The worker transports evidence but cannot configure the kernel verifier per call. The same deployment must still protect kernel bootstrap and must not let one signer self-attest both trust domains. |
| Darken | Threat case: an attacker controlling the ceremony signing key or its trusted issuer can create false ceremony attestations within policy bounds. This implementation cannot establish the issuer's real-world ceremony. |
| Lighten | The least severe supported interpretation is that the code verifies supplied signatures and exact bindings; production ceremony behavior is **Unknown**, not disproved or established. |
| Amplify | Evidence-ID reuse is checked in canonical state and at permit issuance, including concurrent SQLite calls. Fleet-wide key compromise, state rollback, and issuer outages are not proved away. |
| Negate | No second router or ledger is needed: the existing authority poll carries optional evidence to the existing kernel, and the existing audit event records its use. |

**Classification:** code-path and synthetic-test behavior is **Verified** by
the repository tests; the external service remains a **Recorded** contract;
real human participation and protected production bootstrap are **Unknown**.
Decision: continue with this opt-in, fail-closed kernel gate; do not describe it
as a production WebAuthn proof. The smallest next proof is an independently
operated issuer and deployment test that demonstrates the exact ceremony,
key-separation, bootstrap, replay, and failure properties.

## Boundary still open

This repository deliberately contains no production signer or private authority
material. Test signers are test fixtures, not human authentication or signer-
separation evidence. Python object checks do not protect bootstrap from a
hostile worker that can rebuild or mutate the running kernel.

Independent authority requires deployment evidence that:

1. the signer/private credential exists outside the governed workspace and is
   unreadable by the worker principal;
2. the agent cannot replace or reconfigure the verifier on the trusted running
   kernel;
3. the authority authenticates the human, preferably with a passkey and required
   user verification;
4. trusted bootstrap prevents the worker from replacing the kernel clock,
   intent session, verifier, nonce policy, or expiry policy;
5. the SQLite state file is protected from the governed worker and operated with
   deployment-grade rollback, backup, and recovery evidence;
6. verifier public material and configuration are deployed from a protected,
   auditable bootstrap rather than merely represented by the policy contract;
7. signer failure remains fail closed.

Until that deployment exists, claim **externally-verifiable approval-envelope
semantics with pinned asymmetric trust**, not independently human-authenticated
authority.

No historical Preview checkpoint with the same separate ceremony-evidence
gate was identified for temporal transfer. The merged Pulpo 1.0
ceremony-evidence change discussed during this work informed the implementation;
its code and control path were not copied. Preview's existing kernel, policy,
and canonical audit path remain the only permit and state authority.

See [the independent authority proof gate](INDEPENDENT_AUTHORITY_PROOF.md) for
the mandatory external acceptance tests, and see
[the authority boundary decision](AUTHORITY_BOUNDARY_DECISION.md) for the
owner-authorized deployment architecture.
