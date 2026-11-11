# Pulpo Preview graphical UEFI installer

Status: **installer skeleton in the Preview repo, 2026-11-10. Not a bootable ISO yet.**

## What this is

The graphic installer for Pulpo Preview, built on the work that
already exists instead of starting over:

- The wizard steps are the Control Center's Guided Setup (PR #55):
  Welcome, Time servers, Timezone, Network, Storage, Summary.
  Same order, same questions, same validation.
- The config it writes is the Control Center customer config,
  schema `pulpo.control-center-customer-config.v1` — the exact
  document `pulpo-control-center config import` accepts, so the
  installer and the installed system agree on what "configured"
  means. No second config format, no second authority plane.
- The images are the UEFI set made first for this installer
  (`installer/assets/`): boot splash, installer welcome,
  installing progress, square boot logo. Pulpo Preview
  **0.1.0-preview.4** — the welcome/progress mockups' invented
  version strings are not used here.

## What is in this folder

- `assets/pulpo-uefi-boot-splash.bmp` — the boot splash as a
  1920x1080 24-bit BMP, the format GRUB/UEFI graphics mode reads.
  Converted from the PNG original; the PNG stays the source of truth.
- `assets/*.png` — the UEFI image set (boot splash, installer
  welcome, installing progress, square boot logo).
- `grub.cfg` — draft UEFI GRUB config: 5s timeout, splash
  background, Install / Try live / Check media entries.
- `installer-manifest.json` — every installer image, its role,
  size, and SHA-256, so a build can verify nothing was swapped.
- `validate_config.py` — validates a config document against the
  guided-setup rules (NTP, timezone, DHCP/static, gateway on
  subnet, DNS max 3, retention max 24h, storage acknowledgement).
  Run: `python3 installer/validate_config.py installer/pulpo-preview-config.example.json`
- `pulpo-preview-config.example.json` — a valid example config
  (DHCP, America/Phoenix, Ubuntu NTP + pool, local evidence store).
- The clickable wizard ("Pulpo Preview Graphic Installer") stays
  outside this repo as the reference prototype — same steps, same
  rules, and it exports the finished config as a downloadable JSON
  file. This PR is the installer package skeleton, not the wizard UI.

## Rules the installer must not break

- **Gateway is a security control, not just a network setting.**
  DHCP by default. An unset gateway (no default route, no internet
  access) is a valid, deliberate choice — the installer says so
  plainly and never nudges the admin toward "connect to internet".
- **Pulpo governs and reports, that's it.** The installer writes
  config and installs the system. It does not grant authority,
  create permits, or touch the Pulpo kernel. First boot hands off
  to the Control Center's Guided Setup apply path
  (`config import --apply-network` via pkexec); the installer
  never runs as root itself and never stores credentials.
- **Storage honesty:** local evidence is kept at most 24h, and
  Pulpo is NOT responsible for the customer's data, backups, or
  storage. The admin must acknowledge that warning to continue.

## Scope and authority

Packaging, docs, and validation only. No `pulpo/` kernel code, no
Control Center code, and no CI workflow is changed by this PR, and
it grants no authority: `validate_config.py` only reads a config
document, and the images and GRUB config carry no credentials,
keys, or signing material.

## What is NOT done yet (honest gaps)

- No bootable ISO has been built, and nothing here has booted on
  real hardware. The Protectli Vault Pro VP6630 is the target;
  a boot test there is the gate before any "it installs" claim.
- Secure Boot is undecided: shim + Microsoft-signed shim vs
  enrolling Pulpo's own key (MOK). No signing has been done.
- No disk partitioning step exists yet — the wizard collects the
  storage *choice* (external/local, path, retention); the
  partitioner (Calamares or a guided Qt disk step) is still open.

## Next steps, in order

1. Boot-test the ISO skeleton on the VP6630 (or a VM with UEFI
   firmware) — splash, GRUB menu, live boot.
2. Decide Secure Boot (shim vs MOK) and the partitioner.
3. Decide whether the wizard UI itself comes into the repo or
   stays the reference prototype.
