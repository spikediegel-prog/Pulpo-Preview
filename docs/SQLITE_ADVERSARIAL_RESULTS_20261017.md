# Additional SQLite adversarial evidence - 2026-10-17

Local repair branch: `fix/sqlite-audit-integrity-20261017`.
Initial runtime commit: `ded9d24392b5136b0374377c0a2554b9808dc569`.
Original local base: `12d07e37a34c979fc054872299191bb26c8ad387`.
The exact successor commit and tested-source hashes are recorded in the external
evidence manifest and PDF. No push, merge, production database migration or
provider action was performed.

## New findings and patches

The initial additional suite ran 10 methods and had four assertion failures,
without test errors. Two substituted triggers retained the expected names but
startup accepted them. Legacy head rows with floating-point sequence or ID
compared equal to integers and were also accepted.

Startup now compares normalized stored SQL definitions against the same constants
used to create the two canonical audit-head triggers. It checks the trigger's
table as well as name and body. Head IDs/sequences and schema markers now require
actual integer values; head digests require text. Mismatches reject without
overwriting evidence. The original atomic migration and durable-tip repairs
remain in place. No new writer, ledger, authority or credential is introduced.

## Additional test matrix

1. Same-name trigger substitution: both insert guard and tip-advance trigger
   replaced with no-op bodies. Expected: startup rejects, database unchanged.
2. Malformed prior heads: duplicates, wrong ID, float ID, float/text sequence,
   ahead/behind tip, wrong/text/BLOB/NULL digest cases. Expected: reject unchanged.
3. Float schema marker: reject without mutation.
4. Delete all audit rows and the disposable checkpoint: startup and further
   appends reject; the retained head prevents accidental reset.
5. SQLite page-quota exhaustion during approval/permit/audit issuance: rollback
   every table, release transaction, then accept the exact retry after lifting
   the quota. Run in DELETE and WAL modes; SQLite integrity_check returns ok.
6. Five successive failed tip updates followed by recovery: no partial approval
   or permit; exact retry succeeds once and approval replay is denied.
7. Legacy adoption, one-use permit and reopen persistence: run under DELETE and
   WAL journals, synchronous FULL, with decreasing/equal timestamps.
8. Two separate processes simultaneously upgrade the same legacy file and append:
   both complete, one head and one chain, no lost append, in both journal modes.
9. Abrupt process termination: kill before/after migration commit and before/after
   append commit, in both journal modes (eight kill checkpoints). Uncommitted
   changes disappear; committed changes persist; chain and integrity_check pass.
10. Boundary confirmation: restoring a complete older database is accepted.
    This confirms the documented unresolved rollback boundary, not protection.
11. Boundary confirmation: two copied descendants can each consume the same
    previously unspent permit. This confirms the unresolved cross-copy boundary.

The last two methods pass by asserting the observed limitation. They must not be
counted as successful rollback/fork prevention. The suite contains 11 methods:
nine resilience/validation methods and two boundary-confirmation methods, with
parameterized subcases. These are synthetic tests, not statistical reliability
or independent-person approval.

## Final execution

focused: Ran 84 tests in 14.852s / OK
Exit: 0
full: Ran 598 tests in 72.310s / FAILED (failures=3, errors=18, skipped=5)
Exit: 1

Mutations: 19/19 killed; zero survived or
invalid. All kills include assertion failures, and source bytes were restored.
Two new mutation cases remove the trigger-definition and strict-head-type guards.
All 21 failing/erroring identities in the full run match the untouched original
baseline modules after normalizing import prefixes. Existing Windows snapshot
permissions and the inaccessible performance-profile path remain unresolved.
An initial full attempt ran 592 tests with 3 failures, 22 errors and 5 skips:
Git ownership rejection added four proof errors and prevented a class setup.
Its complete log is retained as additional-full-initial-environment.log. The final
rerun supplied a process-scoped Git safe.directory exception for this worktree;
no source or global Git setting changed. This enabled the missing proof methods,
producing the final 598-test count above.
The optional custody-service attempt from the preceding repair run had six import
errors because fastapi was absent; it was not rerun here. No live PostgreSQL tests.

Original checkout hashes unchanged: True.
Original checkout Git status unchanged: True.
Runtime/test source hashes unchanged during final suites: True.

## Reproduction and logs

Python 3.12.14; SQLite 3.53.1; Windows; warnings treated as errors.
Exact executable, argument arrays, working directory, exits and source SHA-256
values are recorded in additional-test-results.json. Complete initial failures,
final focused/full output, 19 mutation logs and baseline output accompany it.
All database writes are under disposable TemporaryDirectory fixtures. Processes
are terminated/joined before cleanup. No original database is opened by a probe.
The final full-run environment also sets GIT_CONFIG_COUNT=1,
GIT_CONFIG_KEY_0=safe.directory and GIT_CONFIG_VALUE_0 to the repair worktree.

Command: C:\Users\spike\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -X utf8 -W error -m unittest tests.test_audit_adversarial tests.test_audit_integrity_migration tests.test_persistence tests.test_audit_checkpoint tests.test_unique_audit_scan tests.test_custody_evidence tests.test_sqlite_connection_cleanup -v
Working directory: C:\Users\spike\Documents\Codex\2026-10-17\referenced-chatgpt-conversation-this-is-an-2\work\Pulpo-Preview-repair

Command: C:\Users\spike\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -X utf8 -W error -m unittest discover -s tests -v
Working directory: C:\Users\spike\Documents\Codex\2026-10-17\referenced-chatgpt-conversation-this-is-an-2\work\Pulpo-Preview-repair

## Eight-pass review and scope

Flip: substitute stored protection bodies instead of trusting their names.
Reverse: trace accepted metadata to Python numeric equality; enforce exact types.
Invert: successful import/startup is insufficient when protective SQL changed.
Inside-Out: same-file metadata cannot independently establish non-rollback or
non-fork history; copied descendants demonstrate this explicitly.
Darken: quota failures and forced termination exercise bounded storage/process
failure points, without representing them as physical power loss.
Lighten: distinguish nine positive resilience methods from two reproduced limits.
Amplify: concurrent processes and repeated failed retries preserve one file's
transaction boundaries; cross-copy global single-use remains unproved.
Negate: compare existing definitions and types; no new authority plane or service.

Verified: executed fixtures, observed initial failures, post-patch outputs.
Recorded: previous optional-service and independent-review statements.
Unknown: original independent-review API/commit; administrator-wide tampering;
concurrent hostile schema-edit races; whole-file rollback/fork prevention;
physical disk/power-loss behavior; managed PostgreSQL/staging; production or
provider containment; independent formal approval. A newer remote Preview branch
exists; this local candidate remains based on the original recorded local main.

No historical transfer or general reusable organizational lesson is claimed.
Source baseline/candidate comparison is bounded local regression evidence.
Decision: local candidate is reviewable; no external deployment/admission claim.
