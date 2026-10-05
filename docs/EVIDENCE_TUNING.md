# Evidence performance tuning (experimental preview)

Implemented on `experimental/evidence-tuning-tool`. The operator passed the
115-test focused suite and 19 packaged executable/installer smoke cases, and
reported that the installed GUI works. See the committed validation evidence.

## Test, then open the app

From `C:\Users\spike\Pulpo1.0`:

```powershell
python -m unittest tests.test_evidence_tuning -v
python scripts/run_pulpo_tests.py --suite focused --log-dir perf-results/tuning-tests
python scripts/benchmark_pulpo_cycle.py --self-test
python -m pulpo.cli tune
```

The window offers Recommended or Custom thread settings, a disposable capture
comparison, Apply, Recommended, Undo setting, a benchmark-only process experiment,
and JSON measurement export. Applying and undoing settings run fresh canonical
serial snapshot checks. Comparisons never automatically apply the fastest count.
The process experiment requires the existing source-checkout benchmark scripts
and psutil, validates their self-tests first, and measures temporary full cycles.

Recommended uses at most two threads. Custom permits integers from zero through
the lesser of the logical CPU count and sixteen. Zero and one collect serially.
This is a bounded experimental range, not a claim that every value is faster.
No hard RAM budget, CPU affinity, or scheduling isolation is implemented.

## Setup integration

```powershell
# Recommended installation settings
python -m pulpo.cli setup --no-calibrate --evidence-install recommended

# Custom installation settings (four threads)
python -m pulpo.cli setup --no-calibrate --evidence-install custom --evidence-workers 4

# Inspect effective default settings
python -m pulpo.cli tune --show
```

On Windows, the default profile is
`%LOCALAPPDATA%\PulpoPreview\evidence-performance.json`. On other systems it is
`~/.config/PulpoPreview/evidence-performance.json`. Saving affects the next
`capture_envelope_surfaces()` invocation without an explicitly supplied collector.
Explicit collectors continue to follow their caller's configuration. Custom
profile paths require callers to use `create_collector(custom_path)`; saving a
custom path does not redirect the default runtime profile.

Missing profiles preserve existing serial behavior. Invalid or stale profiles
use complete collection with the conservative thread recommendation. JSON
duplicates, extra fields, boolean/negative/oversized worker counts, and process
settings are rejected. The profile is bounded to 16 KiB and tied to platform,
Python version, CPU count and implementation hash. The digest detects accidental
corruption; it is not a signature or an authority proof. Every loaded setting is
validated again. The previous valid setting is retained for a freshly checked
undo; a stale or corrupt profile cannot authorize undo.

The Windows launcher installs recommended settings on first use and preserves
an existing profile on subsequent launches. The rebuilt executable opens the
window with `pulpo-preview.exe tune`. Upgrade migration revalidates bounded
settings and preserves the previous setting before rebinding the profile.

## Authority and adversarial review

Purpose: provide performance choices without control over authority decisions.
Outcome: setup and tuning UI share one bounded configuration engine. No
configuration field controls audits, approvals, permits, replay protection,
evidence scope/exclusions, hashing, reconciliation or canonical state ownership.
The tuning code possesses no kernel or state backend. Performance measurements
are not authority evidence. Only the existing full-cycle benchmark creates
disposable canonical fixture states in its coordinator.

- Flip: hostile profiles may try to introduce skip flags or unlimited workers.
  Exact field validation and worker bounds reject them even with a recomputed
  digest; fallback still performs complete collection.
- Reverse: an evidence bypass would require changing collection scope or
  accepting incomplete snapshots. No such setting is exposed; canonical snapshot
  checks precede saves and benchmark acceptance. Existing runtime admission is
  unchanged, and explicit collector behavior remains its existing caller seam.
- Invert: speed does not imply correctness or authority. Failed checks block
  saving, and comparisons never automatically activate a candidate.
- Inside-Out: UI/configuration do not issue approvals or retain canonical writers.
  Source and machine binding are stale-hint checks, not independent trust roots.
- Darken: corrupted settings can reduce performance but cannot select weakened
  verification. Same-account benchmark workers are not an OS security sandbox.
- Lighten: ordinary tuning reads temporary fixtures and writes a local performance
  hint; it does not invoke the fixture executable or change live canonical state.
- Amplify: counts are capped, thread pools close per collection, profile reads are
  size-bounded, saves replace atomically, and process experiments terminate their
  own descendants on timeout. GUI actions serialize and closing waits for work.
- Negate: normal use needs no process pool. Keep process settings benchmark-only
  until production worker failure handling and admission are separately proven.

Continue decision: implement tooling and bounded existing-thread integration.
Smallest next proof: the new regression module, focused suite, full-cycle
self-test, then manual GUI exercise and a frozen build smoke test if packaging.

Verified: checked-in logs show 115 focused tests and 19 packaged smoke cases
passed for the tested source tree and executable hash. Recorded: the operator's
successful manual GUI/install check and process benchmarks on the 5950X.
Proposed: production use of process collectors, which remains unavailable.
Unknown: other hardware/OSes, full production readiness, and new remote CI.
No relevant historical checkpoint is asserted as proof of a reusable performance
lesson. This change does not promote synthetic timings into production evidence.
