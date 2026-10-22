# Guarded SQLite recovery

Status: Proposed. This is an explicit recovery-opening guard for the existing
canonical state backend. It is not automatic protection against arbitrary file
replacement, a recovery authorization, or a new checkpoint service.

An intact older SQLite snapshot can contain an unspent permit even after that
permit was spent in the later database. Its own audit chain cannot prove it is
current. Recovery must compare against the latest trusted state retained outside
the backup's rollback domain. If that reference is unavailable, execution stays
stopped. Never create the expected checkpoint from the backup being recovered.

## Bounded operator procedure

1. Quiesce all governed execution, external effects and state writers. Establish
   the latest trusted canonical state and verify its audit through the existing
   `GovernanceKernel`. Do not certify a compromised database by hashing it.
2. Call `state.recovery_checkpoint()` on that verified state and retain the
   returned comparison value through the operator's existing trusted custody
   process, independently of database rollback. It contains a digest, not a
   credential or permit. Every later canonical write makes that pin stale.
   This change does not invent or certify a custody mechanism.
3. Use SQLite's backup API for a consistent snapshot while quiesced. Confirm the
   pin still describes the latest trusted state. A backup older than that state
   cannot resume execution through this guard; missing post-backup effects
   require a separately authorized reconciliation, not replay or fresh grants.
4. Restore only into a controlled recovery location with execution stopped.
   Open it with the required current checkpoint:

   ```python
   from pulpo import SQLiteKernelState, GovernanceKernel

   state = SQLiteKernelState.recover(
       restored_path, expected_checkpoint=trusted_current_checkpoint
   )
   try:
       kernel = GovernanceKernel(existing_policy, secret=existing_secret,
                                 approval_verifier=existing_verifier, state=state)
       # Existing audit, policy, identity, expiry and replay checks still apply.
       # Resume only through the deployment's separately governed recovery process.
   finally:
       state.close()
   ```

5. Missing, malformed, stale, substituted, unsupported or incomplete state stops
   recovery. Do not fall back to ordinary `SQLiteKernelState(path)` construction,
   regenerate a pin from the candidate, clear replay tables, rotate credentials,
   or issue replacement authority to make recovery pass.

## Implementation and limits

The guard opens an existing file only (`mode=rw`). In the initialization
transaction, `BEGIN IMMEDIATE` holds the writer lock across comparison and
existing schema checks. Comparison happens before migrations or cache creation.
It binds the canonical table contents and schema, including permits, spent bits,
approvals/nonces, directives/revocations, bindings, full audit and head metadata.
Unknown tables/views are refused. A matching audit tip alone is insufficient.
The disposable verification-cache contents are excluded; cache triggers are
included in the schema pin. Kernel bootstrap still verifies the audit afterward.
Capture uses a read transaction and refuses a pending caller transaction.

No pin file, background writer, cloud dependency, external service, signing
credential, second audit source or new canonical mutation method is introduced.
Ordinary constructor/restart behavior is unchanged. Deployments must explicitly
adopt `recover` for recovery; this library change does not wire an operator UI or
certify every service/database combination. Separate budget/effect databases are
outside this checkpoint and require their own governed reconciliation.

If both the database and its expected pin are rolled back, this offline comparison
cannot detect it. The regression suite deliberately demonstrates that boundary.
Trusted freshness, independent custody, arbitrary hostile filesystem replacement,
physical power loss and production recovery remain unproved. No automatic or
unattended production recovery should be inferred from matching hashes.

SQLite snapshot semantics: [SQLite backup API](https://www.sqlite.org/backup.html).

## Required change record and adversarial review

Failure: valid stale backups can restore spent authority. Proposed narrowing:
explicit recovery opens require equality with an independently trusted current
state. No authority is gained and no new canonical transition is exposed. Existing
schema initialization remains inside the existing backend capability boundary;
rejected comparisons do not reach it. Read-only capture does not ratify state.

Flip: hostile snapshots cannot supply their own expected pin. Reverse: reject
before initialization can alter the candidate. Invert: matching old evidence is
not fresh authority. Inside-Out: no self-publishing checkpoint store, grant or
second ledger is added. Darken: co-rollback of state and pin defeats comparison;
execution must remain stopped without independent current evidence. Lighten:
cache corruption need not imply canonical history differs, so cache data is
excluded while its executable triggers are bound. Amplify: lock comparison and
initialization together; check replay tables and revocations, not just audit tip.
Negate: add a bounded opening precondition rather than a provider, credential
rotation, replay-table reset or automatic restoration mechanism.

Exact historical checkpoint: 2140a528d82b600b801982eb2c8c188d43649631.
The readiness negative experiment at that checkpoint accepted a spent permit
after whole-snapshot rollback. Candidate evidence must compare that same fixture
with the trusted-current-pin guard, and retain co-rolled-back/poisoned-reference
cases as explicit non-transfer boundaries. No broader organizational lesson or
historical authority transfer is claimed. No legacy control path is copied.

Classification: implementation Proposed until admitted; test outcomes Verified
only at their recorded commits. Current pin custody/freshness and production
adoption remain Unknown. Continue with isolated Ubuntu WSL and negative tests;
no installed runtime update, merge or deployment is part of this change.

The constitutional mutation harness retains its initialization-transaction test
with an updated exact source pattern and adds removal of the recovery comparison.
Both must be killed by assertion failures in the existing/new negative tests;
an unmatched pattern is invalid evidence and still fails the check. No mutation
or enforcement gate is skipped to accommodate this change.
