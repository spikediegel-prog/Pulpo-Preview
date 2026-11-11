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
- `shot-*.png` — QEMU monitor screendumps: `shot-01-grub` is the
  GRUB menu with the Pulpo splash; the later shots show the boot
  and the GNOME desktop.
- `qemu.log` — QEMU's own stderr.
- `RESULT.md` — the script's verdict.

Pass = the serial log shows `Reached target Graphical Interface`
(or the GNOME Display Manager starting) AND a screenshot shows the
live desktop. A GRUB-menu screenshot alone is not a pass.

## Results

> Fill in from the run. Do not edit this section by hand without
> re-running the test.

| Item | Value |
| --- | --- |
| ISO | (path, size, SHA-256) |
| Date (UTC) | |
| QEMU / OVMF | 8.2.2 TCG, OVMF_CODE_4M.fd |
| GRUB menu + splash | (shot file) |
| Graphical target reached | yes / no |
| Live desktop shown | (shot file) |
| Control Center autostarted | yes / no / not checked |
| Verdict | BOOT OK / INCONCLUSIVE / BOOT FAILED |

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
