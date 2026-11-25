# Recovery-pin operator step

The recovery checkpoint pin (`SQLiteKernelState.recover` /
`recovery_checkpoint`, `pulpo/state.py`) is the only in-repo defence against
whole-database rollback: ordinary construction accepts any self-consistent
older copy of the state file, so a restored backup is indistinguishable from
live state unless it is checked against a pin captured from the live state
before the restore. This document is the required operator procedure for
capturing and using that pin. The procedure is executable as
`pulpo.state.capture_recovery_pin(path)` and is tested end to end in
`tests/test_guarded_recovery.py::test_documented_pin_capture_step`.

## Decision: the pin is NOT persisted alongside state

Persisting the pin in (or next to) the state file would weaken the control
it is meant to provide. A pin stored with the state rolls back with the
state: a whole-file restore would restore the old pin too, and the check
would pass against the rolled-back data. That is the co-rollback the
`recover` docstring warns about ("This does not protect raw file replacement
or co-rollback of the pin"). So no checkpoint store or writer is created by
the code on purpose. The pin's entire value is independent retention, and
that is the operator's responsibility. Nothing here changes that; this
document makes the manual step explicit, required, and testable.

## Required step — capture (at every backup)

1. **Quiesce all writers.** Stop the kernel / process holding the state file.
   A pin captured while writers are active is stale the moment the next
   write lands.
2. **Capture the pin** with `capture_recovery_pin(path)`. It opens the state
   (ordinary construction verifies the audit head and schema), verifies the
   full hash linkage of the audit chain, and returns the pin. It refuses a
   broken chain instead of pinning it, and it writes the pin nowhere.
3. **Retain the pin independently of the state file and its backups** — a
   separate machine, medium, or secret store; never in the same backup set,
   directory, or snapshot as the state file. Record which state file and
   which backup it belongs to, and the time it was captured.
4. **Every subsequent canonical write invalidates the pin.** Capture a fresh
   pin at each backup. An old pin is only useful for detecting that a backup
   is old; it must never be used to open current state.

## Required step — restore

1. Open restored state **only** via
   `SQLiteKernelState.recover(path, expected_checkpoint=<current pin>)`,
   using the latest pin captured from the live state before the loss.
2. If the latest trusted pin is unavailable, **do not derive it from the
   backup and do not use ordinary construction as a fallback. Keep execution
   stopped** and re-establish trust out of band. Ordinary construction would
   accept the restored copy without any freshness check.
3. A pin mismatch refuses the open before initialisation or any write
   (`StateRecoveryError`); the file is left byte-identical.

## Honest limits

- The pin is a comparison value, not authority and not evidence of
  freshness on its own. Its power comes entirely from being current and
  independently retained.
- It does not protect raw file replacement: an attacker who can replace the
  state file and the pin together defeats it. A stale backup opens cleanly
  against its own stale pin — which is why step 4 of capture (keep the pin
  current) is not optional.
- It does not detect tampering that keeps the pin's digest inputs identical;
  the pin covers the canonical tables (`permits`, `approvals`, `directives`,
  `permit_directives`, `audit`, `audit_head`, `audit_integrity_schema`) and
  the schema, and excludes only the disposable audit-verification cache.
- It does not supply trusted time, a policy head, or an independent root of
  trust. Those are separate gaps (see the v9.1 verification report,
  `austin-v91-review-verification-2026-11-09.md` §5a/§6b(b)).
- The custody evidence projection writes directly to the `audit` table
  (`pulpo/custody_evidence.py`) rather than through `SQLiteKernelState`'s
  append path, so it is not covered by the clock-monotonicity check added in
  the same slice. That path is a known follow-up, not a claim made here.
