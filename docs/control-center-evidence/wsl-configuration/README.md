# Recorded WSL Configuration Comparison evidence

Scope and required eight-point/eight-pass record: [Configuration Comparison](../../WSL_CONFIGURATION_COMPARISON.md).

## Validation

- Ubuntu WSL Python 3.14.4: 110 focused tests passed with warnings treated as errors.
- Ubuntu WSL core: 827 tests passed, including two platform-specific skips; no resource warnings.
- Exact logs: [focused](ubuntu-focused.log), [core](ubuntu-core.log), [core summary](ubuntu-core-summary.json).
- [Source and exact log hashes](source-hashes.json) bind the tested files and record the base commit. Source hashes normalize CRLF to LF to match Git blobs.

## Native inspection

All images are native WSLg captures cropped to the application window. No invented measurements or saved candidate were used.

- [Before](pulpo-wsl-configuration-before.png): existing benchmark controls from the previous local WSL tree, whose application code matches the recorded base.
- [After](pulpo-wsl-configuration-after.png): first-run comparison with missing profile, serial default, suggested candidate, Unknown history and no report.
- [Real benchmark](pulpo-wsl-configuration-benchmark.png): the existing disposable comparison completed, correctness PASS. [Actual report](real-benchmark.json) omits the internal profile token. Serial baseline median 4.35 ms; two-worker candidate median 8.34 ms; classification Slower. Five alternating runs per setting, 64 files / 4 MiB capture-only fixtures. No profile was created or saved. This is one workload observation, not a production recommendation or governance attestation.
- [Minimum size](pulpo-wsl-configuration-narrow.png): 640 × 600 content window with wrapped tabs and vertical scrolling.
- [Lower controls](pulpo-wsl-configuration-narrow-controls.png): narrow scrolled view, both action buttons and scope text accessible. A local proposal edit during inspection changed the candidate to zero; no save occurred.

The before/after captures and benchmark use an isolated absent performance-profile path. Historical change time and operator motivation remain Unknown. These recorded checks do not establish full accessibility, production performance, authority enforcement, authenticated history, continuous external-change monitoring or a hard filesystem-read deadline. Windows runtime qualification is outside this change.
