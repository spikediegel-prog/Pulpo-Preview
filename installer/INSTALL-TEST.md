# Pulpo Preview disk installer — install test

How the installer was proven to install, and what the test does
*not* prove. The boot test (`BOOT-TEST.md`) proves the ISO boots;
this file proves it installs.

## Method

`installer/install-test.sh` runs two phases under QEMU + OVMF
(UEFI firmware), with no KVM — neither VM has `/dev/kvm`, so
QEMU runs in TCG and everything is slow. Guest: 2048 MB RAM,
2 vCPUs, q35, `-cpu qemu64`, a 25 GB qcow2 virtual disk, and a
user-mode NIC (`-netdev user` — NAT only, no inbound
connections). The NIC is deliberate: the pulpo-config import
derives the interface from the live session's default route, and
without a NIC there is no interface for the network part of the
config. The boot test's `-net none` does not apply here.

The installer is driven by hand through the QEMU monitor
(`--shot` / `--key` / `--type` / `--mouse` subcommands). A GUI
installer under TCG is not scriptable reliably — timing varies
by minutes — so the script holds the VM up and the operator
drives it, taking a screenshot at each step. The evidence is
the screenshots + the logs, not a script verdict.

The QEMU command attaches a USB tablet (`-device usb-tablet`)
so monitor mouse coordinates are absolute. With only the
default PS/2 mouse they are relative to the guest pointer's
last known position and clicks land in the wrong place.
A `qemu-xhci` USB controller is also attached: `-machine q35`
creates no USB bus by default, so a bare `-device usb-tablet`
makes QEMU exit immediately with "No 'usb-bus' bus found".
Keyboard is the reliable path through the wizard regardless:
`Alt+N` advances (Next), `Alt+I` starts the install from the
summary, `Enter` confirms the install dialog, `Tab` moves
between fields, and `--type` fills them. Note: `--type` does
not send `~` (tilde) — it arrives as `/` — so use full paths
(`/home/ubuntu/...`) when typing in the live session, never `~`.

### Phase install

1. Boot the ISO with the blank disk attached. Wait for the live
   desktop (gdm in `boot.log` + desktop screenshots).
2. In the live session, create the customer config first:
   open the Control Center (autostarted), Guided Setup on the
   System page, and fill in the 6 steps. For the test the
   example config is used (DHCP, America/Phoenix,
   ntp.ubuntu.com + pool.ntp.org, local evidence store
   `/var/lib/pulpo/evidence`, retention 24h / 10%,
   acknowledged). Save it. (Equivalently: copy
   `installer/pulpo-preview-config.example.json` to
   `~/.config/PulpoPreview/control-center-customer-config.json`
   in the live session — the same document the wizard writes.)
3. Open a terminal (Ctrl+Alt+T) and run `sudo -E calamares`
   (the same command the "Install Pulpo Preview" desktop icon
   runs). Confirm the desktop icon exists first
   (`ls ~/Desktop/` shows `install-pulpo.desktop`).
4. Work through Calamares: welcome (requirements pass) →
   keyboard (us) → partition (erase-disk, the default) →
   users (create the admin user; note the name + password —
   the verify phase logs in as this user) → summary → Install.
   Screenshot each step.
5. Wait for the install to finish (unpackfs copies ~11 GB
   under TCG — expect a long time; the progress bar is the
   evidence it is working). The finished page offers a restart.
6. Shut the VM down (do NOT let it reboot into the live ISO
   again — the ISO is still attached and boots first). Create
   `INSTALL_DONE` in the work dir (or `--stop` the VM).

### Phase verify

1. Boot from the virtual disk only (no ISO). The installed
   GRUB (shim + grub, EFI entry "pulpo") is what boots — this
   phase is itself the bootloader proof.
2. At gdm, log in as the user created in the install.
3. Check, in a terminal, and screenshot each result:
   - Desktop reached, Control Center opens (Qt) — the app
     autostarts on login.
   - `/etc/pulpo/customer-config.json` exists and matches the
     config from phase install (same schema, same values).
   - The user profile
     `~/.config/PulpoPreview/control-center-customer-config.json`
     exists.
   - `/etc/systemd/timesyncd.conf` carries the two NTP servers
     (`ntp.ubuntu.com`, `pool.ntp.org`).
   - `/etc/netplan/60-pulpo.yaml` exists and configures DHCP on
     the interface (`dhcp4: true`).
   - The storage record: the Control Center shows the local
     store, retention 24h / 10%, acknowledged.
   - `/var/log/pulpo-installer/` holds the install log and the
     Calamares session log.
   - `efibootmgr -v` shows the "pulpo" boot entry (and the
     ESP at `/boot/efi/EFI/pulpo/` holds `shimx64.efi`).
4. Record the results in the table below.

## Results

### Run 1 — 2026-11-12 ~08:04–08:10 UTC — FAILED (missing partitionLayout)

| Item | Value |
| --- | --- |
| ISO | `~/pulpo-workspace/iso-build/pulpo-preview-0.1.0-live-diskinstall-amd64.iso`, 6,361,186,304 bytes, SHA-256 `5e901eef599c4bdea80942fd4599d4cde63e96a7ab8a513b39ebcb386a5a1a46` |
| Date (UTC) | 2026-11-12 |
| QEMU / OVMF | 8.2.2 TCG, OVMF_CODE_4M.fd, `-cpu qemu64`, 25 GB qcow2, user NIC |
| Live desktop reached | Yes — Qt Control Center open and live (CPU 79.6%→84.0%, Memory ~55%) |
| Config created in the live session | Yes — example config copied to `~/.config/PulpoPreview/control-center-customer-config.json` |
| Calamares ran (welcome → summary → install) | Yes — Welcome, Keyboard (us), Partitions (erase-disk), Users (Pulpo Test / pulpo / pulpo-test / pulpotest1), Summary, Install started 08:04 UTC |
| Erase-disk install finished | **No — FAILED.** Progress 8% ("Filling up filesystems.") then: `Installation Failed — Failed to unpack image "/cdrom/casper/minimal.no-languages.squashfs". rsync failed with error code 13.` |
| Installed system booted (GRUB → gdm → desktop) | Not reached (install failed) |
| Control Center opens on the installed system (Qt) | Not reached |
| Config applied: NTP servers | Not reached |
| Config applied: netplan DHCP | Not reached |
| Config applied: storage record | Not reached |
| Config files present (`/etc/pulpo/`, user profile) | Not reached |
| EFI boot entry "pulpo" present | Not reached |
| Verdict | **FAIL.** Root cause 1: no `partitionLayout` in `partition.conf`, so erase-disk created ONLY the 300 MiB EFI partition (`/dev/vda1`); no root partition was ever planned or created (`/dev/vda2` appears nowhere in the session log; `lsblk` showed only vda1). The mount module had no root to mount, so unpackfs rsynced into a RAM dir. Root cause 2 (same run, same error): the whiteout bug — see Run 2 and `DISK-INSTALLER.md` "The whiteout failure". Fixed by `partitionLayout` (commit `9564fbf`). |

### Run 2 — 2026-11-12 ~09:21–09:32 UTC — FAILED (whiteout)

ISO rebuilt with the `partitionLayout` fix (same size, 6,361,186,304 bytes, SHA-256 `b67ab4aebb445e58ecdad7a5db635cef573e88c812c504a0ad5cbf06d61b33a8`; the fixed `partition.conf` was verified inside the rebuilt live squashfs). The `qemu-xhci` fix (`830aeae`) was also in: QEMU had exited early on run 2's first start with "No 'usb-bus' bus found" until the controller was added.

| Item | Value |
| --- | --- |
| ISO | `~/pulpo-workspace/iso-build/pulpo-preview-0.1.0-live-diskinstall-amd64.iso`, 6,361,186,304 bytes, SHA-256 `b67ab4aebb445e58ecdad7a5db635cef573e88c812c504a0ad5cbf06d61b33a8` |
| Date (UTC) | 2026-11-12 |
| QEMU / OVMF | 8.2.2 TCG, OVMF_CODE_4M.fd, `-cpu qemu64`, 25 GB qcow2, user NIC, `-device qemu-xhci -device usb-tablet` |
| Live desktop reached | Yes — Qt Control Center open and live (CPU 5.1%, Memory 55.8%, Storage 3.9%) |
| Config created in the live session | Yes — example config copied (full path; `--type` drops `~`) |
| Calamares ran (welcome → summary → install) | Yes — Welcome, Keyboard (us), Partitions, Users (same test user), Summary, Install started 09:27 UTC |
| Partition step now shows the root | **Yes — fix verified.** "After:" shows EFI system 300.00 MiB FAT32 + **pulpo_root 24.70 GiB ext4**. Summary lists "Create new 25293MiB partition on /dev/vda (vda) with entries pulpo_root" and "Install Pulpo on new ext4 system partition". The qcow2 grew to ~130 MB (data written to the real disk). |
| Erase-disk install finished | **No — FAILED.** Same error, same layer: `Failed to unpack image "/cdrom/casper/minimal.no-languages.squashfs". rsync failed with error code 13.` (09:32:04 UTC, ~5 min in.) |
| Installed system booted (GRUB → gdm → desktop) | Not reached (install failed) |
| Control Center opens on the installed system (Qt) | Not reached |
| Config applied: NTP servers | Not reached |
| Config applied: netplan DHCP | Not reached |
| Config applied: storage record | Not reached |
| Config files present (`/etc/pulpo/`, user profile) | Not reached |
| EFI boot entry "pulpo" present | Not reached |
| Verdict | **FAIL — blocked on the whiteout bug.** rsync cannot copy the layered squashfs because `minimal.no-languages.squashfs` holds 3,808 overlay whiteouts (char devices 0/0); the whiteout for `usr/share/help-langpack` (a directory) cannot replace the non-empty directory already copied from earlier layers. Reproduced by hand (same rsync, same layer, to the mounted ext4 target): `could not make way for new regular file: usr/share/help-langpack` + `rsync error (code 13) at hlink.c(539)`. Recommended fix: build a single merged `filesystem.squashfs` (Lubuntu-style) — see `DISK-INSTALLER.md` "The whiteout failure". Phase verify has not run; no install has completed. |

Evidence: screenshots in `~/workspace/iso-boot-evidence/install-test/` on the operator machine (`boot3*`, `calamares2*`, `partitions2`, `users2*`, `summary2`, `confirm2`, `installing2`, `progress2-now`, `install-failed-finish`, `session-log`, `exit-codes`, `vda2-grep`, `mount-job`, `rsync-repro*`, `rsync-ext4`, `helplangpack`, `find-char*`); Calamares session logs in the live sessions (`/home/ubuntu/.cache/calamares/session.log`); build logs `/tmp/build-diskinstall5.log` (run 1) and `/tmp/build-diskinstall6.log` (run 2).

## What this does NOT prove

- **Secure Boot enforcement.** Plain OVMF, Secure Boot off.
  The installed system uses Ubuntu's signed shim; booting it
  under Secure Boot enforcement is a separate check.
- **Real hardware.** No install on the Protectli Vault Pro
  VP6630 (or any physical machine) has happened yet. The
  QEMU/OVMF test proves the installer works under UEFI
  firmware; Protectli is still the gate before any "it installs
  on hardware" claim.
- **Hyper-V Gen 2.** The next boot target after this VM test
  (see `DISK-INSTALLER.md`); not tested here.
- **Manual partitioning.** Present in the UI, untested in v1.
  The tested path is erase-disk.
- **LUKS.** Off in v1; not tested.
