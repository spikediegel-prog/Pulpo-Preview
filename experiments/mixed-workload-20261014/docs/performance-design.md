# Pulpo performance design record

Claim classification: VM execution and timing results are **Recorded**; archive integrity and source identity checks are **Verified**; selected settings and future runtime integration are **Proposed**. Causes of the early stalls, real provider performance, and reusable temporal transfer remain **Unknown**. See [publication boundary review](publication-boundary-review.md).

Finalized for isolated testing on October 14, 2026. This record selects a conservative mixed workload profile and preserves experimental alternatives for later review. The selections do not activate a service, modify repository source, or authorize a merge or deployment.

The governing decision is to improve execution scheduling while retaining exact authorization, one-use permits, canonical audit evidence, and SQLite durability. The selected mixed workload uses one SQL writer, two API slots, and zero artificial dispatch pacing. A SQL/API pair every 100 ms is the conservative fixture setting; 95 ms remains an experimental setting with occasional target misses.

## Pinned source and environment

| Item | Recorded value |
| --- | --- |
| Preview repository | `spikediegel-prog/Pulpo-Preview` |
| Preview commit | `d935987f016cfc1038b624a7b4cb6a03ad9f8baa` |
| Baseline repository | `Ironnember/Pulpo1.0` |
| Baseline commit | `d674dbb7a00b471d69bcca84d2f034cf74705e1a` |
| VM Python | 3.12.3 |
| VM SQLite | 3.45.1 |
| Recorded platform | Linux 6.8.0-147-generic x86_64, glibc 2.39 |
| Comparison root in the VM | `<COMPARISON_ROOT>` |

Results came from terminal output supplied by the VM operator. Source checkouts were reported clean after the completed tests. The diagnostic reports bind the source files and test harness with hashes. The original dependency-free comparison and the later Ed25519 validation have separate dependency records; installing the optional cryptography dependency does not retroactively change the original suite evidence.

## Selected designs

### Foreground SQL and API scheduling

| Setting | Selection and scope |
| --- | --- |
| Execution owner | One existing trusted coordinator owns governance and dispatch |
| SQL concurrency | One writer slot |
| API concurrency | Two slots |
| Queue capacity | Eight queued jobs per lane in the mixed arrival fixture |
| Dispatch pacing | Zero artificial spacing |
| Queue TTL | Unset for the selected fixture; canonical permit lifetime checks remain in force |
| Workload | One SQL job and one API-style job per arrival, submitted in that order |
| Conservative arrival interval | 100 ms per pair: 10 pairs, or 20 offered jobs, per second |
| Experimental arrival interval | 95 ms per pair: about 10.53 pairs, or 21.05 offered jobs, per second |
| Latency target | Each job class has P95 below 100 ms in every measured round |

The arrival interval is a test input, not an installed rate limiter or a guarantee of sustainable service capacity. All latency starts at the predeclared scheduled arrival and ends after observed effect completion and slot release. It includes caller backlog, authorization, admission, and execution. Database initialization and final verification are outside that latency clock.

The test uses real disposable SQLite writes with an additional 2 ms delay and a local API-style fake with a 30 ms delay. It provides no measurement of an actual network provider.

### Completion handling candidate

The `ptc_poll` candidate checks for finished workers before additional authorizations and dispatches, using the same completion and slot-release path. Only the external fixture owner schedule changes. Every dispatched job still uses the original orchestrator and canonical permit-consumption gate.

Keep this candidate in the test harness. It reduced completion-observation delay near the arrival boundary, but the 95 and 100 ms confirmation did not establish a sufficient advantage to justify changing Pulpo source. It neither renews permits nor retries executed work.

### SQLite persistence and indexing

Retain the existing canonical transaction boundaries, independent durable transitions, FULL synchronization, and existing journal configuration. The SQLite backend comparison recorded DELETE journal mode and `synchronous=2` for all variants. Disposable batching stress fixtures separately used WAL/FULL effect databases; that does not select WAL for canonical governance state.

Keep `index_audit_events=False` as the control. The opt-in index is a candidate for workloads dominated by repeated identity lookups. On 10,000 seeded audit records, indexed repeated lookup throughput was about 19 times baseline; indexed issuance/consumption median elapsed time was about 1.5 percent greater than baseline. These are operation-specific fixture results.

An index already created in a database persists when the option is subsequently false. Future comparisons must use fresh fixture databases or record whether the index exists; toggling the flag alone does not restore an unindexed control.

### Disposable background batches

Use 32 derived rows as the control and 512 rows as the candidate in further isolated batching tests. The 4096-row case remains a stress fixture; no optimal batch size has been established.

For the separately tested mixed SQL background profile, retain eight total queued slots, reserve two for foreground, and cap queued background work at six. This is distinct from the foreground-only arrival fixture, which has eight slots per SQL/API lane and uses the factory's default reserves. A combined foreground/background service profile has not been validated by the arrival-rate tests.

Bind the exact batch to its intent and execute it through the original owner and permit gate. Record success after commit. Canonical governance transitions remain independent; this design does not delay or combine them into background batches. Active background writes are not preempted, and continuous foreground activity can starve background work.

## Evidence supporting the selections

### Regression and recovery

- Baseline and Preview full suites completed successfully in the isolated environment. Preview ran 575 tests with five skips.
- All three skipped Ed25519 tests subsequently passed separately on both pinned commits with `cryptography==50.0.1`, warnings treated as errors, and no skips.
- The two remaining skipped tests require Windows handle sharing or reparse traversal and remain outside Ubuntu validation.
- The 60-test focused routing, batching, and cleanup suite passed with warnings treated as errors.
- All six batch-interruption boundaries passed three trials each. Tests retained atomic effects, receipt distinctions, canonical replay rejection, audit validity, and released writer locks. Commit-race sampling does not prove a kill occurred inside COMMIT or establish power-loss behavior.
- All 21 idle stress samples completed successfully with bounded queues, exact effects, and replay/audit checks.

### Mixed arrival boundary confirmation

Five rounds of 30 pairs produced 300 measured jobs per mode and interval. All six combinations met the per-class P95 target in all five rounds.

| Pair interval | Mode | SQL P95 ms | API P95 ms | Jobs at or above 100 ms | Worst job ms |
| --- | --- | ---: | ---: | ---: | ---: |
| 100 ms | FIFO | 67.1 | 92.6 | 0 of 300 | 95.1 |
| 100 ms | PTC | 67.1 | 91.8 | 0 of 300 | 94.9 |
| 100 ms | Completion handling candidate | 67.4 | 91.3 | 0 of 300 | 93.9 |
| 95 ms | FIFO | 67.4 | 91.6 | 0 of 300 | 93.4 |
| 95 ms | PTC | 67.2 | 91.6 | 1 of 300 | 149.1 |
| 95 ms | Completion handling candidate | 67.3 | 92.0 | 1 of 300 | 105.7 |

Passing P95 does not mean every job finished below 100 ms. The 100 ms interval is selected for its additional margin and zero observed misses in this confirmation. The 95 ms interval raises offered rate by approximately 5.3 percent and stays experimental.

Earlier arrival-rate trials recorded multi-second delays, including at 100 and 200 ms intervals. Their cause remains unresolved and those failures remain part of the evidence. Later passing rounds do not establish a production latency guarantee or explain away the earlier stalls.

### Scheduling benefits and costs

The independently repeated workload matrix showed approximately 8.2 percent less elapsed time for the slow-API fixture and 4.4 percent less for tiny mixed work. Fast mixed work was about 1.6 percent slower, and SQL-only work about 0.17 percent slower; paired intervals stayed on those respective sides of zero in the confirmation. CPU time increased in all four confirmation cases. PTC is therefore a workload-dependent scheduling choice, not a general performance upgrade.

At an 80 ms pair interval in the diagnostic run, the completion handling candidate reduced pooled API P95 from about 140.0 to 96.6 ms. Only one of three candidate rounds passed both class targets, so this interval is not selected. At 75 ms, none of the candidate rounds passed both class targets.

## Boundaries that future changes must preserve

1. A trusted owner registers paths for exact intents. Route selection and congestion do not confer authority or substitute a target.
2. Effects require the existing canonical permit-consumption point. Scheduling must not pre-consume for an executor that already owns its capability-consumption gate.
3. Permit use remains one-time, with existing expiry, revocation, restart, and replay checks.
4. Successful timing cannot replace exact effects, database integrity, audit validity, or reconciliation evidence.
5. Preserve FULL synchronization and canonical transaction semantics. Do not relax durability or combine governance transitions to meet latency targets.
6. Canonical state remains with its owning coordinator; effect workers own only their disposable effect connections in these fixtures.
7. Backpressure can retain an original unused claim in a bounded caller backlog. It does not authorize replay, renewal, or an automatic retry after an effect.
8. Committed effects without a completion receipt require reconciliation. A missing receipt cannot prove no effect occurred.

## Evidence locations for resuming work

The VM evidence root is `<COMPARISON_ROOT>/results`.

| Relative location | Evidence |
| --- | --- |
| `environment.txt`, `dependencies.txt` | Original comparison environment |
| `baseline.sha`, `preview.sha`, `focused-source.diff` | Pinned source and endpoint comparison |
| `baseline-full.log`, `preview-full.log`, corresponding `.exit` files | Full-suite validation |
| `sqlite-comparison.json` | Raw backend comparison samples and source identity |
| `traffic-matrix.json`, `traffic-synthetic.json` | Initial scheduling fixtures |
| `batch-recovery.json`, `idle-stress.json` | Recovery and background stress evidence |
| `ed25519.xDUmDz` | Both commits' focused Ed25519 validation and dependency record |
| `routing-confirmation.anbraE` | Independent four-case scheduling confirmation |
| `mixed-100ms.KBRGTG` | Initial simultaneous mixed-burst latency test |
| `mixed-arrivals.UYRIuT` | Scheduled-arrival trials including early multi-second failures |
| `mixed-diagnostic.rk1XwJ` | Stage timing and completion handling candidate |
| `mixed-boundary.7WkjX9` | Five-round 95 and 100 ms confirmation |

These locations identify operator-supplied VM evidence; the files have not been copied into this local workspace. Some original comparison filenames were reused across runs. Preserve separate diagnostic directories and terminal records rather than interpreting every historical pasted value as the current contents of an overwritten file.

## Reopening the design

Resume when new workload measurements, provider timings, host/storage changes, or source changes supply a specific reason to reconsider a selection. Pin the new source and environment, use a new results directory, and retain the old evidence.

First resolve the early multi-second stalls and measure the intended real provider workload before making a service-level latency commitment. Change one relevant scheduling or indexing choice at a time and pair it with the appropriate existing control. Evaluate both class-specific P95 and individual misses; keep initialization, steady operation, and recovery scope explicit. Claims of sustainable rates require longer duration and realistic arrival variation than the finite fixtures here.

A candidate must preserve all boundary checks and show repeatable benefit with acceptable tail latency and CPU/memory cost before source integration is considered. Repository modification, merging, pushing, or deployment requires a separate explicit request. This design record schedules no follow-up work.

## Portable publication fixtures

`scripts/benchmark_mixed_arrivals.py` accepts source and output paths, pair counts, repeat counts, intervals, modes, and an expected commit. The default expected commit is the Preview commit in this record. Output stays outside the source checkout. It rejects dirty or mismatched source and preserves existing output directories.

The historical numbers above came from the archived VM harnesses, not from a full rerun of the portable entry point. The publication preparation runs a small fresh-checkout smoke check of all three modes. That check establishes fixture execution and correctness at the smoke workload; it does not establish a new latency boundary or production readiness.

The evidence export preserves raw measurements, archived harnesses, dependency records, logs, and the earlier failing timing trials. Machine-specific paths in text are replaced with placeholders. Its manifest records original and exported hashes and identifies transformed files. This distinguishes the exported copy from the unchanged original evidence retained by the operator.
