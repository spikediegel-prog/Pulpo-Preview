# Recorded WSL usability evidence

Scope and required eight-point/eight-pass review: [WSL usability](../../WSL_USABILITY.md).

## Validation

- Ubuntu WSL Python 3.14.4: 133 focused tests passed with warnings treated as errors.
- Ubuntu WSL core: 850 tests passed, with two platform-specific skips and no resource warnings or Tk callback exceptions in the recorded logs.
- Exact logs: [focused](ubuntu-focused.log), [core](ubuntu-core.log), [summary](ubuntu-core-summary.json).
- [Source/log hashes](source-hashes.json) bind LF-normalized tested files, exact log bytes and the common base commit.
- Model tests cover real cached age/span, paused time and missing/future/non-finite timing without fabricated zero/current values. UI tests cover cache-only Details, activation/teardown timers, direct view links, per-area recall with source reads/saves blocked, saved-session and guide navigation, larger buttons and full Tk scaling 2.0 at 640 × 600. The scaled regression checks keep all graph ranges inside their frame, legend labels inside their legend, Details clear of the legend, and expanded text inside the viewport width. Graph scale captions wrap as well.
- [Calculated legend contrast](legend-contrast.json) records foreground/background colors and luminance ratios for the text labels. This calculation and the keyboard/layout checks are bounded evidence, not a complete accessibility certification.

## Native visual inspection

Captures are native WSLg images cropped to the application window. Before uses local commit 110a0c7d9ba1598a572176f04864664098781d16, whose application tree matches the guided setup subsequently merged to main. Inspection profiles live in isolated private temporary directories. Resource measurements are actual local WSL samples; captures occur at different times and are not a benchmark comparison. No synthetic resource metrics, source export, performance setting or personal preference was saved.

- [Before](pulpo-wsl-usability-before.png): the flat seven-view System navigation and long resource caption.
- [After](pulpo-wsl-usability-after.png): Monitor with contextual view controls, readable location line and collapsed status strip.
- [Details](pulpo-wsl-usability-details.png): native Details click reveals exact local timestamp, VM/volume scope, thresholds and gaps; button focus is visible.
- [Set up](pulpo-wsl-usability-setup.png): native area navigation shows Guide & checklist and Remember setup while retaining the existing checklist.
- [Tune](pulpo-wsl-usability-tune.png): native navigation shows Compare settings and Benchmarks. No comparison was run or candidate saved; results remain unavailable.
- [Larger text](pulpo-wsl-usability-large.png): 640 × 600 with Tk scaling 2.0, wrapping area/view buttons and graph range controls; vertical scrolling remains available.
- [Scaled strip](pulpo-wsl-usability-large-strip.png): all four legend labels and Details remain readable and separate at the larger text scale.
- [Scaled details](pulpo-wsl-usability-large-details.png): expanded resource detail text wraps within the content width and remains vertically scrollable.

These Recorded checks do not cover every font/DPI/window combination, independently authenticate sample time/source, prove service or fleet health, establish governance enforcement or certify complete accessibility. Windows qualification is outside this WSL-only increment.
