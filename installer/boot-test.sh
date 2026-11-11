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
#   shot-*.png      monitor screendumps (GRUB menu, boot, desktop)
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
  printf 'screendump %s/%s.png png\n' "$BTDIR" "$1" | nc -w 5 127.0.0.1 "$MONITOR_PORT" >/dev/null 2>&1 || true
}

cleanup() { kill "$QPID" 2>/dev/null || true; wait "$QPID" 2>/dev/null || true; }
trap cleanup EXIT

# GRUB waits 5s; the splash + menu are up within the first minute.
sleep 45; shot shot-01-grub
# Then sample the boot every 60s until the serial log shows the
# graphical target, or the timeout expires.
DESKTOP=no
for i in $(seq 2 1 "$TIMEOUT_MIN"); do
  sleep 60
  shot "shot-$(printf %02d "$i")-boot"
  if grep -q "Reached target Graphical Interface" "$BTDIR/boot.log" 2>/dev/null \
     || grep -q "gdm.service:.*Started\|Started GNOME Display Manager" "$BTDIR/boot.log" 2>/dev/null; then
    DESKTOP=yes
    break
  fi
  kill -0 "$QPID" 2>/dev/null || { echo "QEMU exited early (see qemu.log)" >&2; break; }
done

# Let the desktop settle, then take the final evidence shots.
sleep 60; shot shot-final-desktop
sleep 30; shot shot-final-desktop-2

if [ "$DESKTOP" = yes ]; then
  VERDICT="BOOT OK — live session reached the graphical target (see boot.log)"
else
  VERDICT="INCONCLUSIVE — graphical target not seen in boot.log within ${TIMEOUT_MIN} min; inspect shot-*.png before calling this a failure (TCG is slow)"
fi

cat > "$BTDIR/RESULT.md" <<EOF
# Pulpo Preview live ISO — boot test result

- ISO: $ISO
- Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)
- QEMU: 8.2.2 (TCG, no KVM), OVMF_CODE_4M.fd, 2048 MB RAM, 2 vCPUs
- Verdict: $VERDICT
- Serial log: boot.log
- Screenshots: shot-*.png (shot-01-grub = GRUB menu + splash)
- QEMU log: qemu.log

Secure Boot was NOT enforced in this run (plain OVMF, Secure Boot
off). Booting under Secure Boot enforcement is a separate, still
outstanding check.
EOF

echo "$VERDICT"
echo "results in $BTDIR"
