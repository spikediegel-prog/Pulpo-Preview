#!/bin/bash
# install-cc-deb.sh — install the signed Control Center release .deb
# into the installed system (Calamares shellprocess@install-cc-deb,
# dontChroot: true), with $1 = the target root mount point
# (${ROOT}). Runs in the LIVE session; the script chroots into the
# target itself to run dpkg, so maintainer scripts run against the
# target.
#
# Why this step exists: the live image carries the Control Center
# as files extracted with dpkg-deb -x (no maintainer scripts, so
# extraction is exact) -- which means the installed system, copied
# from the squashfs, has the Control Center as loose files with no
# dpkg record, no version, and no signature verification. The
# Hyper-V run proved it: dpkg -l showed no pulpo packages on the
# installed system, so nothing on disk could say which signed
# preview was running. This step installs the signed release .deb
# into the target, so the installed system carries a verifiable
# signed build: a version record, an upgrade path, and a dpkg
# owner for every Control Center file.
#
# What it installs: the release bundle the ISO build copies into
# the live image at /usr/share/pulpo-installer/control-center/ --
# the signed Control Center .deb, its release statement
# (release.json), the detached GPG signature (release.json.asc),
# the publisher public key (publisher.gpg), and the Control
# Center's own ubuntu_release.py + check_ubuntu_deb.py. Plus the
# dependency .debs the build unpacked with dpkg-deb -x (python3-tk,
# libxcb-cursor0 and their closure): those exist in the target as
# files but are not registered in dpkg status, so a bare
# `dpkg -i` of the Control Center .deb would fail on unmet
# dependencies. This step installs the whole bundle, so the
# target's dpkg state is accurate for every package.
#
# Verification, before any install: the step calls the Control
# Center's own ubuntu_release.py verify -- the same function that
# verified preview.48 on the dev VM. It checks the statement's
# version and source revision against the values independently
# selected below (pinned in this script, not read from the
# statement), the .deb's name, size and SHA-256 against the
# statement, the detached GPG signature against the publisher key
# (full fingerprint required), the signature time against the
# statement lifetime, and the .deb itself with the Debian
# validator. The statement is time-bounded: preview.48's
# statement expires Wed 2026-11-18 15:00:51 MST, and verify
# fails after that (now >= expires_at). That is fail-closed and
# correct -- an expired release must not install -- but it means
# this ISO's Control Center install has a shelf life, and a
# later build needs a fresh signed release.
#
# Install order: the .debs are installed with one `dpkg -i`
# followed by `dpkg --configure -a`. The single dpkg -i may exit
# non-zero on ordering alone (a package installed before its
# dependency is unpacked is left unconfigured); that is expected
# and not a failure. The --configure -a that follows must exit
# 0, and the final check must show every bundle package as
# "install ok installed" -- anything less fails the install
# loudly, so Calamares marks it FAILED. An installed system
# with an unverified or half-installed Control Center is worse
# than a failed install.
#
# Failure modes (loud where it matters, never silent):
#   - Bundle, statement, signature, key or verify scripts
#     missing: fail. The build gates on them; their absence
#     here means the image is not the one the build produced.
#   - Verification fails (bad hash, bad signature, wrong
#     version/revision, expired statement): fail. Never install
#     an unverified release.
#   - dpkg -i or dpkg --configure -a fails, or any bundle
#     package is not "install ok installed" afterwards: fail.
#   - /proc, /sys or /dev are not mounted in the target
#     (Calamares' mount step normally bind-mounts them for the
#     exec phase): bind-mount the missing ones before the chroot
#     and unmount exactly what this script mounted afterwards --
#     never unmount mounts Calamares owns.
#
# For testing: the script is safe to source -- its side effects
# live in main(), so tests can source it and call bundle_debs /
# verify_release / install_debs directly on a fake bundle and
# target root (no chroot, no root needed for the listing and
# verification-failure paths). The chroot + dpkg part is covered
# by static assertions (the dpkg invocations) and by the install
# test.
set -u

# The signed release this step installs, independently selected
# (pinned here, not read from the statement -- verify() checks
# the statement against these values). Update all three together
# when the release changes; the tests pin them.
EXPECTED_VERSION="0.1.0~ubuntu.preview.48+e3.2077631"
EXPECTED_REVISION="20776311d4c39c1f6ddebe08ddc5880cb2a9c131"
PUBLISHER_FINGERPRINT="19B555C6055FD7B64B848DA67F7B8449ED6FEB20"
CC_DEB_NAME="pulpo-control-center_0.1.0~ubuntu.preview.48+e3.2077631_amd64.deb"

# Release bundle, as copied into the live image by the ISO build.
BUNDLE_DIR="/usr/share/pulpo-installer/control-center"
# Where the bundle .debs are staged inside the target for the install.
TARGET_STAGING="/tmp/pulpo-cc-install"

LOG_PREFIX="[install-cc-deb]"

log() {
    echo "$LOG_PREFIX $*"
}

# bundle_debs <bundle-dir>: print every .deb in the bundle, one
# per line, sorted. Empty output when there are none.
bundle_debs() {
    local bundle="$1"
    [ -d "$bundle" ] || return 0
    local f
    for f in "$bundle"/*.deb; do
        [ -e "$f" ] || continue
        printf '%s\n' "$f"
    done
}

# bundle_packages <bundle-dir>: print the package name of every
# .deb in the bundle, one per line (from each .deb's control
# data, not from the filename).
bundle_packages() {
    local bundle="$1"
    local f
    while IFS= read -r f; do
        [ -n "$f" ] || continue
        dpkg-deb -f "$f" Package 2>/dev/null || return 1
    done <<EOF
$(bundle_debs "$bundle")
EOF
}

# verify_release <bundle-dir>: verify the signed Control Center
# release in the bundle with the Control Center's own
# ubuntu_release.py verify. Returns non-zero (and logs why) when
# any bundle file is missing or the verification fails.
verify_release() {
    local bundle="$1"
    local deb="$bundle/$CC_DEB_NAME"
    local manifest="$bundle/release.json"
    local signature="$bundle/release.json.asc"
    local key="$bundle/publisher.gpg"
    local script="$bundle/ubuntu_release.py"
    for f in "$deb" "$manifest" "$signature" "$key" "$script" "$bundle/check_ubuntu_deb.py"; do
        if [ ! -f "$f" ]; then
            log "release bundle file missing: $f"
            return 1
        fi
    done
    log "verifying $CC_DEB_NAME (version $EXPECTED_VERSION)"
    local out rc=0
    out=$(python3 "$script" verify \
        --artifact "$deb" \
        --version "$EXPECTED_VERSION" \
        --revision "$EXPECTED_REVISION" \
        --manifest "$manifest" \
        --signature "$signature" \
        --public-key "$key" \
        --fingerprint "$PUBLISHER_FINGERPRINT" 2>&1) || rc=1
    if [ "$rc" -ne 0 ]; then
        log "release verification FAILED: $out"
        return 1
    fi
    case "$out" in
        *'"verified": true'*) ;;
        *)
            log "release verification did not report verified: $out"
            return 1
            ;;
    esac
    log "release verified: $EXPECTED_VERSION ($EXPECTED_REVISION)"
    return 0
}

# _mount_if_missing <target> <what> <where>: bind-mount the live
# system's <what> onto <target>/<where> if nothing is mounted
# there yet. Prints "mounted" when it mounted, nothing otherwise.
_mounted_here=""
_mount_if_missing() {
    local target="$1" what="$2" where="$3"
    if mountpoint -q "$target/$where" 2>/dev/null; then
        return 0
    fi
    mount --bind "$what" "$target/$where" || return 1
    _mounted_here="$_mounted_here $where"
    return 0
}

# _unmount_ours <target>: unmount, in reverse order, exactly the
# mounts _mount_if_missing made. Never touches mounts Calamares
# owns.
_unmount_ours() {
    local target="$1"
    local where
    local reversed=""
    for where in $_mounted_here; do
        reversed="$where $reversed"
    done
    for where in $reversed; do
        umount "$target/$where" 2>/dev/null || true
    done
    _mounted_here=""
}

# _package_installed <target> <package>: 0 if the package is
# recorded "install ok installed" in the target's dpkg status.
_package_installed() {
    local target="$1" pkg="$2"
    chroot "$target" dpkg -s "$pkg" 2>/dev/null | grep -q '^Status: install ok installed$'
}

# install_debs <target> <bundle-dir>: install every bundle .deb
# into the target with dpkg, then verify every bundle package is
# "install ok installed". Returns non-zero on failure.
install_debs() {
    local target="$1" bundle="$2"
    local staging="$target$TARGET_STAGING"
    mkdir -p "$staging" || { log "cannot create staging dir in target: $TARGET_STAGING" >&2; return 1; }
    local f
    while IFS= read -r f; do
        [ -n "$f" ] || continue
        cp "$f" "$staging/" || { log "cannot stage $f in target" >&2; rm -rf "$staging"; return 1; }
    done <<EOF
$(bundle_debs "$bundle")
EOF
    _mount_if_missing "$target" /proc proc || { rm -rf "$staging"; return 1; }
    _mount_if_missing "$target" /sys sys || { _unmount_ours "$target"; rm -rf "$staging"; return 1; }
    _mount_if_missing "$target" /dev dev || { _unmount_ours "$target"; rm -rf "$staging"; return 1; }
    local rc=0
    log "installing bundle .debs into the target"
    chroot "$target" dpkg -i "$TARGET_STAGING"/*.deb || {
        log "dpkg -i exited non-zero (may be install order; configuring next)"
        rc=1
    }
    chroot "$target" dpkg --configure -a || {
        log "ERROR: dpkg --configure -a failed in the target" >&2
        _unmount_ours "$target"
        rm -rf "$staging"
        return 1
    }
    local pkg
    while IFS= read -r pkg; do
        [ -n "$pkg" ] || continue
        if ! _package_installed "$target" "$pkg"; then
            log "ERROR: package not installed in target after configure: $pkg" >&2
            _unmount_ours "$target"
            rm -rf "$staging"
            return 1
        fi
    done <<EOF
$(bundle_packages "$bundle")
EOF
    _unmount_ours "$target"
    rm -rf "$staging"
    if [ "$rc" -ne 0 ]; then
        log "dpkg -i reported ordering issues but every bundle package is installed after configure"
    fi
    log "installed bundle packages into the target"
    return 0
}

main() {
    [ $# -ge 1 ] || { log "usage: $0 <target-root>" >&2; return 2; }
    local target="$1"
    [ -d "$target" ] || { log "target root is not a directory: $target" >&2; return 2; }
    verify_release "$BUNDLE_DIR" || {
        log "ERROR: signed release verification failed; refusing to install" >&2
        return 1
    }
    install_debs "$target" "$BUNDLE_DIR" || {
        log "ERROR: failed to install the signed release into the target" >&2
        return 1
    }
    log "signed Control Center $EXPECTED_VERSION installed into the target"
    return 0
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    main "$@"
fi
