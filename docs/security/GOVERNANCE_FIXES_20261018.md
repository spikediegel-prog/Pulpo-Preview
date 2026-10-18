# Governance security fixes — 2026-10-18

## Outcome and authority boundary

**Verified within isolated WSL fixtures:** the local governance audit's six
findings now have corresponding code guards and regression coverage. Authority
is narrowed; no new executor, policy authority, signing credential, ledger or
external provider route is introduced. Production service state and credentials
were not read, rotated or migrated by these tests.

The source baseline is the existing dirty local checkout at
`12d07e37a34c979fc054872299191bb26c8ad387`. Exact baseline and candidate file
hashes accompany this record; the HEAD SHA alone does not identify the code.

## Changes and evidence

| Finding | Change | Exact negative/positive evidence |
| --- | --- | --- |
| F1: expired custody orders | Check trusted time before preflight, inside the existing transmission transaction, and after canonical evidence projection immediately before purchase. The transmission payload records the order deadline. | Expired at entry, expired during preflight, expired during evidence projection and exact-deadline transactional rejection all make zero purchase calls. Existing successful execution and crash/reconciliation tests pass. |
| F2: in-memory replay race | Hold the existing reentrant state lock across issuance, approval replay, directive mutations and complete check/spend/evidence operations. | Scheduled concurrent consumers accept one permit once; the SQLite two-connection control also accepts one. |
| F3: invalid costs | Reject non-integer costs before budget comparisons; bool, fractional and non-finite values cannot obtain permits. | NaN, both infinities, fractions and bools deny; ordinary valid costs retain their existing behavior. |
| F4: old-policy/issuer permits | Bind canonical permits to the issuing policy hash and, for explicitly configured kernel keys, an HMAC-derived issuer tag. Enforce them at consumption in memory and SQLite. | A new policy cannot consume an old-policy permit; an explicitly rotated key cannot consume the old key's permit. Same-context valid use and restart/replay controls remain tested. |
| F5: approval lifetime | Store approval expiry as the permit execution deadline, alongside issue time, in the existing permit record. | Consumption after the signed approval deadline rejects in both backends and after SQLite restart. |
| F6: cross-worker approval polling | Store the authenticated worker identity in the existing authority request; require it on HTTP polls. Persist it through both authority adapters. | A distinct authenticated worker receives 404; the owner receives the signed envelope; missing authentication receives 401. SQLite restart preserves ownership. |

Core regressions are in `tests/test_governance_security_regressions.py` (13 tests).
Authority ownership regressions are in
`authority-service/tests/test_request_ownership.py` (3 tests). The replay test
uses a bounded constructed scheduling pause; it does not assert natural attack
frequency. No real provider or human credential is used.

## Migration and lifecycle behavior

- The existing SQLite `permits` table gains nullable `policy_hash`,
  `issued_at_ns`, `expires_at_ns` and `issuer_hash` columns in its initialization
  transaction. Historical audit rows are not rewritten.
- Kernel-level consumption rejects legacy permits without issuance context.
  It does not backfill current policy or fabricate an expiry for past authority.
  Previously authorized work may therefore require fresh authorization.
- The trusted state backend's direct fixture API remains compatible; it is not
  an exposed worker interface. Custom kernel state implementations must accept
  the new context parameters. They must not silently discard the checks.
- Approval-derived permits now expire at the approval deadline. This explicitly
  narrows the former issuance-only lifetime behavior. Ordinary policy permits
  have no invented global timeout; directive windows remain separately enforced.
- Explicitly configured kernel keys have an issuer binding. Default random
  per-process keys retain shared-state semantics. Old running kernels still
  configured with old keys are not magically revoked: deployment rotation must
  replace those runtimes. No global epoch authority was added.
- Legacy authority requests without recorded worker ownership remain readable
  to trusted in-process service code but cannot be claimed through the worker
  HTTP API. Submitted business principal is not substituted for authenticated
  ownership. The public human ceremony still requires its existing verification.
- If expiry occurs after transmission evidence was committed, the existing
  conservative transmitted state is retained and purchase is blocked. No retry,
  budget release or success is inferred from that condition; reconcile through
  the existing path.

No application database was opened during local source integration, and no
service was restarted. These migration rules take effect when the updated code
is subsequently used to open its own protected state.

## Validation

WSL Ubuntu / Python 3.14.4, warnings treated as errors, using the previously
reviewed constrained test runtime. Final results:

| Suite | Tests including skips | Result |
| --- | ---: | --- |
| Core | 657 | Pass; 2 Windows-only skips |
| Custody service | 45 | Pass; no skips |
| Authority service | 70 | Pass; 4 PostgreSQL integration skips (no test DSN) |

Total: **766 passed, 6 skipped, no failures**. The earlier audit baseline was
750 passed plus 6 skips; its eight exploratory assertions had seven failures.
The corrected candidate adds 16 regressions. One initial new-test error used an
empty credential fixture for a new authority database; that fixture was fixed
before the final passing run. Raw intermediate and final logs are retained.

From the repository root:

```bash
export PYTHONPATH="$PWD:$PWD/custody-service/src:$PWD/authority-service/src"
export PYTHONDONTWRITEBYTECODE=1
python -B -X utf8 -W error -m unittest discover -s tests -v
python -B -X utf8 -W error -m unittest discover -s custody-service/tests -v
python -B -X utf8 -W error -m unittest discover -s authority-service/tests -v
```

Exact executed runtime paths, working directories, environment overrides,
exit codes, source hashes and timings are in the accompanying
`governance-fixes/commands.jsonl`, `before.json` and `candidate-changes.json`.
The source patch, raw logs and preservation result are in
`Pulpo-governance-fixes-evidence.zip` from the local audit task's outputs.

## Canonical mutation review

Permit issuance stores policy/time/issuer context in the existing permit state
and records it in the existing canonical decision evidence. Consumption reads
that context under the existing state transaction/lock. Custody adds a deadline
condition to its existing transmission transition; it does not release a new
capability. Authority creation stores request ownership with the existing
request and durable snapshot; HTTP polling checks ownership before expiry or
pending-evidence work. Schema adoption stays within the existing SQLite
initialization transaction. No new worker write surface is exposed.

## Eight-pass adversarial review

| Pass | Disposition |
| --- | --- |
| Flip | Treat concurrent consumers, delayed holders and other authenticated workers as adversarial. |
| Reverse | Reject before spending an invalid context or releasing an expired transmission; check caller ownership before polling work. |
| Invert | A valid receipt, valid audit or provider acceptance cannot ratify expired authority. |
| Inside-Out | Apply deadline and ownership checks to the trusted executor and authority service as well as workers. |
| Darken | Held permits and delayed handles could accumulate consequences; bounded fixtures do not establish production compromise. |
| Lighten | Preserve shared default-key semantics and trusted in-process ownership access; do not infer a new global revocation service. |
| Amplify | Serialize complete replay transitions and retain spent/revoked state across the tested restarts. |
| Negate | Reuse canonical state/receipt/request boundaries; add no second router, ledger, signer or executor. |

Continue decision: integrate verified source changes only. Legacy source reuse
is limited to existing test helpers and canonical paths. Historical checkpoints
exist; historical temporal transfer was not run and no generally reusable
organizational lesson is being admitted by this current-source repair.

**Unknown/unproven:** live PostgreSQL integration, Windows behavior, production
deployment exploitability, all interleavings and provider-arrival timing after
the final pre-call check. External network containment and real provider-token
custody/revocation remain deployment controls. The tests do not eliminate a
provider's independent credentials or grant authority to modify them.

## Pull request source verification

The PR was independently tested against GitHub main
`c66b95edeb8e6a7a0ccb3ab6040697accdeeffc4` plus this repair delta. The fixture's complete base tree
matched `1f4d0b4a871a3197cae628ef542be51de25e07d6` before applying the changes. All eight
runtime-file preimages matched the local audited baseline after newline
normalization, so no unrelated local changes were transplanted. The PR's copy
of the earlier patch history retains the published version and appends only
this repair entry.

The exact PR candidate passed 657 core, 45 custody and 70 authority tests:
766 passed, 6 skipped, no failures. Read the
[validation manifest](2026-10-18/governance-fixes/summary.json) for exact commands,
source hashes and raw-log hashes, and the
[regression transcript](2026-10-18/governance-fixes/regression-summary.log) for
the 16 new regression results and all six skips.
