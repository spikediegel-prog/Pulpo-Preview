# Owner-scoped resource cleanup

Use the cleanup scope at the lifetime boundary of a trusted execution owner:

```python
from pulpo import ResourceScope, SQLiteKernelState, AuditVerificationEngine

with ResourceScope() as resources:
    state = resources.own(SQLiteKernelState("existing-governance.sqlite"))
    verification = resources.own(AuditVerificationEngine(workers=2))
    # Construct and use the existing kernel/owner with these resources.
    # Finish dispatched work before leaving the scope.
```

Scope exit closes verification workers first, then the database. The same cleanup
runs on normal return, operation error, KeyboardInterrupt or ordinary SystemExit.
Every registered close is attempted even when another close fails; cleanup errors
propagate. Registering the same object twice closes it once. A scope is terminal
after close and cannot accept new resources or be nested/reused. Only register
resources owned by this caller. The scope retains the resource object until
cleanup completes, including when its close callback is static or unbound.
Shared or borrowed resources remain their owner's
responsibility. Workers must stop using the database before database close.

`SQLiteKernelState` also supports `with SQLiteKernelState(path) as state:` and
repeatable explicit close. Its constructor closes a newly created connection if
configuration or schema initialization raises. Custody connection configuration
now does the same. Existing short-lived proposal/evidence/budget connections retain
their transaction-then-close paths.

This is shutdown cleanup, not periodic sweeping: closing a connection still in
use would be unsafe. There is no global registry, destructor, exit hook, process
killer, file deletion, flush of queued effects, transaction commit or automatic
retry. Uncommitted SQLite work rolls back on close; committed work remains durable.
Abrupt process termination, forced kill, power loss and operating-system shutdown
are not guaranteed to execute Python cleanup; their recovery still depends on
the existing durable transaction and reconciliation protocol.

Integration: the overall-cycle benchmark owns its state and collector cleanup
through the scope. Collector shutdown is attempted even if resource sampling
fails, and database close is attempted if worker cleanup fails. Adaptive audit
verification likewise attempts cleanup of all engines instead of stopping at the
first shutdown error. No authority gate or canonical transaction changes.

## Adversarial transformation review

- Flip: cleanup ownership is explicit; untrusted requests cannot register shared
  connections or revoke another owner's active resources.
- Reverse: shutdown first stops workers, then closes their database; callers must
  quiesce work before scope exit rather than use cleanup as cancellation.
- Invert: cleanup failure is propagated, never classified as successful close.
- Inside-Out: the scope only calls existing registered close methods; it has no
  kernel, permit, router, signing material or authority source.
- Darken: partial initialization, operation errors, interrupts, rollback and a
  failing worker close are tested. Forced termination remains outside this claim.
- Lighten: connections already closed safely retain their existing behavior.
- Amplify: duplicate registration is deduplicated; all remaining closes are
  attempted after failure, and a closed scope cannot register new work.
- Negate: standard ExitStack implements cleanup without a new daemon or sweeper.

Verified locally: 111 Windows lifecycle, connection, custody, routing, parallel
verification, checkpoint and persistence tests pass. The overall-cycle self-test
passes with serial/thread and one/two process helpers, including replay denial,
reconciliation, restart and shutdown. Verification caches clear even if pool
shutdown raises; adaptive engine cleanup attempts the remaining engines.

Verified Linux validation: WSL2 Python 3.14.4 run
`wsl-results-20261012-023557-6428` passes 560 core, 116 focused, 41 routing and
12 explicit lifecycle/connection tests. Core and focused report zero resource
warnings. Thread/process overall-cycle self-tests and all benchmark correctness
checks pass. All six runner exit codes are zero. Validation is local and disposable;
forced termination and production recovery remain outside this evidence.
Latest resource-retention regression also passes in Linux run
`wsl-results-20261012-042140-11776`: 13 explicit lifecycle/connection tests and
568 core tests pass; all nine runner stages pass with zero core/focused warnings.
