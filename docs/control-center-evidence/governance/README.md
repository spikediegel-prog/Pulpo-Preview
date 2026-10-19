# Native Governance observation evidence

Parent implementation: `f3a982f0a5eccd65ad043894d34f3c65abe93ac3` (PR #23).
Scope and eight-pass authority review: [Governance observer](../../GOVERNANCE_OBSERVER.md).

## Verified bounded validation

- Windows Python 3.12.10: **80 tests, OK, five POSIX-only skips**.
- Ubuntu WSLg Python 3.14.4: **80 tests, OK, two Windows-only skips**.
- Ubuntu full core: **711 tests, no assertion failures, two Windows-only skips**.
  The strict runner **fails** on three existing ResourceWarnings (HTTPError
  cleanup and two SQLite finalizers), also recorded before this change in the
  resource-overview evidence. The full gate is not green. Full-core ran before
  the final presentation-only row reflow; the focused suite ran after it.
- Native visual inspection at 1200 x 900 and 640 x 600; source selection through
  the native picker, row expansion, scrolling and minimum-width controls.

```text
python3 -W error -m unittest tests.test_governance_observer tests.test_mcp_plugin tests.test_mcp_boundary tests.test_control_center tests.test_local_resources tests.test_evidence_tuning -v
python3 scripts/run_pulpo_tests.py --suite core --log-dir ../governance-core-results
```

Same focused command with the bundled Windows Python. Raw transcripts and the
strict core summary are adjacent. Tests cover a real disposable canonical
export, repeated/replayed/substituted reads without canonical audit or snapshot
changes; missing/relative/directory/FIFO inputs; duplicate/injected/malformed/
oversized/deep JSON; inconsistent counts/tips; empty and failed audit reports;
selection cancellation, failed refresh clearing prior values and session clear.
The existing loader tests cover private permissions, symlink/reparse checks,
Windows handle sharing and trusted export behavior. None imply hostile host
containment or authenticated deployment observation.

## Captures

Captures are native WSLg windows, cropped only to remove surrounding desktop.

- `before.png`: exact base-commit Governance page, loaded as a temporary module
  for visual comparison. The repository source was not replaced.
- `empty.png`: new first-run page; all evidence Unknown.
- `test-snapshot.png`: real export from a disposable in-memory canonical kernel
  with a read-only policy and an actually empty audit. The export is not from a
  deployment and cannot prove enforcement. No fabricated sample metrics.
- `narrow.png`: minimum-width responsive rows.

Manual inspection used separate absent performance profiles; no profile was
saved. No authority credentials, permits or deployment data were used. The test
export lives outside the checkout; no canonical database was opened by the UI.

Claims: **Verified** for these bounded checks, **Recorded** for selected metadata,
**Unknown** for freshness, provenance and live deployment governance. No merge or
deployment. Source/test hashes are in `source-hashes.json`.
