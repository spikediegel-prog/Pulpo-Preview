#!/bin/bash
# Pulpo Preview — installer module: strip live-only packages from
# the installed system, before the initramfs step.
#
# Runs in the LIVE session as root (Calamares shellprocess with
# dontChroot: true), with $1 = the target root mount point
# (${ROOT}). The live image carries packages that exist only to
# boot the live session; the installed system must not keep them:
#   - casper: the live-boot logic (an initramfs hook plus
#     scripts/casper* that probe for a live medium). If it stays
#     installed, the install's initramfs step regenerates an
#     initrd that runs casper's find_livefs and drops to an
#     (initramfs) shell with no ISO attached — run 10, the primary
#     boot failure. Casper is a leaf (nothing in the image depends
#     on it) and the ONLY live-only package in the 1,823-package
#     image (checked against the built squashfs dpkg status: no
#     ubiquity, lupin-casper or live-boot is installed).
#
# The removal runs inside the target chroot (dpkg --purge), so the
# package's maintainer scripts run against the target, not the
# live session. casper.postrm does not run update-initramfs (it
# only does a guarded systemd daemon-reload, which is a no-op
# inside the chroot because /run/systemd/system does not exist
# there, plus deb-systemd-helper purge), so the purge itself never
# regenerates an initrd; the initramfs step that follows
# regenerates it casper-free. The verify-initramfs step after
# initramfs gates on the built initrd containing no casper logic.
#
# The purge does not remove everything casper left behind. The
# live image also carries /etc/initramfs-tools/conf.d/casperize.conf
# (export CASPER_GENERATE_UUID=1), which is owned by NO package —
# no .list under /var/lib/dpkg/info/ contains it — so dpkg --purge
# casper correctly leaves it, and mkinitramfs copies
# /etc/initramfs-tools/conf.d/*.conf into the rebuilt initrd
# (run 11: the rebuilt initrd contained exactly that one casper
# path). This step therefore deletes every casper-named file under
# the target's /etc/initramfs-tools/conf.d/ after the purge.
# The line itself is inert without the casper scripts, so the
# gate does not fail on it — but a live leftover has no business
# in an installed system, and deleting it here is what
# remove-live is for.
#
# Failure modes (loud where it matters, never silent):
#   - No casper package, initramfs paths, or conf files in the
#     target: warn and exit 0. The step is idempotent, and a
#     future image without casper must not fail the install.
#   - The purge fails, or casper's hook/scripts/conf files are
#     still present afterwards: exit non-zero, so Calamares marks
#     the install FAILED. An installed system with a live initramfs
#     is worse than a failed install.
#   - /proc, /sys or /dev are not mounted in the target (Calamares'
#     mount step normally bind-mounts them for the exec phase):
#     bind-mount the missing ones before the chroot and unmount
#     exactly what this script mounted afterwards — never unmount
#     mounts Calamares owns.
#
# For testing: the script is safe to source — its side effects
# live in main(), so tests can source it and call casper_present
# / verify_casper_removed / remove_casper_confd_files directly on
# a fake target root (no chroot, no root needed). The chroot +
# dpkg part is covered by a static assertion (the purge
# invocation) and by the install test.
set -u

# Live-only packages to purge from the target, one per line.
# casper is the only one (see the header); extend this list only
# with a package proven live-only the same way (present in the
# image, nothing depends on it, no installed-system use).
LIVE_PACKAGES="casper"

# Initramfs paths casper owns. If any of these survives in the
# target after the purge, the removal did not take.
CASPER_INITRAMFS_PATHS="usr/share/initramfs-tools/hooks/casper
usr/share/initramfs-tools/scripts/casper
usr/share/initramfs-tools/scripts/casper-functions
usr/share/initramfs-tools/scripts/casper-helpers
usr/share/initramfs-tools/scripts/casper-bottom
usr/share/initramfs-tools/scripts/casper-premount"

LOG_PREFIX="[remove-live]"

log() { echo "$LOG_PREFIX $*"; }

# _casper_package_installed <root>: 0 if the target's dpkg status
# records casper as "install ok installed".
_casper_package_installed() {
    local root="$1"
    local status="$root/var/lib/dpkg/status"
    [ -f "$status" ] || return 1
    grep -q "^Package: casper$" "$status" || return 1
    local entry
    entry="$(awk '/^Package: casper$/ {p=1} p && /^Status:/ {print; exit} p && /^$/ {p=0}' "$status")"
    case "$entry" in
        *"install ok installed"*) return 0 ;;
    esac
    return 1
}

# casper_confd_files <root>: print every casper-named file under
# the target's /etc/initramfs-tools/conf.d/, one per line. Empty
# output when there are none (run 11: casperize.conf, owned by no
# package, survives dpkg --purge).
casper_confd_files() {
    local root="$1"
    local confd="$root/etc/initramfs-tools/conf.d"
    [ -d "$confd" ] || return 0
    local f
    for f in "$confd"/*casper*; do
        [ -e "$f" ] || continue
        printf '%s\n' "$f"
    done
}

# remove_casper_confd_files <root>: delete every casper-named file
# under the target's /etc/initramfs-tools/conf.d/. Plain file
# deletion, not a package purge — these files belong to no
# package, so there is nothing to purge. Returns non-zero if a
# deletion fails.
remove_casper_confd_files() {
    local root="$1"
    local f rc=0
    while IFS= read -r f; do
        [ -n "$f" ] || continue
        log "removing live conf file: ${f#$root/}"
        rm -f "$f" || rc=1
    done <<EOF
$(casper_confd_files "$root")
EOF
    return "$rc"
}

# casper_present <root>: 0 if casper is recorded installed in the
# target's dpkg status, any of its initramfs paths exists, or a
# casper-named file exists under /etc/initramfs-tools/conf.d/.
casper_present() {
    local root="$1"
    _casper_package_installed "$root" && return 0
    local p
    while IFS= read -r p; do
        [ -n "$p" ] || continue
        [ -e "$root/$p" ] && return 0
    done <<EOF
$CASPER_INITRAMFS_PATHS
EOF
    [ -n "$(casper_confd_files "$root")" ] && return 0
    return 1
}

# verify_casper_removed <root>: 0 if casper is gone from the
# dpkg status (not "install ok installed"), none of its
# initramfs paths remains in the target, and no casper-named file
# remains under /etc/initramfs-tools/conf.d/.
verify_casper_removed() {
    local root="$1"
    if _casper_package_installed "$root"; then
        log "casper still recorded installed in dpkg status"
        return 1
    fi
    local p
    while IFS= read -r p; do
        [ -n "$p" ] || continue
        if [ -e "$root/$p" ]; then
            log "casper initramfs path still present: $p"
            return 1
        fi
    done <<EOF
$CASPER_INITRAMFS_PATHS
EOF
    local f
    while IFS= read -r f; do
        [ -n "$f" ] || continue
        log "casper conf file still present: ${f#$root/}"
        return 1
    done <<EOF
$(casper_confd_files "$root")
EOF
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
    # Reverse the list by prepending each word.
    local reversed=""
    for where in $_mounted_here; do
        reversed="$where $reversed"
    done
    for where in $reversed; do
        umount "$target/$where" 2>/dev/null || true
    done
    _mounted_here=""
}

# purge_live_packages <root>: chroot into the target and purge
# the live-only packages with dpkg. Returns non-zero on failure.
purge_live_packages() {
    local target="$1"
    _mount_if_missing "$target" /proc proc || return 1
    _mount_if_missing "$target" /sys sys || { _unmount_ours "$target"; return 1; }
    _mount_if_missing "$target" /dev dev || { _unmount_ours "$target"; return 1; }
    local pkg rc=0
    for pkg in $LIVE_PACKAGES; do
        log "purging $pkg from the target"
        chroot "$target" dpkg --purge "$pkg" || rc=1
        [ "$rc" -eq 0 ] || break
    done
    _unmount_ours "$target"
    return "$rc"
}

main() {
    [ $# -ge 1 ] || { log "usage: $0 <target-root>" >&2; return 2; }
    local target="$1"
    [ -d "$target" ] || { log "target root is not a directory: $target" >&2; return 2; }
    if ! casper_present "$target"; then
        log "casper is not installed in the target; nothing to remove"
        return 0
    fi
    if _casper_package_installed "$target"; then
        purge_live_packages "$target" || {
            log "ERROR: failed to purge the live packages from the target" >&2
            return 1
        }
    fi
    remove_casper_confd_files "$target" || {
        log "ERROR: failed to remove the live conf files from the target" >&2
        return 1
    }
    verify_casper_removed "$target" || {
        log "ERROR: casper is still present in the target after the purge" >&2
        return 1
    }
    log "live packages removed: $LIVE_PACKAGES"
    return 0
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    main "$@"
fi
