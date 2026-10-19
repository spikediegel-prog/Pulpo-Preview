# Evidence monitor: bounded validation

Base `ee33ece`. Design, integration, authority boundary, exact counter meanings,
limits and eight-pass review: [Evidence monitor](../../EVIDENCE_MONITOR.md).

## Tests

- Ubuntu WSLg / Python 3.14.4: **163 targeted tests pass**, two Windows-only skips.
- Windows / Python 3.12.10: **163 targeted tests pass**, six POSIX-only skips.
- Final strict Ubuntu core: **757 tests pass**, two Windows-only skips,
  **zero ResourceWarnings**, runner exit 0. Includes final pause/resume and FIFO
  protection changes. The cleanup fix already merged in PR #25 is the base.

A broad rerun exposed Tk variables finalized by worker-thread garbage collection
after window closure. The fix gives variables explicit window ownership, releases
variables/traces and breaks callback cycles on the owning UI thread. Regression
coverage checks weak references are cleared before worker collection. Final core
passes without that abort or resource warnings. The final targeted run also covers
the last Overview evidence-description clarification.

```text
python3 -W error -m unittest tests.test_evidence_observation tests.test_control_center tests.test_resource_lifecycle tests.test_mcp_boundary tests.test_mcp_plugin tests.test_ollama_proposal tests.test_governance_observer tests.test_local_resources tests.test_evidence_tuning tests.test_persistence tests.test_audit_checkpoint -v
python3 scripts/run_pulpo_tests.py --suite core --log-dir ../evidence-core-final
```

Same targeted command with bundled Windows Python/Tk. Raw transcripts and strict
summary are adjacent. Source hashes use LF-normalized bytes for portable review.

Cases cover actual SQLite transaction success/rollback/deferred commit failure,
unchanged DB bytes/audit under repeated exports, privacy redaction and 24-record
cap, wrong/live-transaction owner rejection, absent memory-backend metrics,
strict schema and FIFO rejection, duplicate/replayed/substituted samples,
counter resets, missing counters, source changes, time gaps, bounded history,
source freshness, optional Ollama usage with unchanged proposal API, source
selection, alerts, filter matching, pause/resume, hidden-page pause, invalid
refresh clearing values, existing source loader, tuning and cleanup behavior.

## Native inspection

Before/after at 1200 x 900; narrow layout at 640 x 600. Checked actual native
file selection, live graph updates, row reflow, keyboard paging, Pause for review,
gray health during review, and the Rejections filter with stable copyable hashes.
The existing full tuning interface remains available in its expandable section;
automated comparison/save/failure-recovery tests exercise that compatibility path.

- `before.png`: exact base-commit Evidence UI, loaded in a separate inspection
  process from temporary base sources; repository files were not replaced.
- `monitor.png`: **actual measured activity from a disposable canonical SQLite
  workload**. Test read decisions, consumption, replay rejection and policy
  denials are real local test transitions; no deployment activity is implied.
- `narrow.png`: all three graph series and reflowed review control.
- `narrow-review.png`: explicit historical review with positive health gray.
- `alerts.png`: separate AI Unknown values, meaningful warnings and filtered
  canonical rejection references. No raw payload, bearer permit or prompt.
- `stale.png`: stopped source; current rates Unknown and passing physical
  health/capacity indications gray rather than a false current all-clear.

Captures are cropped only to remove the surrounding desktop. AI inference was
not run for screenshots and no AI metrics were fabricated. Synthetic provider
response fixtures verify valid/missing/malformed token metadata separately.
The disposable owner was stopped after inspection and exited cleanly. Separate
inspection profiles remained absent; no setting was saved.

Production observation requires the documented owner-side export integration;
no database is opened by the UI. Deployment identity/provenance, enforced quotas,
provider billing, full evidence payload review, backups/recovery, screen-reader
and all-DPI qualification, large-production-DB overhead and hostile host/ACL
containment remain outside this evidence. No merge or deployment.
