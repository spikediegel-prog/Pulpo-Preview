# SQLite operation connection cleanup

Recorded: Python 3.14 reported unclosed SQLite connections during the Linux core
suite even though unittest returned success. A connection transaction context
commits or rolls back; it does not close the connection.

The evidence convergence and proposal commitment stores now wrap each owned
transaction context in `contextlib.closing`. Transaction exit runs first, then
close, including early returns and exceptions. Connection configuration failures
also close before re-raising. Two test fixture connections receive the same
cleanup. Persistent kernel connections keep their existing lifetime.

Verified locally: 52 targeted tests pass on Windows Python 3.12, covering cleanup,
custody evidence, consequence reconciliation, hostile outcome memory and routing.
Lifecycle tests check that initialization, reads, duplicate
proposal creation, accepted claims, expired/replayed claims, and failed evidence
initialization leave their owned connections unusable. Existing custody evidence
tests cover abort and reconciliation semantics. Linux verification remains
completed in the refreshed WSL run described below.

Recorded: the broader Windows core run executes 536 tests with four failures,
13 errors and eight skips; the focused run executes 116 with one symlink
privilege error. These runs are not clean Linux validation. Zero resource-warning
lines were recorded, but Python 3.12 does not provide the same SQLite finalizer
warning coverage as Python 3.14.

The suite runner records resource-warning counts and fails when those warnings
appear, including unraisable finalizer warnings that do not change unittest's
exit status. Warnings are not suppressed.

## Adversarial transformation review

- Flip: callers cannot extend connection lifetime through the returned proposal
  or count; neither exposes a connection.
- Reverse: premature closure could lose a transaction; transaction context exit
  precedes closing on both return and exception.
- Invert: a passing unittest exit with cleanup warnings now fails the runner.
- Inside-Out: evidence and proposal stores retain their existing authority and
  transaction gates; cleanup adds no writer, router, or evidence source.
- Darken: failed setup and denied claims must close and propagate their existing
  errors; failed initialization and denied claims are tested.
- Lighten: deferred garbage collection explains warnings near unrelated tests;
  those nearby test names do not establish allocation origin.
- Amplify: repeated reads and claims close at operation boundaries rather than
  accumulating connections until garbage collection.
- Negate: deterministic cleanup needs no cache, schema change, relaxed sync
  setting, or new authority capability.

Verified: refreshed WSL2 Python 3.14.4 run on ext4, recorded in
`wsl-results-20261012-015320-3515`, passes all 543 core tests, 116 focused tests,
and 33 routing tests. Core and focused reports record zero resource warnings;
the core log also contains no ignored-exception messages. The prior core run
recorded 59 resource-warning lines. This confirms cleanup for the exercised paths.

Recorded: seven measured runs per mode yield immediate versus idle-batch
foreground P95 108.010 -> 7.713 ms, wall time 202.062 -> 189.077 ms, CPU time
21.235 -> 12.698 ms and disposable effect commits 64 -> 22. All final-row,
one-use permit, audit and empty-queue checks pass. These compare routing modes
within the updated run, not the isolated effect of connection cleanup. Idle-batch
wall time is close to the prior 189.350 ms; a cleanup speedup is not established.
