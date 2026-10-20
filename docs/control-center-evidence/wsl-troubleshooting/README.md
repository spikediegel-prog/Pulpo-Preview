# Recorded WSL troubleshooting evidence

Scope, authority boundary and required analytical review: [WSL troubleshooting](../../WSL_TROUBLESHOOTING.md).

## Tests

- Ubuntu WSL Python 3.14.4: 116 focused tests passed with warnings treated as errors.
- Ubuntu WSL core: 833 tests passed with two platform-specific skips and no resource warnings.
- Exact logs: [focused](ubuntu-focused.log), [core](ubuntu-core.log), [core summary](ubuntu-core-summary.json).
- [Source and log hashes](source-hashes.json) record the exact tested source files (LF-normalized, matching Git blobs), exact log bytes and historical base commit.
- UI tests actually read a private temporary Evidence export, check its capacity, reject its subsequent invalid replacement, suppress old measurements and export the exact frozen preview. Other cases exercise export cancellation/failure, source privacy under injected raw text, stale/future observations, missing capacity, WSL-only gating, keyboard/narrow layout, cache-only navigation and teardown. These are controlled test fixtures, not live production measurements.

## Native visual inspection

Native WSLg captures are cropped to the application window. The before tree is the previous local WSL commit cf913895c8c14fb6aa3a526e8bf983b4337b5c8c, whose application files match the recorded main base. The inspection uses a separate absent performance-profile path; no performance hint was saved.

- [Before](pulpo-wsl-troubleshooting-before.png): existing System diagnostics.
- [After](pulpo-wsl-troubleshooting-after.png): new nine-row view after an explicit existing local diagnostic refresh. Live service health and unselected source/capacity observations remain Unknown. No invented metrics.
- [Report](pulpo-wsl-troubleshooting-report.png): visible frozen JSON preview and explicit export control.
- [Minimum size](pulpo-wsl-troubleshooting-narrow.png): 640 × 600 content window, two-column System tabs and vertical scrolling.
- [Narrow controls](pulpo-wsl-troubleshooting-narrow-controls.png): scrolled action buttons and report preview remain available without horizontal clipping.
- [Recorded preview](recorded-preview.json): exact safe projection from the narrow inspection; only the local diagnostic refresh was performed. Wide and narrow previews have separate generation times.

All observations are Recorded, not independently authenticated. No live service probe, provider request, database opening, repair, restart, permission change, recovery test or governance attestation occurred. This evidence does not establish full accessibility or production readiness. Windows runtime qualification is outside this WSL-only change.
