# Pulpo Preview live ISO — boot test

How the ISO was proven to boot, and what the test does *not* prove.

## Method

`installer/boot-test.sh` boots the built ISO under QEMU + OVMF
(UEFI firmware), with no KVM — the build VM has no `/dev/kvm` and
no VMX/SVM flag, so QEMU runs in TCG (software emulation) and the
boot is slow. Guest: 2048 MB RAM, 2 vCPUs, q35 machine, no network
(`-net none` — the live session must not need the network to reach
the desktop).

Evidence collected in a run directory under
`~/pulpo-workspace/iso-build/` (`boot-test/` for the preview.47 run,
`boot-test-qt48/` and `boot-test-qt48b/` for the preview.48 runs):

- `boot.log` — kernel + userspace serial log. The ISO's GRUB
  entries carry `console=ttyS0 console=tty0`, so the log lands here
  while still showing on screen.
- `shot-*.ppm` — QEMU monitor screendumps (PPM, not PNG: this
  QEMU writes PPM content whatever the extension):
  `shot-grub-*` is a burst across the 5 s GRUB window;
  `shot-NN-boot` samples the boot every 60 s until gdm starts;
  `shot-final-NNNs` samples the desktop every 60 s for 8 minutes
  after gdm (60 s–480 s), with a harmless Ctrl keypress before each
  shot so an idle-blanked screen wakes instead of staying black.
  gdm starting is not the desktop: under TCG the autologin session
  and GNOME Shell need several more minutes (the first preview.48
  run's finals, 90 s after gdm, were a black screen; the desktop
  appeared ~300 s after gdm).
- `qemu.log` — QEMU's own stderr.
- `RESULT.md` — the script's verdict.

Pass = the serial log shows the GNOME Display Manager starting
AND a screenshot shows the live desktop. A GRUB-menu screenshot
alone is not a pass. The pass criterion is gdm, not `Reached
target Graphical Interface`: that line never reaches the serial
log in this setup (the log goes quiet after the login prompt even
though the desktop comes up), so waiting for it always ends
INCONCLUSIVE on a good boot. Guest CPU is `-cpu qemu64`. Two CPU
notes, both verified 2026-11-11: qemu64 provides SSE3 but none of
SSSE3/SSE4.1/SSE4.2/POPCNT (x86-64-v2). The vendored Qt 6.12 in the
preview.47 `.deb` required v2 and died with `Illegal instruction
(core dumped)` (SIGILL) while importing — the fault was the v2
baseline, not AVX (adding only the v2 features, no AVX, makes Qt
load). The preview.48 `.deb` (Control Center PR #66) vendors
PySide6 6.9.3, which starts on x86-64-v1, so the Qt interface is
exercised by this boot test; the launcher also probes Qt in a
child and falls back to Tkinter if Qt cannot start. `-cpu max`
was tried instead: much slower under TCG, and gnome-shell itself
crashed ("Oh no! Something has gone wrong") with no working
desktop, so it is not used.

## Results

### Run 2026-11-11, preview.48 (Control Center PR #66)

Two boots of the same ISO. The first run's verdict was BOOT OK
(gdm in `boot.log`) but its final screenshots were a black screen:
the settle after gdm was only 90 s, and the desktop needs ~300 s
under TCG. `boot-test.sh` now samples the desktop for 8 minutes
after gdm instead; the second run is the evidence run.

| Item | Value |
| --- | --- |
| ISO | `~/pulpo-workspace/iso-build/pulpo-preview-0.1.0-live-qt48-amd64.iso`, 6,313,017,344 bytes, SHA-256 `dcc8b99606e904cec7bd82bc8defc172f6b0ea223fc3a0d4b128e559e06f5838` |
| Date (UTC) | 2026-11-11 19:14 (second run; first run 18:58) |
| QEMU / OVMF | 8.2.2 TCG, OVMF_CODE_4M.fd, `-cpu qemu64` |
| GRUB menu + splash | not captured (see note) |
| gdm started (serial log) | yes — `Started gdm.service` in `boot.log` (both runs) |
| Live desktop shown | yes — second run `shot-final-300s.png` / `shot-final-480s.png`: GNOME desktop, PULPO-PREVIEW-README.txt on the desktop |
| Control Center autostarted | **yes — the Qt Control Center is open and live**: Overview page with the PULPO sidebar (MONITOR / REVIEW / WORKSPACE, "YOUR HARDWARE. YOUR DATA. YOUR RULES."), Activity monitor CPU 58.3% at 19:10 → 55.4% at 19:14, memory 54.2% → 54.1%, history 2m 18s → 5m 48s. The values changing between shots proves the app is running, not a frozen frame. No SIGILL, no crash file. This is the first time the Qt interface has been seen running in the live session under `qemu64`. |
| Verdict | BOOT OK (both runs; second run is the Qt evidence) |

Evidence: `~/pulpo-workspace/iso-build/boot-test-qt48b/` (second run)
and `boot-test-qt48/` (first run); PNG copies of the Qt shots in
`~/workspace/iso-boot-evidence/qt48/`
(`shot-final-300s.png`, `shot-final-360s.png`, `shot-final-480s.png`).

### Run 2026-11-11, preview.47 (PR #124)

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
- The Control Center autostart crash (preview.47 run):
  `/var/crash/` held exactly one file,
  `_usr_bin_pulpo-control-center.1000.crash`, and running the
  launcher by hand in the live session printed `Illegal
  instruction (core dumped)`. The Tkinter interface
  (`pulpo-control-center-tk`) opens and runs; the Qt interface is
  the one that SIGILLs under `qemu64`. See the CPU notes in Method.
  Fixed in preview.48: the Qt Control Center autostarts and runs
  in the live session (see the preview.48 run above).
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
