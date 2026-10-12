# Disposable batch interruption and recovery

The test forcibly terminates a real child process on disposable local databases:
SIGKILL on Linux, TerminateProcess on Windows. It bypasses Python cleanup so the
checks exercise SQLite restart behavior rather than only exception handling.
Effects use WAL with FULL synchronization. Governance uses the existing durable
SQLite state and canonical permit-consumption gate. The exact eight-row batch is
bound into the fixture intent by SHA-256. Production databases are never opened.

| Interruption boundary | Required result on reopen |
| --- | --- |
| Queued before dispatch | No rows/receipt; original permit is unused. |
| Permit consumed, before write | No rows/receipt; spent permit cannot dispatch again. |
| Four rows inserted in an open transaction | No partial batch; rollback on reopen, permit remains spent. |
| Kill racing COMMIT | Either zero or all eight rows, no receipt, no replay. |
| COMMIT returned, before receipt | All eight rows, no receipt; reconciliation required. |
| Receipt commit returned | All eight rows and one receipt bound to the exact digest. |

The commit race uses a synchronized signal immediately before COMMIT and may
terminate the process before, during or after that call. It does not establish
that a kill occurred inside SQLite's commit operation. No power-loss or production
capacity claim is made. Forced-stop tests complement the graceful cleanup tests.

Restart verifies both database integrity and the canonical audit, checks exact
row/receipt contents, acquires and rolls back a new writer transaction to test
lock release, and rejects consumed-permit replay through the existing owner.
The queued-only case proves first use still works, then denies second use.
Replay checks leave effect rows and receipts unchanged. Newly constructed router
queues are empty; volatile work is not automatically recovered or retried.

The receipt is disposable fixture completion data in a separate transaction after
the effect, not canonical audit evidence. A missing receipt cannot prove that the
effect did not commit. Recovery reports observed state and does not invent a
receipt, re-execute a consumed batch, or grant a replacement permit. This test
does not implement an automatic recovery service.

Run `python -W error scripts/test_batch_recovery.py --repeats 3 --json report.json`.
The JSON records each boundary, rows, receipts, permit consumption before the
probe, child termination code, integrity/replay results and source hashes.
The root suite also includes six regression cases. The WSL kit runs the repeated
trial and records `batch_recovery` as an additional required runner stage.

## Adversarial transformation review

- Flip: a crashed/untrusted worker's absent receipt cannot authorize replay.
- Reverse: the original gate consumes the exact permit before any effect; restart
  cannot revive a consumed permit or recreate a volatile queue automatically.
- Invert: durable rows without a receipt are reported as needing reconciliation,
  not successful completion or proof of no effect.
- Inside-Out: fixtures use the existing kernel/owner; receipt data confers no
  governance authority and recovery observations do not append completion claims.
- Darken: partial transaction, commit ambiguity and missing receipt are exercised
  with real forced termination. Power-loss behavior remains unverified.
- Lighten: an undispatched queued claim remains unused; first dispatch is legitimate
  and is distinguished from replay of a consumed claim.
- Amplify: all six boundaries repeat independently; exact contents and replay
  protection are checked after restart without accumulating effects.
- Negate: readback and explicit reconciliation classification avoid blind retries,
  new authority gates, cleanup daemons or alternate evidence ledgers.

Verified Windows validation: 18 forced child terminations (three per boundary)
pass; 59 combined interruption, lifecycle, connection and routing tests pass.
Verified Linux validation: run `wsl-results-20261012-030534-7933` passes all
18 repeated forced-stop trials; each child exits with SIGKILL status -9. Reopen
shows zero partial batches, released writer locks, valid audits and rejected
spent-permit replay. All three commit-race trials observed rollback (zero rows),
so this run does not demonstrate both possible outcomes at that race boundary.
After-commit trials retain eight rows without receipts and require reconciliation;
after-receipt trials retain eight rows and one exact receipt. The 566-test core
suite, 116 focused tests, 41 routing tests, 12 lifecycle tests, cycle self-tests
and benchmark also pass. Core/focused resource-warning counts remain zero.
