# Idle background work in the existing router

Local candidate based on Preview PR #8. This is an opt-in library integration,
not a running SQL daemon or an upstream release.

Trusted execution owners may register `Path(..., background=True)` for explicitly
disposable derived work. Every path defaults to foreground; no SQL text, model
output, resource name or caller hint is used to infer authority or access.
Equivalent alternatives must share the same background classification.

```python
paths = (
    Path("foreground", "sql", foreground_intent),
    Path("derived-export", "sql", exact_export_intent, background=True),
)
traffic = TrafficControl.for_sql_api(paths)
```

Foreground claims are placed before queued background claims, with FIFO within
each class. Background dispatch is blocked while any foreground claim is queued
or active, including paused foreground work. An already active background effect
is not cancelled; foreground can use an independent free lane. This conservative
idle definition can starve background work under sustained foreground load.

The original per-lane queue and slot bounds apply to both classes together.
Mixed lanes reserve one queued slot for foreground by default. Background count
is capped at `queue_limit - foreground_reserve`; foreground can use every slot,
including unused background capacity. Already queued foreground entries count
toward occupying the reserve, so capacity is not left idle unnecessarily.
Configure `Lane(..., foreground_reserve=N)` or the profile's
`sql_foreground_reserve` / `api_foreground_reserve` keyword arguments. Reserve
must be an exact integer from zero through the lane's queue limit. Zero restores
shared admission; reserving every slot prevents background admission in a mixed
lane. A mixed single-slot lane therefore admits only foreground by default.
Background-only lanes use their entire queue. No entries are evicted and rejected
admission consumes no permit. Foreground can still backpressure foreground when
the queue is full, and an already active background effect can delay dispatch.
TTL expiry scans every bounded entry because priority can reorder deadlines.
Timer reporting includes background expiry even when priority blocks dispatch.

The router has no writer, executor, callback, signing credential or canonical
state reference. `PulpoOrchestrator.traffic_dispatch()` still performs the sole
canonical permit consumption and releases the slot in `finally`. Priority never
renews, revokes, retries or substitutes an intent. No canonical schema, policy,
SQLite durability setting, transaction boundary or audit payload changes.

## Disposable batching belongs to the existing execution owner

Prepare bounded derived rows in RAM, bind the exact batch to its existing intent,
and commit that batch inside the owner's original dispatch scope. Record success
only after commit. Canonical state writes are never delayed or combined by this
feature. Separate individual permissions cannot be silently promoted into a new
batch permission. The router itself neither groups effects nor executes SQL.

The provided local PowerShell benchmark uses real disposable SQLite WAL
databases, identical fixed effects and one-use permits in each mode. Idle modes
now use the library's background flag; only disposable telemetry rows are batched.
Its fixed single synchronous owner and synthetic arrival schedule do not prove
production capacity, real concurrent-read throughput or a universally optimal
batch size. Results are Recorded local measurements.

## Validation and boundary review

Run `python -W error -m unittest tests.test_traffic tests.test_idle_routing -v`.
Tests cover legacy behavior, strict classification, priority/FIFO, active and
paused foreground blocking, non-preemption, shared capacity, reordered TTL,
forged permits, failed batch rollback without receipt, slot release and no retry.
Reserve tests cover strict bounds, default single-slot protection, foreground use
of all slots, occupied reserves, equivalent-lane fallback, expiry, concurrent
background admission and background-only lanes.

Eight-pass analytical review:

| Pass | Boundary |
| --- | --- |
| Flip | Untrusted work cannot select trusted route configuration; forged claims still face consumption. |
| Reverse | Dispatch priority is separate from permission; no effect is reachable without the original gate. |
| Invert | Queue admission and a completed calculation are not durable completion. |
| Inside-Out | Router retains no canonical writer or executor; owner retains its original responsibility. |
| Darken | Classification aliases, mixed paths, full queues, reserve saturation, failed writes and stale deadlines are tested. |
| Lighten | Existing paths remain foreground by default and preserve their prior ordering. |
| Amplify | Concurrent admission holds the existing lock; background cannot exceed its cap. Starvation and latency from an active batch remain possible. |
| Negate | Owners can leave background classification unused without changing canonical execution. |

Authority remains unchanged. Canonical mutations remain the original permit
consumption/rejection behind the existing owner. Historical temporal-transfer
proof was not performed; general reuse and production benefit remain Unknown.

Verified local reserve validation: WSL2 Python 3.14.4 on ext4, saved in
`wsl-results-20261012-022019-4967`, passes 41 routing, 116 focused and 551 core
tests. Core and focused logs record zero resource warnings. All benchmark
correctness checks pass. Recorded seven-round foreground P95 is 108.693 ms
immediate versus 7.898 ms idle-batch; wall time is 202.771 versus 188.963 ms.
The benchmark does not saturate admission; reserve protection is established by
targeted queue tests, including simultaneous background admissions.
