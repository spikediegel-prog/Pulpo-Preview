#!/usr/bin/env python3
"""Shared squashfs metadata helpers for the installer build.

merge-plan.py, ownership-pseudo.py and ownership-gate.py all need
the same three facts from a squashfs archive's `unsquashfs -ll`
listing: the permission mode, the numeric owner/group, and the
path. The parsing is subtle — a symlink line carries its target
after ' -> ', so the path is not the last field, and device lines
carry a major/minor pair before the path — and getting it wrong in
one place silently mis-plans the merge (build #8 failed exactly
that way, on symlink paths). So the parsing lives here, once,
and the three scripts import it.

Ownership resolution: `unsquashfs -ll` displays owner/group
through the HOST's passwd/group (like ls -l), so the displayed
name is the host's name for the stored numeric id — and when the
host cannot resolve an id it prints the number itself. The
inverse mapping therefore resolves a displayed name through the
host NSS and passes a displayed number straight through. That is
exact: a name that came from the host's resolution maps back to
the same number through the same namespace. (Do NOT resolve
through the image's /etc/group: the host calls gid 101 "lxd"
while the image calls it "messagebus" — resolving the displayed
"lxd" through the image would give 123, not the stored 101.)
"""

import grp
import pwd
import subprocess


def mode_octal(mode):
    """9-char permission string (no type char) -> 4-digit octal.

    chmod does NOT accept a bare "rwx------" symbolic string
    (it needs a who: u=rwx,go=), so the plan carries octal.
    's'/'S' in an x slot are setuid/setgid, 't'/'T' sticky.
    """
    def triplet(t):
        return (4 if t[0] == "r" else 0) + (2 if t[1] == "w" else 0) \
            + (1 if t[2] in "xst" else 0)
    special = (4 if mode[2] in "sS" else 0) \
        + (2 if mode[5] in "sS" else 0) \
        + (1 if mode[8] in "tT" else 0)
    return f"{special}{triplet(mode[0:3])}{triplet(mode[3:6])}{triplet(mode[6:9])}"


def parse_ll_lines(lines):
    """Yield (mode, owner, group, path, rdev) for `unsquashfs -ll` lines.

    rdev is (major, minor) as strings for device entries, None
    otherwise. It is what distinguishes an overlay whiteout
    (char device 0,0) from a real device node (/dev/null 1,3).

    The path is NOT the last field: a symlink line is
    "lrwxrwxrwx root/root SIZE DATE TIME PATH -> TARGET", so
    parts[-1] is the TARGET, not the link. The path starts after
    the time field — index 5 for files/dirs/symlinks/fifos,
    index 6 for devices (which carry a major, minor pair) — and
    runs up to '->' for a symlink. (Taking parts[-1] recorded
    every symlink under its target's bare name, so the expected
    list missed every symlink path — build #8's file-list diff
    failed on etc/alternatives/* and the like.)
    """
    for line in lines:
        parts = line.split()
        if len(parts) < 6:
            continue
        mode, owner_group = parts[0], parts[1]
        if "/" not in owner_group or not mode:
            continue
        owner, group = owner_group.split("/", 1)
        is_device = mode[0] in "bc"
        path_idx = 6 if is_device else 5
        if len(parts) <= path_idx:
            continue
        rest = parts[path_idx:]
        if "->" in rest:
            rest = rest[:rest.index("->")]
        path = " ".join(rest)
        if not path.startswith("squashfs-root/"):
            continue
        rdev = None
        if is_device and len(parts) >= 4:
            rdev = (parts[2], parts[3])
        yield mode, owner, group, path[len("squashfs-root/"):], rdev


def parse_ll(layer):
    """Yield (mode, owner, group, path, rdev) for one squashfs layer."""
    out = subprocess.run(
        ["unsquashfs", "-ll", layer],
        capture_output=True, text=True, check=True,
    ).stdout
    yield from parse_ll_lines(out.splitlines())


def resolve_uid(owner):
    """Displayed owner (name or number) -> numeric uid.

    Fails loudly on a name the host cannot resolve: guessing
    would silently assign the wrong owner to a system file.
    """
    if owner.isdigit():
        return int(owner)
    try:
        return pwd.getpwnam(owner).pw_uid
    except KeyError:
        raise ValueError(f"cannot resolve owner {owner!r} to a uid")


def resolve_gid(group):
    """Displayed group (name or number) -> numeric gid.

    Fails loudly on a name the host cannot resolve: guessing
    would silently assign the wrong group to a system file.
    """
    if group.isdigit():
        return int(group)
    try:
        return grp.getgrnam(group).gr_gid
    except KeyError:
        raise ValueError(f"cannot resolve group {group!r} to a gid")
