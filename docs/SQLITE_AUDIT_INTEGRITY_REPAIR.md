# Local Preview SQLite integrity repair

Base: `12d07e37a34c979fc054872299191bb26c8ad387`.
Status: local candidate, not published or admitted. Date: 2026-10-17.

Follow-up evidence and two additional patches are recorded in
`SQLITE_ADVERSARIAL_RESULTS_20261017.md`. Counts below describe the first repair;
the follow-up record contains the latest test totals and source binding.

## Failure and resulting behavior

Initialization previously ran `executescript` followed by a legacy `ALTER` without
one enclosing transaction. An injected ALTER failure left newly created tables
behind. Initialization now executes individual DDL statements under one
`BEGIN IMMEDIATE`, including legacy validation, optional index creation, ALTER,
tip metadata adoption and trigger publication. Failure, including commit failure,
rolls the entire upgrade back and closes the connection.

The verification checkpoint remains disposable. Previously, deleting the final
audit row invalidated the checkpoint, then full verification accepted the shorter
valid prefix. The existing canonical audit now has subordinate `audit_head`
metadata, plus an `audit_integrity_schema` marker distinguishing legacy adoption
from an upgraded database whose head disappeared. These are not another ledger
or evidence source. The actual record bodies, hashes and sequence remain canonical.

For legacy adoption, validate the complete existing sequence-ordered chain before
publishing its tip. If a head already exists, require an exact match and preserve
it; never overwrite it to fit the remaining history. For upgraded databases,
missing or mismatched head metadata or missing append triggers rejects startup.
Normal reads check the tip and records within the same SQLite snapshot. Bootstrap
checks the tip before considering checkpoint fallback.

An audit insert checks its predecessor against both persisted tip metadata and
the actual last row. Its AFTER INSERT trigger advances the tip in the same
transaction. This covers both existing kernel appends and custody evidence
projection, without adding another callable writer. An exception during head
advancement rolls back the audit insert and its enclosing governed transition.

## Authority and compatibility

Authority gained: none. Acceptance is narrowed for missing or inconsistent audit
state. Existing permit, approval, replay, policy, custody and provider boundaries
remain in place. New metadata creation/legacy adoption occurs only in backend
initialization; tip advancement occurs within existing audit insert transactions.
No human signing credential, provider access or production database is required.

Record hashing and timestamp semantics are unchanged. Equal/decreasing timestamps
remain valid because canonical order uses SQLite sequence. Sequence edits are
rejected; no timestamp sorting or automatic repair/reordering of evidence is
introduced. The original independent review's exact implementation was not
identified, so this is a repair of reproduced local Preview behavior, not an
assertion that its unknown schema/API was copied or repaired verbatim.

Legacy adoption establishes only the valid history present at adoption. It cannot
detect a suffix already lost before adoption. Both audit and tip remain within
one mutable database; a hostile administrator can replace them together or restore
an older complete database. Independent rollback/fork/power-loss protection is not
claimed. Deliberately removing both the version marker and tip can imitate a legacy
database. Existing malformed-value coercion/worker-custody issues from PR #302 are
separate and are not claimed fixed by this patch.

## Executed evidence

- Verified: 73 focused tests pass with warnings treated as errors, covering
  migration rollback, commit failure, corrupt legacy data, matching/mismatched
  preexisting heads, missing head row/table, tail deletion, insert rollback,
  decreasing timestamps, separate-process restart, concurrent one-use/replay,
  custody projection and checkpoint fallback.
- Verified: 17/17 constitutional mutations killed by assertion failures, no
  survived/invalid mutations. Three new mutations remove the upgrade transaction,
  persisted-head comparison or insert guard. All mutated files restored byte for
  byte after the run.
- Recorded: the first broader run executed 585 tests, with 3 failures, 18 errors
  and 5 skips. The four failing modules rerun against untouched original source
  reproduced the same 3 failures/18 errors (44 tests, 1 skip). Errors involve
  Windows snapshot permissions and an inaccessible existing performance-profile
  path. This is not a passing full Windows suite.
- Verified final-source broader run: 587 tests in 62.454 seconds, with the same
  3 failures, 18 errors and 5 skips. All 21 failing/erroring test identities match
  the untouched-source baseline modules after normalizing import prefixes.
- Unknown: custody-service integration suite in this runtime; all six discovered
  modules failed import because the optional `fastapi` dependency is absent.
- No PostgreSQL, hosted CI, container deployment, live provider, or physical
  power-loss proof was performed.

The changed checkpoint test strengthens the expected behavior: tail deletion
must fail closed without publishing a replacement checkpoint. It no longer
treats shortened-history acceptance as a successful cache fallback.

## Eight-pass analytical review

- Flip: hostile/malformed input cannot choose a new head to match a shortened
  history. Missing and mismatched metadata are explicit denial cases.
- Reverse: prevent partial migration at the enclosing transaction and prevent
  silent tail adoption before cache fallback or a subsequent append.
- Invert: accepting a valid prefix is insufficient when it disagrees with the
  retained tip. Green cache verification cannot override that mismatch.
- Inside-Out: the cache grants no authority; tip metadata is subordinate to full
  chain verification, and same-database administrator compromise remains outside
  this bounded integrity claim.
- Darken: test ALTER denial, failed commit, missing table/row, mismatched prior
  head, corrupt legacy payload and failed tip update using disposable fixtures.
- Lighten: sequence permutation is rejected safely; it is not an authorized
  reconstruction/migration input. Existing clock rollback remains valid.
- Amplify: BEGIN IMMEDIATE serializes adoption and existing concurrent appends;
  existing replay/concurrency regressions remain passing.
- Negate: reuse the canonical append transactions and SQLite triggers rather
  than adding a second ledger, authority service or public writer.

Decision: bounded local candidate is reviewable; publication, merge and deployment
remain separate. Runtime outputs are Verified only for executed fixtures; wider
transfer and production guarantees remain Unknown. The exact base/candidate
comparison is local baseline evidence. No general organizational lesson or
cross-historical temporal-transfer claim is made.
