#!/bin/bash
# verify-clean-iso.sh — fail-closed check that a built ISO is
# clean (release) or dev, and nothing leaked across the line.
#
# Usage:
#   installer/verify-clean-iso.sh [--dev|--clean] [--iso PATH | --squashfs PATH]
#       [--list-file FILE] [--xorriso PATH] [--ownership-map FILE]
#       [--rootfs DIR] [--repo PATH]
#     --dev        expect a dev build (marker + dev files present)
#     --clean      expect a clean release build (default: no dev
#                  artefacts at all)
#     --iso        ISO to check (filesystem.squashfs is extracted
#                  with xorriso, then listed with unsquashfs -l)
#     --squashfs   squashfs file to check directly (what
#                  build-iso.sh step 8b passes: the squashfs that
#                  was just packed, before it is mapped into the
#                  ISO — no xorriso needed)
#     --list-file  test hook: read a pre-captured `unsquashfs -l`
#                  listing instead of running unsquashfs (the unit
#                  tests use it; the build never does)
#     --xorriso    xorriso binary (default: xorriso on PATH)
#     --ownership-map  run installer/ownership-gate.py against
#                  the squashfs with this map (step 8b passes the
#                  build's merge-plan ownership.txt); with
#                  --rootfs, the gate also collapses hardlink
#                  groups the way step 5 does
#     --repo       repo root (default: the parent of this script's
#                  directory); used to find ownership-gate.py
#
# What it asserts, on the built squashfs listing — in BOTH modes:
#   - no xrdp / sshd binaries unpacked in the live rootfs
#     (usr/sbin/sshd, usr/sbin/xrdp, usr/sbin/xrdp-sesman,
#     usr/bin/xrdp). The dev tools ship as .debs in the dev
#     bundle and are installed into the TARGET at install time;
#     they must never be unpacked into the live session, not
#     even on a dev build. (The base image carries an
#     sshd-keygen@.service.d config fragment; that is not a
#     binary and does not trip this check — the paths are
#     matched exactly, not by substring.)
#   - no authorized_keys anywhere under /etc/skel. The SSH key
#     is installed into the TARGET user's home at install time
#     by dev-setup.sh, never baked into skel, not even on a
#     dev build.
#   - the Control Center release bundle survived into the image:
#     release.json, publisher.gpg, ubuntu_release.py,
#     check_ubuntu_deb.py, and at least one .deb under
#     usr/share/pulpo-installer/control-center/. (The exact
#     bundle-count gate lives in build-iso.sh step 4f; this is
#     the survival check that the squashfs the ISO carries is
#     the one the build gated.)
#   - settings.conf exists and runs the pulpo-config step.
#
# Clean mode additionally asserts:
#   - no DEV-BUILD marker, no dev-setup.sh, no dev-bundle/,
#     no dev-customer-config.json, no settings-dev.conf;
#   - settings.conf does not reference dev-setup.
#
# Dev mode (--dev) asserts the inverse:
#   - DEV-BUILD marker present (and, when the squashfs itself
#     is available, its content names a dev build);
#   - dev-setup.sh, settings-dev.conf and dev-customer-config.json
#     present; dev-bundle/ holds .debs including xrdp,
#     openssh-server and tailscale;
#   - settings.conf references shellprocess@dev-setup.
#
# With --ownership-map it also runs ownership-gate.py (the step-5
# gate) against the squashfs, so step 8b re-proves the exact
# squashfs the ISO carries passed the ownership gate.
#
# Fail-closed: any hit, any missing file the mode requires, any
# unreadable input, or a failing ownership gate exits 1 and
# prints every failure. Exit 0 only when every check passed.
# The script never modifies the ISO or the squashfs.
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="${REPO_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
MODE="clean"
ISO=""
SQUASHFS=""
LIST_FILE=""
XORRISO="xorriso"
OWNERSHIP_MAP=""
ROOTFS=""

while [ $# -gt 0 ]; do
  case "$1" in
    --dev) MODE="dev"; shift;;
    --clean) MODE="clean"; shift;;
    --iso) ISO="$2"; shift 2;;
    --squashfs) SQUASHFS="$2"; shift 2;;
    --list-file) LIST_FILE="$2"; shift 2;;
    --xorriso) XORRISO="$2"; shift 2;;
    --ownership-map) OWNERSHIP_MAP="$2"; shift 2;;
    --rootfs) ROOTFS="$2"; shift 2;;
    --repo) REPO_ROOT="$2"; shift 2;;
    *) echo "unknown option: $1" >&2; exit 2;;
  esac
done

FAILURES=""

fail() {
    echo "FAIL: $*"
    FAILURES="$FAILURES
$*"
}

# _has <path>: 0 when the exact path is in the listing.
_has() {
    grep -qxF "$1" "$LISTING" 2>/dev/null
}

# _has_prefix <prefix>: 0 when any listing path starts with the prefix.
_has_prefix() {
    grep -q "^$(printf '%s' "$1" | sed 's/[.[\*^$]/\\&/g')" "$LISTING" 2>/dev/null
}

# --- inputs ---------------------------------------------------------------
if [ -n "$LIST_FILE" ]; then
    [ -f "$LIST_FILE" ] || { echo "list file missing: $LIST_FILE" >&2; exit 2; }
    LISTING="$LIST_FILE"
    # Normalise: unsquashfs -l lines are "squashfs-root/<path>".
    LISTING_NORM="$(mktemp)"
    sed 's|^squashfs-root/||' "$LIST_FILE" > "$LISTING_NORM"
    LISTING="$LISTING_NORM"
    trap 'rm -f "$LISTING_NORM"' EXIT
elif [ -n "$SQUASHFS" ]; then
    [ -f "$SQUASHFS" ] || { echo "squashfs missing: $SQUASHFS" >&2; exit 2; }
    command -v unsquashfs >/dev/null 2>&1 || { echo "missing: unsquashfs" >&2; exit 2; }
    LISTING="$(mktemp)"
    trap 'rm -f "$LISTING"' EXIT
    unsquashfs -l "$SQUASHFS" 2>/dev/null | sed 's|^squashfs-root/||' > "$LISTING" \
        || { echo "cannot list squashfs: $SQUASHFS" >&2; exit 1; }
    [ -s "$LISTING" ] || { echo "empty squashfs listing: $SQUASHFS" >&2; exit 1; }
elif [ -n "$ISO" ]; then
    [ -f "$ISO" ] || { echo "ISO missing: $ISO" >&2; exit 2; }
    command -v unsquashfs >/dev/null 2>&1 || { echo "missing: unsquashfs" >&2; exit 2; }
    [ -x "$XORRISO" ] || command -v "$XORRISO" >/dev/null 2>&1 \
        || { echo "missing: xorriso ($XORRISO)" >&2; exit 2; }
    WORK="$(mktemp -d)"
    trap 'rm -rf "$WORK"' EXIT
    "$XORRISO" -osirrox on -indev "$ISO" -extract /casper/filesystem.squashfs "$WORK" \
        > "$WORK/xorriso-extract.log" 2>&1 \
        || { echo "cannot extract filesystem.squashfs from $ISO (see $WORK/xorriso-extract.log)" >&2; exit 1; }
    SQUASHFS="$WORK/filesystem.squashfs"
    [ -f "$SQUASHFS" ] || { echo "filesystem.squashfs not in ISO: $ISO" >&2; exit 1; }
    LISTING="$(mktemp)"
    trap 'rm -rf "$WORK"; rm -f "$LISTING"' EXIT
    unsquashfs -l "$SQUASHFS" 2>/dev/null | sed 's|^squashfs-root/||' > "$LISTING" \
        || { echo "cannot list squashfs from $ISO" >&2; exit 1; }
    [ -s "$LISTING" ] || { echo "empty squashfs listing from $ISO" >&2; exit 1; }
else
    echo "usage: $0 [--dev|--clean] [--iso PATH | --squashfs PATH | --list-file FILE]" >&2
    exit 2
fi

# --- common checks (both modes) -------------------------------------------
# No remote-access binaries unpacked in the live rootfs, even on a
# dev build: the dev tools ship as .debs and are installed into
# the target at install time. Exact paths only — the base image
# carries an sshd-keygen@.service.d fragment, which is not a
# binary and must not trip this check.
for bin in usr/sbin/sshd usr/sbin/xrdp usr/sbin/xrdp-sesman usr/bin/xrdp; do
    if _has "$bin"; then
        fail "remote-access binary unpacked in the live rootfs: $bin"
    fi
done
# No SSH key baked into skel, in either mode: dev-setup.sh
# installs the key into the TARGET user's home at install time.
if _has_prefix "etc/skel/.ssh/"; then
    fail "authorized_keys material under /etc/skel (SSH key baked into the image)"
fi
if grep -q "^etc/skel/.*/authorized_keys$" "$LISTING" 2>/dev/null; then
    fail "authorized_keys under /etc/skel (SSH key baked into the image)"
fi
# The Control Center release bundle must have survived into the
# image (the exact count gate is build-iso.sh step 4f; this is
# the survival check on the squashfs the ISO carries).
for f in usr/share/pulpo-installer/control-center/release.json \
         usr/share/pulpo-installer/control-center/publisher.gpg \
         usr/share/pulpo-installer/control-center/ubuntu_release.py \
         usr/share/pulpo-installer/control-center/check_ubuntu_deb.py; do
    _has "$f" || fail "Control Center bundle file missing from the image: $f"
done
if ! grep -q "^usr/share/pulpo-installer/control-center/[^/]*\.deb$" "$LISTING" 2>/dev/null; then
    fail "Control Center bundle holds no .deb in the image"
fi
# settings.conf must exist and run the config carry-through.
if _has "etc/calamares/settings.conf"; then
    if [ -n "$SQUASHFS" ] && [ -f "$SQUASHFS" ]; then
        SETTINGS_TMP="$(mktemp -d)"
        if unsquashfs -ignore-errors -d "$SETTINGS_TMP" "$SQUASHFS" \
                etc/calamares/settings.conf > /dev/null 2>&1; then
            grep -q "shellprocess@pulpo-config" \
                "$SETTINGS_TMP/etc/calamares/settings.conf" \
                || fail "settings.conf does not run shellprocess@pulpo-config"
            if [ "$MODE" = "clean" ]; then
                grep -q "dev-setup" "$SETTINGS_TMP/etc/calamares/settings.conf" \
                    && fail "settings.conf references dev-setup on a clean build"
            else
                grep -q "shellprocess@dev-setup" \
                    "$SETTINGS_TMP/etc/calamares/settings.conf" \
                    || fail "settings.conf does not run shellprocess@dev-setup on a dev build"
            fi
        else
            fail "cannot extract etc/calamares/settings.conf from the squashfs"
        fi
        rm -rf "$SETTINGS_TMP"
    fi
else
    fail "settings.conf missing from the image"
fi

# --- mode checks ------------------------------------------------------------
DEV_MARKER="usr/share/pulpo-installer/DEV-BUILD"
DEV_FILES=(
    "usr/share/pulpo-installer/calamares/dev-setup.sh"
    "usr/share/pulpo-installer/dev-customer-config.json"
    "etc/calamares/settings-dev.conf"
)
if [ "$MODE" = "clean" ]; then
    _has "$DEV_MARKER" && fail "DEV-BUILD marker present on a clean build"
    for f in "${DEV_FILES[@]}"; do
        _has "$f" && fail "dev file present on a clean build: $f"
    done
    _has_prefix "usr/share/pulpo-installer/dev-bundle/" \
        && fail "dev-bundle/ present on a clean build"
else
    _has "$DEV_MARKER" || fail "DEV-BUILD marker missing on a dev build"
    for f in "${DEV_FILES[@]}"; do
        _has "$f" || fail "dev file missing on a dev build: $f"
    done
    if _has_prefix "usr/share/pulpo-installer/dev-bundle/"; then
        for pkg in xrdp openssh-server tailscale; do
            grep -q "^usr/share/pulpo-installer/dev-bundle/${pkg}_[^/]*\.deb$" "$LISTING" 2>/dev/null \
                || fail "dev-bundle/ is missing the $pkg .deb"
        done
    else
        fail "dev-bundle/ missing on a dev build"
    fi
    # The marker must name a dev build, when the squashfs itself
    # is available to read it from.
    if [ -n "$SQUASHFS" ] && [ -f "$SQUASHFS" ] && _has "$DEV_MARKER"; then
        MARKER_TMP="$(mktemp -d)"
        if unsquashfs -ignore-errors -d "$MARKER_TMP" "$SQUASHFS" \
                "$DEV_MARKER" > /dev/null 2>&1; then
            grep -qi "dev" "$MARKER_TMP/$DEV_MARKER" \
                || fail "DEV-BUILD marker does not name a dev build"
        else
            fail "cannot extract the DEV-BUILD marker from the squashfs"
        fi
        rm -rf "$MARKER_TMP"
    fi
fi

# --- ownership gate (step 5, re-run on the squashfs the ISO carries) ------
if [ -n "$OWNERSHIP_MAP" ]; then
    if [ -z "$SQUASHFS" ] || [ ! -f "$SQUASHFS" ]; then
        fail "ownership gate requested but no squashfs available (--list-file cannot run it)"
    else
        [ -f "$OWNERSHIP_MAP" ] || fail "ownership map missing: $OWNERSHIP_MAP"
        GATE="$REPO_ROOT/installer/ownership-gate.py"
        [ -f "$GATE" ] || fail "ownership-gate.py missing: $GATE"
        GATE_ARGS=("$SQUASHFS" "$OWNERSHIP_MAP")
        [ -n "$ROOTFS" ] && GATE_ARGS+=(--rootfs "$ROOTFS")
        GATE_LOG="$(mktemp)"
        if ! python3 "$GATE" "${GATE_ARGS[@]}" > "$GATE_LOG" 2>&1; then
            fail "ownership gate failed on the built squashfs (see $GATE_LOG)"
        else
            rm -f "$GATE_LOG"
        fi
    fi
fi

if [ -n "$FAILURES" ]; then
    echo "verify-clean-iso: FAIL ($MODE) — $(printf '%s' "$FAILURES" | grep -c . ) failure(s)"
    exit 1
fi
echo "verify-clean-iso: PASS ($MODE)"
exit 0
