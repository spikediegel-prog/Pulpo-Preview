# Pulpo Preview with performance tuning

This package includes the preview executable, a per-user installer script and
the tuning window. No Python installation or administrator account is required
to run the packaged app. Processes remain benchmark-only in the source checkout.

Extract the ZIP, then run in its folder:

```powershell
# Recommended first install; preserve an existing valid custom setting on upgrade
pwsh -NoProfile -File .\Install-PulpoPreview.ps1

# Explicit custom install or update (example: four threads)
pwsh -NoProfile -File .\Install-PulpoPreview.ps1 -Mode Custom -Workers 4
```

The executable installs to `%LOCALAPPDATA%\Programs\PulpoPreview` and settings
remain in `%LOCALAPPDATA%\PulpoPreview`. Start-menu shortcuts open setup and
performance tuning. `-ResetSettings` explicitly selects recommended settings
instead of preserving them. `-NoShortcuts` is for isolated installation tests.

Upgrades validate the saved thread bounds and snapshot correctness before
rebinding an old hint to the new executable. Unsupported/corrupt profiles fail
the installer without overwriting settings; a previous executable is restored
when available. Each previous executable backup has a unique filename and is
retained. No service, PATH, firewall, policy, live audit or credential change is
made. Files in the profile directory are never removed by this installer.
The manifest hash is a package consistency check, not a publisher signature.

## Operator checks from the source checkout

```powershell
python scripts/run_pulpo_tests.py --suite focused --log-dir perf-results/tuning-package-tests
python scripts/check_windows_exe.py dist/windows-tuning-preview/pulpo-preview.exe --installer dist/windows-tuning-preview/Install-PulpoPreview.ps1 --output perf-results/tuning-exe-smoke.json --work-dir work/tuning-exe-smoke
```

The smoke script isolates LOCALAPPDATA, avoids real Start-menu shortcuts, and
removes Python from the app's search PATH. It checks bundled Tk widgets, custom
settings, migration from a synthetic stale executable binding, and repeat
installation. It is not visual approval of the window or an upgrade proof from
every historical release. Open the installed tuning shortcut for that manual
check. Automated test execution is left to the operator.

Build with the existing dependency environment:

```powershell
pwsh -NoProfile -File scripts/build_windows_exe.ps1 -SkipDependencyInstall
```

Omit `-SkipDependencyInstall` when build dependencies need installation. Outputs
are `dist/windows-tuning-preview/` and `dist/pulpo-preview-tuning-windows.zip`.
The earlier `dist/windows-preview/` artifact remains available.

## Adversarial review and claims

Purpose: package the approved tuning UI and preserve bounded performance hints.
Flip: reject corrupt/extra-control profiles and verify copied executable hashes.
Reverse: setup/tuning have no canonical state writer; installer touches only
program files, local hints and shortcuts. Invert: faster settings are not an
authority success; fresh snapshot checks precede migration. Inside-Out: hashes
detect consistency, never grant authority. Darken: same-user file replacement is
not a sandbox against hostile local code. Lighten: install is an ordinary local
preview tool deployment. Amplify: upgrades retain unique executable backups,
serialize profile replacement, and do not remove settings. Negate: source tuning
and the original portable preview remain available.

Continue: submit the tested package sources for review; do not assert production
readiness. No relevant historical checkpoint is promoted as reusable runtime
evidence. Verified: 115 focused tests and 19 packaged smoke cases passed in the
committed operator logs. Recorded: build output and the operator's successful
manual installation/GUI check. Unknown: other hardware, historical release
upgrades, broader production readiness, and new remote CI.
