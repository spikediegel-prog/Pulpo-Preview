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
#   - The script never touches the live system's own services:
#     `config import --root $TARGET` skips the timesyncd restart
#     and the netplan apply when the root is not /.
#
# For testing: PULPO_CC_BIN overrides the Control Center binary
# (tests point it at a stub), PULPO_LIVE_CONFIG_GLOB overrides
# where the live session's config is looked for, and PULPO_IFACE
# overrides the fallback interface used when the import cannot
# find one. Production runs set none of these.
set -u

TARGET="${1:?usage: pulpo-config-install.sh <target-root>}"
CC_BIN="${PULPO_CC_BIN:-/usr/bin/pulpo-control-center}"
LIVE_CONFIG_GLOB="${PULPO_LIVE_CONFIG_GLOB:-/home/*/.config/PulpoPreview/control-center-customer-config.json /root/.config/PulpoPreview/control-center-customer-config.json}"
LOGDIR="$TARGET/var/log/pulpo-installer"
LOGFILE="$LOGDIR/pulpo-config-install.log"
mkdir -p "$LOGDIR"

log() { echo "[pulpo-config] $*"; echo "[pulpo-config] $*" >> "$LOGFILE"; }

fail() { log "ERROR: $*"; exit 1; }

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
IMPORT_OUT="$LOGDIR/config-import.out"
if "$CC_BIN" config import --root "$TARGET" --apply-network "$SRC" > "$IMPORT_OUT" 2>&1; then
    log "config import applied (time, storage, network)"
else
    if grep -q "no_network_interface_found" "$IMPORT_OUT"; then
        log "no network interface found by the import (offline live session?)"
        # Retry with the first non-loopback interface, even if it
        # has no address yet — netplan only needs the name, and
        # the installed system will DHCP on it at first boot.
        IFACE="${PULPO_IFACE:-$(ls /sys/class/net 2>/dev/null | grep -v '^lo$' | sort | head -1 || true)}"
        if [ -n "$IFACE" ]; then
            log "retrying import with --interface $IFACE"
            if "$CC_BIN" config import --root "$TARGET" --apply-network \
                    --interface "$IFACE" "$SRC" > "$IMPORT_OUT" 2>&1; then
                log "config import applied with --interface $IFACE"
            else
                log "WARNING: network config could not be applied (see $IMPORT_OUT)"
                log "Time and storage were applied before the network step;"
                log "the config is preserved in the target, and Guided Setup"
                log "on the installed system can apply the network from it."
                log "The install proceeds."
            fi
        else
            log "WARNING: this machine has no non-loopback interface;"
            log "network config could not be applied. Time and storage"
            log "were applied; the config is preserved in the target and"
            log "Guided Setup on the installed system can apply the"
            log "network from it. The install proceeds."
        fi
    else
        log "config import failed (see below); the install cannot proceed"
        log "with an unapplied config. Import output:"
        sed 's/^/[import] /' "$IMPORT_OUT" | tee -a "$LOGFILE"
        fail "config import failed"
    fi
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
