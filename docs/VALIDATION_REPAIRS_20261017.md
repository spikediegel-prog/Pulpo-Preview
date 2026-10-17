# Strict audit verification and complete execution-handle binding

Claim classification: executable local evidence at the final recorded commit is
**Verified** only within disposable SQLite/fake-provider boundaries. Independent
certification, service endpoints, PostgreSQL and production behavior are **Unknown**.
Exact commands, logs, hashes, counts and baseline comparisons are delivered in
the round 4 evidence package outside the repository.

## Invariants and repairs

1. Normal, accelerated and checkpoint verification must not change the meaning
   of persisted audit values. A stored fractional timestamp previously became an
   integer in the accelerated reader, allowing a wrong digest acceptance and an
   authenticated checkpoint that survived restart. The reader now returns exact
   validated values. Storage reads and bootstrap check types before trusting any
   cached prefix, including a cache published by the old implementation. The
   optional engine checks types before cache lookup/worker dispatch; normal
   kernel verification also checks canonical field types. Float/bool/int cache
   key equality cannot substitute one type for another.
2. Invalid execution handles must not claim custody, flush pending evidence,
   preflight an adapter or execute a provider request. The executor now validates
   the complete existing authorization commitment against the persisted attempt,
   nested attempt identity, original creation epoch, receipt schema/type/object,
   and existing custody receipt signature before any of those effects.

`budget_ceiling_cents` is now a required field of `GovernedDomainAttempt`; it was
already included in the original authorization commitment, but was absent from
the returned handle. The coordinator supplies it, and the executor recomputes
the unchanged `pulpo.custody-authorization.v0` commitment using the stored permit
hash and all bound handle fields. The authorization hash format and database
schema are unchanged. Old manually constructed or serialized handles missing
this field must fail closed; callers must use the trusted coordinator's complete
handle. Do not invent replacement approvals or reissue spent permits to adapt.

## Authority and canonical state

Authority is narrowed: no extra approval, signing key, permit, writer, router,
ledger or provider capability is introduced. The same executor remains the sole
entry point for this bounded domain path. Handle validation is read-only and
precedes existing custody/evidence mutation. Accepted handles follow the existing
one-use transmission and reconciliation lifecycle. Receipt verification uses
the already trusted custody verifier, with synthetic test credentials only.

The patch adds no canonical mutation. Existing audit checkpoint publication,
custody claim/transmission and evidence projection retain their current governed
boundaries. No persistent data is silently coerced or repaired: malformed audit
state raises an integrity failure. Legitimate receipt/authorization provenance
does not independently prove a provider outcome.

## Adversarial transformation review

- **Flip:** treat caller-supplied handles and stored row types as hostile. Test
  every previously unchecked field, nested receipt mutations and numeric aliases.
- **Reverse:** prevent the first side effect by validating before claim/resume;
  prevent bad cache publication/acceptance before prefix verification.
- **Invert:** a plausible hash, signed cache or provider claim cannot excuse
  malformed provenance. Old poisoned authenticated caches must reject unchanged.
- **Inside-Out:** test both verifier routes and the cache itself. Signed receipt
  authenticity is checked independently of the supplied handle commitment.
- **Darken:** compose malformed timestamp, optional acceleration, checkpoint and
  restart; compose altered handle, resumed executor and unrelated pending evidence.
- **Lighten:** corruption or redundant metadata can explain the original cases.
  They do not prove arbitrary orders, budget overspending or a remote exploit.
- **Amplify:** retain seeded state-model steps, rollback injections, repeated
  projection, bounded load, and lost-response/restart/replay controls.
- **Negate:** disposable SQLite and fake adapters provide the proof without
  production data, real credentials or external execution.

Stop/continue reconciliation: the reproduced side effects were confined to
synthetic fixtures. No alternate external route or credential export was created
or used. Continue only through the existing bounded executor. Smallest next proof:
the exact unchanged 30-probe oracle must pass, and removal of each new protection
must produce assertion failures in the committed regression suite.

## Evidence and temporal scope

The unchanged external oracle was red at base
`f34f71e2dbeeb9bb5d1934a6cbe69ebbb7debbfe` (30 tests, 11 failures, zero errors).
The matching verifier/handle subset also reproduced on the untouched original
checkout at its separately recorded exact SHA (24 tests, 10 failures). Compare
these exact baselines with the final candidate, preserving the same synthetic
authority, policies, budgets and fake providers. No future authority is imported
into those baseline states. This is bounded regression transfer, not a generally
reusable organizational lesson or a claim of independent third-party approval.

Repository tests include old authenticated-cache rejection, cache type aliases,
all handle substitutions (including the newly supplied budget ceiling), altered
receipts and zero adapter/projection side effects. The original external oracle
remains unchanged for independent red/green comparison. Targeted weakening tests
check handle validation, engine type checks, old-cache type checks and receipt
signature verification; all sources must be restored byte-for-byte afterward.

## Boundaries

Same-database administrator trust and whole-database rollback/fork limits remain.
This does not solve fork-inherited worker capabilities, real power loss, fleet
aggregation or live provider semantic drift. Direct SQLite returns integrity
exceptions for malformed row types; callers must treat these as denial. Optional
FastAPI service tests and PostgreSQL require a separate environment; do not
interpret their unavailable coverage as a pass. Existing Windows full-suite
failures must remain visible and be compared by exact problem identity.

## Recorded final checks

Verified: unchanged external oracle 30/30 PASS; focused suite 163/163 PASS;
34 new repository methods; all four deliberate weakenings killed by assertion
failures. Full suite: 632 tests in 109.838s, 3 failures, 18 errors, 5 skips; all
21 failure/error identities match the untouched original Windows baseline.
Original checkout hashes and status unchanged. Mutation sources restored byte
for byte. A trailing blank line was removed after testing; Python AST unchanged.
