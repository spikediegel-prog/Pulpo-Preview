# Pulpo Preview live ISO — boot test

How the ISO was proven to boot, and what the test does *not* prove.

## Method

`installer/boot-test.sh` boots the built ISO under QEMU + OVMF
(UEFI firmware), with no KVM — the build VM has no `/dev/kvm` and
no VMX/SVM flag, so QEMU runs in TCG (software emulation) and the
boot is slow. Guest: 2048 MB RAM, 2 vCPUs, q35 machine, no network
(`-net none` — the live session must not need the network to reach
the desktop).

Evidence collected in `~/pulpo-workspace/iso-build/boot-test/`:

- `boot.log` — kernel + userspace serial log. The ISO's GRUB
  entries carry `console=ttyS0 console=tty0`, so the log lands here
  while still showing on screen.
- `shot-*.ppm` — QEMU monitor screendumps (PPM, not PNG: this
  QEMU writes PPM content whatever the extension):
  `shot-01-grub` is the GRUB menu with the Pulpo splash; the later
  shots show the boot and the GNOME desktop.
- `qemu.log` — QEMU's own stderr.
- `RESULT.md` — the script's verdict.

Pass = the serial log shows the GNOME Display Manager starting
AND a screenshot shows the live desktop. A GRUB-menu screenshot
alone is not a pass. The pass criterion is gdm, not `Reached
target Graphical Interface`: that line never reaches the serial
log in this setup (the log goes quiet after the login prompt even
though the desktop comes up), so waiting for it always ends
INCONCLUSIVE on a good boot. Guest CPU is `-cpu qemu64`. Two CPU
notes, both verified 2026-11-11: the Control Center's vendored Qt
dies with `Illegal instruction (core dumped)` (SIGILL) under
qemu64, which lacks the AVX instructions it uses — the Tkinter
Control Center is the proof the app works in the live session, and
the Qt interface needs real hardware to be checked. `-cpu max`
was tried instead: much slower under TCG, and gnome-shell itself
crashed ("Oh no! Something has gone wrong") with no working
desktop, so it is not used.

## Results

Run 2026-11-11 (QEMU 8.2.2 TCG, OVMF_CODE_4M.fd, 2048 MB RAM,
2 vCPUs, `-cpu qemu64`, `-net none`). The script's own verdict was
INCONCLUSIVE because its gdm grep pattern did not match the log
line format (`Started <esc>gdm.service<esc> - ...`); the pattern
is fixed in this PR. The evidence below is from the serial log and
the screenshots, not from that verdict.

| Item | Value |
| --- | --- |
| ISO | `~/pulpo-workspace/iso-build/pulpo-preview-0.1.0-live-amd64.iso`, 6,313,541,632 bytes, SHA-256 `6e989f7e16ecab0eab189e717751844814329312b498f27795a275bcfcfd0cc8` |
| Date (UTC) | 2026-11-11 |
| QEMU / OVMF | 8.2.2 TCG, OVMF_CODE_4M.fd, `-cpu qemu64` |
| GRUB menu + splash | (shot file — see note) |
| gdm started (serial log) | yes — `Started gdm.service` in `boot.log` |
| Live desktop shown | yes — `shot-11-boot.png`: GNOME desktop, PULPO-PREVIEW-README.txt on the desktop |
| Control Center autostarted | autostarted and crashed (Qt SIGILL, see below); Tkinter Control Center opened manually and runs (Overview with live CPU/memory/storage, Guided Setup button) |
| Verdict | BOOT OK (desktop reached; script verdict INCONCLUSIVE is the grep bug above) |

Notes:
- The GRUB menu + splash screenshot was not captured in the timed
  runs: the menu shows for 5s ~20-25s into the boot, and the shots
  landed on either side of it (black screen before, kernel log
  after). The menu itself is proven by `boot/grub/grub.cfg`
  extracted from the ISO (Pulpo entries, splash image referenced)
  and by the boot itself, which used that GRUB config (the kernel
  booted with `console=ttyS0 console=tty0` from it). A burst of
  shots across the GRUB window is in `boot-test.sh` for the next
  run; the menu screenshot remains to be captured.
- The Control Center autostart crash: `/var/crash/` held exactly
  one file, `_usr_bin_pulpo-control-center.1000.crash`, and running
  the launcher by hand in the live session printed `Illegal
  instruction (core dumped)`. The Tkinter interface
  (`pulpo-control-center-tk`) opens and runs; the Qt interface is
  the one that SIGILLs under `qemu64`. See the CPU notes in Method.
- A `-cpu max` run was also done the same day: gdm started, but
  gnome-shell crashed ("Oh no! Something has gone wrong") and no
  working desktop appeared, so it is not the evidence run.

## What this does NOT prove

- **Secure Boot enforcement.** The run uses plain OVMF with
  Secure Boot off. The ISO reuses Ubuntu's signed shim/grub
  unchanged (so it *should* boot under Secure Boot via Microsoft's
  key), but that has not been demonstrated — booting under the
  `OVMF_CODE_4M.secboot.fd` variant, or on real firmware with
  Secure Boot on, is a separate, still outstanding check.
- **Real hardware.** No boot on the Protectli Vault Pro VP6630
  (or any physical machine) has happened yet.
- **Disk installation.** There is no disk installer in this
  milestone; the ISO is live-only. Booting the live session says
  nothing about installing to disk.
- **Control Center function.** The autostart only proves the app
  launches in the live session; its governance behaviour is
  covered by the repo's own test suite, not by this boot test.
