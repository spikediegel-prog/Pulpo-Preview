#!/bin/bash
# pulpo-trust-launcher.sh -- mark the live desktop installer launcher
# as trusted, once, at live-session login.
#
# GNOME shows a .desktop file on the Desktop as untrusted (red-X
# icon, double-click does nothing) until it is executable AND has
# metadata::trusted set. PR #129 set the executable bit; "Allow
# Launching" in Nautilus does both. This script does the second half:
# it runs `gio set <launcher> metadata::trusted true` on the real
# path, as the live user, with a real session bus (via the autostart
# entry in /etc/skel/.config/autostart/), then touches the file so
# the desktop icon refreshes, and removes its own autostart entry so
# it runs once.
#
# A build-time gio set cannot do this: the trust metadata lives in
# the user's gvfs-metadata store, keyed by the runtime path, and
# needs a session bus. Setting it at login, on the real path, is
# the same approach openSUSE and other live images use.
#
# It must never break login: every failure is swallowed and main()
# always returns 0. If gio is missing, the bus is not up, or the
# launcher is absent, it just does nothing.
#
# remove-live deletes this script and its autostart entry from the
# installed system, so they never run there.

LOG_PREFIX="[pulpo-trust-launcher]"

LAUNCHER_NAME="install-pulpo.desktop"
AUTOSTART_NAME="pulpo-trust-launcher.desktop"

log() {
    echo "$LOG_PREFIX $*"
}

# trust_live_launcher: set metadata::trusted on the live desktop
# launcher, if it exists. Retries briefly: the gvfs metadata daemon
# spawns on demand and the session bus can be slow right after login.
# Returns 0 always -- a failure must never break login.
trust_live_launcher() {
    local launcher="$HOME/Desktop/$LAUNCHER_NAME"
    [ -f "$launcher" ] || { log "no live desktop launcher at $launcher; nothing to trust"; return 0; }
    command -v gio >/dev/null 2>&1 || { log "gio is not available; cannot trust the launcher"; return 0; }
    local attempt
    for attempt in 1 2 3; do
        if gio set "$launcher" metadata::trusted true 2>/dev/null; then
            touch "$launcher" 2>/dev/null || true
            log "live desktop launcher trusted: $launcher"
            return 0
        fi
        sleep 2
    done
    log "could not set metadata::trusted on $launcher after 3 attempts; leaving it untrusted"
    return 0
}

# remove_own_autostart: delete our autostart entry so this runs once.
remove_own_autostart() {
    local entry="$HOME/.config/autostart/$AUTOSTART_NAME"
    [ -e "$entry" ] || return 0
    rm -f "$entry" 2>/dev/null || true
    log "removed autostart entry: $entry"
    return 0
}

main() {
    trust_live_launcher
    remove_own_autostart
    return 0
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    main "$@"
fi
