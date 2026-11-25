# E3 native Ubuntu state-upgrade proof

Verified on 2026-10-29 using synthetic state only. The existing canonical kernel
and SQLite migration remain the sole writer; no authority or product runtime
change is introduced by this test script.

`scripts/prove_e3_state_upgrade.py` reconstructs the real legacy checkpoint
`12d07e37a34c979fc054872299191bb26c8ad387` in a detached Git worktree. That old
kernel creates a new synthetic database and consumes a permit for a read action
available to its own policy. The current kernel opens the same database, retains
the exact audit prefix, verifies the chain and rejects that spent permit through
successive process restarts. No future credentials or approvals enter the old
checkpoint. Only a fixed public synthetic fixture secret is used; the temporary
database and permit are removed rather than exported into the evidence report.

The migration/persistence suites ran 39 tests without skips. A separate newer
schema fixture is rejected without modifying its SQL contents. Evidence:
`/home/spikediegel/pulpo-e3-evidence-20261029/remaining/state-upgrade-v2.json`
and its `.tests.log`. The initial fixture attempted to update the current
version=1 SQL constraint and was correctly blocked by SQLite; the corrected
fixture replaces the marker table as a newer producer would. The failed first
report is retained, not overwritten.

Verified scope is one real legacy schema to the current implementation, atomic
migration failure handling, restart consistency and replay refusal. Historical
adoption cannot prove a prefix lost before migration. Kernel/database downgrade
is unsupported; Control Center application rollback does not roll back canonical
state. This is not customer backup, physical durability or external integrity
qualification. No production state was opened.

## Doctrine record

1. Invariant/failure: migration preserves the existing audit prefix and spent
   permits; corruption, partial migration and unknown schema fail closed.
2. Authority delta: none. No new signer, executor, owner or policy expansion.
3. Canonical mutations: existing kernel writes only a disposable test database;
   future-schema refusal is checked against an exact pre/post SQL snapshot.
4. Evidence: 39 selected tests plus independent historical creation, migration,
   restart and future-schema refusal; exact source SHAs are in the JSON report.
5. Limits: no database downgrade or general all-version upgrade claim, no
   customer retention/external-copy responsibilities, no signed-release claim.
6. Claims: test outcomes Verified; reports Recorded; broader qualification Unknown.
7. Reuse: existing migration and persistence tests and canonical SQLite backend.
8. Temporal boundary: exact legacy worktree remains unchanged; current checks
   preserve old state without transporting future authority into the past.

Analytical passes: Flip/Reverse distinguish supported forward migration from
unsupported downgrade; Invert challenges corrupt/unknown state; Inside-Out
keeps the observer outside the writer; Darken tests missing/broken heads;
Lighten keeps scope synthetic; Amplify uses existing concurrency/transaction
tests; Negate verifies replay denial and rollback after failure. No review
grants release or deployment authority.
