#!/bin/bash
# Pulpo Preview — installer module: write the GRUB prefix
# redirect stub for Ubuntu's signed GRUB.
#
# Runs in the LIVE session as root (Calamares shellprocess with
# dontChroot: true), with $1 = the target root mount point
# (${ROOT}), AFTER the bootloader step.
#
# Ubuntu's signed grubx64.efi has its config prefix baked in as
# /EFI/ubuntu at build time — `strings` on the signed binary in
# the image shows the literal "/EFI/ubuntu", and run 10's
# fallback GRUB reported prefix=(hd0,gpt1)/EFI/ubuntu with
# package_version 2.12-1ubuntu7.3, the same binary. grub-install
# --bootloader-id=pulpo only names the ESP directory; it cannot
# change the prefix, because with shim present grub-install
# installs the prebuilt SIGNED binary instead of generating one.
# The signed GRUB therefore looks for EFI/ubuntu/grub.cfg, which
# a pulpo install does not have — both the NVRAM entry (shim ->
# EFI/pulpo/grubx64.efi) and the fallback (EFI/boot/bootx64.efi,
# a copy of the same binary) drop to a grub> shell. Run 10
# proved the fallback half live; the NVRAM half fails the same
# way, for the same reason — the two paths run the same binary
# with the same prefix.
#
# This step writes EFI/ubuntu/grub.cfg as a redirect stub (the
# stock-Ubuntu form) that points the signed GRUB at the real menu
# in /boot/grub/grub.cfg (written by grub-mkconfig). One stub
# fixes both boot paths, because both run the same binary. The
# stub is found by device-independent UUID search, so it does not
# assume the ESP is (hd0,gpt1). The full menu stays where
# grub-mkconfig wrote it (EFI/pulpo/grub.cfg and
# /boot/grub/grub.cfg); only the redirect is added.
#
# This does NOT weaken Secure Boot: the stub is a config file,
# not a binary — the signed GRUB still loads, and under Secure
# Boot enforcement the chain (shim -> signed GRUB -> config)
# is unchanged. Replacing the signed GRUB with an unsigned one
# built with prefix EFI/pulpo would break Secure Boot, so that
# was not done.
#
# Failure modes (loud where it matters, never silent):
#   - No UUID for / in the target's /etc/fstab: exit non-zero.
#     The stub cannot be written without a device-independent
#     way to find the root partition.
#   - The ESP is not mounted at $TARGET/boot/efi: exit non-zero.
#   - The stub cannot be written or does not contain the UUID
#     afterwards: exit non-zero.
#
# For testing: the script is safe to source — its side effects
# live in main(), so tests can source it and call root_uuid /
# grub_stub_content directly on a fake target root (no root and
# no chroot needed).
set -u

LOG_PREFIX="[grub-prefix-stub]"

log() { echo "$LOG_PREFIX $*"; }

# root_uuid <target>: print the UUID of the target's root
# filesystem, from its /etc/fstab (/ entry, UUID=... form).
# Returns non-zero when fstab has no UUID for /.
root_uuid() {
    local target="$1"
    local fstab="$target/etc/fstab"
    [ -f "$fstab" ] || return 1
    awk '$2 == "/" && $1 ~ /^UUID=/ {sub(/^UUID=/, "", $1); print $1; exit}' "$fstab"
}

# grub_stub_content <root-uuid>: print the redirect stub.
grub_stub_content() {
    local uuid="$1"
    cat <<EOF
# Pulpo Preview — GRUB prefix redirect (run 10).
# Ubuntu's signed grubx64.efi has its config prefix baked in as
# /EFI/ubuntu at build time; --bootloader-id only names the ESP
# directory. The real menu is /boot/grub/grub.cfg, so this stub
# points the signed GRUB at it. Without it, both the NVRAM entry
# and the fallback drop to a grub> shell.
search --no-floppy --fs-uuid --set=root $uuid
set prefix=(\$root)/boot/grub
configfile \$prefix/grub.cfg
EOF
}

main() {
    [ $# -ge 1 ] || { log "usage: $0 <target-root>" >&2; return 2; }
    local target="$1"
    [ -d "$target" ] || { log "target root is not a directory: $target" >&2; return 2; }
    local uuid
    uuid="$(root_uuid "$target")" || {
        log "ERROR: no UUID for / in $target/etc/fstab" >&2
        return 1
    }
    [ -n "$uuid" ] || {
        log "ERROR: no UUID for / in $target/etc/fstab" >&2
        return 1
    }
    local esp="$target/boot/efi"
    [ -d "$esp" ] || {
        log "ERROR: ESP is not mounted at $esp" >&2
        return 1
    }
    mkdir -p "$esp/EFI/ubuntu" || {
        log "ERROR: cannot create $esp/EFI/ubuntu" >&2
        return 1
    }
    grub_stub_content "$uuid" > "$esp/EFI/ubuntu/grub.cfg" || {
        log "ERROR: cannot write $esp/EFI/ubuntu/grub.cfg" >&2
        return 1
    }
    grep -q "fs-uuid --set=root $uuid" "$esp/EFI/ubuntu/grub.cfg" || {
        log "ERROR: stub does not contain the root UUID" >&2
        return 1
    }
    log "wrote $esp/EFI/ubuntu/grub.cfg (root UUID $uuid)"
    return 0
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    main "$@"
fi
