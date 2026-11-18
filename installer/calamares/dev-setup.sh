#!/bin/bash
# dev-setup.sh — dev/test-only Calamares step for the --dev ISO.
#
# Runs in the LIVE session as root (Calamares shellprocess@dev-setup,
# dontChroot: true), with $1 = the target root mount point
# (${ROOT}). Only runs on a dev build: it refuses to do anything
# unless the DEV-BUILD marker exists in the live image
# (/usr/share/pulpo-installer/DEV-BUILD, stamped by
# installer/build-iso.sh --dev). A clean (release) image has no
# marker, no dev bundle, and no dev-setup instance in its
# settings.conf, so this step cannot run there even by mistake.
#
# What it does, in order:
#   1. verifies the dev bundle holds the xrdp, openssh-server and
#      tailscale .debs (fetched by the build, never unpacked into
#      the live image — they are installed here, into the target,
#      with dpkg -i so maintainer scripts run);
#   2. installs the whole bundle into the target (dpkg -i, then
#      dpkg --configure -a, then every bundle package must read
#      "install ok installed" — the install-cc-deb.sh pattern);
#   3. enables xrdp and ssh in the target (systemctl enable in a
#      chroot; the .wants symlinks are verified afterwards — the
#      .deb postinsts normally create them already, the explicit
#      enable is belt-and-braces);
#   4. installs the corrected dev customer config through the
#      SAME import path as pulpo-config-install.sh (it calls that
#      script with PULPO_LIVE_CONFIG_GLOB pointed at the baked
#      dev config, so time, storage and network are applied from
#      the same document by the same code). A live Guided Setup
#      config, if one exists, is overridden by the dev config —
#      the dev ISO is a test artifact with a known-good config,
#      and the override is logged loudly;
#   5. writes the hatch SSH PUBLIC key to the new user's
#      ~/.ssh/authorized_keys (0600, owned by the user) so the
#      installed system is reachable over SSH for testing;
#   6. creates /var/lib/pulpo/evidence (0755, owned by the user),
#      the local evidence dir the dev config points at.
#
# NEVER baked in, here or by the build: no Tailscale auth key or
# any credential, no password, no installer account, no private
# key. The SSH key below is the hatch PUBLIC key only (verified
# against the dev VM's ~/.ssh/authorized_keys, 2026-11-17); the
# private half never leaves the build machine. Tailscale is
# installed but NOT joined: `tailscale up` on the installed
# system still needs a human-supplied auth key. XRDP and SSH are
# reachable only on whatever network the installed system is on;
# the dev ISO is a test artifact, never published.
#
# The step's log: log() writes every line to stdout (Calamares
# shows it in the GUI Details box) AND to
# $target/var/log/pulpo-installer/dev-setup.log, inside the
# target so it survives on the installed system.
#
# Failure modes (loud where it matters, never silent):
#   - No DEV-BUILD marker: fail. This step must never run on a
#     clean image; a missing marker means the image is not the
#     one the dev build produced.
#   - Bundle, dev config, or config-install script missing, or
#     any of xrdp / openssh-server / tailscale absent from the
#     bundle: fail. The build gates on them; their absence here
#     means the image is not the one the build produced.
#   - dpkg -i or dpkg --configure -a fails, or any bundle
#     package is not "install ok installed" afterwards: fail.
#   - systemctl enable fails AND the .wants symlinks are
#     missing afterwards: fail.
#   - Dev config import fails: fail. A dev config that cannot
#     be applied must not be silently dropped.
#   - An authorized_keys already exists in the target user's
#     ~/.ssh: fail. The target is fresh from unpackfs and skel
#     carries no .ssh; an existing file means something else
#     already seeded a key, and appending blindly would hide it.
#   - No UID-1000 user in the target: fail. The users module
#     must have created the first user before this step runs.
#   - /proc, /sys or /dev are not mounted in the target: bind-
#     mount the missing ones before the chroot and unmount
#     exactly what this script mounted afterwards — never
#     unmount mounts Calamares owns (the install-cc-deb.sh
#     pattern).
#
# For testing: PULPO_DEV_MARKER, PULPO_DEV_BUNDLE_DIR,
# PULPO_DEV_CONFIG and PULPO_DEV_PUBKEY override the live-image
# paths and the key; PULPO_CONFIG_INSTALL_SCRIPT overrides the
# pulpo-config-install.sh path (tests point it at a stub);
# PULPO_DEV_IMPORT_USER overrides the user the config import
# runs as when this script runs as root (default `ubuntu`;
# tests set it to the current user). The script is safe to
# source — its side effects live in main(), so tests can source
# it and call require_dev_marker / bundle_debs / install_ssh_key
# / create_evidence_dir directly on a fake bundle and target
# root (no chroot, no root needed for those paths). The chroot +
# dpkg part is covered by static assertions and by the install
# test.
set -u

# The hatch SSH PUBLIC key only — verified against the dev VM's
# ~/.ssh/authorized_keys (2026-11-17). The private half is never
# in this repo, never in the image, never in the bundle.
HATCH_PUBLIC_KEY="${PULPO_DEV_PUBKEY:-ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAII6I1QynbsUwGdsGFu2pvhsTK22WHGeUr19H/eNF3RDk hatch}"

# Dev artefacts, as copied into the live image by the ISO build.
MARKER="${PULPO_DEV_MARKER:-/usr/share/pulpo-installer/DEV-BUILD}"
BUNDLE_DIR="${PULPO_DEV_BUNDLE_DIR:-/usr/share/pulpo-installer/dev-bundle}"
DEV_CONFIG="${PULPO_DEV_CONFIG:-/usr/share/pulpo-installer/dev-customer-config.json}"
CONFIG_INSTALL="${PULPO_CONFIG_INSTALL_SCRIPT:-/usr/share/pulpo-installer/calamares/pulpo-config-install.sh}"
# Where the bundle .debs are staged inside the target for the install.
TARGET_STAGING="/tmp/pulpo-dev-install"

# The user the config import runs as (passed through to
# pulpo-config-install.sh as PULPO_IMPORT_USER). Calamares runs
# this script as root; the import drops to the live session's
# non-root user (default `ubuntu`, uid 1000) for the same reason
# as in pulpo-config-install.sh: the Control Center's
# scratch-root guard refuses root for any --root != /.
IMPORT_USER="${PULPO_DEV_IMPORT_USER:-ubuntu}"

# Whether this script is running as root (Calamares) or already
# non-root (tests / dev). Under fakeroot, id -u reports 0.
AS_ROOT=0
[ "$(id -u)" -eq 0 ] && AS_ROOT=1

LOG_PREFIX="[dev-setup]"

# The step log file, inside the target so it survives on the
# installed system. Set by main() once the target root is
# known; empty until then (tests and direct function calls
# leave it unset, and log() just prints to stdout).
LOG_FILE=""

# log <message...>: print a step log line to stdout, and append
# it to the step log file when one is set.
log() {
    echo "$LOG_PREFIX $*"
    [ -n "$LOG_FILE" ] && echo "$LOG_PREFIX $*" >> "$LOG_FILE"
}

# _tee: pass stdin through to stdout (so Calamares' Details box
# still shows it) and append it to the step log file when one is
# set. Used for the dpkg output, whose raw lines are the
# diagnosis when an install fails.
_tee() {
    if [ -n "$LOG_FILE" ]; then
        tee -a "$LOG_FILE"
    else
        cat
    fi
}

# require_dev_marker: 0 when the DEV-BUILD marker exists in the
# live image; non-zero (and logs why) otherwise. The marker is
# the proof this is a dev build — without it this step must not
# run, and must say so loudly.
require_dev_marker() {
    if [ -f "$MARKER" ]; then
        log "dev build marker present: $MARKER"
        return 0
    fi
    log "ERROR: no dev build marker ($MARKER) — refusing to run" >&2
    log "This step only runs on a --dev ISO; a clean image has no marker" >&2
    return 1
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

# check_bundle <bundle-dir>: the bundle must hold the three dev
# packages (xrdp, openssh-server, tailscale) as .debs. Returns
# non-zero (and logs why) when any is missing.
check_bundle() {
    local bundle="$1"
    [ -d "$bundle" ] || { log "dev bundle missing: $bundle" >&2; return 1; }
    local pkg found
    for pkg in xrdp openssh-server tailscale; do
        found=$(ls "$bundle/${pkg}_"*.deb 2>/dev/null | head -1 || true)
        if [ -z "$found" ]; then
            log "dev bundle is missing the $pkg .deb" >&2
            return 1
        fi
        log "dev bundle holds: $(basename "$found")"
    done
    return 0
}

# _mount_if_missing <target> <what> <where>: bind-mount the live
# system's <what> onto <target>/<where> if nothing is mounted
# there yet. Prints nothing; records mounts in _mounted_here.
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

# install_dev_debs <target> <bundle-dir>: install every bundle
# .deb into the target with dpkg, then verify every bundle
# package is "install ok installed". Returns non-zero on failure.
install_dev_debs() {
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
    log "installing dev bundle .debs into the target"
    # The glob must expand inside the chroot, not on the host:
    # the host has no $TARGET_STAGING, so the host shell passes
    # the literal pattern to dpkg (the install-cc-deb.sh run-15
    # lesson). The glob stays literal inside double quotes and
    # the chroot's sh expands it.
    chroot "$target" sh -c "dpkg -i $TARGET_STAGING/*.deb" 2>&1 | _tee
    if [ "${PIPESTATUS[0]}" -ne 0 ]; then
        log "dpkg -i exited non-zero (may be install order; configuring next)"
        rc=1
    fi
    chroot "$target" dpkg --configure -a 2>&1 | _tee
    if [ "${PIPESTATUS[0]}" -ne 0 ]; then
        log "ERROR: dpkg --configure -a failed in the target" >&2
        _unmount_ours "$target"
        rm -rf "$staging"
        return 1
    fi
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
    log "installed dev bundle packages into the target"
    return 0
}

# enable_dev_services <target>: enable xrdp and ssh in the
# target (systemctl enable in a chroot, which only writes the
# .wants symlinks — no running systemd is needed). The .deb
# postinsts normally create the symlinks already; the explicit
# enable is belt-and-braces, and the symlinks are the gate:
# enable may fail while the symlinks already exist, which is
# fine — only missing symlinks afterwards fail the step.
enable_dev_services() {
    local target="$1"
    _mount_if_missing "$target" /proc proc || return 1
    _mount_if_missing "$target" /sys sys || { _unmount_ours "$target"; return 1; }
    _mount_if_missing "$target" /dev dev || { _unmount_ours "$target"; return 1; }
    chroot "$target" systemctl enable xrdp ssh 2>&1 | _tee || true
    _unmount_ours "$target"
    local svc link
    for svc in xrdp ssh; do
        link="$target/etc/systemd/system/multi-user.target.wants/$svc.service"
        if [ -L "$link" ] || [ -e "$link" ]; then
            log "service enabled in target: $svc"
        else
            log "ERROR: $svc not enabled in target ($link missing)" >&2
            return 1
        fi
    done
    return 0
}

# install_dev_config <target>: install the baked dev customer
# config through the same import path as pulpo-config-install.sh
# — call that script with PULPO_LIVE_CONFIG_GLOB pointed at the
# dev config, so time, storage and network are applied from the
# same document by the same code. A live Guided Setup config, if
# one exists, is overridden by the dev config (logged loudly:
# the dev ISO is a test artifact with a known-good config).
install_dev_config() {
    local target="$1"
    [ -f "$DEV_CONFIG" ] || { log "dev customer config missing: $DEV_CONFIG" >&2; return 1; }
    [ -x "$CONFIG_INSTALL" ] || { log "config install script missing/not executable: $CONFIG_INSTALL" >&2; return 1; }
    local live
    # shellcheck disable=SC2086 (word splitting the glob is the point)
    for live in /home/*/.config/PulpoPreview/control-center-customer-config.json; do
        if [ -s "$live" ]; then
            log "WARNING: live Guided Setup config exists ($live); the dev config takes precedence on a dev build"
            break
        fi
    done
    log "installing dev customer config via pulpo-config-install.sh"
    env "PULPO_LIVE_CONFIG_GLOB=$DEV_CONFIG" "PULPO_IMPORT_USER=$IMPORT_USER" \
        "$CONFIG_INSTALL" "$target" 2>&1 | _tee
    # PIPESTATUS of the pipeline above: _tee is the last command,
    # so capture the config script's status from the pipe.
    if [ "${PIPESTATUS[0]}" -ne 0 ]; then
        log "ERROR: dev config import failed" >&2
        return 1
    fi
    log "dev customer config applied"
    return 0
}

# target_user <target>: print "name uid gid" of the target's
# first user (UID 1000, created by the users module). Empty
# output when there is none.
target_user() {
    local target="$1"
    awk -F: '$3 == 1000 {print $1, $3, $4; exit}' "$target/etc/passwd" 2>/dev/null || true
}

# install_ssh_key <target> <user> <uid> <gid>: write the hatch
# PUBLIC key to the new user's ~/.ssh/authorized_keys (0600,
# owned by the user). Fails loudly when an authorized_keys
# already exists — the target is fresh from unpackfs and skel
# carries no .ssh, so an existing file means something else
# already seeded a key.
install_ssh_key() {
    local target="$1" user="$2" uid="$3" gid="$4"
    local sshdir="$target/home/$user/.ssh"
    local authkeys="$sshdir/authorized_keys"
    if [ -e "$authkeys" ]; then
        log "ERROR: $authkeys already exists; refusing to add a key blindly" >&2
        return 1
    fi
    mkdir -p "$sshdir" || { log "cannot create $sshdir" >&2; return 1; }
    printf '%s\n' "$HATCH_PUBLIC_KEY" > "$authkeys" \
        || { log "cannot write $authkeys" >&2; return 1; }
    chmod 0700 "$sshdir"
    chmod 0600 "$authkeys"
    if [ "$AS_ROOT" -eq 1 ]; then
        chown "$uid:$gid" "$sshdir" "$authkeys" \
            || { log "cannot chown $sshdir" >&2; return 1; }
    fi
    log "SSH public key installed for $user (~/.ssh/authorized_keys, 0600)"
    return 0
}

# create_evidence_dir <target> <uid> <gid>: create
# /var/lib/pulpo/evidence (0755, owned by the user), the local
# evidence dir the dev config points at.
create_evidence_dir() {
    local target="$1" uid="$2" gid="$3"
    local dir="$target/var/lib/pulpo/evidence"
    mkdir -p "$dir" || { log "cannot create $dir" >&2; return 1; }
    chmod 0755 "$dir"
    if [ "$AS_ROOT" -eq 1 ]; then
        chown "$uid:$gid" "$dir" \
            || { log "cannot chown $dir" >&2; return 1; }
    fi
    log "evidence dir created: /var/lib/pulpo/evidence (0755)"
    return 0
}

main() {
    [ $# -ge 1 ] || { log "usage: $0 <target-root>" >&2; return 2; }
    local target="$1"
    [ -d "$target" ] || { log "target root is not a directory: $target" >&2; return 2; }
    # The step log lives inside the target so it survives on the
    # installed system. Set it before the marker check, so a
    # refusal is captured too.
    LOG_FILE="$target/var/log/pulpo-installer/dev-setup.log"
    mkdir -p "$(dirname "$LOG_FILE")" || { log "cannot create log dir in target" >&2; return 1; }
    require_dev_marker || {
        log "ERROR: refusing to run the dev setup on a non-dev image" >&2
        return 1
    }
    check_bundle "$BUNDLE_DIR" || {
        log "ERROR: dev bundle incomplete; refusing to install" >&2
        return 1
    }
    local user uid gid
    read -r user uid gid <<< "$(target_user "$target")"
    if [ -z "${user:-}" ]; then
        log "ERROR: no UID-1000 user in the target yet; the users module must run first" >&2
        return 1
    fi
    log "target user: $user ($uid:$gid)"
    install_dev_debs "$target" "$BUNDLE_DIR" || {
        log "ERROR: failed to install the dev bundle into the target" >&2
        return 1
    }
    enable_dev_services "$target" || {
        log "ERROR: failed to enable xrdp/ssh in the target" >&2
        return 1
    }
    install_dev_config "$target" || {
        log "ERROR: failed to install the dev customer config" >&2
        return 1
    }
    install_ssh_key "$target" "$user" "$uid" "$gid" || {
        log "ERROR: failed to install the SSH public key" >&2
        return 1
    }
    create_evidence_dir "$target" "$uid" "$gid" || {
        log "ERROR: failed to create the evidence dir" >&2
        return 1
    }
    log "dev setup complete: xrdp + openssh-server + tailscale installed, xrdp/ssh enabled, dev config applied, SSH key + evidence dir in place"
    log "NOTE: tailscale is installed but NOT joined — run 'tailscale up' with a human-supplied auth key. No credential is baked into this image."
    return 0
}

if [ "${BASH_SOURCE[0]:-}" = "$0" ]; then
    main "$@"
fi
