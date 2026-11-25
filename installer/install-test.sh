#!/bin/bash
# Pulpo Preview disk installer — UEFI VM install test (QEMU + OVMF, TCG).
#
# Two phases, both under QEMU with no KVM (neither VM has /dev/kvm):
#   install: boot the live ISO with a blank virtual disk attached,
#            wait for the GNOME desktop, then HOLD with the QEMU
#            monitor open so the operator can drive the Calamares
#            installer (keyboard/mouse via the subcommands below).
#            The installer is driven by hand on purpose: Calamares
#            is a GUI and its timing under TCG is not scriptable
#            reliably. The evidence is the screenshots + logs.
#   verify:  boot the INSTALLED system from the virtual disk (no
#            ISO attached), wait for gdm + the desktop, then HOLD
#            so the operator can log in and check the installed
#            system (desktop, Control Center, applied config).
#
# The install is driven through the QEMU monitor (telnet) with:
#   install-test.sh --work-dir DIR --shot NAME   # screendump
#   install-test.sh --work-dir DIR --key KEYS    # sendkey (e.g. "ctrl-alt-t", "ret")
#   install-test.sh --work-dir DIR --type "text" # type a string (sendkey per char is slow; use --type)
#   install-test.sh --work-dir DIR --mouse      # left-click at the CURRENT pointer position only
#   install-test.sh --work-dir DIR --stop        # power down the VM
#
# Usage:
#   installer/install-test.sh --iso PATH [--work-dir PATH] [--disk PATH]
#                             [--disk-size GB] [--phase install|verify]
#                             [--timeout-min N]
#     --iso        ISO to boot (install phase; default: $WORK/pulpo-preview-0.1.0-live-diskinstall-amd64.iso)
#     --work-dir   scratch dir for disk/logs/shots (default: $WORK/install-test)
#     --disk       virtual disk (default: $WORK/install-test/pulpo-test.qcow2)
#     --disk-size  virtual disk size in GB (default: 25)
#     --phase      install (default) or verify
#     --timeout-min  give up waiting for the desktop after N minutes (default: 30)
#
# Requirements (same extracted .deb prefix as boot-test.sh):
#   $TOOLS/usr/bin/qemu-system-x86_64, qemu-img
#   $TOOLS/usr/share/OVMF/OVMF_CODE_4M.fd, OVMF_VARS_4M.fd
#   nc (for the QEMU monitor over telnet)
#
# Networking: the install phase attaches a user-mode NIC
# (``-netdev user``) — NOT ``-net none`` — so the live session has
# an interface with a default route. The pulpo-config import
# derives the interface from the live session's default route;
# without a NIC there is no interface and the network part of the
# config cannot be applied. User networking gives the guest NAT
# only (no inbound connections, no host access beyond the gateway).
#
# Outputs in the work dir:
#   pulpo-test.qcow2   the virtual disk (install writes here; verify boots from it)
#   boot.log           kernel + userspace serial log (install phase)
#   boot-verify.log    serial log (verify phase)
#   shot-*.ppm         monitor screendumps (PPM; this QEMU writes PPM
#                      content whatever the extension)
#   qemu.log / qemu-verify.log   QEMU's own stderr
#   monitor.port / vnc.display   how the subcommands reach this run
#   OVMF_VARS_4M-install.fd     install-phase NVRAM, preserved when
#                               the install phase ends; the verify
#                               phase boots from it (run 10: the old
#                               script copied pristine vars at every
#                               launch, destroying the installed
#                               boot entry it wanted to check)
#   RESULT.md          verdict, written by the operator at the end
#                      of each phase (the script cannot judge a GUI).
#
# What this does NOT prove: Secure Boot enforcement (plain OVMF,
# Secure Boot off), real hardware (Protectli is still the gate),
# or Hyper-V Gen 2 (the next boot target after this VM test).
set -euo pipefail

VERSION="0.1.0"
WORK="${WORK:-$HOME/pulpo-workspace/iso-build}"
TOOLS="${TOOLS:-$HOME/pulpo-workspace/iso-tools}"
ISO=""
BTDIR=""
DISK=""
DISK_SIZE=25
# Guest RAM in MiB. Raised from 2048 to 4096 after the VM host was
# upgraded to 5.8 Gi (2026-11-12): run 4 stalled for 5+ hours with
# zero progress at -m 2048 on a 3.8 Gi host — the guest and the host
# were both starving. 4096 leaves ~1.8 Gi for the idle host during
# the test. Do not go back to 2048; 3072 is the floor if the host
# struggles.
MEM_MB=4096
PHASE="install"
TIMEOUT_MIN=30
MONITOR_PORT=4445
VNC_DISPLAY=2

# --- subcommands (talk to a running QEMU) ---
# These need only --work-dir; they read the monitor port from it.
SUBCMD=""
SUBARG=""
while [ $# -gt 0 ]; do
  case "$1" in
    --iso) ISO="$2"; shift 2;;
    --work-dir) BTDIR="$2"; shift 2;;
    --disk) DISK="$2"; shift 2;;
    --disk-size) DISK_SIZE="$2"; shift 2;;
    --phase) PHASE="$2"; shift 2;;
    --timeout-min) TIMEOUT_MIN="$2"; shift 2;;
    --shot) SUBCMD="shot"; SUBARG="$2"; shift 2;;
    --key) SUBCMD="key"; SUBARG="$2"; shift 2;;
    --type) SUBCMD="type"; SUBARG="$2"; shift 2;;
    --mouse) SUBCMD="mouse"; shift;;
    --stop) SUBCMD="stop"; shift;;
    *) echo "unknown option: $1" >&2; exit 2;;
  esac
done

[ -n "$BTDIR" ] || BTDIR="$WORK/install-test"
[ -n "$DISK" ] || DISK="$BTDIR/pulpo-test.qcow2"

mon() { # mon <qmp-line> — send one line to the QEMU monitor
  local port
  port="$(cat "$BTDIR/monitor.port" 2>/dev/null || echo "$MONITOR_PORT")"
  printf '%s\n' "$1" | nc -w 5 127.0.0.1 "$port" >/dev/null 2>&1 || true
}

case "$SUBCMD" in
  shot)
    mkdir -p "$BTDIR"
    mon "screendump $BTDIR/$SUBARG.ppm"
    echo "shot: $BTDIR/$SUBARG.ppm"
    exit 0;;
  key)
    mon "sendkey $SUBARG"
    echo "sent key: $SUBARG"
    exit 0;;
  type)
    # Type a string by sending each character as a key. All keys go
    # through ONE monitor connection, in order: a separate nc per
    # character lets connections overlap when the monitor is slow,
    # and the guest then receives the characters scrambled. Slow
    # under TCG, but reliable; the installer fields are short (name,
    # password, hostname).
    {
    for (( i=0; i<${#SUBARG}; i++ )); do
      ch="${SUBARG:$i:1}"
      case "$ch" in
        ' ') key="spc";;
        '-' ) key="minus";;
        '_' ) key="shift-minus";;
        '.' ) key="dot";;
        '/' ) key="slash";;
        '@' ) key="shift-2";;
        [A-Z]) key="shift-${ch,,}";;
        '~') key="shift-grave";;
        '`') key="grave";;
        '!') key="shift-1";;
        '#') key="shift-3";;
        '$') key="shift-4";;
        '%') key="shift-5";;
        '^') key="shift-6";;
        '&') key="shift-7";;
        '*') key="shift-8";;
        '(') key="shift-9";;
        ')') key="shift-0";;
        ':') key="shift-semicolon";;
        ';') key="semicolon";;
        ',') key="comma";;
        '?') key="shift-slash";;
        '"') key="shift-apostrophe";;
        "'") key="apostrophe";;
        '\') key="backslash";;
        '|') key="shift-backslash";;
        '<') key="shift-comma";;
        '>') key="shift-dot";;
        '=') key="equal";;
        '+') key="shift-equal";;
        '[') key="bracket_left";;
        ']') key="bracket_right";;
        '{') key="shift-bracket_left";;
        '}') key="shift-bracket_right";;
        *) key="$ch";;
      esac
      printf 'sendkey %s\n' "$key"
      sleep 0.2
    done
    } | nc -w 5 127.0.0.1 "$(cat "$BTDIR/monitor.port" 2>/dev/null || echo "$MONITOR_PORT")" >/dev/null 2>&1 || true
    echo "typed: $SUBARG"
    exit 0;;
  mouse)
    # mouse — left-click at the CURRENT pointer position.
    # NO positioning: the QEMU monitor mouse_move command is a
    # no-op for the usb-tablet (absolute). Probed 2026-11-12
    # (build #10, probe-mouse work dir): mouse_move was confirmed
    # delivered to the monitor (prompt returned, tablet is the
    # active mouse per 'info mice') in five attempts (500 0,
    # 1000 500, 500 300, home -30000 -30000 then 500 0 twice,
    # 0 300) and the pointer never moved (screendumps
    # byte-identical). Earlier "relative" readings were the
    # sampling loop / desktop moving the pointer, not mouse_move.
    # So --mouse cannot move the pointer to (X, Y); it only
    # clicks wherever the pointer happens to be. Verify by
    # screenshot after every click. Keyboard (--key/--type) is
    # the reliable driver; Calamares is fully
    # keyboard-navigable. A VNC absolute PointerEvent is the only
    # known way to position the pointer (not implemented).
    mon "mouse_button 1"
    sleep 0.3
    mon "mouse_button 0"
    echo "clicked at current pointer position (no positioning)"
    exit 0;;
  stop)
    mon "system_powerdown"
    sleep 10
    pkill -f "qemu-system-x86_64.*$BTDIR" 2>/dev/null || true
    echo "stopped"
    exit 0;;
esac

# --- main phases ---
[ -n "$ISO" ] || ISO="$WORK/pulpo-preview-$VERSION-live-diskinstall-amd64.iso"
QEMU="$TOOLS/usr/bin/qemu-system-x86_64"
QEMU_IMG="$TOOLS/usr/bin/qemu-img"
OVMF_CODE="$TOOLS/usr/share/OVMF/OVMF_CODE_4M.fd"
OVMF_VARS_SRC="$TOOLS/usr/share/OVMF/OVMF_VARS_4M.fd"

for f in "$QEMU" "$QEMU_IMG" "$OVMF_CODE" "$OVMF_VARS_SRC"; do
  [ -f "$f" ] || { echo "missing input: $f" >&2; exit 1; }
done
command -v nc >/dev/null 2>&1 || { echo "missing: nc" >&2; exit 1; }

mkdir -p "$BTDIR"
echo "$MONITOR_PORT" > "$BTDIR/monitor.port"
echo "$VNC_DISPLAY" > "$BTDIR/vnc.display"
# OVMF_VARS must be writable; never write into the extracted prefix.
# Run 10: the verify phase used to copy the PRISTINE vars at every
# launch, destroying the NVRAM boot entry the install had just
# created — so the verify boot could only ever exercise the
# fallback path, and the efibootmgr "pulpo" check was untestable.
# The install phase preserves its vars to OVMF_VARS_4M-install.fd
# when it ends (below); the verify phase reuses that file when it
# exists, so the verify boot tests the actual installed entry.
# A verify run with no preserved install vars falls back to the
# pristine file (old behaviour) and warns that the entry is
# untestable.
if [ "$PHASE" = verify ] && [ -f "$BTDIR/OVMF_VARS_4M-install.fd" ]; then
  echo "== verify: reusing install-phase NVRAM ($BTDIR/OVMF_VARS_4M-install.fd) =="
  cp "$BTDIR/OVMF_VARS_4M-install.fd" "$BTDIR/OVMF_VARS_4M.fd"
else
  if [ "$PHASE" = verify ]; then
    echo "== verify: no install-phase NVRAM found; using pristine vars (NVRAM entry untestable) ==" >&2
  fi
  cp "$OVMF_VARS_SRC" "$BTDIR/OVMF_VARS_4M.fd"
fi

export LD_LIBRARY_PATH="$TOOLS/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

# Debian's QEMU relocation (see boot-test.sh): a `qemu-bundle`
# dir next to the binary, or TCG fails to load.
BUNDLE_DIR="$TOOLS/usr/bin/qemu-bundle"
mkdir -p "$BUNDLE_DIR"
ln -sfn ../.. "$BUNDLE_DIR/usr"
ln -sfn ../../../etc "$BUNDLE_DIR/etc"

if [ "$PHASE" = install ]; then
  [ -f "$ISO" ] || { echo "missing input: $ISO" >&2; exit 1; }
  if [ ! -f "$DISK" ]; then
    echo "== creating virtual disk $DISK (${DISK_SIZE}G) =="
    "$QEMU_IMG" create -f qcow2 "$DISK" "${DISK_SIZE}G"
  else
    echo "== reusing existing virtual disk $DISK (delete it to start over) =="
  fi
  echo "== Pulpo Preview install test (phase: install) =="
  echo "iso    : $ISO"
  echo "disk   : $DISK"
  echo "work   : $BTDIR"
  echo "monitor: telnet 127.0.0.1:$MONITOR_PORT (VNC :$VNC_DISPLAY)"
  echo "timeout: ${TIMEOUT_MIN} min to reach the desktop (TCG, no KVM — expect slow)"
  "$QEMU" -machine q35 -m $MEM_MB -smp 2 -cpu qemu64 \
    -drive if=pflash,format=raw,readonly=on,file="$OVMF_CODE" \
    -drive if=pflash,format=raw,file="$BTDIR/OVMF_VARS_4M.fd" \
    -drive if=virtio,format=qcow2,file="$DISK" \
    -cdrom "$ISO" -boot d \
    -display vnc=:$VNC_DISPLAY -monitor "telnet:127.0.0.1:$MONITOR_PORT,server,nowait" \
    -serial "file:$BTDIR/boot.log" \
    -netdev user,id=net0 -device virtio-net-pci,netdev=net0 \
    -device VGA,vgamem_mb=64 \
    -device qemu-xhci \
    -device usb-tablet \
    >"$BTDIR/qemu.log" 2>&1 &
  QPID=$!
  BOOTLOG="$BTDIR/boot.log"
elif [ "$PHASE" = verify ]; then
  [ -f "$DISK" ] || { echo "missing virtual disk: $DISK (run phase install first)" >&2; exit 1; }
  echo "== Pulpo Preview install test (phase: verify — boot the INSTALLED system) =="
  echo "disk   : $DISK"
  echo "work   : $BTDIR"
  echo "monitor: telnet 127.0.0.1:$MONITOR_PORT (VNC :$VNC_DISPLAY)"
  echo "timeout: ${TIMEOUT_MIN} min to reach the desktop (TCG, no KVM — expect slow)"
  # No ISO attached; boot from the disk. The installed GRUB is
  # Ubuntu's (shim + grub from the base image), so this is also
  # the check that the bootloader install worked.
  "$QEMU" -machine q35 -m $MEM_MB -smp 2 -cpu qemu64 \
    -drive if=pflash,format=raw,readonly=on,file="$OVMF_CODE" \
    -drive if=pflash,format=raw,file="$BTDIR/OVMF_VARS_4M.fd" \
    -drive if=virtio,format=qcow2,file="$DISK" \
    -boot c \
    -display vnc=:$VNC_DISPLAY -monitor "telnet:127.0.0.1:$MONITOR_PORT,server,nowait" \
    -serial "file:$BTDIR/boot-verify.log" \
    -netdev user,id=net0 -device virtio-net-pci,netdev=net0 \
    -device VGA,vgamem_mb=64 \
    -device qemu-xhci \
    -device usb-tablet \
    >"$BTDIR/qemu-verify.log" 2>&1 &
  QPID=$!
  BOOTLOG="$BTDIR/boot-verify.log"
else
  echo "unknown phase: $PHASE (install|verify)" >&2; exit 2
fi

echo "qemu pid $QPID"
echo "$QPID" > "$BTDIR/qemu.pid"

cleanup() { kill "$QPID" 2>/dev/null || true; wait "$QPID" 2>/dev/null || true; }
# Clean up only on abort (Ctrl-C / TERM), NOT on normal exit: the
# sampling loops end long before a full install finishes, and the
# closing message promises the VM stays running for the operator
# to drive. An EXIT trap would kill QEMU mid-install as soon as
# the script finished sampling. (Run 4 only survived because the
# script happened to block in cleanup's wait on the starved host.)
trap cleanup INT TERM

shot() { # shot <name>
  mon "screendump $BTDIR/$1.ppm"
}

# GRUB shows for 5s once OVMF hands over (~20-25s in under TCG);
# take a burst across the window (install phase only — the verify
# phase has the installed GRUB, whose menu is also worth catching).
sleep 15
for t in 17 19 21 23 25 27 29; do
  shot "shot-grub-$t"
  sleep 2
done
# Sample the boot every 60s until the serial log shows gdm started.
DESKTOP=no
for i in $(seq 3 1 "$TIMEOUT_MIN"); do
  sleep 60
  shot "shot-$(printf %02d "$i")-boot"
  if grep -qE "Started.*(gdm\.service|GNOME Display Manager)" "$BOOTLOG" 2>/dev/null; then
    DESKTOP=yes
    break
  fi
  kill -0 "$QPID" 2>/dev/null || { echo "QEMU exited early (see qemu*.log)" >&2; break; }
done

# gdm starting is not the desktop: under TCG the autologin session
# and GNOME Shell need several more minutes. Sample every minute
# for 8 minutes; sendkey ctrl before each shot so an idle-blanked
# screen wakes instead of staying black.
for wait in 60 120 180 240 300 360 420 480; do
  sleep 60
  mon "sendkey ctrl"
  shot "shot-final-$(printf %03d "$wait")s"
done

if [ "$DESKTOP" = yes ]; then
  echo "DESKTOP REACHED — gdm in $BOOTLOG, desktop screenshots in $BTDIR"
else
  echo "DESKTOP NOT CONFIRMED — gdm not seen in $BOOTLOG within ${TIMEOUT_MIN} min; inspect shot-*.ppm (TCG is slow)"
fi
echo ""
echo "The VM is still running. Drive it with:"
echo "  $0 --work-dir $BTDIR --shot <name>     (screendump)"
echo "  $0 --work-dir $BTDIR --key <keys>       (sendkey, e.g. ctrl-alt-t, ret, tab)"
echo "  $0 --work-dir $BTDIR --type \"text\"      (type a string)"
echo "  $0 --work-dir $BTDIR --mouse             (left-click at current pointer position; no positioning)"
echo "  $0 --work-dir $BTDIR --stop             (power down)"
echo ""
echo "Phase install: open a terminal (ctrl-alt-t), run 'sudo -E calamares',"
echo "and work through the installer (erase-disk, create the user,"
echo "finish). When the install is done and the VM is shut down,"
echo "re-run this script with --phase verify to boot the installed system."
echo "Phase verify: log in at gdm, open a terminal, and check the"
echo "installed system (see INSTALL-TEST.md for the checklist)."
echo ""
echo "Holding the VM up until $BTDIR/INSTALL_DONE exists (or this process is killed)."
while [ ! -f "$BTDIR/INSTALL_DONE" ]; do
  sleep 30
  kill -0 "$QPID" 2>/dev/null || { echo "QEMU exited (see qemu*.log)"; break; }
done
# Preserve the install-phase NVRAM (with the boot entry the
# install created) so the verify phase can boot from it — see the
# launch block above. Runs on both exits of the hold loop
# (INSTALL_DONE found, or QEMU exited after --stop); the copy is
# harmless for the verify phase, which never writes it back.
if [ "$PHASE" = install ] && [ -f "$BTDIR/OVMF_VARS_4M.fd" ]; then
  cp "$BTDIR/OVMF_VARS_4M.fd" "$BTDIR/OVMF_VARS_4M-install.fd"
  echo "preserved install-phase NVRAM to $BTDIR/OVMF_VARS_4M-install.fd (verify phase reuses it)"
fi
echo "INSTALL_DONE found (or QEMU exited); stopping."
