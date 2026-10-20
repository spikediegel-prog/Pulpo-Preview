# WSL recovery package review evidence

Implementation commit: `1258605c1549726be0334e452f6d384affc2dd65`.
Package version: `0.1.0-wsl-recovery-preview.1` (unsigned review preview).

The exact full core log records **898 tests, OK with 2 Windows-specific skips**,
with warnings treated as errors. All 26 WSL package tests passed, including the
independent setup-window construction test, launcher lifetime locking, explicit
removal confirmation, invalid ownership, symlinks/traversal, tampered package
contents, unexpected files, failed/interrupted replacement and repeated repair.

`packaged-smoke.json` records 12 real zipapp lifecycle cases in isolated temporary
HOME and application directories: initial check, installation, packaged GUI
construction, installed check, corruption diagnosis, repair, repair using the
retained setup copy, GUI construction after repair, removal twice,
reinstallation and final removal. Synthetic canaries at the actual saved-profile
and session-preference filenames, an evidence database location and a checkout
location remained byte-for-byte unchanged. No production workload, state
database, credential or evidence export was inspected.

`artifact-binding.json` binds the exact archive SHA-256, package manifest,
implementation commit, packaged manager hash and exact full-suite log hash.
Every bundled Python file was compared with the committed source after CRLF/LF
normalization; asset bytes matched exactly. The application payload is unchanged
from the existing UI. The artifact was built from the clean implementation
commit before these evidence-only files were added.

## Native visual inspection remains outstanding

The independent setup window was launched against a separate temporary test
installation. Native window inventory reported
`[WARN:COPY MODE] Pulpo — WSL Setup & Repair (Ubuntu)`. After activation, native
capture showed the background desktop rather than the application's contents.
The existing Control Center window had the same WSLg warning before this work.
No screenshot of unrelated applications was saved as product evidence; no visual
approval is claimed. GUI widget construction passed, but that does not prove
usable WSLg presentation. The temporary setup process was closed and its owned
test application was uninstalled. The current user checkout and shortcuts were
not changed. No Windows installer, merge, release publication or deployment was
performed.

These checks do not establish publisher authentication, production enforcement,
graphics-service repair, all supported Ubuntu/Python versions or resistance to a
hostile process already running with the same user's OS permissions.
