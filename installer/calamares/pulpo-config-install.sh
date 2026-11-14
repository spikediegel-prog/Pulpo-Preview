#!/bin/bash
# Pulpo Preview — installer module: carry the wizard's customer
# config into the installed system.
#
# Runs in the LIVE session as root (Calamares shellprocess with
# dontChroot: true), with $1 = the target root mount point
# (${ROOT}). It:
#   1. finds the customer config JSON the wizard wrote in the
#      live session (~/.config/PulpoPreview/
#      control-center-customer-config.json, schema
#      pulpo.control-center-customer-config.v1),
#   2. copies it to the target as /etc/pulpo/customer-config.json
#      (the system record) and into the new user's profile
#      (~/.config/PulpoPreview/control-center-customer-config.json),
#   3. runs `pulpo-control-center config import --root $TARGET
#      --apply-network` so the target's timesyncd, netplan and
#      storage records are written from the same document,
#   4. copies the Calamares session log into the target for
#      post-install diagnosis.
#
# The import itself runs as the live session's NON-ROOT user
# (default `ubuntu`, uid 1000), never as root: the Control
# Center's scratch-root guard refuses root for any --root != /
# (system_config.py _require_privilege:
# scratch_root_must_not_run_as_root) — run 8 died on exactly
# that, at step 10/15, because Calamares runs this script as
# root and the import was invoked directly. The script drops
# privileges with runuser for the import only; everything else
# (the copies, the log) still runs as root. The target dirs the
# import must write are pre-created with the import user's
# ownership first, and root ownership is restored afterwards —
# the applied system files must end up root-owned. The import's
# HOME is set to the import user's home so its profile record
# (best-effort) lands in the live user's profile, not root's.
#
# Failure modes (loud where it matters, never silent):
#   - No config JSON in the live session: the user skipped Guided
#     Setup. Warn and exit 0 — install without a config is fine;
#     Guided Setup remains available on the installed system.
#   - Config found but the import fails validation: exit
#     non-zero, so Calamares marks the install FAILED with this
#     log. A config that cannot be applied must not be silently
#     dropped. (The import validates the document before it
#     applies anything, so a validation failure means nothing
#     was applied.)
#   - Config found, import fails ONLY because no network
#     interface can be found (offline live session): retry with
#     the first non-loopback interface from /sys/class/net. If
#     that still fails, warn and exit 0 — time and storage are
#     already applied by then (the import applies them before
#     the network step), the config is preserved in the target,
#     and Guided Setup on the installed system can apply the
#     network from the same document. An offline machine is a
#     normal case for Pulpo, not an install failure.
#   - The import user does not exist in the live session, or
#     runuser cannot drop to it: fail loudly. There is no
#     fallback to running the import as root — the guard would
#     refuse it, and a silent fallback would hide the breakage.
#   - The script never APPLIES anything to the live system:
#     `config import --root $TARGET` skips the timesyncd restart
#     and the netplan apply when the root is not /. But `netplan
#     generate --root-dir` still ATTEMPTS a live `systemctl
#     daemon-reload` as the invoking (non-root) user — it fails
#     (permission denied) and is non-fatal: generate still exits
#     0 when its inputs are readable. That attempt is netplan's
#     own, not the script's, and it changes nothing live.
#
# For testing: PULPO_CC_BIN overrides the Control Center binary
# (tests point it at a stub), PULPO_LIVE_CONFIG_GLOB overrides
# where the live session's config is looked for, PULPO_IFACE
# overrides the fallback interface used when the import cannot
# find one, and PULPO_IMPORT_USER overrides the user the import
# runs as when this script runs as root (default `ubuntu`; tests
# set it to the current user). Production runs set none of these. The script is safe to
# source: its side effects live in main(), so tests can source
# it and call prepare_import_dirs / restore_import_ownership
# directly (under fakeroot, where chown is faked, the ownership
# dance is observable with stat).
set -u

# The user the import runs as. Resolved to uid/gid/home by
# resolve_import_ids() in main().
IMPORT_USER="${PULPO_IMPORT_USER:-ubuntu}"
IMPORT_UID=""
IMPORT_GID=""
IMPORT_HOME=""

# Whether this script is running as root (Calamares) or already
# non-root (tests / dev). Under fakeroot, id -u reports 0, which
# is what the ownership tests rely on.
AS_ROOT=0
[ "$(id -u)" -eq 0 ] && AS_ROOT=1

# Dirs inside the target the import must write (see
# system_config.py: apply_time_config writes
# etc/systemd/timesyncd.conf, apply_network_config writes
# etc/netplan/60-pulpo.yaml and runs `netplan generate
# --root-dir`, which writes under run/systemd/{network,system}
# and run/udev/rules.d). _atomic_write creates a temp file in
# the parent dir and renames it, so the PARENT dir must be
# writable by the import user — not just the file.
# `netplan generate` also READS every YAML under the root,
# including pre-existing files under lib/netplan/ — the image
# ships lib/netplan/00-network-manager-all.yaml 0600 root:root,
# unreadable by the import user. That dir is handed over by
# prepare_lib_netplan / restore_lib_netplan below (run 9), not
# by IMPORT_DIRS: the import only reads it, and its
# owner:group AND mode must be restored afterwards.
IMPORT_DIRS=(
    "etc/systemd" "etc/netplan"
    "run/systemd/network" "run/systemd/system" "run/udev/rules.d"
)

# Set by main(); the tests that source this file set them first.
TARGET=""
CC_BIN="${PULPO_CC_BIN:-/usr/bin/pulpo-control-center}"
LIVE_CONFIG_GLOB="${PULPO_LIVE_CONFIG_GLOB:-/home/*/.config/PulpoPreview/control-center-customer-config.json /root/.config/PulpoPreview/control-center-customer-config.json}"
LOGDIR=""
LOGFILE=""

# Pre-existing state of the target's lib/netplan/ (see
# prepare_lib_netplan): one "mode uid gid path" line per entry,
# recorded before the handover and restored afterwards. Empty
# when the dir does not exist in the target.
LIB_NETPLAN_STATE=""

log() { echo "[pulpo-config] $*"; echo "[pulpo-config] $*" >> "$LOGFILE"; }

fail() { log "ERROR: $*"; exit 1; }

resolve_import_ids() {
    IMPORT_UID="$(id -u "$IMPORT_USER" 2>/dev/null)" \
        || fail "import user $IMPORT_USER does not exist in the live session"
    IMPORT_GID="$(id -g "$IMPORT_USER" 2>/dev/null)" \
        || fail "import user $IMPORT_USER has no primary group"
    IMPORT_HOME="$(getent passwd "$IMPORT_USER" 2>/dev/null | cut -d: -f6)"
    [ -n "$IMPORT_HOME" ] || IMPORT_HOME="/home/$IMPORT_USER"
}

prepare_import_dirs() {
    local dir
    for dir in "${IMPORT_DIRS[@]}"; do
        mkdir -p "$TARGET/$dir" \
            || fail "could not create $TARGET/$dir"
    done
    if [ "$AS_ROOT" -eq 1 ]; then
        chown "$IMPORT_UID:$IMPORT_GID" "${IMPORT_DIRS[@]/#/$TARGET/}" \
            || fail "could not hand the import dirs to $IMPORT_USER"
    fi
    prepare_lib_netplan
}

# Hand the target's lib/netplan/ to the import user so `netplan
# generate --root-dir` (run by the import as $IMPORT_USER) can
# READ the pre-existing files there. The image ships
# lib/netplan/00-network-manager-all.yaml 0600 root:root (run 9:
# generate died with Permission denied on it); the dir itself is
# 0755 but is handed over too, in case a future image ships it
# tighter. Only the ownership is changed here — never the mode —
# so a 0600 file stays 0600, owned by the import user for the
# duration of the import. The pre-existing owner:group AND mode
# of every entry are recorded in LIB_NETPLAN_STATE for
# restore_lib_netplan. Regular files only: a symlink under
# lib/netplan/ is not followed (chown would retarget it).
# No-op when the dir does not exist in the target.
prepare_lib_netplan() {
    local dir="$TARGET/lib/netplan"
    [ -d "$dir" ] || return 0
    LIB_NETPLAN_STATE=""
    local entry file
    entry="$(stat -c '%a %u %g %n' "$dir")" \
        || fail "could not stat $dir"
    LIB_NETPLAN_STATE="$entry"
    while IFS= read -r file; do
        entry="$(stat -c '%a %u %g %n' "$file")" \
            || fail "could not stat $file"
        LIB_NETPLAN_STATE="$LIB_NETPLAN_STATE
$entry"
    done < <(find "$dir" -type f | sort)
    if [ "$AS_ROOT" -eq 1 ]; then
        chown "$IMPORT_UID:$IMPORT_GID" "$dir" \
            || fail "could not hand $dir to $IMPORT_USER"
        find "$dir" -type f -exec chown "$IMPORT_UID:$IMPORT_GID" {} + \
            || fail "could not hand $dir files to $IMPORT_USER"
        log "lib/netplan handed to $IMPORT_USER (modes recorded, to restore)"
    fi
}

restore_import_ownership() {
    [ "$AS_ROOT" -eq 1 ] || return 0
    # Applied system files must end up root-owned: the import ran
    # as $IMPORT_USER and created them with that ownership.
    local file
    for file in etc/systemd/timesyncd.conf etc/netplan/60-pulpo.yaml; do
        if [ -e "$TARGET/$file" ]; then
            chown root:root "$TARGET/$file" \
                || fail "could not restore root ownership of $TARGET/$file"
        fi
    done
    chown root:root "${IMPORT_DIRS[@]/#/$TARGET/}" \
        || fail "could not restore root ownership of the import dirs"
    # netplan generate's output under the target's /run is shadowed
    # by tmpfs at first boot, but leave no $IMPORT_USER-owned files
    # behind on the disk. (Only the dirs the import could have
    # written into; /run itself and anything unpackfs put there
    # are untouched.)
    chown -R root:root "$TARGET/run/systemd" "$TARGET/run/udev" \
        2>/dev/null || true
    restore_lib_netplan
}

# Undo prepare_lib_netplan: restore the pre-existing
# owner:group AND mode of the dir and every file recorded
# there. The mode matters, not just the ownership: the image's
# 00-network-manager-all.yaml is 0600 by design (netplan warns
# when it is more open), so handing it back as 0644 would be a
# permanent loosening. Runs before the import's outcome is
# decided (like restore_import_ownership itself), so a failed
# import never leaves loosened files behind. No-op when there
# is nothing recorded, or when not root (non-root runs never
# handed anything over).
restore_lib_netplan() {
    [ "$AS_ROOT" -eq 1 ] || return 0
    [ -n "$LIB_NETPLAN_STATE" ] || return 0
    local line mode uid gid path
    while IFS= read -r line; do
        [ -n "$line" ] || continue
        read -r mode uid gid path <<< "$line"
        [ -e "$path" ] || fail "lib/netplan entry vanished during the import: $path"
        chown "$uid:$gid" "$path" \
            || fail "could not restore ownership of $path"
        chmod "$mode" "$path" \
            || fail "could not restore mode $mode of $path"
    done <<< "$LIB_NETPLAN_STATE"
    log "lib/netplan ownership and modes restored"
}

run_import() {
    # "$@" is the import's argument list (after `config import`).
    # As root, drop to the import user; already non-root (tests),
    # run the CLI directly — runuser refuses non-root callers.
    if [ "$AS_ROOT" -eq 1 ]; then
        runuser -u "$IMPORT_USER" -- env "HOME=$IMPORT_HOME" \
            "$CC_BIN" config import "$@"
    else
        "$CC_BIN" config import "$@"
    fi
}

main() {
    TARGET="${1:?usage: pulpo-config-install.sh <target-root>}"
    LOGDIR="$TARGET/var/log/pulpo-installer"
    LOGFILE="$LOGDIR/pulpo-config-install.log"
    mkdir -p "$LOGDIR"

    # The import user only matters when this script runs as root
    # (Calamares): non-root runs invoke the CLI directly, as the
    # current user, and never need the import user to exist.
    if [ "$AS_ROOT" -eq 1 ]; then
        resolve_import_ids
    fi

    [ -d "$TARGET" ] || fail "target root $TARGET does not exist"
    [ -x "$CC_BIN" ] || fail "Control Center binary not executable: $CC_BIN"

    # 1. Find the wizard's config JSON in the live session.
    SRC=""
    # The glob is unquoted on purpose (word splitting expands it);
    # shellcheck would complain, and it is right in general — here
    # the expansion is the point.
    # shellcheck disable=SC2086
    for candidate in $LIVE_CONFIG_GLOB; do
        if [ -s "$candidate" ]; then SRC="$candidate"; break; fi
    done
    if [ -z "$SRC" ]; then
        log "WARNING: no customer config found in the live session"
        log "(looked in /home/*/.config/PulpoPreview/ and /root/.config/PulpoPreview/)"
        log "The install proceeds without a config; Guided Setup on the"
        log "installed system can create one. Nothing was applied."
        exit 0
    fi
    log "customer config found: $SRC"

    # 2. Copy it into the target (system record + new user's profile).
    mkdir -p "$TARGET/etc/pulpo"
    cp "$SRC" "$TARGET/etc/pulpo/customer-config.json" \
        || fail "could not copy config to $TARGET/etc/pulpo/customer-config.json"
    chmod 644 "$TARGET/etc/pulpo/customer-config.json"
    log "system record written: /etc/pulpo/customer-config.json"

    # The users module creates the first user with UID 1000.
    TARGET_USER="$(awk -F: '$3 == 1000 {print $1; exit}' "$TARGET/etc/passwd" 2>/dev/null || true)"
    TARGET_IDS="$(awk -F: '$3 == 1000 {print $3":"$4; exit}' "$TARGET/etc/passwd" 2>/dev/null || true)"
    if [ -n "$TARGET_USER" ]; then
        PROFILE_DIR="$TARGET/home/$TARGET_USER/.config/PulpoPreview"
        mkdir -p "$PROFILE_DIR"
        cp "$SRC" "$PROFILE_DIR/control-center-customer-config.json" \
            || fail "could not copy config to the user profile"
        chmod 644 "$PROFILE_DIR/control-center-customer-config.json"
        if [ -n "$TARGET_IDS" ]; then
            chown -R "$TARGET_IDS" "$TARGET/home/$TARGET_USER/.config" 2>/dev/null || \
                log "WARNING: could not chown the profile dir (continuing)"
        fi
        log "user profile written: /home/$TARGET_USER/.config/PulpoPreview/control-center-customer-config.json"
    else
        log "WARNING: no UID-1000 user in the target yet; profile copy skipped"
        log "(the system record at /etc/pulpo/customer-config.json is still in place)"
    fi

    # 3. Apply the config to the target's system files.
    # The import runs as $IMPORT_USER (never as root — the CLI's
    # scratch-root guard refuses root). Prepare the dirs it must
    # write, run it, then restore root ownership. The import's
    # outcome is decided AFTER the restore, so a failed import
    # never leaves $IMPORT_USER-owned system files behind.
    # Failure stays fatal: a config that cannot be applied must
    # not be silently dropped.
    IMPORT_OUT="$LOGDIR/config-import.out"
    prepare_import_dirs
    IMPORT_OK=0
    if run_import --root "$TARGET" --apply-network "$SRC" > "$IMPORT_OUT" 2>&1; then
        log "config import applied (time, storage, network)"
        IMPORT_OK=1
    elif grep -q "no_network_interface_found" "$IMPORT_OUT"; then
        log "no network interface found by the import (offline live session?)"
        # Retry with the first non-loopback interface, even if it
        # has no address yet — netplan only needs the name, and
        # the installed system will DHCP on it at first boot.
        IFACE="${PULPO_IFACE:-$(ls /sys/class/net 2>/dev/null | grep -v '^lo$' | sort | head -1 || true)}"
        if [ -n "$IFACE" ]; then
            log "retrying import with --interface $IFACE"
            if run_import --root "$TARGET" --apply-network \
                    --interface "$IFACE" "$SRC" > "$IMPORT_OUT" 2>&1; then
                log "config import applied with --interface $IFACE"
                IMPORT_OK=1
            else
                log "WARNING: network config could not be applied (see $IMPORT_OUT)"
                log "Time and storage were applied before the network step;"
                log "the config is preserved in the target, and Guided Setup"
                log "on the installed system can apply the network from it."
                log "The install proceeds."
                IMPORT_OK=1
            fi
        else
            log "WARNING: this machine has no non-loopback interface;"
            log "network config could not be applied. Time and storage"
            log "were applied; the config is preserved in the target and"
            log "Guided Setup on the installed system can apply the"
            log "network from it. The install proceeds."
            IMPORT_OK=1
        fi
    fi
    restore_import_ownership
    if [ "$IMPORT_OK" -eq 0 ]; then
        log "config import failed (see below); the install cannot proceed"
        log "with an unapplied config. Import output:"
        sed 's/^/[import] /' "$IMPORT_OUT" | tee -a "$LOGFILE"
        fail "config import failed"
    fi

    # 4. Keep the Calamares session log with the install record.
    for clog in /root/.cache/calamares/session.log \
                /home/*/.cache/calamares/session.log; do
        if [ -s "$clog" ]; then
            cp "$clog" "$LOGDIR/calamares-session.log" 2>/dev/null || true
            log "Calamares session log copied to /var/log/pulpo-installer/"
            break
        fi
    done

    log "done."
    exit 0
}

if [ "${BASH_SOURCE[0]:-}" = "$0" ]; then
    main "$@"
fi
