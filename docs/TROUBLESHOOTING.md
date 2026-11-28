# Pulpo troubleshooting notes

Ongoing notes — what broke, why, and how it was fixed. Add dated entries
as new issues are found; this is a living record, not a polished manual.
Each entry names the symptom, the cause, and the fix or workaround.
Entries fixed in a shipped build say so. Entries that can recur say so,
because a one-time fix is not a fix for those.

Related docs: Control Center setup and troubleshooting live in the
Control Center repo (`docs/UBUNTU_QUICK_START.md` and
`docs/UBUNTU_XFCE_TROUBLESHOOTING.md`, which carry the Control Center
known issues in full). Installer docs live in `installer/`
(`README.md`, `DISK-INSTALLER.md`, `BOOT-TEST.md`, `INSTALL-TEST.md`).
WSL-specific troubleshooting is in `docs/WSL_TROUBLESHOOTING.md`.

## Control Center on Ubuntu — known issues

These recur on Ubuntu. An Ubuntu update can bring them back, so they are
recorded here as known issues rather than fixed by a one-time workaround.

### Network: "Apply network settings" fails (netplan permissions)

Symptom (seen on preview.50 and preview.58 / build #38, 2026-11-27): in
Control Center, Network settings, clicking **Apply network settings**
fails with:

```
Apply failed: netplan_generate_failed: ** (generate:5393): WARNING **:
Permissions for /etc/netplan/01-network-manager-all.yaml are too open.
Netplan configuration should NOT be accessible by others.. Nothing was changed.
```

Cause: Ubuntu ships `/etc/netplan/01-network-manager-all.yaml` readable
by others, and netplan generate refuses to run while that file is too
open. Control Center saves the values you entered (shown as "Saved
configuration") but the apply step cannot change the system, so the
address stays as it was.

Fix: tighten the file, then Apply again in Control Center:

```bash
sudo chmod 600 /etc/netplan/01-network-manager-all.yaml
```

Workaround: set the address through Ubuntu Settings (or `nmcli` /
netplan directly) instead of Control Center.

Recurrence: an Ubuntu update can replace or reset that file and
reintroduce the too-open permissions, so the same Apply failure can come
back after an update. If it does, re-run the `chmod 600` above and Apply
again. The durable fix — Control Center writing the file with mode 0600
itself — is planned for a future Control Center build and is not yet
shipped. Seen on preview.50 and preview.58 (build #38).

### apt-get upgrade removed the gateway

Symptom (confirmed live 2026-11-28, build #38 on Beta): after setting a
static address (192.168.250.20/24), gateway (192.168.250.1), and DNS
through Ubuntu Settings, running `apt-get upgrade` removed the gateway
by the time the upgrade finished. No default route remained, so the
appliance could not reach the internet directly.

Cause: not yet isolated. The gateway set through Ubuntu Settings did not
survive the upgrade — the update reset the network configuration. This
is the recurrence the entry above warns about, now confirmed rather than
hypothetical: an update can undo network settings. It may have been a
specific Ubuntu patch that caused it, and a future patch may correct it
— that is not known. Until it proves otherwise, treat the gateway as
something to re-verify after every update.

Fix: re-add the gateway (through Ubuntu Settings, or `nmcli`, or netplan
with the file at 0600 followed by `netplan apply`), then verify a default
route exists with `ip route`. After every `apt-get upgrade` or Ubuntu
update, re-check `ip route` and the Control Center network display — do
not assume the gateway survived the update.

Status: known issue, confirmed live 2026-11-28. Root cause not yet
isolated; the gateway must be re-verified after each update until the
underlying reset is understood. Resolved the same night by a restart,
which restored the gateway (NetworkManager re-applied the saved
connection), plus `sudo chmod 600` on the netplan file so the Control
Center Apply can run.

### Saved network shows DHCP or empty while the system has a static address

Symptom: after setting a static address outside Control Center (for
example through Ubuntu Settings), Control Center's saved network still
shows DHCP or empty, even though the system is using the static address.

Cause: Control Center shows its own saved configuration, not the live
system state. An address set outside Control Center is not picked up
into its saved view.

Workaround: verify the live address with `ip addr` or Ubuntu Settings.
Set the address through Control Center (once the Apply fix above is in
place) so its saved configuration matches the system.

### Display timezone defaults to Etc/UTC

Symptom: times in Control Center show in Etc/UTC even when the system
timezone is set to another zone (for example America/Phoenix).

Cause: the Control Center display timezone is its own setting, separate
from the system timezone, and it defaults to Etc/UTC. This is how it
functions, not a bug.

Fix: set the display timezone in Control Center to match the system
timezone.

## Installer and ISO build

### Installer refuses the Control Center .deb (version pin skew)

Symptom (build #37, 2026-11-27): Calamares fails with
`install-cc-deb.sh` exit 1 — "release bundle file missing:
.../pulpo-control-center_0.1.0~ubuntu.preview.50+e3.0625357_amd64.deb"
and "signed release verification failed; refusing to install".

Cause: `installer/calamares/install-cc-deb.sh` hardcodes the expected
Control Center version/revision/deb name, and the ISO bundled a newer
Control Center than the pins named. The installer correctly failed
closed on the skew.

Fix: update the pins in `install-cc-deb.sh`, the matching test pins in
`tests/test_disk_installer.py`, and the defaults in `installer/build-iso.sh`
so all three name the bundled version. Fixed in Preview PR #169;
build #38 carries the corrected pins (preview.58) and installs.

Rule: whenever the bundled Control Center version changes, the pins and
the bundle must change together. A version bump in one place without the
others reproduces this failure.

### Install launcher shows no icon (stale icon cache)

Symptom (build #37, 2026-11-27): the live desktop shows "Install Pulpo
Preview" with a generic document icon.

Cause: `pulpo.png` was in the rootfs at
`/usr/share/icons/hicolor/512x512/apps/pulpo.png`, but the base image's
`icon-theme.cache` did not list it and `build-iso.sh` never ran
`gtk-update-icon-cache` — GTK treats the cache as authoritative.

Fix: `build-iso.sh` now runs
`gtk-update-icon-cache -f "$ROOTFS/usr/share/icons/hicolor"` after
copying `pulpo.png`. Fixed in Preview PR #169; build #38 shows the icon.
Verify in a built rootfs with `grep -c pulpo` on the cache (build #38: 2;
build #37: 0).

### Build takes ~18 minutes; the rsync step is the slow part

A full ISO build takes about 18 minutes. Step [3/8] (rsync of the merged
view to a plain directory, ~232,819 paths) is the slow part; the build
can sit on that step for 10+ minutes with no new log lines. That is
normal. Do not kill it for appearing stuck — check that the rsync is
still running before concluding it hung.

### build-iso.sh hard-requires the signed release bundle

If the Control Center `.deb`, `release.json`, or `release.json.asc` is
missing from the expected paths, `build-iso.sh` exits 1 before the long
build starts. That is a fast, safe failure — check the bundle paths
first. The defaults now point at the preview.58 bundle (PR #169); pass
explicit paths if a different bundle is intended.

### Building a Control Center .deb needs PySide6 6.9.3 exactly

The Control Center build script refuses PySide6 versions other than
6.9.3. The system may have a newer PySide6 installed (6.12.0 was present
on the Dev VM). Install the exact version with
`pip install --user --break-system-packages PySide6==6.9.3` before
building the `.deb`.

### xorriso is not on the system PATH

`xorriso` (used to read and write ISOs) is fetched as a `.deb` and
extracted into the build environment, not installed system-wide. On the
Dev VM it lives at
`~/pulpo-workspace/iso-build/rootfs/usr/bin/xorriso` — invoke it with
`LD_LIBRARY_PATH` set to the matching lib dir, as `build-iso.sh` does.
To pull a file out of a built ISO without mounting (sudo mount needs a
password), use `xorriso -osirrox on -indev <iso> -extract <iso-path>
<local-path>`, then `unsquashfs` to inspect the squashfs.

### A redundant preview.51 .deb sits in the Control Center dist/

A `preview.51` `.deb` built from the same Control Center source sits in
the Control Center repo's `dist/` and is redundant. Do not use it. The
bundled version is preview.58 (source dd7e502).

## Virtual machines, SSH, and Tailscale

### SSH sessions die at ~5 minutes

SSH sessions via `~/workspace/ssh_vm.sh` die at about 5 minutes (Broken
pipe, exit 255) even with output flowing. This is a hard session limit,
not an idle timeout. A remote build survives the disconnect. For long
jobs, run them with `nohup` plus a log file, then check progress with
short repeated probes — do not wait on a long-lived SSH session.

### Plain ssh fails with "Operation not permitted"

Plain `ssh` to the Dev VM fails. Always go through the Tailscale proxy
with the hatch key — that is what `~/workspace/ssh_vm.sh` does (ProxyCommand
`python3 ~/workspace/ssh_tailscale_proxy.py`, key `~/.ssh/id_ed25519`).
Do not try to use `ssh_vm.sh` itself as `GIT_SSH_COMMAND`; it hardcodes
host/user and is not usable there. For the `vm` git remote, set
`GIT_SSH_COMMAND` to the raw ssh invocation with the same proxy options.

### The host runs one VM at a time

The host runs one VM at a time. The Dev VM is the build machine; Public
Beta is the test/release target. Switch between them as needed — if one
VM does not respond, check whether the other is the one currently up.

### Reaching Beta

- Beta LAN: 192.168.250.20. Beta Tailscale: 100.78.139.41.
- Direct Tailscale SSH works via `~/workspace/ssh_beta.sh`
  (`spikediegel@100.78.139.41`, hatch key, `IdentitiesOnly=yes`).
- `scp`/`sftp` to Beta fails ("subsystem request failed"). Transfer files
  with `ssh_beta.sh "cat > /path" < file` and verify with md5sum.
- Beta has no `curl`, no `pip`/`ensurepip`, no `pytest`, and no `git`.
  Tooling that needs those must be fetched in or worked around.
- Beta's host key changes on every ISO reinstall. Expect a host-key
  warning and re-accept it after a reinstall.
- The Dev VM's own key is NOT authorized on a fresh Beta image (only the
  hatch key is in Beta's authorized_keys). Pass the hatch key explicitly
  (`-i` + `IdentitiesOnly`); the LAN jump fails with permission denied
  if the key is not passed explicitly.
- Beta is also reachable through the Dev VM as a jump host.
- A fresh ISO install does not carry the SSH key. After a fresh install
  from the ISO, SSH with the hatch key is denied until the key is
  re-added to `~/.ssh/authorized_keys` on the new install (700 on
  `.ssh`, 600 on the file). The key must never ship in a product image,
  so it is not there by default. Symptom is "Permission denied
  (publickey,password,keyboard-interactive)" even though sshd is running
  and the key is being offered. Verify the offered key's fingerprint
  with `ssh-keygen -lf ~/.ssh/id_ed25519.pub` and confirm it is in
  `authorized_keys`. Also check the username: on the build #38 Beta
  install the account is `spikedeigel` (a typo for `spikediegel`, from
  the install) and the hostname is `spikedeigel-virtualmachine`. If the
  key was added under the wrong name, SSH fails for the right name. That
  account has no passwordless sudo, so `sudo` needs a password.
- Beta's Tailscale node goes offline when the gateway is gone. Tailscale
  needs a default route to reach the tailnet, so a missing gateway also
  breaks Tailscale SSH even though the service is running. The LAN route
  (192.168.250.20 via the Dev VM jump host) still works. After the build
  #38 reinstall, Beta's Tailscale IP is 100.121.146.73 (hostname
  spikedeigel-virtualmachine); the old 100.78.139.41 node is stale.
- The jump-host script's nested ProxyCommand quoting:
  `~/workspace/ssh_beta_via_dev.sh` reaches Beta on the LAN via the Dev
  VM. Its nested ProxyCommand must use `%%h %%p` for the inner ssh —
  plain `%h %p` gets expanded by the outer ssh to Beta's LAN address,
  and the Tailscale proxy then closes the connection. Fixed 2026-11-28.
  If the jump fails with "proxy closed connection", check that quoting
  first.

### Pulling an ISO to Windows: use the LAN, not Tailscale

`scp` to the Dev VM Tailscale IP (100.127.211.25) timed out from Windows,
and `tailscale` is not recognized in Mike's PowerShell (the Tailscale CLI
is not installed/on PATH on the Windows host). The working route is the
host-only VM network: `Test-NetConnection 192.168.250.10 -Port 22`
succeeds via `vEthernet (Pulpo-Dev)`. Pull with:

```powershell
scp spikediegel@192.168.250.10:/home/spikediegel/pulpo-workspace/iso-build/<iso> $env:USERPROFILE\Downloads\
```

Dev VM LAN: 192.168.250.10. Dev VM Tailscale: 100.127.211.25.

### Never install Tailscale as a snap on a Pulpo box

A snap Tailscale install is AppArmor-confined: it is denied reading
`/etc/ssh` host keys and denied calling `org.freedesktop.login1
CreateSession`, so Tailscale SSH auth passes but the session dies at
spawn ("operation not permitted") and the user is locked out. Fix is the
snap-to-.deb swap (state file migrates, node identity is preserved, no
re-share/re-tag needed). The `--dev` ISO variant already bundles
Tailscale as a `.deb`; the clean/release ISO carries no Tailscale by
design. A snap on a box came from a manual post-install, not the ISO.

### The cat is a suspect

Boo sleeps on the keyboard and knows how to turn its LEDs off. She is
the prime suspect for the Dev VM's clean poweroff on 2026-11-19 11:42 MST
(keyboard LEDs were off when Mike came back) and for garbled typed
fragments. If a session shows unexplained input or a clean poweroff with
no other cause, check the cat first.

## GitHub and pull requests

### gh on the Dev VM resolves to the upstream repo, not the fork

In the Pulpo-Preview clone on the Dev VM, bare `gh` commands resolve to
Ironnember/Pulpo1.0 (upstream), not spikediegel-prog/Pulpo-Preview
(origin). Always pass `--repo spikediegel-prog/Pulpo-Preview` on every
`gh pr` command there. (Caught 2026-11-09 and again 2026-11-27: bare `gh`
showed upstream PR numbers and states.)

### gh pr edit silently does nothing on the Dev VM

`gh pr edit` returns no error and makes no change there. Use
`gh api -X PATCH repos/<owner>/<repo>/pulls/<N> --input <json>` instead;
it returns real success/errors.

### Deleting a branch closes the PRs it heads AND the PRs it bases

Deleting a branch on origin closes the PRs it heads and the PRs it bases
(verified 2026-11-27: deleting one branch auto-closed #161 as its head
and #162 as its base). Never delete a branch that is a live PR's base —
retarget the dependent PR first, while it is still open. The base cannot
be changed once the PR is closed, and a PR whose base is gone cannot be
reopened; the fix is a fresh PR.

### MERGED does not prove the commits reached main

A PR showing MERGED does not prove its commits reached main. (PR #166
merged into its base branch, not main, because GitHub had not retargeted
its base yet — it merged 77 seconds after #165. Nineteen refresh commits
were missing from main and had to be re-landed as #168.) Before building,
verify ancestry: `git merge-base --is-ancestor <tip> origin/main`.

### Every push dismisses prior approvals (merge law)

Main ruleset `require_last_push_approval`: every push dismisses prior
approvals for merge purposes. The path is branch update, then a fresh
human approval after the update, then predicate re-check, then gate
dispatch. An approval submitted even seconds before an update push does
not count. Mike merges himself; plan for one fresh approval per PR on its
final head.

### A plain local-path git clone hardlinks the object store

A plain local-path `git clone` hardlinks the source's object store, so it
contains objects reachable only from the source's other remotes. To test
Preview-only conditions, clone with a `file://` URL (transport, no
hardlinks) and confirm the foreign object is absent with
`git cat-file -t <sha>`.

## Test gate and CI

### The gate baseline has 5 pre-existing environmental failures

At main 4e0b7685 the full gate is 2134 tests with failures=2, errors=3,
skipped=118, expected failures=1. Those 5 failures/errors are
pre-existing and environmental (container root, umask 0007) — they are
the baseline, not regressions. Compare a new gate run against that
baseline; only failures beyond it are new.

### test_disk_service_recovery errors under /tmp worktrees

That test errors under `/tmp` worktrees ("disk fixture must not use
volatile memory storage") and fails identically at a clean baseline in
`/tmp`. It passes in non-`/tmp` worktrees and in CI. Not a regression.

### A single CI failure can be a flake — re-run before chasing it

One CI failure on PR #160 was a flake (Preview Security Audit
custody-service QoS benchmark); a re-run passed. If a single check fails
while the rest are green and the failure does not reproduce locally,
re-run it before treating it as a real regression.

## Process — who does what

- Main is protected: changes go by PR with the required checks, never by
  direct push. Mike merges himself.
- Mike signs releases with his own publisher GPG key. Nobody signs for him.
- Mike sends his own mail. Drafts are handed to him, never sent or
  forwarded on his behalf.
- Ask Mike for approval before Pulpo Preview changes.
- "Fix them" (for a port) means adapting to Preview drift — the PRs were
  CI-green on Pulpo1.0 and need porting to Preview's state.
- Never weaken a governance check to make a port pass.
- Spyglass is internal-only by a hard rule: no internet-facing access,
  no external access mechanism from Pulpo. Spyglass stays out-of-band and
  is never a Kraken component.
- The Dev VM's Pulpo1.0 copy is Austin's to sync. Do not touch it.
  Pulpo Preview — not canonical Pulpo1.0 — is what belongs on the
  Pulpo-OS-Dev VM.
