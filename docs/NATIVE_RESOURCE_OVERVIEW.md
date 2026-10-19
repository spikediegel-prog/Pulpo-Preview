# Native resource overview

The approved charcoal / purple / soft-white mockup is implemented inside the
existing Tk Control Center. Run `pulpo tune`; no service, browser, telemetry
account or new package dependency is needed. Ubuntu desktop/WSLg still needs
the standard `python3-tk` package.

## What is observed

The top of Overview contains live CPU, memory and storage graphs. The collector
reads only local OS resource counters and filesystem capacity:

- Linux CPU: deltas of aggregate `/proc/stat` counters. Guest time is not counted
  twice; idle includes iowait. The first interval, resets and failed reads are
  Unknown, never synthetic zero usage.
- Linux memory: `MemTotal - MemAvailable` from bounded `/proc/meminfo` reads.
  Missing/malformed counters are Unknown; `MemFree` is not substituted.
- Windows CPU/memory: `GetSystemTimes` and `GlobalMemoryStatusEx` via standard
  ctypes. Unsupported OS counters remain Unknown; no psutil dependency is added.
- Storage: `shutil.disk_usage` for `/` on Linux or the local home-drive root on
  Windows. The actual volume is labeled. This is capacity used, not disk I/O.

WSL is explicitly a Linux VM view, not the full Windows host. Physical-host,
per-process and container/cgroup-limit observations are not claimed.

Visible Overview samples every two seconds. Other pages, withdrawn/minimized
windows pause collection and reset the CPU interval. Timers are owned by the
window and cancelled on destruction. Reads are synchronous, bounded local
counter/stat calls, not remote probes; Python's ordinary bytecode caching can
still occur. No application telemetry file is created.

History is session-only, bounded to 1,801 observations (up to one hour at the
nominal interval). One-minute, 15-minute and one-hour views never invent history.
Missing readings or intervals over five seconds break the plotted line. History
is cleared when the window closes. The UI labels its source, observation time
and timezone, selected volume and seconds of history collected.

## Color and status semantics

Graphs are purple below 75%, amber from 75%, red from 90%. Labels and values
accompany the color. These are explicit resource-attention thresholds, not
security conclusions or universal CPU/memory sizing recommendations.

Below the graphs, horizontal expandable rows show Connections, Governance,
Evidence and System. The red-to-green bars use discrete state positions, not
averaged scores. Gray means Unknown. Resource failures are not averaged away;
the System summary identifies elevated readings or incomplete observations.
Green in System means only that all three observed resource values are below
the stated thresholds. It does not establish complete diagnostics or readiness.

Connections, Governance and Evidence remain Unknown because no authoritative
observer is configured. Resource values and disposable benchmark success cannot
change those rows into an enforcement or canonical-audit pass. Expanding a row
explains scope and the next step; its action uses the existing page navigation.
Existing evidence settings, validation, comparison, undo and export APIs remain
unchanged. First-run guidance remains below the status list. Narrow windows
stack graphs, wrap summaries and move time-range controls onto their own row.

## Authority / eight-pass review

Invariant: resource health and reachability must not be promoted into governed
execution. Authority unchanged; no canonical mutation introduced or exposed.
The sampler retains no kernel, executor, canonical state backend, signer,
credential or authority-service client. Existing local performance-setting
writes still require their original explicit actions and checks. No second
ledger, audit source, authority plane, provider route or remote listener exists.

- Flip: unavailable/malformed counters yield Unknown, not a convenient success.
- Reverse: the resource callback can update only the resource-scoped System row;
  it has no authoritative observation that could promote governance.
- Invert: a low reading or passing fixture never becomes deployment enforcement.
- Inside-Out: local session history is transient OS telemetry, not canonical audit.
- Darken: missing files, zero/reset CPU intervals, invalid memory, invalid storage
  and gaps are tested. They do not generate repaired or fabricated values.
- Lighten: first-interval Unknown and absent saved settings are normal first-run
  conditions, not evidence of an incident.
- Amplify: history and reads are bounded; one timer per monitor, hidden-page
  pause, and root-destruction cancellation prevent accumulating collectors.
- Negate: reuse Tk and standard local OS interfaces; no new daemon, database,
  credential or observation endpoint is needed.

Legacy behavior source: the existing canonical tuning UI and callbacks. The
approved mockup supplies layout only; its illustrative metrics are not shipped
in runtime code. Historical commits exist, but no cross-checkpoint temporal
transfer or reusable organizational lesson is admitted by this UI increment.

## Validation and remaining limits

See `control-center-evidence/native-resources/` for test transcripts, source
hashes and native WSLg captures. Claim classification: Verified for bounded
parsing, UI/lifecycle tests and observed rendering; Recorded for displayed OS
readings; Unknown for live deployment enforcement and untested platforms.
Synthetic threshold/error fixtures in tests are not actual host measurements.

Focused Windows and Ubuntu tests exercise unavailable/reset counters, threshold
boundaries, missing-history gaps, bounded retention, expandable rows, narrow
layout, hidden-page pause, existing comparisons/saves and callback cleanup.
The broader core gate retains three pre-existing cleanup warnings (HTTPError
and SQLite finalizers); it must not be presented as green solely because unittest
assertions pass. Screen-reader compatibility, all DPI scales, long-running
hour-history soak and packaged Linux distribution remain unqualified. No merge
or deployment is performed by this change.
