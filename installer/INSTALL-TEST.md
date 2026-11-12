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

### Run (fill in after the test)

| Item | Value |
| --- | --- |
| ISO | (path, size, SHA-256) |
| Date (UTC) | |
| QEMU / OVMF | 8.2.2 TCG, OVMF_CODE_4M.fd, `-cpu qemu64`, 25 GB qcow2, user NIC |
| Live desktop reached | |
| Config created in the live session | |
| Calamares ran (welcome → summary → install) | |
| Erase-disk install finished | |
| Installed system booted (GRUB → gdm → desktop) | |
| Control Center opens on the installed system (Qt) | |
| Config applied: NTP servers | |
| Config applied: netplan DHCP | |
| Config applied: storage record | |
| Config files present (`/etc/pulpo/`, user profile) | |
| EFI boot entry "pulpo" present | |
| Verdict | |

Evidence: (work dir on the test machine, screenshot names).

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
