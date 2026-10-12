# Idle batching stress fixtures

The bounded test runs seven scenarios in fresh child processes, three rounds per
scenario: 32-, 512- and 4096-row batches; foreground bursts; sustained queued
foreground; eight simultaneous observers; and a 40 ms hold inside an active
background transaction. Each row has a 256-character derived payload. Each run
uses disposable WAL/FULL effect SQLite and existing FULL canonical governance
state. The registered foreground reserve is two of eight queue slots.

Foreground and background writes pass through the original owner and exact
one-use permit gate. One effect writer runs asynchronously so the coordinator
can admit foreground while a background transaction is active. Exact derived
batches are bound into their intents by SHA-256. Completion follows COMMIT.

Concurrent observer threads use independent `mode=ro` and `query_only` connections;
each verifies write rejection. Observers are fixture readback, outside dispatch,
and do not measure governed read-permit throughput. Every observer performs reads.
All workers stop and close their own connections before scope cleanup completes.

The suite checks exact rows, integrity, permit counts/replay denial, valid audit,
empty final queues, eight-slot total bounds and six-slot background bounds.
Prefilled scenarios verify foreground admission when the background quota is full.
Sustained foreground must finish before any background start. The slow batch must
overlap foreground admission; it is not cancelled or preempted.

Metrics include foreground P50/P95/max arrival-to-commit latency; oldest/P95
background arrival-to-dispatch wait; P95/max effect-write duration including
connection setup and COMMIT; peak queues; failed admission attempts by class;
concurrent reads and worst read duration; wall/CPU time; and fresh-process peak
memory including fixture construction and verification. It also counts reads
that start and finish while a writer transaction is open; the slow-active-batch
case requires such read progress.
Source hashes are recorded.
Three-round summaries are medians of per-run metrics. These are stress recordings,
not benchmark comparisons proving isolated improvements or production capacity.

All jobs are finite and fixture-bounded outside the router, with at most 45 seconds
per child workload. Backpressure causes admission attempts with the same unused
claim, never retry of an executed effect. Pending jobs outside the router model a
bounded caller backlog, not a new installed buffer. No policy, transaction,
durability, runtime batch size, read pool or fairness setting is changed by this test.

## Recorded Windows results

All 21 scenario runs pass on Python 3.12.14. Median per-run measurements:

| Scenario | Foreground P95 ms | Oldest background wait ms | Max write ms | Peak memory MiB |
| --- | ---: | ---: | ---: | ---: |
| 32-row batches | 426.4 | 716.1 | 2.9 | 35.2 |
| 512-row batches | 423.5 | 720.8 | 4.7 | 36.8 |
| 4096-row batches | 428.9 | 803.7 | 14.0 | 43.7 |
| Bursts | 972.9 | 1149.2 | 3.0 | 35.6 |
| Sustained foreground | 1741.9 | 1897.4 | 5.5 | 35.9 |
| Eight observers | 693.5 | 1094.6 | 7.4 | 37.4 |
| Slow active batch | 478.9 | 1018.6 | 44.3 | 37.1 |

All scenarios hit eight queued jobs and six queued background jobs without
exceeding either cap. Finite sustained foreground delays background approximately
1.9 seconds; unlimited foreground can still starve it. Bursty schedules exceed
observed dispatch throughput and increase foreground wait despite reserved queue
space. A reserve protects admission, not an execution-time deadline. The 40 ms
active transaction delays later foreground work; there is no preemption.
The slow-active-batch scenario records a median 94 observer reads that start and
finish while a writer transaction is open, confirming concurrent read progress.

Evidence: `idle-stress-windows.json` and `idle-stress-windows.log` in local outputs.
Linux stress validation is verified below. Use the dedicated PowerShell launcher
with `-WSL` to run only stress scenarios against a fresh verified ext4 snapshot.
The regular full WSL runner includes stress as its eighth required stage.

## Verified Linux stress results

Run `wsl-results-20261012-032220-9493` verifies source hashes and ext4 storage;
WSL2 Python 3.14.4 passes all 21 fresh-process scenario runs. Every sample records
exact rows, valid audit, rejected permit replay and empty final queues. Total
queue never exceeds eight; background never exceeds six. No resource-warning,
ignored-exception or traceback lines occur in the stress log.

| Scenario | Foreground P95 ms | Oldest background wait ms | Max write ms | Peak memory MiB |
| --- | ---: | ---: | ---: | ---: |
| 32-row batches | 173.8 | 412.7 | 2.2 | 32.3 |
| 512-row batches | 176.4 | 425.1 | 5.4 | 34.0 |
| 4096-row batches | 171.7 | 463.1 | 9.1 | 42.3 |
| Bursts | 533.8 | 642.4 | 2.3 | 32.9 |
| Sustained foreground | 1043.0 | 1128.7 | 5.6 | 33.1 |
| Eight observers | 473.8 | 829.4 | 6.8 | 35.2 |
| Slow active batch | 246.3 | 738.8 | 43.6 | 34.4 |

The eight-observer scenario completes a median 4572 reads, including 1120 that
start and finish with a writer transaction open. The slow-active-batch scenario
records 1619 such overlapping reads. Foreground P95 is lower than the Windows
run in all seven scenarios; different Python versions and filesystem stacks
prevent assigning the difference solely to the operating system. Sustained
foreground still defers background until it drains, and active writes remain
non-preemptible. No fairness or batch policy was changed by this test.

## Adversarial transformation review

- Flip: observers reject writes and cannot mint or consume governance permits.
- Reverse: only the original owner dispatches each exact write; scheduling does
  not combine individual foreground rights into a batch right.
- Invert: all rows and audit/replay checks must pass; fast timing alone cannot pass.
- Inside-Out: coordinator retains the existing kernel; worker only receives an
  already-dispatched exact fixture effect and owns its effect connection.
- Darken: bursts, reserved-space saturation, slow active writes and simultaneous
  observers are bounded fixtures; power loss and indefinite operation remain untested.
- Lighten: larger delays reflect overload and fixture overhead, not proof of data loss.
- Amplify: fixed queue bounds and exact rows are checked while admissions repeat;
  sustained foreground demonstrates background deferral without allowing replay.
- Negate: stress needs no new production router, write cache, authority gate or sweeper.
