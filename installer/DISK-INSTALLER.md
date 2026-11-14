# Pulpo Preview disk installer — Calamares

Status: **built in this PR** (Calamares in the ISO + config +
`installer/install-test.sh`). The ISO is no longer live-only.
The install test results live in `INSTALL-TEST.md` — read that
file, not this line, before claiming an install works.

## The decision: Calamares, not a custom partitioner

**Calamares 3.3.5** (Ubuntu 24.04 `noble/universe`), the same
installer Lubuntu, Kubuntu and Ubuntu Unity ship on 24.04. A
custom from-scratch partitioner was rejected: partitioning,
bootloader install and system copy are dangerous code (a mistake
loses data), and Calamares already does all of it, proven, on
this exact base. There is no benefit to reimplementing it and
every reason not to.

Evidence for the decision (all verified 2026-11-11 on the build
VM, against the Ubuntu 24.04.5.1 base ISO):

- **Available:** `calamares` 3.3.5-0ubuntu4 in noble/universe,
  not installed by default. `calamares-settings-ubuntu` does NOT
  exist as a package in noble; settings are split between
  `calamares-settings-ubuntu-common` (1:24.04.40) and the
  per-flavour packages (lubuntu, kubuntu, ubuntu-unity). Pulpo
  authors its own settings (this folder) — that was needed
  anyway, since no flavour's settings match Pulpo.
- **Qt5/KF5, not Qt6:** the Ubuntu 24.04 Calamares package is
  built against Qt5 + KDE Frameworks 5 (libqt5core5t64,
  libkf5coreaddons5, libkpmcore12, libparted2t64), even though
  upstream Calamares 3.3 is Qt6-compatible. That is fine — Qt5
  is fully supported on 24.04 — but it means the GNOME base
  image lacks the whole Qt5/KF5 stack.
- **No maintainer scripts:** the `calamares` .deb ships no
  postinst (control files are only `control`, `md5sums`,
  `shlibs`, `triggers`), so `dpkg-deb -x` extraction — the
  build's existing rootless pattern — loses nothing.
- **Bootloader tooling already in the live image:** `shim-signed`,
  `grub-efi-amd64-signed`, `efibootmgr`, `dosfstools`, `e2fsprogs`,
  `parted`, `os-prober`, `squashfs-tools`, `grub-common` are all
  in the base image's `filesystem.manifest`. The bootloader
  module (Python, `main.py` in the .deb) runs `grub-install` in
  the target and installs `shimx64.efi` via `efibootmgr` — the
  standard Ubuntu Secure Boot path.
- **Cost of adding it:** dependency closure of `calamares` is
  432 packages; 116 are not in the base image, all fetched as
  `.deb`s from the Ubuntu archive: 67 MB download, ~200 MB
  unpacked (Qt5/KF5 libs + kpmcore + fonts). Two `-gles`
  alternatives (`libqt5gui5-gles`, `libqt5quick5-gles`) are
  excluded by the build — the desktop uses GLX, and unpacking
  both variants would overwrite the same files. The list is in
  `build-iso.sh` step 4f.
- **Reference settings read, not guessed:** Lubuntu's
  `settings.conf` + module configs and ubuntu-common's module
  configs were extracted from their `.deb`s and adapted. Where
  a config is copied verbatim (fstab, finished, machineid,
  mount, umount, grubcfg) the file says so.

## What the installer is

- **Show:** welcome → keyboard → partition → users → summary →
  finished. The partition step defaults to erase-disk
  (`initialPartitioningChoice: erase`); manual partitioning is
  present in the UI (standard Calamares) but is NOT the tested
  path in v1 — see Limits. LUKS is off in v1 (a documented next
  step).
- **Exec:** partition → mount → unpackfs → machineid → fstab →
  keyboard → users → displaymanager (gdm + the "ubuntu" GNOME
  session) → hwclock (UTC) → pulpo-config → remove-live →
  initramfscfg → initramfs → verify-initramfs → grubcfg →
  bootloader (GRUB + shim, EFI boot entry "pulpo") →
  grub-prefix-stub → umount.
- **Skipped deliberately:** `locale` (v1 is English-only; the
  system timezone stays UTC by design and the display timezone
  lives in the customer config), `networkcfg` (the Pulpo config
  is the network authority — it writes
  `/etc/netplan/60-pulpo.yaml`; networkcfg would fight it),
  `packages` / `automirror` / `pkgselect` (nothing to install
  post-install; the image is the deliverable, and the live
  session is offline by default). One removal IS done
  post-install, by the remove-live step: casper is live-only,
  and if it stays installed the initramfs step regenerates a
  live initrd (run 10) — see "The casper initramfs" below. The
  old claim here — "nothing to install or remove" — was wrong,
  and run 10 proved it.
- **Welcome requirements:** 16 GB storage, 0.5 GB RAM, root.
  The internet check is deliberately absent — an offline live
  session is a valid state — and GeoIP is disabled.
- **Launch:** an "Install Pulpo Preview" desktop icon in the
  live session (`install-pulpo.desktop`, `sudo -E calamares`;
  the live user has passwordless sudo). There is deliberately
  NO GRUB "Install" entry in v1 — the GRUB menu stays live-only
  and the install is a deliberate click in the live session.
  A GRUB install entry is a follow-on.
- **Branding:** Pulpo dark #1E1A26, one neon-green (#39FF14)
  accent for the current step, logo/icon from the square boot
  logo, welcome + slideshow from the UEFI boot splash. The
  installer-welcome mockup is NOT used: it carries an invented
  version string ("1.0.0-preview", real Preview is 0.1.0) and
  "Connect to internet" copy that conflicts with the
  no-internet-by-default gateway principle.

## The partitionLayout requirement (the first install-test failure)

`partition.conf` MUST carry a `partitionLayout` entry for the
root partition:

```yaml
partitionLayout:
    - name: "pulpo_root"
      filesystem: unknown
      mountPoint: "/"
      size: 100%
```

(`filesystem: unknown` means "use `defaultFileSystemType`",
ext4; `size: 100%` is 100% of the remaining space after the EFI
system partition, which is created separately from
`efiSystemPartition` / `efiSystemPartitionSize` and is NOT part
of the layout.)

Without it, erase-disk creates ONLY the 300 MiB EFI system
partition and leaves the rest of the disk as free space. The
failure mode is silent and misleading: the partition step's
"After" preview shows only "EFI system 300.0 MiB FAT32 + Free
Space", the mount module has no root partition to mount so the
target (`/tmp/calamares-root-*`) stays a plain directory on the
live session's RAM overlay, and there is nowhere real to install
to. The first install test (2026-11-12) failed exactly this way:
the session log showed only the jobs "Create new 300MiB
partition on /dev/vda" and "Set flags on partition /dev/vda1",
`/dev/vda2` never appeared anywhere in the log, and `lsblk`
confirmed the disk held only vda1. (That run's unpackfs rsync
also failed with error 13 — but that was the whiteout bug, not
the missing root partition; see "The whiteout failure" below.
The partitionLayout fix is still necessary: without it there is
no root partition and no real install target.) The
`partitionLayout` shape is copied from
`calamares-settings-lubuntu` (same Calamares 3.3.5, same base),
whose root entry is the proven reference. Guarded by
`test_partition_layout_has_root_taking_remaining_space`.

## The layered squashfs problem (and the merge that solves it)

Ubuntu 24.04.5 desktop has NO single `casper/filesystem.squashfs`:
the live system is 21 layered squashfs files (3 base layers +
language layers). The flavour settings packages all reference
`filesystem.squashfs` because their ISOs are built single-layer;
that path does not exist on this base and would fail the install
outright.

Pulpo's build merges the BOOT CHAIN only — `minimal` ->
`minimal.standard` -> `minimal.standard.live`, in dependency
order, live layer topmost (`MERGE_LAYERS` in `build-iso.sh`
step 3, Lubuntu-style) — into one `filesystem.squashfs`, and
`unpackfs.conf` points at that single file. That chain is
exactly what casper mounts at boot in a stock live session
(`setup_overlay()` derives it from `LAYERFS_PATH` by stripping
dot-suffixes — proven in run 3's initrd analysis). The other
18 layers are language layers casper never mounts at boot, so
they are excluded from the merge: including them can only let
a language layer override the live layer on a shared path
(run 6 below). The installed system therefore carries no
language packs — exactly as a stock live session, which mounts
the same three layers. The merge mounts each chain layer with
squashfuse and composes them with fuse-overlayfs, rootless (no
sudo, no chroot, no user namespace — unprivileged user
namespaces are blocked on the build VM, so a kernel overlay
mount is not available; FUSE is the rootless equivalent, proven
by hand 2026-11-12 on the two layers around the fatal whiteout).
The overlay lowerdir is the REVERSE of dependency order, so the
live layer is the topmost lower layer. The layers are built as
diffs (each file lives in exactly one layer — the live layer's
extracted tree is 1.86 GB, not the ~10 GB a cumulative tree
would be), so the order only matters for the few files present
in more than one layer. All 21 filenames were verified against
the base ISO with `xorriso -find /casper` and are pinned in
`tests/test_disk_installer.py` (`CASPER_LAYERS`, the step-2
presence check; `MERGE_LAYERS` is the merge order).

The overlay is the COMPOSITION, not the working directory. A
non-root user cannot write through a FUSE overlay whose lower
layers are root-owned — the kernel's permission checks reject
mkdir/open in the root-owned 0755 lower directories — so the
build copies the merged view with rsync (`-aH`, which preserves
permissions and hardlinks) into a plain directory the build user
owns, and customises that. rsync cannot read the root-only paths
through the overlay (`/etc/shadow`, `/boot/vmlinuz`, the snap
files, `/root`, ...); `installer/merge-plan.py` enumerates them
from the layers' own metadata (`unsquashfs -ll`, which reads the
archives and bypasses the permission checks), the build excludes
them from the rsync, and extracts them directly from the
archives with unsquashfs (files from their providing layer;
directories merged layer by layer through staging, because
targeted unsquashfs extraction skips a directory that already
exists in the destination, and a whiteout in a layer must be
applied before that layer's files land). The plain directory is
what gets customised and packed with mksquashfs `-all-root`
plus a pseudo-file restoring the layers' true ownership
(see "The ownership flattening" below).

The merge is not cosmetic: if a layer deletes a file from a
lower layer, the diff contains an overlay whiteout, and a
squashfs-copy does not reproduce a deletion the way the overlay
does. The overlay resolves whiteouts (and opaque dirs) during
the merge, so the merged squashfs has no whiteouts and no
cross-layer hard-link conflicts, and unpackfs' single rsync
copies a coherent filesystem. **This bit, twice** — see "The
whiteout failure" below. The build verifies the merge three
ways (zero 0/0 whiteouts in the overlay view AND in the plain
directory, the plain directory's file list matching the expected
composition from the layers' metadata exactly, and the debconf
database being the live layer's — `templates.dat` holds the
`passwd/*` templates) and fails loudly if any of them fails.
There is deliberately no `usr/share/help-langpack` check: the
chain's bottom layer (`minimal`) legitimately holds 3,917
help-langpack files, which the stock live session mounts too;
the old check proved the `minimal.no-languages` whiteout was
resolved, and that layer is never merged now.

## The merge-order failure (run 6)

The first chain of fixes (whiteout merge, boot fix, GIS fix)
all assumed the merge order was alphabetical, last wins —
"as casper does". That assumption is WRONG, and run 6
(2026-11-12, build #11) proved it at three levels:

- The merged image's debconf database is from the WRONG
  layer: build #11's `templates.dat`/`config.dat` have 152
  `Name` entries and 0 `passwd/*` entries — matching
  `minimal.standard.zh` (a language layer), not the live layer
  (319 templates incl. `passwd/*`).
- The merge resolved conflicts by alphabetical order, last
  wins, over all 21 layers — but casper at boot mounts only
  the dependency chain (`minimal` -> `minimal.standard` ->
  `minimal.standard.live`, derived by stripping dot-suffixes).
  The language layers are never mounted at boot, so they never
  override the live layer in a real live session — but the
  build mounted all 21 and let a language layer win.
- Chain of causation: no `passwd/*` templates in debconf ->
  casper-bottom `25adduser`'s `user-setup-apply` gates on
  `db_get passwd/make-user`, gets empty, skips user creation
  entirely -> no `ubuntu` user exists -> GDM autologin targets
  a nonexistent user, fails, and GDM starts the dedicated
  `gnome-initial-setup` session (uid 119) instead -> GIS
  Welcome holds the desktop. The build #11 GIS fix (skel
  marker + autostart suppression) works as designed and is NOT
  the failure — it cannot help here, because this GIS comes
  from GDM's session choice, which neither mechanism controls.

**Fix (build #12): merge ONLY the boot chain**, in dependency
order (see the merge section above). The debconf check is a
build gate, not a hope: the build fails unless the merged
`templates.dat` holds >=300 templates including `passwd/*`
(live layer: 319 / 16). Do NOT use `gnome.initial-setup=0` on
the kernel line as the fix — it would only mask a missing-user
failure. The run-5 TTY mystery is closed by the same finding:
there is no `ubuntu` shadow entry at all, so no password could
succeed; the live user is created at boot only.

## Never run two builds sharing one work dir (build #12 incident)

Build #12 was first launched without `--out` (default output
name `live-amd64.iso` — the wrong file) and "killed" by killing
the pid `nohup` reported (`$!`). That pid was the nohup
wrapper, not the build: the build itself survived and kept
running. A second build was then launched with `--out`, and
both builds shared `$WORK` (`merge/`, `rootfs/`, `merge-plan/`)
— racing on the same FUSE mounts and the same plain directory,
while the second build's step-3 `rm -rf $MERGE` churned through
the first build's still-mounted layers (318k `rm` errors). The
fix: kill the BUILD pid (the `/bin/bash installer/build-iso.sh`
process, not the `bash -c` launch shell and not `$!` from a
`nohup ... &` launch — verify with `ps aux | grep
"[b]uild-iso.sh"`), then kill its orphaned children (an `rsync`
survived, holding the view mount busy), unmount the FUSE mounts
(`fusermount3 -u` on the view first, then each layer), remove
the stale `merge/` `rootfs/` `merge-plan/` dirs, and relaunch
exactly one build. The build script itself never runs two
builds; the guard is the operator's launch discipline. Evidence:
`iso-build/build12-double-run.log` (the raced run).

## The whiteout failure (the second install-test failure, and the first)

Calamares' unpackfs copies each squashfs layer with rsync
(`-aHAXSr`, `--filter=-x trusted.overlay.*`). rsync does NOT
understand overlayfs whiteouts. A whiteout is a char device
with major/minor 0/0 that means "delete this path from the
lower layers". rsync copies it as a char-device file instead
of deleting the target path — and it FAILS outright when the
whiteout targets a non-empty directory, because it cannot
replace the directory with the char device.

The failing layer is `minimal.no-languages.squashfs` (the 6th
of 21, after the five language layers). It holds 3,808
whiteout char devices (verified: `find <layer> -type c | wc -l`
= 3808), mostly CJK font configs. The fatal one is a whiteout
for the whole directory `usr/share/help-langpack`:

- In the layer: `c--------- 3808 root root 0, 0 ... /usr/share/help-langpack`
  (a whiteout char device, "delete this directory").
- On the target (already copied from earlier layers):
  `usr/share/help-langpack/` is a non-empty directory holding
  whiteout char devices (`de`, `en_AU`, ...).

rsync fails with (reproduced by hand, same command, same
layer, to the mounted ext4 target):

```
could not make way for new regular file: usr/share/help-langpack
Hlink node data for 17 already has path:etc/fonts/conf.avail/25-arphic-ukai-render.conf
rsync error: errors with program diagnostics (code 13) at hlink.c(539) [generator=3.2.7]
cannot delete non-empty directory: usr/share/help-langpack
```

Calamares reports it as `Failed to unpack image
"/cdrom/casper/minimal.no-languages.squashfs". rsync failed
with error code 13.` Both install-test runs died on this
exact layer and error — run 1 (no root partition, target was a
RAM dir) and run 2 (root partition present, target was the real
ext4 disk, 130 MB written before the failure). The partition
fix did not touch this; the whiteout is a separate, second bug.
A manual rsync of the same layer to a scratch dir on the live
overlay SUCCEEDS (all 3,808 whiteouts copied as char devices,
51 MB) — the failure needs the target to already hold the
directory the whiteout deletes, which is exactly the
multi-layer install case.

**Fix implemented (2026-11-12): build a single merged
`filesystem.squashfs`, Lubuntu-style** — `build-iso.sh` step 3
merges the layers at build time (squashfuse mounts +
fuse-overlayfs, reverse lowerdir so the topmost layer is the
live layer), copies the merged view with rsync into a plain
directory, customises that directory as the build always did,
and points `unpackfs.conf` at the single squashfs packed from
it. The overlay resolves whiteouts (and opaque dirs) during
the merge, so the merged squashfs has no whiteouts and no
cross-layer hard-link conflicts, and unpackfs' single rsync
copies a coherent filesystem. (First implemented merging all
21 layers alphabetically; corrected in build #12 to merge only
the boot chain — see "The merge-order failure" above — after
run 6 proved a language layer could override the live layer.)
Verified by hand 2026-11-12 on the full 21-layer
merge: 71,987 whiteouts in the layers, **zero** 0/0 whiteouts
in the merged view. The build verifies the merge three ways
(zero 0/0 whiteouts in the overlay view AND in the plain
directory; the fatal whiteout's target
`usr/share/help-langpack` absent or empty — a higher layer
re-creates the directory itself, empty, which is correct; and
the plain directory's file list matching the expected
composition from the layers' metadata exactly) and fails loudly
otherwise. Three traps, all found the hard way: (a) the merged
view legitimately holds the static `/dev` nodes (null, zero,
console, tty, urandom, random, full, ptmx — real major/minor,
not whiteouts), so the count must be 0/0 devices ONLY, not
every char device; (b) the merged view holds root-only
`/run/*` dirs the build user cannot traverse, so a full-tree
`find` exits 1 — under `pipefail` + `set -e` with stderr
discarded, that killed the first merge build SILENTLY right
after the whiteout count, with no error line. The scans now
tolerate traversal errors explicitly (stderr kept, warning
logged) instead of dying on them. (c) The overlay is READ-ONLY
for a non-root user: the second merge build died customising
through it — `dpkg-deb -x` into the overlay failed with
"Cannot mkdir: Permission denied" / "Cannot utime: Operation
not permitted", because the kernel rejects writes into
root-owned 0755 lower directories. That is why the build
rsyncs to a plain directory and customises that; the overlay
is only ever read. The same root-ownership is why rsync
cannot read 101 root-only paths (60 files, 41 dirs) through the overlay
(`/etc/shadow`, `/boot/vmlinuz`, the snap files, `/root`,
...): `installer/merge-plan.py` enumerates them from the
layers' metadata and the build extracts them directly from
the archives. A directory counts as unreadable unless the
build user can BOTH list it and traverse it — a dir with
execute but no read (`drwx--x--x` `/etc/sssd`, `run/sudo`,
`var/lib/gdm3`, `var/lib/snapd/void`, `var/lib/sss/deskprofile`)
fails rsync exactly like an unreadable one, and the first
rsync run died on exactly those five. The 8 static `/dev`
nodes are also excluded (rsync cannot copy devices as
non-root): the squashfs carries no static `/dev` nodes and
`/dev` is a devtmpfs at runtime, exactly as in the old
unsquashfs-built image, which skipped them the same way. Two more unsquashfs quirks the fixup depends
on: targeted extraction of a directory SKIPS it if the
directory already exists in the destination (and skips an
empty directory entirely), so each layer's directory goes
through a fresh staging directory and is merged with `cp -a`;
and targeted extraction of a FILE creates nothing when the
file's parent directory already exists in the destination —
the rootfs already holds the parents from the rsync, so the
files go through staging too (build #4 died on exactly this:
all four fixup calls created 0 files, and the first missing
file was `boot/System.map-7.0.0-31-generic`); and the expected
file list must account for ANCESTOR whiteouts — a whiteout at
a directory hides the whole subtree under it from lower
layers (the no-languages layer whiteouts
`usr/lib/libreoffice/program/resource/de`, deleting every
`.mo` file under it), so a path is visible only if its
topmost real entry sits above the topmost whiteout at the
path or any ancestor of it. Build #8's file-list diff failed
on 35,389 lines of hidden LibreOffice language files before
that was fixed, and on every symlink before that (the
`unsquashfs -ll` line for a symlink is `PATH -> TARGET`, so
taking the last field records the link under its target's
bare name — the path is the field after the time, up to
`->`). The diff is the definitive check: it compares the
plain directory against the expected composition from the
layers' metadata, and it must be empty.
and the layers hold cross-layer hardlinks (3,811 in the `en`
layer alone — font configs whose primaries live in the
`no-languages` layer), which `unsquashfs` cannot create when
extracting one layer at a time — the rsync from the overlay
preserves them (`-H`), which a per-layer unsquashfs merge
could not. The ISO ships only the single file: the 21 layers
and their per-layer `.size`/`.manifest`
records are removed by the xorriso rebuild, `filesystem.size`
is updated by the customisation delta, and `SHA256SUMS`/
`md5sum.txt` are rewritten to the single file. Do NOT fix a
future copy failure by excluding whiteout paths from the rsync:
a path that is a whiteout in one layer can be a real file in a
later layer, so a blanket exclude can omit files that should
be present; only the ordered merge respects that. The install
test (run 3) is the check that the fix holds.

## The GIS blocker (the third install-test failure)

Run 5 (2026-11-12) booted cleanly — the boot fix is verified live,
no casper panic, the desktop loads — and then stopped one step
later: the live session autostarts gnome-initial-setup (GIS), whose
Welcome page covers the desktop and never lets go. GIS is modal
and swallows the shell (Super, Ctrl+Alt+T, Alt+F2, Alt+Tab,
Escape, Alt+F4 all no-ops), the autostarted Control Center is
never seen, and Calamares is never reached. The install never
started; the test disk stayed 196K. The whiteout fix and the boot
fix are still untested by a real install.

### What GIS is, and which one ran

GIS is `/usr/libexec/gnome-initial-setup --existing-user`,
launched from `/etc/xdg/autostart/gnome-initial-setup-first-login.desktop`
(`AutostartCondition=unless-exists gnome-initial-setup-done`).
It runs inside the ubuntu GNOME session as an autostarted app —
run5-desktop.png proves it: a normal desktop (top bar with the
system indicators, Ubuntu wallpaper, GIS as a window covering
only the left two-thirds, the pointer visible on the desktop).
It is NOT gdm's initial-setup session: gdm does start a
session for the `gnome-initial-setup` system user at boot
(`session-c1.scope` in boot.log), but that session STOPPED early,
before the desktop came up. The persistent GIS is the autostart.

### Why it runs — determined, and what is not

The autostart is gated ONLY by the marker
`~/.config/gnome-initial-setup-done`. GIS ran, so the marker was
absent from the ubuntu user's `~/.config` at session start.
That much is determined.

Stock casper is supposed to create the marker at boot:
casper-bottom/52gnome_initial_setup does
`mkdir -p /root/home/$USERNAME/.config` then
`touch /root/home/$USERNAME/.config/gnome-initial-setup-done`.
The initrd shipped in the ISO was extracted and checked
(`unmkinitramfs`): its 52 and 25 scripts are byte-identical to
the squashfs copies, 52 is in the casper-bottom ORDER file, and
`set -e` is commented out in the casper script (so a failure in
an earlier script cannot skip 52). USERNAME is `ubuntu` — the
flavour override reads the first word of `/.disk/info`
("Ubuntu" → "ubuntu"), and the ISO's `.disk/info` is unchanged
from the base. casper-bottom DOES run at boot: 15autologin must
have run (gdm autologin is commented out in the image's
custom.conf, yet the desktop came up) and 25adduser must have
run (the ubuntu user exists in the booted session; it is not in
the image's /etc/passwd).

So 52 was invoked, with the right username, in a boot where
casper-bottom runs — and the marker still was not there. The
exact step where 52's touch fails to land is NOT determined
from static evidence. It needs a guest shell to check whether
`/home/ubuntu/.config/gnome-initial-setup-done` exists in the
booted system (and whether the sibling marker from
59disable_mozc_autosetup, which uses the same mkdir/touch/chown
pattern, is there too). That check is a run-6 item, from the
desktop terminal once GIS is suppressed. The fix below does not
wait for it and does not rely on casper-bottom at all.

### The fix (build-iso.sh step 4g, verified in step 5)

Two independent mechanisms, both build-time, both verified:

(a) Bake the marker into `/etc/skel/.config/gnome-initial-setup-done`,
so every live-session home — and every user created from skel —
carries it regardless of what casper-bottom does at boot.
(b) Disable the autostart entry itself (`Hidden=true` appended to
`gnome-initial-setup-first-login.desktop`), so even if the marker
is somehow absent, GIS cannot start.

Step 4g fails the build if the marker is not in skel or if the
autostart entry (when present in the base image) is not disabled.
Step 5 verifies the same two facts in the NEW squashfs (targeted
unsquashfs extraction into a fresh directory) before the ISO is
rebuilt — the fix is proven in the built image, not just in the
plain directory.

### Consequence (deliberate): no GIS on the installed system either

Calamares copies the whole rootfs, so both changes land on disk:
the installed system's `/etc/skel` carries the marker and its
GIS autostart entry is disabled. The installed system therefore
never runs GIS on first login. That is correct for Pulpo — the
Pulpo wizard (Guided Setup) already collects timezone, NTP and
network, and GIS's first-run prompts would be redundant and
confusing on an appliance. A user can still run
gnome-initial-setup by hand; only the autostart is removed.

### The live TTY login (run-5 finding, unresolved at runtime)

The live `ubuntu` user rejects an empty password AND the password
`ubuntu` at the tty2/tty3 login prompt, so there is no shell to
kill GIS or inspect the guest. That is surprising on paper: the
image's PAM carries `pam_unix.so nullok` (empty passwords
allowed), and 25adduser runs `chroot /root passwd -d ubuntu`
(delete the password) after `user-setup-apply` creates the user
with the blank DES crypt `U6aMy0wojraho`. But the image carries
NO ubuntu credential at all — the user is not in the image's
/etc/passwd or /etc/shadow (count 0 in both); the account and its
password exist only as a boot-time effect of 25adduser. So the
real password state can only be read from a booted guest, and
run 5 shows the boot-time mechanism did not produce a working
blank login. The reliable guest-shell path for run 6 is the
desktop terminal (Ctrl+Alt+T) once GIS is suppressed — the live
user has passwordless sudo (`ubuntu ALL=(ALL) NOPASSWD: ALL`,
written by 25adduser to /etc/sudoers.d/casper). From there, run 6
must read the ubuntu shadow entry and re-test the TTY login and
report the real state; do not guess a password.

## The ownership flattening (run 7)

Build #12 (merge-order fix) booted and reached the live desktop
AS the `ubuntu` user — the run-6 fix is proven. The install is
blocked one step later, at the Calamares Welcome requirements
check: "There are no partitions to install on." The 25 GB virtio
disk IS visible to the guest (`lsblk`: `vda` 25G), but Calamares'
partition module finds no device, because KPMCore's privileged
D-Bus helper cannot spawn: `Failed to execute program
org.kde.kpmcore.helperinterface: Permission denied`.

Root cause is the whiteout-fix repack, not the merge order. The
non-root rsync merge loses owner:group, and `mksquashfs
-all-root` sets every file to root:root — including
`/usr/lib/dbus-1.0/dbus-daemon-launch-helper`, whose correct
ownership is 4754 root:messagebus (gid 101). The messagebus user
(gid 101) is neither the owner nor in group root, and other has
no permission, so the daemon's execve of the setuid helper fails
with EACCES and the helper never spawns as root. This is a
regression from the whiteout-fix repack (build #9/#10 era),
first observable in run 7 because runs 4–6 never reached
Calamares; run 1 worked because it predated the repack
(multi-layer squashfs, no rsync-merge + `-all-root`).

Scope is a class, not one file: 242 paths in the merged image
carry a non-root owner or group. The install-blocking one is the
D-Bus launch helper; the rest are collateral the fix must also
restore: `/etc/polkit-1/rules.d` (root:polkitd, gid 987),
`/usr/bin/crontab` (setgid crontab, gid 997),
`/etc/ssl/private` (root:ssl-cert, gid 106), `/etc/shadow` +
`/etc/gshadow` (640 root:shadow, gid 42) and the setgid-shadow
helpers (`chage`, `expiry`, `unix_chkpwd`,
`pam_extrausers_chkpwd`), `/usr/sbin/pppd` (4754, group dip,
gid 30), `/etc/ppp` + `/etc/chatscripts` (group dip),
`/usr/bin/ssh-agent` (setgid syslog, gid 104). Do NOT fix it
with a one-file chown/chgrp in the build.

**Fix (build #13): restore the layers' true ownership with a
mksquashfs pseudo-file, no root required.**
`installer/merge-plan.py` emits `ownership.txt`: path, numeric
uid/gid, mode for every merged path, taken from the layers' own
`unsquashfs -ll` metadata (names resolve through the host NSS —
the same namespace the listing displays them in — so a displayed
name maps back to the stored id; an unresolvable name fails the
build loudly). `installer/ownership-pseudo.py` walks the staging
rootfs and emits `"m"` (modify) pseudo entries for every path
whose true owner:group is not root:root, plus a mode-correction
entry for any path whose staging mode differs from the map. The
mode in every entry is the map's mode — the layers are
authoritative. The pack runs `mksquashfs ... -all-root
-pseudo-override -pf ownership.pseudo`: `-pseudo-override` is
what makes the entries win over `-all-root` (proven by hand:
without it the entries are ignored). Files the build added (not
in any layer) stay root:root via `-all-root`, as they should.
`installer/ownership-gate.py` then compares every path in the
built squashfs against the ownership map (owner:group:mode) and
requires build-added files to be root:root; the D-Bus launch
helper is checked explicitly (4754 root:messagebus, gid 101).
No root is needed anywhere in this fix: the pseudo-file is built
from the layers' metadata, and the gate verifies the result
rather than trusting it.

### The owner-unreadable directory (build #13, first attempt)

The first build #13 attempt failed the ownership gate on exactly
one path: `/var/lib/snapd/void` is in the ownership map (mode
0111, root:root — snapd's mountpoint) but missing from the built
squashfs. Cause: mksquashfs packs a directory by listing it, as
the build user, and mode 0111 gives nobody read permission — so
a non-root mksquashfs silently drops the directory. It is the
only owner-unreadable path in the image (verified: exactly 1 of
232,819 map paths lacks the owner-read bit), and the same path
was already missing from the build #12 image — no gate yet
existed to catch it, and no symptom from its absence was observed
in run 7's live session; the image was still unfaithful to the
layers. Fix, still with no root: `installer/staging-readable.py`
chmods u+r every map path whose staging mode lacks owner-read,
before the pack; `installer/ownership-pseudo.py` now takes the
mode in every entry from the map and emits a mode-correction
entry where staging differs, so the packed entry carries the
true 0111. The gate verifies the result — a missed path still
fails the build loudly instead of shipping wrong.

## Config carry-through (the wizard's answers reach the disk)

The 6-step wizard (Welcome, Time servers, Timezone, Network,
Storage, Summary) is the config surface and is run BEFORE the
installer in the live session (Control Center Guided Setup). The
installer does not collect the answers twice. The carry-through
is a Calamares `shellprocess` module (`pulpo-config`), which
runs AFTER `users` (so the target user's home exists) and
BEFORE `grubcfg` (so a config failure aborts before the
bootloader is written):

1. Find the wizard's JSON in the live session
   (`~/.config/PulpoPreview/control-center-customer-config.json`,
   schema `pulpo.control-center-customer-config.v1`).
2. Copy it to the target as `/etc/pulpo/customer-config.json`
   (the system record) and into the new user's profile
   (`~/.config/PulpoPreview/control-center-customer-config.json`,
   UID 1000 from the target's `/etc/passwd`).
3. Run `pulpo-control-center config import --root $TARGET
   --apply-network <json>`. That command is installer-safe by
   design (verified in the Control Center source): with
   `--root != /` it writes the target's `timesyncd.conf` and
   netplan file and never restarts the live system's services
   or applies netplan to the live session. It validates the
   document exactly like manual input first. One imprecision
   to know: `netplan generate --root-dir` still ATTEMPTS a live
   `systemctl daemon-reload` as the invoking (non-root) user —
   it fails (permission denied) and is non-fatal (generate
   still exits 0 when its inputs are readable). That attempt is
   netplan's own, not the script's, and it changes nothing live.
   The import runs as the live session's NON-ROOT user
   (`ubuntu`, uid 1000), never as root: the Control Center's
   scratch-root guard refuses root for any `--root != /`
   (`system_config.py` `_require_privilege`:
   `scratch_root_must_not_run_as_root`) — run 8 died on exactly
   that, at step 10/15, because Calamares runs this script as
   root and the import was invoked directly. The script drops
   privileges with `runuser -u ubuntu` for the import only
   (HOME set to the import user's home, so its best-effort
   profile record lands in the live user's profile). The five
   target dirs the import must write (`etc/systemd`,
   `etc/netplan`, `run/systemd/network`, `run/systemd/system`,
   `run/udev/rules.d` — the last three for `netplan generate
   --root-dir`) are pre-created with the import user's
   ownership first, and root ownership is restored afterwards:
   the applied files (`timesyncd.conf` 644, `60-pulpo.yaml`
   600) end up root-owned. `netplan generate` also READS every
   YAML under the root, including pre-existing files under
   `lib/netplan/` — the image ships
   `lib/netplan/00-network-manager-all.yaml` 0600 root:root
   (run 9 died on exactly that: generate could not open it as
   the import user). The script hands the dir and its files to
   the import user before the import and restores owner:group
   AND mode afterwards (0600 stays 0600 — a permanent chmod
   644 is not the fix; netplan itself warns 644 is too open).
   There is no fallback to running the
   import as root. The Control Center repo is untouched — the
   fix lives entirely in the installer (Mike's decision, option
   (b), 2026-11-13).
4. Copy the Calamares session log into the target at
   `/var/log/pulpo-installer/`.

Failure modes (in `pulpo-config-install.sh`, loud where it
matters):

- No config in the live session (Guided Setup skipped): warn
  and proceed. Install without a config is fine; Guided Setup
  remains available on the installed system.
- Import fails validation: fail the install (exit non-zero).
  A config that cannot be applied must not be silently dropped.
- The import user does not exist in the live session, or
  runuser cannot drop to it: fail the install loudly. (Run 8's
  failure was the mirror image: the import ran as root and the
  CLI's guard refused it. Either way the install fails rather
  than booting with an unapplied config.)
- The import's test gap (run 8): the script's tests stubbed
  `PULPO_CC_BIN` and the CLI's scratch-root tests run non-root,
  so the real-CLI + root + scratch-root combination was never
  exercised. Closed by `test_real_cli_import_as_non_root`
  (real CLI, non-root, scratch root, no stub) and
  `test_import_ownership_prepare_and_restore` (the chown dance
  under fakeroot).
- Run 9's failure (the lib/netplan gap): the import's `netplan
  generate` reads the target's pre-existing netplan files, and
  `lib/netplan/00-network-manager-all.yaml` is 0600 root:root
  in the image — unreadable by the non-root import user. The
  script's chown dance covered only the five dirs the import
  writes, not the dir it only reads. Fixed by extending the
  dance to `lib/netplan/` with owner:group AND mode restore
  (0600 stays 0600); covered by the extended
  `test_real_cli_import_as_non_root` (0600 files under
  lib/netplan/ present) and
  `test_import_ownership_prepare_and_restore` (modes 600/640
  restored under fakeroot).
- Import fails only because no network interface can be found
  (offline live session): retry with the first non-loopback
  interface from `/sys/class/net` — netplan only needs the
  name, and the installed system will DHCP on it at first boot.
  If that still fails, warn and proceed: time and storage are
  already applied by then (the import applies them before the
  network step), the config is preserved in the target, and
  Guided Setup on the installed system can apply the network
  from the same document. An offline machine is a normal case
  for Pulpo, not an install failure.
- The display timezone is a Control Center display preference
  stored in the profile document, NOT a system timezone change:
  the appliance stays on UTC by design.

## The casper initramfs (run 10: the install completes, the system does not boot)

Run 10 was the first completed install in runs 1–10 ("All done",
~19:32 UTC): pulpo-config succeeded and all 15 steps ran. The
verify phase then failed at the boot chain, on two defects.

**Defect 1 (primary): the installed initrd is casper-flavoured.**
The casper package IS installed in the target (its dpkg records
and its initramfs hook/scripts survive unpackfs), and the
install's initramfs step regenerates the initrd with casper's
hook and scripts in it — so the new initrd runs casper's
`find_livefs`, probes for a live medium (`/init: line 38: can't
open /dev/sr0`), and drops to an `(initramfs)` shell with no ISO
attached. The kernel cmdline is a normal installed entry
(`root=UUID=...`, no live flags) and blkid confirms the UUID;
the entry and the disk are right, the initrd is wrong. Nothing
in the installer removed the live packages: `settings.conf`
said "nothing to install or remove post-install". That premise
was wrong — a normal Ubuntu installer strips the live system,
and this one must too.

Fix (build #16): a `shellprocess@remove-live` exec step after
pulpo-config and before initramfscfg, running
`installer/calamares/remove-live-packages.sh`, which chroots
into the target and runs `dpkg --purge casper`. Casper is the
ONLY live-only package in the 1,823-package image (checked
against the built squashfs dpkg status: no ubiquity,
lupin-casper or live-boot is installed) and a leaf (nothing
depends on it), so the purge list is exactly `casper` until
another package is proven live-only the same way.
casper.postrm does not run update-initramfs, so the purge
itself never regenerates an initrd; the initramfs step that
follows regenerates it casper-free. A `shellprocess@verify-
initramfs` exec step after initramfs gates on the built image:
it lists every `/boot/initrd.img-*` in the target with
lsinitramfs and fails the install if any of them contains casper
boot logic — a path under `scripts/casper*` or `hooks/casper*`
in the image (mkinitramfs copies the casper scripts to
`scripts/casper*`; hooks are not normally copied into the image,
verified on a stock initrd). A bare config line such as
`conf/conf.d/casperize.conf` is NOT boot logic and does not fail
the gate. The gate lists each image exactly once (the listing
goes to a temp file; the greps run against it), and its
Calamares timeout is 1200 s — one lsinitramfs pass over the
~90 MB initrd takes ~5.7 min under TCG. Tests:
`RemoveLivePackagesTests` (package list, present/removed
detection on a fake target, chroot-dpkg purge invocation,
conf.d leftover detection and removal) and
`VerifyInitramfsTests` (fake cpio initrds with and without a
casper hook, main() pass/fail/no-initrd, single-listing-pass
count, timeout value, casperize.conf-only initrd passes).

Fix (build #17): run 11 failed the install in the gate itself,
on two defects. (1) Timeout: Calamares killed the gate at its
60 s timeout, but the gate then took 11m28s under TCG — two
full lsinitramfs passes, ~5.7 min each. The gate now lists the
image once (single streamed pass through a temp file; the
matches are reported from that listing, never by re-listing)
and the timeout is 1200 s (~3.5x the single-pass TCG cost; on
real hardware the gate takes seconds). (2) Leftover conf: the
rebuilt initrd contained exactly one casper-named path,
`conf/conf.d/casperize.conf` (`export CASPER_GENERATE_UUID=1`),
owned by NO package, from the target's
`/etc/initramfs-tools/conf.d/` — `dpkg --purge casper` leaves
it, and mkinitramfs copies `conf.d/*.conf` into the image. The
line is inert without the casper scripts, so the gate no longer
fails on it (see the narrowed rule above) — and remove-live
now deletes every casper-named file under the target's
`conf.d/` after the purge, with its verify extended to check
they are gone, so the target ships clean of casper entirely.

**Defect 2 (secondary): the fallback GRUB has the wrong prefix —
and so does the NVRAM entry's GRUB.** The scripted verify boot
(fresh NVRAM) loaded `BOOTX64.EFI`, a GRUB 2.12 reporting
`prefix=(hd0,gpt1)/EFI/ubuntu`, while no `EFI/ubuntu/` exists —
so it dropped to a `grub>` shell. The first reading was that the
fallback had been installed with the stock `ubuntu` id instead
of the `pulpo` id. That reading is WRONG, and the correction
matters: Ubuntu's SIGNED grubx64.efi has its config prefix
baked in as `/EFI/ubuntu` at build time — `strings` on
`/usr/lib/grub/x86_64-efi-signed/grubx64.efi.signed` in the
image shows the literal "/EFI/ubuntu", and the fallback GRUB
reported package_version 2.12-1ubuntu7.3, the same binary.
With shim present, grub-install installs that prebuilt signed
binary instead of generating one, so `--bootloader-id=pulpo`
only names the ESP directory — it cannot change the prefix.
The NVRAM entry runs the SAME binary (shim ->
`EFI/pulpo/grubx64.efi`), so it fails the same way: the signed
GRUB looks for `EFI/ubuntu/grub.cfg`, which a pulpo install
does not have. A fallback "installed with the pulpo id" is
therefore not achievable by copying or by grub-install — the
prefix is not a property of the copy, it is baked into the
binary. Replacing the signed GRUB with an unsigned one built
with prefix EFI/pulpo would break Secure Boot, so that was
not done.

Fix (build #16): a `shellprocess@grub-prefix-stub` exec step
after bootloader and before umount, running
`installer/calamares/grub-prefix-stub.sh`, which writes
`EFI/ubuntu/grub.cfg` as a redirect stub (the stock-Ubuntu
form): UUID search for the root partition, `set
prefix=($root)/boot/grub`, `configfile $prefix/grub.cfg`. One
stub fixes both boot paths, because both run the same signed
binary with the same prefix. The stub is a config file, not a
binary, so it does not weaken Secure Boot. Tests:
`GrubPrefixStubTests` (stub content, fstab UUID parsing,
write/failure cases, settings order); run 11's boot test
(fresh NVRAM -> fallback -> menu, and NVRAM entry -> menu)
proves it live.

**Harness fix (same build): the verify phase destroyed the
NVRAM entry it wanted to check.** `install-test.sh` copied the
pristine `OVMF_VARS_4M.fd` over the work dir at every launch,
so the verify boot always ran with fresh NVRAM. The install
phase now preserves its vars to `OVMF_VARS_4M-install.fd` when
it ends, and the verify phase reuses that file when it exists
(falling back to pristine, with a warning, when it does not).
The `efibootmgr` "pulpo" check is testable again, and the
verify boot tests the actual installed entry first; the
fallback path is tested second, by booting with fresh NVRAM.

## Hyper-V Generation 2 (next boot target)

Mike plans to boot the ISO in Hyper-V after the VM test. The
ISO and installer are built to be Hyper-V Gen 2 compatible, but
Hyper-V itself cannot be tested from the build VM — the
QEMU/OVMF test is the proof produced here, and Hyper-V Gen 2
is named as the next boot target.

What was verified (not assumed):

- The ISO's EFI boot chain is preserved verbatim by the build
  (xorriso replays the base image's BIOS eltorito + appended
  EFI system partition); Ubuntu's signed shim/grub/kernel are
  untouched, so the ISO boots under Secure Boot via Microsoft's
  key — under the right template (below).
- **Secure Boot template:** Hyper-V Gen 2 enables Secure Boot
  by default, and the DEFAULT template ("Microsoft Windows")
  rejects Linux bootloaders (the VM falls through to PXE boot).
  For Linux guests the template must be **"Microsoft UEFI
  Certificate Authority"**. That is a setup instruction for the
  person creating the Hyper-V VM, recorded here and in the PR
  body. Expected behaviour, not proven.
- **Drivers in the initramfs:** the base ISO's initrd contains
  `hv_storvsc`, `hv_netvsc`, `hv_vmbus`, `hv_utils`,
  `hyperv-keyboard`, `hid-hyperv` and `pci-hyperv` (checked in
  the extracted initrd), and the kernel config
  (`CONFIG_HYPERV=y`, `CONFIG_HYPERV_STORAGE=m`,
  `CONFIG_HYPERV_NET=m`, `CONFIG_DRM_HYPERV=m`,
  `CONFIG_HYPERV_BALLOON=m`) confirms full Hyper-V support.
  The live session and the installed system can see Hyper-V
  disks (storvsc, presented as `/dev/sda`) and network (netvsc).
- **No QEMU-specific assumptions in the ISO/installer:**
  Calamares enumerates whatever block devices exist (no virtio
  assumption); the GRUB `console=ttyS0` is harmless on Hyper-V
  (no emulated serial port — the kernel continues on tty0);
  the config import derives the interface from the live
  session's default route (netvsc presents `eth0` in both the
  live session and the installed system).
- **Copying the ISO to Windows:** the ISO is ~6.3 GB — it does
  not fit on a FAT32 volume. Copy it over the network or to an
  NTFS/exFAT drive. The deliverable is recorded with path +
  size + SHA-256 (see `INSTALL-TEST.md`).

What is NOT verified: actually booting the ISO in Hyper-V Gen
2, the "Microsoft UEFI Certificate Authority" template step,
and the installer running on a Hyper-V virtual disk. Those are
the next checks, on Mike's Windows machine.

## Space plan (build + test)

The build VM's disk was 84% full (9.4 GB free) when this work
started; Mike expanded it 2026-11-11 and it is now 117 GB with
~52 GB free. The numbers, measured:

- ISO rebuild peak transient: ~20 GB (extracted tree ~5 GB +
  the plain merged rootfs ~11 GB + new squashfs ~4 GB). The
  merge itself is the big disk use now: the 21 layers are FUSE
  mounts (virtual, no extraction) but the rsync copy into the
  plain directory is a full ~11 GB tree, and it stays until
  after mksquashfs. The stale `new-filesystem.squashfs`
  (a regenerable intermediate from the preview.48
  build) was deleted before rebuilding, giving ~10.7 GB free.
  Tight, but it fits.
- The install test does NOT run on the build VM: a 25 GB
  virtual disk plus the new ISO does not fit alongside the
  existing ISOs, and deleting a deliverable (the merged #125
  ISO, the base ISO) to make room was not done. The test runs
  on the hatch VM (147 GB free) with the ISO + QEMU/OVMF
  tooling copied over Tailscale. The superseded #124 ISO
  (6.3 GB) is the named cleanup candidate if space is ever
  needed on the build VM — it is reproducible from main
  3837fb7, but deleting it is Mike's call, not this PR's.
- No KVM on either VM, so all QEMU testing is TCG (slow).
  The install test is a long background run; see
  `INSTALL-TEST.md` for the timings.

## What this does NOT do (honest limits)

- **Manual partitioning** is present in the UI (standard
  Calamares) but untested in v1. The tested path is
  erase-disk. A manual-partitioning test is a follow-on.
- **LUKS** (disk encryption) is off in v1. The partition
  module supports it (`luksGeneration: luks2` is set for when
  it is enabled); enabling it adds a passphrase step the
  install test does not cover.
- **Secure Boot enforcement** is not demonstrated (QEMU uses
  plain OVMF, Secure Boot off; Hyper-V Gen 2 is the next
  target). The ISO and the installed system both reuse
  Ubuntu's signed shim; Pulpo's own key / MOK decision is
  still open. No Pulpo key has been generated or enrolled.
- **Real hardware:** no boot on the Protectli Vault Pro
  VP6630 (or any physical machine) has happened yet. The
  QEMU/OVMF install test proves the installer works under UEFI
  firmware; the Protectli test is still the gate before any
  "it installs on hardware" claim.
- **No GRUB "Install" entry** in v1 (deliberate — install is a
  click on the desktop icon in the live session). A GRUB
  install entry is a follow-on.
- **The installed system's GRUB menu** will say "Ubuntu"
  (from the base image's `/etc/default/grub`) even though the
  UEFI boot entry is "Pulpo". Cosmetic; a `GRUB_DISTRIBUTOR`
  change is a follow-on.
- **First-boot service:** there is none. The config is applied
  at install time; if that fails the install fails loudly
  rather than deferring to first boot. The config file is
  preserved at `/etc/pulpo/customer-config.json` so it can be
  re-imported by hand.
- **The installer never runs as root itself for governance:**
  Calamares runs as root in the live session (standard — it
  has to write the disk), but it grants no authority, creates
  no permits, and never touches the Pulpo kernel. First boot
  hands off to the Control Center's Guided Setup apply path.
