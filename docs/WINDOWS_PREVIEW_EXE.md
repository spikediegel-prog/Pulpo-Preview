# Pulpo Preview - The Mad Lads Playground: Windows executable

This is an unofficial **portable Windows x64 setup CLI**, bundled with Python. It is not an MSI installer, Windows service, desktop governance UI, official release, or production-readiness claim. Optional MCP and asymmetric cryptography extras are not included in this setup-only build.

## Use the executable

Extract the downloaded ZIP into a folder, then double-click `pulpo-preview.exe`. Quick start runs the existing setup self-check with conservative settings and writes `%LOCALAPPDATA%\PulpoPreview\setup-report.json`. It checks that a valid synthetic audit is accepted and a tampered stored hash is rejected. No calibration or authority change is requested by quick start. Press Enter to close the console.

For explicit calibration or other setup options, open PowerShell in that folder:

```powershell
.\pulpo-preview.exe --help
.\pulpo-preview.exe setup --json-report setup-report.json
```

Explicit `setup` retains the source CLI defaults: a profile under `.pulpo` in the current directory and bounded synthetic calibration if no matching profile exists. Reports do not authorize consequential execution. The machine-bound profile is performance data, not an authority credential.

## Download from the preview branch

Open [Windows Preview Executable runs](https://github.com/spikediegel-prog/Pulpo-Preview/actions/workflows/windows-preview-exe.yml), choose a successful run at the desired preview commit, and download its `pulpo-preview-windows-x64-<commit>` artifact. GitHub sign-in may be required. Artifacts expire after 30 days. The ZIP contains the executable, these instructions, its SHA-256 checksum, source commit, and executable smoke-test results. Read the [preview evidence and Windows limitations](https://github.com/spikediegel-prog/Pulpo-Preview/blob/preview/PREVIEW.md) before testing.

The executable is unsigned. Code signing and independent clean-machine reproduction remain Unknown; do not treat a checksum as a publisher signature. No Windows security protection is disabled by the build or instructions.

## Reproduce the build

On Windows with Python 3.11 or later available:

```powershell
.\scripts\build_windows_exe.ps1
python scripts/check_windows_exe.py dist/windows-preview/pulpo-preview.exe --output dist/windows-preview/smoke-test-report.json --work-dir work/windows-exe-smoke
```

The builder uses an isolated environment under `work/windows-exe-build` and pinned PyInstaller dependencies. It packages the existing `pulpo.cli` through a launcher that calls `multiprocessing.freeze_support()` before parsing command-line arguments. No governance decision, permit, budget, transaction, or audit algorithm is replaced. Dependencies come from the standard Python package registry; frozen binaries are built on Windows rather than cross-compiled. See [PyInstaller usage](https://pyinstaller.org/en/stable/usage.html) and [multiprocessing guidance](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#multi-processing).

## Evidence and boundaries

Verified local prototype: Windows 11 x64, bundled Python 3.12.10, PyInstaller 6.22.3; seven executable checks passed with project source and Python removed from the search path. Checks cover help, quick start, conservative fallback, multiprocessing calibration, matching-profile reuse, and invalid-command rejection. Local prototype executable checksum and size are in [the recorded smoke result](https://github.com/spikediegel-prog/Pulpo-Preview/blob/preview/perf-results/windows-exe-smoke.json); each hosted build has its own checksum and evidence. Builds are not claimed byte-for-byte reproducible.

The full Windows suite still has recorded pre-existing failures. Bundling does not repair those features. Passing setup confirms only its bounded software self-check. Physical-hardware performance, deployment containment, live provider behavior and universal Windows compatibility remain Unknown.
