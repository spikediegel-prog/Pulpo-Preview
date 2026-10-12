# Original overall-cycle workload on Linux

The launcher now defaults to **serial only**. Helpers are explicitly opt-in for
testers: pass `-Helpers 2` for serial/two-helper comparison or `-Helpers 4`
for serial/four-helper comparison. The source CLI defaults to `--workers 0`.
Record counts, repeats, iterations and file fixture remain unchanged. It saves a
helper comparison against the prior serial/four-helper Linux report. Pass
`-Helpers 4` to reproduce the original four-helper configuration below. This
changes benchmark selection, not an installed global evidence profile. A small
Windows functional check passes with serial and two helpers; Linux two-helper
performance measurements are verified below.

The dedicated PowerShell launcher runs the existing cycle benchmark against a
fresh, source-hash-verified local snapshot on disk-backed ext4. WSL temporary
databases and evidence files stay on that Linux filesystem. Only result logs and
JSON are copied/written to Windows outputs after measurements.

Settings match the original Windows baseline:

- Histories: 1000, 10000 and 50000 audit records.
- Evidence workers: serial (0) and four threads.
- Five repeats, ten iterations per case: 50 cycle samples per combination.
- Four surfaces, 20 files per surface, 4096 bytes per file.
- Existing FULL SQLite durability; no process-worker/resource-sampling additions.

The eight stage timings cover approval/permit issue, durable permit consumption,
before evidence, simulated file effect, after evidence, reconciliation/digest,
canonical evidence append and total cycle. Startup/first capture/shutdown and
amortized timing are separate. Fresh-process full/checkpoint/checkpoint-plus-20
restart timings are recorded. Fixture setup, approval signing and postchecks are
excluded as in the original benchmark; OS caches are not flushed.

This is the original benchmark workload on current local code. It uses synthetic
approval fixtures and disposable databases. It does not route/batch writes through
the idle scheduler, and cannot attribute cycle changes to idle batching. The
local evidence read size and cleanup code differ from the original Windows
baseline; Python, SQLite and filesystem stacks also differ. The generated
comparison reports those limits instead of claiming an isolated OS speedup.

The launcher runs only this workload, without repeating earlier suites. It saves
`overall-cycle-linux.json`, `overall-cycle.log`, original Windows baseline,
source manifest, filesystem metadata, comparison JSON/Markdown and a run summary.
Resource warnings fail the runner even if the benchmark process returns zero.
Comparison rejects mismatched workload settings and non-Windows/Linux platforms.

Verified run `wsl-results-20261012-034015-9681` completes on WSL2 Python 3.14.4,
disk-backed ext4, with verified source overlay, zero resource warnings and both
benchmark/comparison exit codes zero. All original workload settings match.

| History records | Serial cycle ms | Four-thread cycle ms | Serial amortized ms | Four-thread amortized ms |
| ---: | ---: | ---: | ---: | ---: |
| 1000 | 14.159 | 49.506 | 14.807 | 51.939 |
| 10000 | 14.607 | 49.477 | 17.501 | 53.399 |
| 50000 | 13.825 | 49.357 | 26.110 | 62.718 |

Recorded evidence capture is approximately 1.8-2.0 ms serial versus 19.1-19.5 ms
with four threads, for 80 small 4096-byte files. Four helpers are about 3.4-3.6
times slower for the full cycle in this fixture; the observation does not justify
changing all workloads or all installations to serial.

Serial approval/permit issue, permit consumption and evidence append each cost
approximately 3.0-3.4 ms, accounting for most of the roughly 14 ms cycle. Their
canonical authority and durability boundaries remain unchanged by measurement.
Kernel bootstrap grows from 2.3 ms at 1000 records to 103.4 ms at 50000 records,
raising amortized cost despite stable steady-cycle timings.

At 50000 records, full restart verification is 297.3 ms, checkpoint restart 105.9
ms, and checkpoint-plus-20 restart 162.6 ms. Restart timing excludes schema
initialization and uses fresh processes without clearing OS caches. These are
recorded restart measurements, not a proposal to trust only audit-head metadata.

## Two-helper Linux validation

Verified run `wsl-results-20261012-035414-11039` completes with the same record
counts, five repeats and ten iterations, zero resource warnings and both runner
exit codes zero. The paired serial control is stable at roughly 14 ms.

| History records | Current serial ms | Prior four helpers ms | Current two helpers ms | Two-helper amortized ms |
| ---: | ---: | ---: | ---: | ---: |
| 1000 | 13.792 | 49.506 | 23.753 | 24.738 |
| 10000 | 14.050 | 49.477 | 23.716 | 26.774 |
| 50000 | 14.105 | 49.357 | 23.667 | 36.156 |

Two helpers lower steady cycle time by approximately 52 percent versus four
across these separate runs. Serial remains approximately 40-42 percent faster
than two helpers in the current run. Evidence capture takes approximately
1.8-2.0 ms serial versus 6.6-6.7 ms with two helpers. This supports fewer helpers
for the small-file fixture, not a universal configuration rule. The requested
helper option remains available; serial is now the default. Runtime helper
profiles likewise require a valid explicit choice; missing/invalid profiles use serial.
