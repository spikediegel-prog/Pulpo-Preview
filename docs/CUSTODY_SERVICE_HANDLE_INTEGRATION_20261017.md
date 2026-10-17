# Complete custody references across the service boundary

## Failure and scope

Verified at PR #14 commit `6b1919b96bb3be1d1d1d8253535fabcb91ee8010`:
GitHub's custody-service suite ran 26 tests with two failures. The same failures
reproduce locally after installing repository-pinned dependencies in an isolated
virtual environment. Valid execution requests returned 409 because the service
still supplied a three-field `SimpleNamespace` to an executor that now requires
the complete validated `GovernedDomainAttempt`.

The other failed CI job, `test`, is the admission dependency gate: custody failed
and container isolation was skipped. It is not a separate runtime defect.

## Repair and authority delta

The trusted service authorization path records the original complete coordinator
handle and its already signed custody receipt in the existing canonical audit
as `custody_domain_authorization`, after canonical permit consumption, protected
reservation attempt and successful custody authorization. No new ledger or table
is introduced. The worker's external opaque handle and HTTP schema are unchanged;
the worker receives no full reference, permit, signing credential or new route.

Execution and reconciliation reload exactly one matching record through a
verified kernel session. Missing, malformed or duplicate preimages fail closed.
All echoed external fields must match; the full preimage and original receipt
must still match the stored custody authorization commitment and verifier before
pending evidence may be projected or any adapter/observer invoked. The executor's
validation remains in place at its own entry point.

This adds one canonical audit append per successful trusted service
authorization, under the existing exact authorization flow. It exposes no new
writer to the worker and does not grant or expand authority. The record supplies
durable commitment metadata, not a fresh authorization source. A valid audit
cannot ratify a different policy, reservation, signed receipt or consequence.

The append occurs after custody commit. If the append fails or the process dies
first, the one-use permit remains spent and no executable handle can be returned
or recreated from worker fields. Availability may be lost; authority is not
reissued. Old service attempts without this complete persisted record remain
fail-closed; no live data migration or automatic approval/permit repair is made.

## Evidence

The candidate service suite has 32 tests: the original 26 plus six methods that
cover seven changed worker fields across execute/reconcile, a pending unrelated
evidence obligation, service reconstruction before execution and reconciliation,
replay, failed authorization append, duplicate records, changed stored policy or
receipt in an otherwise valid audit, and valid recovery with pending evidence.
The candidate passes all 32 under `-W error`, using disposable SQLite and fake
providers/observers. URL/handle identity mismatch returns the existing HTTP 400;
other altered references return 409. No real provider requests are made.

The 163 focused core regressions are rerun in the same isolated environment.
Three targeted weakening checks exercise projection-before-validation,
first-record selection on ambiguity, and omission of service-side provenance
validation. Exact outcomes, commands, logs and source hashes are retained in the
operator's evidence package; remote CI must validate the pushed final commit.

## Eight-pass review

- **Flip:** hostile worker metadata is compared with the original trusted record
  before any governed evidence/custody effect or provider/observer call.
- **Reverse:** trace HTTP 409 back to the incomplete internal reference; recover
  provenance through the existing audit rather than weakening executor checks.
- **Invert:** an internally valid audit record or provider success is insufficient
  if its preimage does not match original custody commitment and receipt.
- **Inside-Out:** distrust the audit preimage itself; valid-chain forged policy,
  forged signature, extra receipt fields and ambiguity must reject.
- **Darken:** combine an altered external handle with resumed service and pending
  unrelated evidence. Both execution and reconciliation must remain non-mutating.
- **Lighten:** the CI failure is an integration mismatch, not evidence of an
  arbitrary provider bypass. Keep legitimate restart recovery working.
- **Amplify:** reuse handles after restart and after one transmission; each fake
  consequence remains one-use, with conservative reconciliation semantics.
- **Negate:** persist only subordinate metadata in the existing audit. Do not
  create a second authority store, accept worker-reconstructed orders, re-sign
  substituted credentials or relax the complete-handle validator.

Stop/continue: no alternate external route or new credential-bearing capability
was created. Continue only through the existing trusted service/executor seams.
The smallest next proof is the final commit's custody and container/admission CI.

## Boundaries and classification

Verified: baseline reproduction and candidate disposable local cases. Recorded:
previous GitHub failure and subsequent CI outcomes by exact commit. Unknown until
CI completes: remote candidate service/container/admission results. Production,
real providers, hardware power loss and same-store administrator rollback/fork
resistance remain outside this proof. Local Windows full-suite limitations from
the previous report remain; the whole core suite was not rerun locally for this
service-only source change.

Temporal transfer is limited to the exact failing service commit and its
candidate, preserving synthetic policy, authority, budget and provider behavior.
No general organizational lesson, future authority or independent certification
is imported into that comparison.

Final local checks: service32/32 and focused core163/163 pass with warnings
as errors. All three weakenings are killed by assertion failures; mutated
source is restored byte-for-byte. The initial mutation campaign exposed a missing
observer-call assertion, which was strengthened before final validation.
