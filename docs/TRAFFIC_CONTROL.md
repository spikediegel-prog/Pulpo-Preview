# Pulpo Traffic Control initial proof

Status: Experimental PTC prototype, based on Pulpo-Preview/main at
`115478fd468543ab74c6b7e96c98188b667d777d`, submitted for review against that
development surface. No live deployment. Austin's Ironnember/Pulpo1.0 was not
modified.

Experimental branch: `experimental/ptc-prototype`. Run
`python scripts/demo_traffic.py --repeats 5 --output demo.json` to try the
prototype on disposable local state. The trial runs 24 actual SQLite inserts
and 12 delayed in-process API-style calls per flow, with the same sql=1/api=2
limits. Governance and scheduling stay on the owning thread; effect workers
receive only exact immutable intents, never a kernel or permit.

Verified local trial: all 10 flows (5 FIFO and 5 PTC) completed identical exact
effects, consumed exactly 36 canonical permits, preserved valid audits and
released every slot. Disposable SQLite connections are explicitly closed
before Windows temporary-directory cleanup. Recorded wall-time medians:
FIFO 325.7 ms, PTC 259.9 ms, a 20.2% reduction on this fixture. These values
include canonical SQLite consumption and worker overhead; the API delay is
artificial. Live provider performance and production integration remain Unknown.

Selected profile: `TrafficControl.for_sql_api(paths, ...)` fixes one SQL writer
slot, two API slots and zero artificial pacing, with bounded queue sizes
(16 per lane unless the trusted owner chooses another validated bound). Mixed
and interleaved work retains independent lanes and equivalent-path selection.
The tests and unpaced demos/benchmarks now use this same explicit profile.
Optional pacing remains an explicit experimental constructor path only, not
part of this selected profile. No automatic traffic classification, live
deployment, new provider target, batching or SQLite implementation change is
introduced. Existing exact-intent and canonical authority checks are preserved.

## Boundary and use

PTC schedules claims of already-authorized work. It cannot mint, renew, revoke,
consume, decode or reinterpret permits, call providers, invoke tools, or write
canonical state. Admission checks a decision's shape and exact intent hash;
it cannot authenticate that decision. The existing orchestrator's
`traffic_dispatch()` calls the canonical `kernel.consume()` immediately before
yielding a dispatch. Forged or stale claims therefore never reach the caller's
effect block through this seam. Slot release happens even on rejection or
exception, and never requeues or renews a consumed permit.

Trusted execution owners register immutable `Lane` and `Path` descriptions.
The initial path contract is deliberately narrow: every eligible path must
contain the exact same immutable Intent, including principal, action, resource,
cost and session. PTC does not choose providers, rewrite resources or construct
alternate mechanisms. Configuration belongs to the execution owner, subject to
existing execution policy; it is not an intelligence-controlled approval list.
No new authority for multiple targets/providers is claimed.

Each SQL/API lane has 1..1024 concurrent slots and 1..1024 pending entries.
Admission selects the least loaded permitted lane with queue space; dispatch
can select another registered equivalent path with a free slot. Full queues
raise `Backpressure` without spending a permit. Occupied or paused lanes delay
work; eligible independent lanes continue. Lane queues rotate fairly, with
FIFO within each queue. Only queue heads are considered: this prototype does
not promise optimal scheduling or starvation freedom under every arrival mix.
The trusted owner may signal a bounded 0..60 second cooldown. This is
pre-dispatch contention handling, with no automatic retry after any effect.

The trusted owner can also set `Lane.min_dispatch_interval` to a finite
0..1 second minimum start-to-start gap. The default is zero. A SQL lane can
retain one writer slot and a bounded queue while pacing repeated starts;
API lanes keep their independent slots and zero gap. This caps dispatch rate
without modifying transactions, durability, connection ownership or SQLite
configuration. `ready_delay()` reports the next unoccupied queued path's timer
delay so the existing owner can wait for that timer or a worker completion
without a busy loop. PTC does not own workers or sleeps. No automatic tuning,
permit renewal or retry is introduced.

The helper retains no kernel, executor, signing credential or callback. It is
not exposed through MCP, transport, CLI or a read-only UI. The orchestrator
already possesses the canonical governed consumption capability. Its new seam
introduces only the same `permit_consumed`/`permit_rejected` state transitions
and audit events as direct canonical consumption. There is no second ledger,
audit source, policy decision, router or executor.

## Minimal fixture example

```python
from pulpo import GovernanceKernel, Intent, Policy
from pulpo.orchestrator import PulpoOrchestrator
from pulpo.traffic import Path, TrafficControl

# Disposable local fixture only. Production authority uses existing doctrine.
intent = Intent("fixture", "fixture", "fixture:sql:exact")
kernel = GovernanceKernel(Policy(frozenset({"fixture"}), 0))
owner = PulpoOrchestrator(kernel)
traffic = TrafficControl.for_sql_api(
    (Path("sql-primary", "sql", intent),),
)
traffic.enqueue(intent, kernel.evaluate(intent), ("sql-primary",))
with owner.traffic_dispatch(traffic) as dispatch:
    if dispatch is not None:
        assert dispatch.work.intent == intent
        # Trusted owner's exact bounded effect would occur here.
```

The caller holds the context until work completes, including awaiting an async
effect inside the context if applicable. Exhausted lanes yield None; permit
rejections raise OrchestrationError. There are no background workers, hidden
wait loops, automatic retries, durable queues or crash recovery. Queue loss
does not grant authority or reset canonical replay protection. Admission and
slot accounting are locked; kernel backend threading rules still apply.
SQLite owners need a separate canonical connection in each owning thread.
In-memory governance must remain on its owning thread. Slots are local to
one helper, not a distributed concurrency cap.

Do not pre-consume permits for commerce/custody executors that already consume
or claim their own capabilities. Integrating lane occupancy around those
existing executors requires retaining their original canonical consumption
point. Production adapter wiring and grouping are Proposed future work, not
activated by this proof. External consequence uncertainty still requires the
existing reconciliation path, never a PTC retry.

PTC preserves existing lifetime semantics. Directive-bound permits are checked
for live expiry, parent state and revocation by canonical state at consumption.
Approval-envelope expiry is checked by the kernel when issuing a permit;
ordinary permits do not acquire a new expiry rule from PTC. This change does
not claim to repair or broaden those pre-existing semantics.

## Verification and recorded measurement

Verified locally on Windows/Python 3.12.14:

- 17 PTC tests passed, including unauthorized/forged claims, substituted target,
  congestion, exact alternate paths, one-use after uncertain effect failure,
  backpressure without spending, concurrency limits, lane rotation, cooldown,
  invalid bounds, directive expiry/revocation on memory and SQLite, persistent
  restart replay, simultaneous bounded admissions and concurrent SQLite replay.
  Three additional pacing tests cover API progress, no consumption while
  waiting, rejection after expiry during spacing and invalid interval bounds.
- The selected combined suites now pass all 127 tests on Windows. Four
  directive test fixtures now use a TemporaryDirectory with a database path
  instead of holding NamedTemporaryFile open while reopening it with SQLite.
  All existing assertions remain intact. The untouched exact base ran 110
  tests, with 106 passing and those 4 Windows errors; the earlier uncorrected
  PTC run reproduced the same errors. Original logs are retained separately.
- Canonical kernel, orchestrator, execution-context, authority, audit-checkpoint,
  persistence and custody-executor suites were included. Only temporary-file
  fixture construction changed; canonical backend semantics remain unchanged.

Run with `python -m unittest tests.test_traffic -v`. The combined suite adds
`tests.test_kernel tests.test_directives tests.test_orchestrator
tests.test_execution_context_binding tests.test_audit_checkpoint
tests.test_persistence tests.test_authority tests.test_custody_executor`.

Windows: double-click `scripts/Run-PTC-Tests.cmd` to run the selected regression
suite, or run `scripts/Run-PTC-Tests.ps1 -Suite PTC` for just the 17 PTC tests.
The runner finds Python 3.11+ or accepts `-Python` with an explicit executable.
It does not install dependencies or modify authority. Use `-LogPath` to save
output. Its exit code reflects the actual unittest result.

Existing benchmark scripts cover audit/state/capture cycles rather than traffic
scheduling. `scripts/benchmark_traffic.py` adds a sibling discrete-event fixture
using actual canonical permits and the orchestrator seam. FIFO and PTC use
identical targets, sql=1/api=2 concurrency and synthetic service durations.
Every run checks exact permit-consumption counts, concurrency and final audit.
Run `python scripts/benchmark_traffic.py --count 200 --repeats 5 --output result.json`.

The wider local benchmark is
`python scripts/benchmark_traffic_matrix.py --repeats 9 --output matrix.json`.
It measures nine arrival/duration mixes, with one excluded warm-up per mode,
alternating FIFO/PTC order and separate traced-memory runs. Only PTC allocates
its lane/path/queue structures; the FIFO baseline does not retain a dummy PTC
helper. Both execute identical exact jobs with identical concurrency limits.
Dispatch timings include canonical consumption and worker effects. Fixture
total adds database creation, permit issuance/admission, final verification and
cleanup. CPU is whole-process CPU; Python allocation peaks exclude native
SQLite allocations and process RSS. Optional `--cases` selects a subset.

Raw paired results and bootstrap intervals should accompany claims. A sum of
scenario medians weights each scenario once and is not an estimate of actual
Pulpo traffic. Single-lane controls cannot gain through lane isolation; apparent
wall-time improvements there must be treated as host/SQLite timing variation
unless another cause is independently established. The wide matrix is a local
fixture benchmark, not a production performance or historical-transfer proof.

Recorded final matrix (nine measured pairs per case):

| Fixture | FIFO total ms | PTC total ms | PTC time reduction |
| --- | ---: | ---: | ---: |
| SQL burst then API | 491.8 | 426.4 | 13.3% |
| API burst then SQL | 470.3 | 476.2 | -1.3% |
| Interleaved | 506.7 | 404.9 | 20.1% |
| SQL only | 516.2 | 580.6 | -12.5% |
| API only | 423.7 | 415.9 | 1.8% |
| Tiny mixed | 80.2 | 69.1 | 13.8% |
| No artificial delay | 436.9 | 359.2 | 17.8% |
| SQL heavy | 1221.9 | 1151.4 | 5.8% |
| Slow API-style calls | 602.7 | 476.3 | 21.0% |

Positive reduction is faster; negative is slower. The constructed one-of-each
portfolio sums to 4.750 seconds FIFO vs 4.360 seconds PTC (8.2% shorter time),
with 6.7% more summed median whole-fixture CPU time. Extra measured peak Python
allocations are 4.5..13.4 KiB; scheduler admission adds 0.14..2.46 ms per case.
Five of nine paired bootstrap intervals cross zero. Only the interleaved,
tiny-mixed, no-artificial-delay and slow-API cases resolve a positive paired
reduction in this sample. The slow-API interval is about 14.6..32.5%. Windows
CPU timer granularity and uncontrolled filesystem timing limit interpretation.
An earlier apparent API-only gain vanished in a 15-repeat recheck; its final
paired interval again crosses zero. Raw initial/recheck/final data are retained.

The scheduler-only check (1,000 jobs, 15 repeats, synthetic service costs)
measured FIFO dispatch at 12.35 ms vs PTC 20.34 ms mixed, and 12.06 ms vs
20.00 ms SQL-only: about 8 microseconds extra dispatch work per job. SQL-only
simulated service makespan stays equal, while mixed service makespan improves
from 2,499 to 2,000 units. This separates CPU overhead from modeled isolation
benefit; synthetic service units are not real execution latency.

The recorded matrix above predates optional dispatch spacing. The new SQL-only
tuning experiment is `python scripts/benchmark_sql_shaping.py --output sql.json`.
It compares zero, 5 ms and 20 ms gaps with one SQL slot and the same exact
work, then validates a candidate on fresh samples. Its local hint rule requires
at least 10% lower summed relative median absolute deviation and no case more
than 5% slower in both training and validation. This is a bounded experimental
criterion, not authority to activate settings or proof of a universal optimum.
The zero-gap default remains unchanged regardless of the measured hint.

Raw local evidence is in `docs/evidence/ptc/`: the selected-profile test log,
Windows baseline comparison, wider workload matrix, scheduler-only costs,
SQL-shaping training/validation and fresh selected-profile demonstration.
The evidence manifest binds the final runtime/test/script files by SHA256.
Earlier measurements precede the final convenience profile constructor and
optional spacing; their scope is labeled above rather than claiming every
recorded sample was collected from the final Git commit. The selected-profile
regression and demonstration cover the selected runtime source.

Recorded SQL shaping outcome: training used seven samples per setting/case;
fresh validation used five samples per setting/case. The 5 ms candidate slowed
fresh SQL-only median total from 363.6 to 479.2 ms (+31.8%), interleaved from
413.9 to 525.1 ms (+26.9%), and slow-API from 480.0 to 545.4 ms (+13.6%).
SQL-only relative median absolute deviation dropped from 4.1% to 0.75%, but
interleaved variation worsened from 0.11% to 1.70%. Lower variability therefore
does not establish an acceptable throughput tradeoff. The 20 ms candidate was
79..137% slower in training and was not selected for validation. Neither
candidate satisfied the experiment's no-more-than-5%-slowdown criterion.
Keep the measured conservative local hint: one SQL writer slot, bounded queue,
zero artificial dispatch spacing, independent API lanes. No universal best
SQLite configuration or native-system performance claim is made.

Additional eight-pass review for pacing: Flip—hostile pacing can delay work but
cannot grant authority; Reverse—the canonical consume gate blocks effects after
permit expiry; Invert—smooth timing cannot classify an unauthorized effect as
success; Inside-Out—timer state is separate from canonical authority time and
PTC retains no writer; Darken—a long bounded gap can expire queued work and
increase latency; Lighten—ordinary backpressure is not evidence of attack;
Amplify—queues, slots and gaps remain bounded, and repeated submissions still
face canonical one-use consumption; Negate—keep zero-gap scheduling unless the
local pacing measurement passes fresh validation. Continue only with disposable
fixtures. No authority gain, new canonical mutation, provider route or executor
is introduced. A relevant historical SQL pacing checkpoint has not been found;
no temporal-transfer or native-installation performance claim is made.

Recorded synthetic result (200 jobs, 5 repetitions): mixed SQL burst then API
work takes 499 service units with strict global FIFO and 400 with PTC (19.8%
less makespan, 28.0% less mean completion time). SQL-only control takes 200 in
both. Host dispatch median was about 2.55 ms FIFO vs 4.37 ms PTC mixed, and
2.44 ms vs 4.07 ms SQL-only. PTC adds bookkeeping overhead; actual providers,
SQL work, host contention, latency and production throughput are Unknown.
These simulated service costs are not real performance measurements.

## Eight-pass adversarial transformation review

Purpose: reduce execution contention while preserving canonical authority.
Exact outcome: a bounded ephemeral lane helper around existing consumption.
Authority boundary: trusted execution owner -> existing orchestrator -> kernel.

| Pass | Finding and smallest control |
| --- | --- |
| Flip | A forged decision can enter a queue; the canonical kernel, not queue admission, rejects it before the effect block. A hostile same-process execution owner remains outside this helper's protection. |
| Reverse | Target substitution requires either a mismatched configured path or a forged intent hash; exact path equality catches the former, canonical consumption catches the latter. |
| Invert | Provider success after unauthorized dispatch cannot count as success. No provider call exists in PTC; tests require zero effect-block calls after rejection. |
| Inside-Out | PTC holds neither kernel nor credentials; it cannot self-authorize. The existing orchestrator's consumption capability remains governed and is not exported to a transport. |
| Darken | Plausible hostile claims saturate local queues and delay valid work. Fixed lane limits cap retained work; there is no global fleet or process isolation proof. |
| Lighten | Ordinary bursts and provider cooldowns explain congestion without implying attack. Scheduling measurements are synthetic and do not prove real provider throughput. |
| Amplify | Duplicate permits across queues/paths/workers can amplify attempts; canonical one-use SQLite consumption allows one success, including after restart. Slot release never resets replay state. |
| Negate | A callback executor or new authority service is unnecessary. Store immutable work descriptors and reuse the existing canonical consumption seam. |

Continue decision: proceed only with this local fixture proof. No credentials,
live provider routes, execution-mechanism substitution, alternate consequence
objects or expanded capability custody are introduced. Configured same-target
lanes are scheduling hints; no provider-authority expansion was reconciled or
granted. Unknown/malformed authority still fails at the canonical gate.

Legacy source: existing orchestrator/kernel consumption and canonical state,
without copying another executor's control path. The base comparison is a
regression check, not a temporal-transfer lesson claim. No relevant historical
PTC checkpoint exists in the examined current surface; no reusable historical
performance or authority-transfer proof is asserted. Broader integration,
distributed caps, safe grouping and production scheduling remain Proposed.
