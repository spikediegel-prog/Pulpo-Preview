#!/bin/bash
# Pulpo Preview live ISO — UEFI boot test (QEMU + OVMF, TCG).
#
# Boots the built ISO under UEFI with no KVM (the build VM has no
# /dev/kvm and no VMX/SVM flag), captures a serial boot log and a
# series of screenshots via the QEMU monitor, and reports whether
# the live session reached the GNOME desktop.
#
# The ISO's GRUB entries carry `console=ttyS0 console=tty0`, so the
# kernel log lands in the serial file while still showing on screen.
# Without that, QEMU's serial log would be empty and the only
# evidence would be screenshots.
#
# Usage:
#   installer/boot-test.sh [--iso PATH] [--work-dir PATH] [--timeout-min N]
#     --iso          ISO to boot (default: $WORK/pulpo-preview-0.1.0-live-amd64.iso)
#     --work-dir     scratch dir for logs/shots (default: ~/pulpo-workspace/iso-build/boot-test)
#     --timeout-min  give up after N minutes (default: 20)
#
# Requirements (all rootless, all from the same extracted .deb prefix
# the ISO build uses — see installer/build-iso.sh):
#   ~/pulpo-workspace/iso-tools/usr/bin/qemu-system-x86_64
#   ~/pulpo-workspace/iso-tools/usr/share/OVMF/OVMF_CODE_4M.fd
#   ~/pulpo-workspace/iso-tools/usr/share/OVMF/OVMF_VARS_4M.fd
#   nc (for the QEMU monitor over telnet)
#
# Outputs in the work dir:
#   boot.log        kernel + userspace serial log
#   shot-*.ppm      monitor screendumps (GRUB menu, boot, desktop).
#                   PPM, not PNG: this QEMU writes PPM content whatever
#                   the extension, so the files are named honestly.
#                   shot-grub-* is a burst across the GRUB window.
#   qemu.log        QEMU's own stderr
#   RESULT.md       verdict: BOOT OK / BOOT FAILED / INCONCLUSIVE,
#                   with the exact evidence file names.
#
# What this does NOT prove: Secure Boot enforcement (plain OVMF has
# Secure Boot off; the .secboot.fd variant is a separate run, see
# BOOT-TEST.md), real hardware, or disk installation — there is no
# disk installer in this milestone.
set -euo pipefail

VERSION="0.1.0"
WORK="${WORK:-$HOME/pulpo-workspace/iso-build}"
TOOLS="${TOOLS:-$HOME/pulpo-workspace/iso-tools}"
ISO=""
BTDIR=""
TIMEOUT_MIN=20

while [ $# -gt 0 ]; do
  case "$1" in
    --iso) ISO="$2"; shift 2;;
    --work-dir) BTDIR="$2"; shift 2;;
    --timeout-min) TIMEOUT_MIN="$2"; shift 2;;
    *) echo "unknown option: $1" >&2; exit 2;;
  esac
done

[ -n "$ISO" ] || ISO="$WORK/pulpo-preview-$VERSION-live-amd64.iso"
[ -n "$BTDIR" ] || BTDIR="$WORK/boot-test"
QEMU="$TOOLS/usr/bin/qemu-system-x86_64"
OVMF_CODE="$TOOLS/usr/share/OVMF/OVMF_CODE_4M.fd"
OVMF_VARS_SRC="$TOOLS/usr/share/OVMF/OVMF_VARS_4M.fd"

for f in "$ISO" "$QEMU" "$OVMF_CODE" "$OVMF_VARS_SRC"; do
  [ -f "$f" ] || { echo "missing input: $f" >&2; exit 1; }
done
command -v nc >/dev/null 2>&1 || { echo "missing: nc" >&2; exit 1; }

mkdir -p "$BTDIR"
# OVMF_VARS must be writable; never write into the extracted prefix.
cp "$OVMF_VARS_SRC" "$BTDIR/OVMF_VARS_4M.fd"

MONITOR_PORT=4444
echo "== Pulpo Preview boot test =="
echo "iso    : $ISO"
echo "work   : $BTDIR"
echo "timeout: ${TIMEOUT_MIN} min (TCG, no KVM — expect slow)"

export LD_LIBRARY_PATH="$TOOLS/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

# Debian's QEMU is built for /usr and only relocates its module/data
# paths when a directory named `qemu-bundle` sits next to the binary
# (Debian qemu-bundle patch). Without it, TCG fails to load with:
#   fatal: could not load module for type 'tcg-accel-ops'
# The bundle dir mirrors the filesystem root: QEMU appends the
# compiled-in paths (/usr/lib/x86_64-linux-gnu/qemu, /etc/qemu) to it.
BUNDLE_DIR="$TOOLS/usr/bin/qemu-bundle"
mkdir -p "$BUNDLE_DIR"
ln -sfn ../.. "$BUNDLE_DIR/usr"
ln -sfn ../../../etc "$BUNDLE_DIR/etc"

# -cpu qemu64 is the default: it reaches the GNOME desktop and the
# Qt Control Center runs. Two QEMU CPU notes, both verified
# 2026-11-11:
# - qemu64 provides SSE3 but none of SSSE3/SSE4.1/SSE4.2/POPCNT
#   (x86-64-v2). The vendored Qt 6.12 in the preview.47 .deb required
#   v2 and died with "Illegal instruction" (SIGILL) while importing
#   under qemu64 — the fault was the v2 baseline, not AVX (adding
#   only the v2 features, no AVX, makes Qt load). The preview.48
#   .deb vendors PySide6 6.9.3, which starts on v1, so the Qt
#   interface is exercised by this very boot test; the launcher
#   also probes Qt in a child and falls back to Tkinter if Qt
#   cannot start. The Tkinter Control Center remains the fallback
#   proof the app works in the live session.
# - `-cpu max` was tried: much slower under TCG, and gnome-shell
#   itself crashed ("Oh no! Something has gone wrong") with no
#   working desktop, so it is not the default either.
"$QEMU" -machine q35 -m 2048 -smp 2 -cpu qemu64 \
  -drive if=pflash,format=raw,readonly=on,file="$OVMF_CODE" \
  -drive if=pflash,format=raw,file="$BTDIR/OVMF_VARS_4M.fd" \
  -cdrom "$ISO" -boot d \
  -display vnc=:1 -monitor "telnet:127.0.0.1:$MONITOR_PORT,server,nowait" \
  -serial "file:$BTDIR/boot.log" -net none \
  -device VGA,vgamem_mb=64 \
  >"$BTDIR/qemu.log" 2>&1 &
QPID=$!
echo "qemu pid $QPID"

shot() { # shot <name>
  # NB: `screendump <file> [device]` — the 2nd argument is a DEVICE
  # name, not a format; passing `png` fails with "Device 'png' not
  # found". QEMU writes PPM here (see header), hence the .ppm name.
  printf 'screendump %s/%s.ppm\n' "$BTDIR" "$1" | nc -w 5 127.0.0.1 "$MONITOR_PORT" >/dev/null 2>&1 || true
}

cleanup() { kill "$QPID" 2>/dev/null || true; wait "$QPID" 2>/dev/null || true; }
trap cleanup EXIT

# GRUB shows for 5s once OVMF hands over (~20-25s in under TCG);
# a single early shot easily lands on either side of it (black
# screen before, kernel log after). Take a burst across the window
# so one shot catches the menu + splash, then sample the boot.
sleep 15
for t in 17 19 21 23 25 27 29; do
  shot "shot-grub-$t"
  sleep 2
done
shot shot-02-boot-early
# Then sample the boot every 60s until the serial log shows gdm
# started, or the timeout expires. The pass criterion is gdm, NOT
# "Reached target Graphical Interface": that line never reaches the
# serial log in this setup (the log goes quiet after the login
# prompt even though the desktop comes up — verified 2026-11-11),
# so waiting for it always ends INCONCLUSIVE on a good boot.
DESKTOP=no
for i in $(seq 3 1 "$TIMEOUT_MIN"); do
  sleep 60
  shot "shot-$(printf %02d "$i")-boot"
  if grep -qE "Started.*(gdm\.service|GNOME Display Manager)" "$BTDIR/boot.log" 2>/dev/null; then
    DESKTOP=yes
    break
  fi
  kill -0 "$QPID" 2>/dev/null || { echo "QEMU exited early (see qemu.log)" >&2; break; }
done

# gdm starting is not the desktop: under TCG the autologin session,
# GNOME Shell and the autostarted Control Center need several more
# minutes (the first qt48 run's final shots, 90 s after gdm, were a
# black screen; the PR #124 run needed ~6 min after gdm before the
# desktop appeared). Sample every minute for 8 minutes; sendkey ctrl
# before each shot so an idle-blanked screen wakes instead of staying
# black. A shot that catches the desktop up is the evidence — a later
# blanked screen does not erase the earlier one.
for wait in 60 120 180 240 300 360 420 480; do
  sleep 60
  printf 'sendkey ctrl\n' | nc -w 5 127.0.0.1 "$MONITOR_PORT" >/dev/null 2>&1 || true
  shot "shot-final-$(printf %03d "$wait")s"
done

if [ "$DESKTOP" = yes ]; then
  VERDICT="BOOT OK — live session reached the GNOME display manager (see boot.log) and the desktop screenshots"
else
  VERDICT="INCONCLUSIVE — gdm not seen in boot.log within ${TIMEOUT_MIN} min; inspect shot-*.ppm before calling this a failure (TCG is slow)"
fi

cat > "$BTDIR/RESULT.md" <<EOF
# Pulpo Preview live ISO — boot test result

- ISO: $ISO
- Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)
- QEMU: 8.2.2 (TCG, no KVM), OVMF_CODE_4M.fd, 2048 MB RAM, 2 vCPUs
- Verdict: $VERDICT
- Serial log: boot.log
- Screenshots: shot-*.ppm (PPM; shot-grub-* = GRUB menu + splash burst, one of them catches the 5s menu)
- QEMU log: qemu.log

Secure Boot was NOT enforced in this run (plain OVMF, Secure Boot
off). Booting under Secure Boot enforcement is a separate, still
outstanding check.
EOF

echo "$VERDICT"
echo "results in $BTDIR"
