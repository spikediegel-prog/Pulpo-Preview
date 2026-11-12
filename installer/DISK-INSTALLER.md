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
  session) → hwclock (UTC) → pulpo-config → initramfscfg →
  initramfs → grubcfg → bootloader (GRUB + shim, EFI boot entry
  "pulpo") → umount.
- **Skipped deliberately:** `locale` (v1 is English-only; the
  system timezone stays UTC by design and the display timezone
  lives in the customer config), `networkcfg` (the Pulpo config
  is the network authority — it writes
  `/etc/netplan/60-pulpo.yaml`; networkcfg would fight it),
  `packages` / `automirror` / `pkgselect` (nothing to install or
  remove post-install; the image is the deliverable, and the
  live session is offline by default).
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

## The layered squashfs problem (the one real surprise)

Ubuntu 24.04.5 desktop has NO single `casper/filesystem.squashfs`:
the live system is 21 layered squashfs files (3 base layers +
language layers). The flavour settings packages all reference
`filesystem.squashfs` because their ISOs are built single-layer;
that path does not exist on this base and would fail the install
outright.

Pulpo's `unpackfs.conf` lists all 21 files in alphabetical
order. That order reproduces the live session, verified from the
base ISO's initrd: casper's `setup_overlay()` globs the files
alphabetically and prepends each to its overlay lowerdir list,
so the last file alphabetically is topmost; unpackfs copies in
config order with later copies overwriting earlier ones, so
alphabetical order here puts the topmost layer last. The layers
are built as diffs (each file lives in exactly one layer — the
live layer's extracted tree is 1.86 GB, not the ~10 GB a
cumulative tree would be), so the order only matters for the few
files present in more than one layer. All 21 filenames were
verified against the base ISO with `xorriso -find /casper`.

Known risk, stated plainly: if a layer deletes a file from a
lower layer, the diff contains an overlay whiteout, and a
squashfs-copy does not reproduce a deletion the way the overlay
does. **This bit, twice** — see "The whiteout failure" below.
The install test is the check; it failed on the whiteout.

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

**Recommended fix (not yet implemented): build a single
merged `filesystem.squashfs`, Lubuntu-style.** Lubuntu's
`unpackfs.conf` (same Calamares 3.3.5, same Ubuntu 24.04 base)
references one file, `/cdrom/casper/filesystem.squashfs` —
their ISOs are built single-layer. Merge the 21 layers at
build time (mount them as an overlayfs, in reverse-alphabetical
lowerdir order so the last-alphabetical layer is topmost, as
casper does; then `mksquashfs` the merged view), customise
that one squashfs as the build does today, and point
`unpackfs.conf` at it. The kernel's overlayfs resolves
whiteouts (and opaque dirs) during the merge, so the merged
squashfs has no whiteouts and no cross-layer hard-link
conflicts, and unpackfs' single rsync copies a coherent
filesystem. The 21-layer `unpackfs.conf` and the
`test_all_casper_layers_listed_in_alphabetical_order` test
would be replaced by the single-file form. Do NOT fix this by
excluding whiteout paths from the rsync: a path that is a
whiteout in one layer can be a real file in a later layer, so
a blanket exclude can omit files that should be present; only
the ordered merge respects that.

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
   document exactly like manual input first.
4. Copy the Calamares session log into the target at
   `/var/log/pulpo-installer/`.

Failure modes (in `pulpo-config-install.sh`, loud where it
matters):

- No config in the live session (Guided Setup skipped): warn
  and proceed. Install without a config is fine; Guided Setup
  remains available on the installed system.
- Import fails validation: fail the install (exit non-zero).
  A config that cannot be applied must not be silently dropped.
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
started. The numbers, measured:

- ISO rebuild peak transient: ~9 GB (extracted tree ~5 GB +
  unpacked live layer ~2.1 GB with Calamares + new squashfs
  ~1.5 GB). The stale `new-minimal.standard.live.squashfs`
  (1.28 GB, a regenerable intermediate from the preview.48
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
