# System diagnostics and explicit tuning

Claim: **Recorded** implementation and test observations. The System page extends
the canonical native Control Center in place, using its existing palette,
navigation, responsive resource monitor and expandable status rows.

## Operator workflow

Diagnostics shows local CPU, memory and labeled-volume capacity history, then
installation, runtime, temporary workspace, configuration, time and recovery
rows. Package version, interpreter/Tcl/Tk versions and the effective local
performance hint are observations. Missing build provenance, service health,
clock synchronization, updates and tested recovery remain **Unknown**. This
window running does not establish that a kernel or service is healthy.

Preview, copy or explicitly export a redacted support summary. It excludes host
name, file paths, credentials and raw logs. No report is sent automatically.
The profile path remains visible locally for troubleshooting.

Tuning & benchmarks compares the current effective worker count against a
candidate from 0 through the existing machine-dependent limit (maximum 16).
0 and 1 both use serial collection. Each side gets five repetitions, in
alternating order, with at most one spawned child process at a time. The
existing capture benchmark and correctness checks run against disposable
fixtures: 64 files with 4 MiB total payload, not a production database or full
governed cycle. Existing Evidence tuning controls remain available and share a
busy guard with System operations.

Results show median and observed range, spread, files/second, process CPU core
percentage, peak child-process RSS and fixture payload. CPU can exceed 100% on
multiple cores. RSS includes child startup and correctness checks; it is not
total system memory or parent-plus-child usage. Payload excludes filesystem
metadata/allocation overhead. Unavailable memory measurements are **Unknown**.

**Faster**/**Slower** requires a median difference greater than 5% and
non-overlapping observed timing ranges; otherwise **Inconclusive**. Comparing
two serial settings is always Inconclusive. This heuristic is not a statistical
confidence interval or a universal tuning recommendation.

Comparison never saves settings. An explicit Save tested candidate rechecks
correctness through the existing atomic settings path. A report expires after
15 minutes or a machine, source, profile or candidate change. Reports cannot be
imported as save authorization. Restore previous setting reuses the existing
restore path and fresh validation. On first save, the checked effective serial
baseline is recorded as the previous setting so restore works without an older
profile file. The optional `fallback_previous` keyword leaves existing callers
of `save_settings` unchanged. The updated tuning source digest conservatively
invalidates old source-bound hints until checked again.

## Resource, cancellation and failure boundaries

There is a 45-second comparison deadline plus worker shutdown/cleanup time, a
16 MiB temporary-volume free-space start floor and one child at a time. There
is **no hard RAM cap** or hard real-time guarantee against a stalled OS. Each
child's temporary-directory root is the parent-owned workspace. Cancellation
or timeout terminates and joins the child before removing that exact workspace;
kill is a fallback after termination. If shutdown cannot be confirmed, fixtures
are retained and further performance operations are blocked for operator
investigation. No unverified live workspace is recursively removed.

Cancelled, failed, stale or incomplete comparisons cannot enable saving. A
failed fresh save check preserves profile bytes. No automatic retries, OS
tuning, permission changes, repairs, updates or service restarts are introduced.
Closing the window while an operation is active is guarded; Cancel remains
available for comparisons. Hostile OS/process behavior is not contained by a
security sandbox; this is a fixed local diagnostic workload.

## Required change record

1. **Invariant/failure:** observations and synthetic performance checks must not
   become governance attestations or silently change a setting. First-save
   restore needs a real validated baseline.
2. **Authority delta:** unchanged. No permit, signer, credential, executor,
   orchestrator, kernel, canonical state backend or service client is retained
   by System. `NO_WRITE_ROUTE != NO_WRITE_CAPABILITY` remains the rule.
3. **Canonical mutations:** none introduced or exposed. New local effects are
   disposable fixtures, explicitly selected exports and an explicit local
   performance-hint save/restore through the existing checked atomic path.
   These do not grant policy, identity, budget, permission or execution rights.
4. **Evidence:** [review artifacts](control-center-evidence/system-tuning/README.md)
   include native before/after and narrow-window inspection, real WSL
   comparison, correctness/cancel/timeout/stale-save/restore regressions and
   full core results. UI lifecycle tests explicitly finalize destroyed test
   interpreters on the owning UI thread; background jobs retain no Tk objects.
5. **Limits:** no governance enforcement, production throughput, database health,
   backup recovery, network connectivity, update availability, fleet health,
   frozen-binary runtime or WSLg visual correctness is proved by these checks.
6. **Classification:** measurements and test runs are Recorded; the timing
   classification is a limited inference from those samples; unobserved health
   remains Unknown. No new Verified enforcement claim.
7. **Legacy source:** reuse `benchmark_threads`, `check_settings`, atomic
   `save_settings`/`restore_previous`, `ResourceMonitor` and `StatusRow`; no
   copied kernel control path, second ledger/router or authority plane.
8. **Temporal transfer:** no reusable historical authority/learning lesson is
   admitted. The before screenshot reconstructs only the presentation module
   at base `66fba112134f98612a04e16f6af4b2bac91c7387`; it is not temporal-transfer
   proof. No historical approvals, credentials or budgets are replayed.

## Eight-pass adversarial review

| Pass | Result and boundary |
| --- | --- |
| Flip | A confused UI can request fixed local tests and explicit profile writes, but has no canonical writer or authority credential. Session reports are not imported from arbitrary files. |
| Reverse | An unwanted profile change requires explicit Save/Restore through fresh correctness checks; incomplete, altered or stale comparisons are rejected before Save. No canonical mutation route exists here. |
| Invert | A fast capture with incorrect evidence is failure. Correctness PASS is not transition legitimacy or enforcement verification. |
| Inside-Out | UI and child do not originate/ratify authority. Diagnostic exports are observations, not a new canonical audit source. |
| Darken | Threat case: a faulty child stalls or consumes resources. One-child concurrency, fixed fixtures, deadline and verified-stop-before-cleanup bound ordinary failures; no hard RAM or hostile-OS containment claim. |
| Lighten | Timing differences can arise from scheduling, cache, VM and filesystem effects. Preserve raw samples/ranges and allow Inconclusive without claiming a governance defect. |
| Amplify | Mutual exclusion covers both legacy and System performance jobs. No automated retry loop; unverified termination blocks subsequent jobs rather than accumulating workers. |
| Negate | Reuse existing capture/check/save paths and local OS observations. No service integration, OS tuning capability or replacement UI framework is needed. |
