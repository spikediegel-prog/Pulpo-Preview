# WSL Control Center installation and recovery preview

Status: Proposed for review. This is a WSL application package, not a native
Windows installer. Windows Setup & Repair development is deferred in
[the packaging plan](CONTROL_CENTER_PACKAGING_PLAN.md).

## Use the package

Prerequisites: WSL Ubuntu, Python 3.11 or newer, and Ubuntu's `python3-tk` package
for graphical windows. Use your normal WSL account, without sudo. The package
does not install system dependencies or repair the WSL graphics service.

Obtain `Pulpo-Control-Center-WSL.pyz` from a trusted source. In WSL, open it with:

```bash
python3 /path/to/Pulpo-Control-Center-WSL.pyz
```

The independent **WSL Setup & Repair** window offers Install, Repair / Reinstall,
Open, Uninstall and Check setup. This first preview needs that WSL launch command;
double-click installation from Windows Explorer is not implemented. It performs
no network access, Git operations, pip installation or automatic update.

The default application directory is `~/.local/share/pulpo-control-center`.
Installation writes only that owned directory and a maintenance lock beside it.
The lock remains after removal so another process cannot bypass a held lock by
recreating the pathname. No PATH, Windows shortcut or existing checkout is changed.
The package contains the existing Pulpo application modules and assets, an isolated
Python launcher and a separate copy of Setup & Repair. It uses the installed
system Python; no additional Python environment or optional authority service is
created. The launcher disables user Python paths and bytecode writes.

To reopen maintenance after installation:

```bash
python3 ~/.local/share/pulpo-control-center/Pulpo-Setup.pyz
```

Close the packaged Control Center before repair/removal. Other existing checkout
windows are separate installations. A shared application lifetime lock blocks
exclusive maintenance; the setup window disables its controls during an operation.

## Recovery without a working GUI

The original downloaded package remains usable when application modules or the
installed setup copy are damaged. Its command-line operations do not require Tk
or a display:

```bash
python3 /path/to/Pulpo-Control-Center-WSL.pyz check
python3 /path/to/Pulpo-Control-Center-WSL.pyz repair
python3 /path/to/Pulpo-Control-Center-WSL.pyz launch
python3 /path/to/Pulpo-Control-Center-WSL.pyz uninstall --yes
```

Check setup reports the Python/Tk prerequisites, whether DISPLAY is configured,
the recorded installed version and application file differences from the retained
package. DISPLAY presence is not a successful graphical connection. No source
exports, user settings, credentials or evidence databases are inspected. If the
retained package itself is damaged, use the original trusted package to repair.

Repair reconstructs missing or changed application files in a private sibling
staging directory, verifies CLI construction, then swaps directories. Failure
before replacement leaves the old application intact; a failed second rename
restores it. A retained `.previous` installation is recovered on the next repair
if the application directory is absent. If both copies survived an interruption,
neither is silently discarded: follow the reported uninstall-then-repair steps.
An abrupt process kill may leave a private staging directory; it is not
automatically searched or deleted. Inspect it manually before cleanup.

Removal requires a matching ownership record and refuses unexpected files,
symlinks, special files or substituted installation parents. Missing owned files
are repairable. An absent/corrupt ownership record fails closed; retain the
directory and have its contents reviewed rather than force-deleting it. Do not
store personal files inside the application directory.

Saved settings under `~/.config/PulpoPreview`, exported observations, evidence
databases and development checkouts stay outside package ownership. There is no
settings-reset or purge option. Opening the installed app uses its existing
settings behavior; restoring a saved source location still requires an explicit
first read. Repair cannot prove a collector is running or enforcement is verified.
Machine/source-bound tuning settings may require explicit revalidation after
changing application versions; repair does not rewrite those settings.

Internal hashes and the adjacent SHA-256 file detect damaged artifacts; they do
not authenticate the publisher. This preview is unsigned. A malicious package or
same-user attacker is outside this integrity check's protection. Normal user
filesystem permissions apply; this is not an OS sandbox or a trust boundary
against another process running as that user.

## Build and validate

```bash
python3 scripts/build_wsl_package.py --version 0.1.0-wsl-recovery-preview.1
python3 -W error -m unittest tests.test_wsl_package -v
python3 scripts/check_wsl_package.py dist/Pulpo-Control-Center-WSL.pyz --output /tmp/wsl-package-smoke.json
```

The version is the package version; the existing application project version is
unchanged. Payload hashes identify exact bundled application bytes. The recorded
Git revision identifies the checkout HEAD at build time; an uncommitted build
must not be represented as a clean release from that revision.

## Required change record

1. Failure addressed: recovery currently depends on a working checkout and
   manual commands; app damage should not prevent a separate maintenance tool.
2. Canonical authority is unchanged. Maintenance gains only ordinary user-level
   application installation/removal in its selected owned directory.
3. No canonical state mutation, owner, writer, credential handling or additional
   authority plane is introduced. The package ships existing modules; maintenance
   never imports Pulpo or instantiates a kernel. Its construction check invokes
   existing CLI help only. Open launches the existing observer/tuning UI.
4. Exact success/adversarial and packaged validation results are recorded with
   the review evidence; isolated synthetic canaries cover settings, evidence and
   checkout preservation, repeated repair/removal and interrupted replacement.
5. Evidence does not prove publisher authenticity, all Ubuntu/WSL versions,
   graphics-service repair, arbitrary hostile same-user races, production
   enforcement or generic update/rollback correctness. No update service exists.
6. Implementation is Proposed for review; passing checks are Verified only for
   their recorded cases; native captures are Recorded observations.
7. Existing CLI, UI, settings locations and Python zipapp are reused without
   copying a governance control path. The existing Windows installer is not run.
8. No relevant historical WSL package checkpoint exists. No temporal replay or
   generally reusable governance lesson is claimed.

## Analytical eight-pass review

- Flip: untrusted downloads execute code; internal hashes are explicitly not
  publisher authentication. Select a trusted artifact; do not auto-download.
- Reverse: accidental data deletion starts with path ownership confusion. Fixed
  directory naming, matching ownership metadata, no-follow path checks and
  refusing unknown entries constrain application cleanup.
- Invert: installation/CLI/GUI success never establishes verified enforcement.
- Inside-Out: the maintenance process holds no kernel, owner, source export,
  evidence database or human credential; it cannot grant governance authority.
- Darken: damaged metadata and unexpected files block cleanup; staging failures
  preserve the old application. Hostile same-user modification is not sandboxed.
- Lighten: missing Tk or a broken DISPLAY can explain startup failure without
  evidence of application corruption; diagnostics keep these checks separate.
- Amplify: repeat repair/removal and concurrent attempts must preserve data and
  respect maintenance/application locks. Recovery does not sweep nearby folders.
- Negate: use a small independent offline WSL package; defer Windows installers,
  automatic updates, settings reset and new runtime services.
