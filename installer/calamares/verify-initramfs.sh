#!/bin/bash
# Pulpo Preview — installer module: gate the built initrd.
#
# Runs in the LIVE session as root (Calamares shellprocess with
# dontChroot: true), with $1 = the target root mount point
# (${ROOT}), AFTER the initramfs step. It lists every
# /boot/initrd.img-* in the target with lsinitramfs and fails the
# install if any of them contains casper boot logic (a casper
# script or hook). The remove-live step before initramfs
# should have made this impossible; the gate exists so a
# regression fails the install loudly instead of shipping a
# system that drops to an (initramfs) shell on first boot (run 10:
# the casper initrd probed for a live medium with no ISO
# attached, because the casper package was still installed when
# the initramfs step regenerated the image).
#
# What counts as casper boot logic (run 11): a path under
# scripts/casper* or hooks/casper* in the image. mkinitramfs
# copies the casper scripts into the initrd at scripts/casper,
# scripts/casper-functions, scripts/casper-helpers,
# scripts/casper-bottom and scripts/casper-premount (run 3:
# /scripts/casper in the live initrd); hooks are not normally
# copied into the image (verified: no hooks/ dir in a stock
# initrd), but the pattern covers them if they ever are. A bare
# config line such as conf/conf.d/casperize.conf is NOT boot
# logic — nothing in the initrd reads CASPER_GENERATE_UUID — so
# the gate does not fail on it (run 11: the old "any path
# mentioning casper" rule failed the image over that one inert
# line, while the initrd had no casper hook or scripts and would
# very likely have booted). The remove-live step deletes the
# leftover conf file from the target; the gate checks the thing
# that would actually break boot.
#
# Cost (run 11): one lsinitramfs pass over the ~90 MB initrd
# takes ~5.7 min under TCG (decompression-bound), ~seconds on
# real hardware. The gate therefore lists the image ONCE per
# initrd — the listing goes to a temp file and the greps run
# against the file — instead of listing it twice (once to check,
# once more to print the matches on error), which cost 11m28s
# under TCG and could never finish inside the old 60 s timeout.
# The Calamares timeout for this step is 1200 s (see
# shellprocess_verify-initramfs.conf), ~3.5x the single-pass
# TCG cost.
#
# Failure modes (loud where it matters, never silent):
#   - No initrd found in the target: exit non-zero. The
#     initramfs step should have built one; an absent image is
#     itself a broken install.
#   - Any initrd contains casper boot logic: exit non-zero, so
#     Calamares marks the install FAILED.
#   - Neither lsinitramfs nor unmkinitramfs is available, or the
#     image cannot be listed: exit non-zero. A gate that cannot
#     inspect the image must not silently pass it.
#
# For testing: the script is safe to source — its side effects
# live in main(), so tests can source it and call
# initramfs_contains_casper directly on a fake initrd (built with
# cpio), with no root and no target needed.
set -u

LOG_PREFIX="[verify-initramfs]"

# Casper boot logic inside an initrd: a casper script or hook.
# The (^|/) prefix covers both the real layout (scripts/casper*
# at the image root) and a usr/share/initramfs-tools/... layout.
CASPER_BOOT_PATH_RE='(^|/)(scripts|hooks)/casper'

log() { echo "$LOG_PREFIX $*"; }

# _list_initramfs <initrd>: print the initrd's contents, one
# path per line. Prefers lsinitramfs; falls back to
# unmkinitramfs -l. Returns non-zero if neither is available.
_list_initramfs() {
    local initrd="$1"
    if command -v lsinitramfs >/dev/null 2>&1; then
        lsinitramfs "$initrd"
    elif command -v unmkinitramfs >/dev/null 2>&1; then
        unmkinitramfs -l "$initrd"
    else
        return 1
    fi
}

# initramfs_contains_casper <initrd> [matches-out]: 0 if the
# initrd contains casper boot logic, 1 if it is clean, 2 when it
# cannot be listed at all. Exactly one listing pass: the listing
# is written to a temp file and grepped there, so the caller can
# report the matches (via matches-out, when given) without
# listing the image a second time.
initramfs_contains_casper() {
    local initrd="$1" matches_out="${2:-}"
    [ -f "$initrd" ] || return 2
    local tmp
    tmp="$(mktemp)" || return 2
    if ! _list_initramfs "$initrd" >"$tmp" 2>/dev/null; then
        rm -f "$tmp"
        return 2
    fi
    if grep -Eq "$CASPER_BOOT_PATH_RE" "$tmp"; then
        if [ -n "$matches_out" ]; then
            grep -E "$CASPER_BOOT_PATH_RE" "$tmp" >"$matches_out" || true
        fi
        rm -f "$tmp"
        return 0
    fi
    rm -f "$tmp"
    return 1
}

main() {
    [ $# -ge 1 ] || { log "usage: $0 <target-root>" >&2; return 2; }
    local target="$1"
    [ -d "$target" ] || { log "target root is not a directory: $target" >&2; return 2; }
    command -v lsinitramfs >/dev/null 2>&1 || command -v unmkinitramfs >/dev/null 2>&1 || {
        log "ERROR: neither lsinitramfs nor unmkinitramfs is available; cannot gate the initrd" >&2
        return 1
    }
    local found=0
    local initrd rc matches
    matches="$(mktemp)" || { log "ERROR: cannot create temp file" >&2; return 2; }
    for initrd in "$target"/boot/initrd.img-*; do
        [ -e "$initrd" ] || continue
        found=1
        : >"$matches"
        initramfs_contains_casper "$initrd" "$matches"
        rc=$?
        if [ "$rc" -eq 0 ]; then
            log "ERROR: $initrd contains casper boot logic" >&2
            cat "$matches" >&2 || true
            rm -f "$matches"
            return 1
        elif [ "$rc" -eq 2 ]; then
            log "ERROR: cannot list $initrd" >&2
            rm -f "$matches"
            return 1
        fi
        log "clean: $initrd"
    done
    rm -f "$matches"
    if [ "$found" -eq 0 ]; then
        log "ERROR: no initrd found in $target/boot" >&2
        return 1
    fi
    log "initrd gate passed"
    return 0
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    main "$@"
fi
