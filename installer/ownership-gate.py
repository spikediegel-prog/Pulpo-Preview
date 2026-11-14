#!/usr/bin/env python3
"""Gate: the built squashfs must carry the layers' true ownership.

Usage: ownership-gate.py <built.squashfs> <ownership.txt>
        [--rootfs <staging-dir>] [--ll-file <file>]

Runs `unsquashfs -ll` on the built squashfs and compares every
path against ownership.txt (from installer/merge-plan.py):
owner:group:mode must match the topmost layer's values exactly.
Paths in the squashfs but not in the map are files the build
added in step 4; they must be root:root (they take -all-root).

The D-Bus launch helper is checked explicitly: it must be 4754
root:messagebus (gid 101) — run 7, 2026-11-13: -all-root
flattened it to root:root, the system bus could not spawn the
KPMCore helper, and Calamares saw no disk.

--rootfs is the staging tree the squashfs was packed from. It is
needed only to resolve hardlink groups: hardlinked paths share
one inode, so they share one ownership, and if the map disagrees
within a group the first path in sorted order wins — the same
collapse ownership-pseudo.py applies. Without --rootfs the gate
compares per-path, which fails loudly (but less precisely) on
such a disagreement.

--ll-file is a test hook: read a pre-captured `unsquashfs -ll`
listing instead of running unsquashfs (the unit tests use it;
the build never does).

Exits 1 on any mismatch, printing every mismatching path
(capped at 50 lines in the report; the count is exact).
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from squashfs_meta import mode_octal, parse_ll_lines, resolve_gid, resolve_uid

DBUS_HELPER = "usr/lib/dbus-1.0/dbus-daemon-launch-helper"


def collapse_by_hardlink(rootfs, own):
    """Collapse the ownership map by staging hardlink groups.

    Returns a new map where every path in a hardlink group
    carries the (uid, gid) of the first in-map path in sorted
    order, plus a list of warnings for groups that disagreed.
    """
    by_inode = {}
    for dirpath, dirnames, filenames in os.walk(rootfs):
        rel_dir = os.path.relpath(dirpath, rootfs)
        for name in dirnames + filenames:
            full = os.path.join(dirpath, name)
            rel = name if rel_dir == "." else rel_dir + "/" + name
            st = os.lstat(full)
            by_inode.setdefault((st.st_dev, st.st_ino), []).append(rel)
    collapsed = dict(own)
    warnings = []
    for paths in by_inode.values():
        if len(paths) == 1:
            continue
        vals = {own[p] for p in paths if p in own}
        if len(vals) > 1:
            candidates = sorted(p for p in paths if p in own)
            winner = candidates[0]
            warnings.append(
                f"hardlink group {sorted(paths)} disagrees on "
                f"ownership {sorted(vals)}; using {own[winner]} "
                f"from {winner}"
            )
            for p in paths:
                if p in own:
                    collapsed[p] = own[winner]
    return collapsed, warnings


def main(argv):
    args = argv[1:]
    ll_file = None
    rootfs = None
    positional = []
    i = 0
    while i < len(args):
        if args[i] == "--ll-file":
            i += 1
            ll_file = args[i]
        elif args[i] == "--rootfs":
            i += 1
            rootfs = args[i]
        else:
            positional.append(args[i])
        i += 1
    if len(positional) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    squashfs, map_path = positional

    own = {}  # relpath -> (uid, gid, mode_octal)
    with open(map_path, encoding="utf-8") as f:
        for line in f:
            path, uid, gid, mode = line.rstrip("\n").split("\t")
            own[path] = (int(uid), int(gid), mode)
    plain = {p: (u, g) for p, (u, g, _m) in own.items()}

    warnings = []
    if rootfs is not None:
        collapsed, warnings = collapse_by_hardlink(rootfs, plain)
        expected = {p: (collapsed[p][0], collapsed[p][1], own[p][2])
                    for p in own}
    else:
        expected = dict(own)

    if ll_file is not None:
        with open(ll_file, encoding="utf-8") as f:
            lines = f.read().splitlines()
    else:
        out = subprocess.run(
            ["unsquashfs", "-ll", squashfs],
            capture_output=True, text=True, check=True,
        ).stdout
        lines = out.splitlines()

    built = {}  # relpath -> (mode_octal, uid, gid)
    for mode, owner, group, path, rdev in parse_ll_lines(lines):
        if mode[0] in "bc":
            continue  # no static /dev nodes in the built image
        built[path] = (mode_octal(mode[1:]),
                       resolve_uid(owner), resolve_gid(group))

    mismatches = []
    for path in sorted(expected):
        uid, gid, mode = expected[path]
        if path not in built:
            mismatches.append(f"{path}: missing from built squashfs")
        elif built[path] != (mode, uid, gid):
            bmode, buid, bgid = built[path]
            mismatches.append(
                f"{path}: built {bmode} {buid}:{bgid}, "
                f"expected {mode} {uid}:{gid}"
            )
    for path in sorted(built):
        if path not in expected:
            _mode, uid, gid = built[path]
            if (uid, gid) != (0, 0):
                mismatches.append(
                    f"{path}: build-added file is not root:root "
                    f"({uid}:{gid})"
                )

    # The explicit run-7 check.
    helper = built.get(DBUS_HELPER)
    if helper != ("4754", 0, 101):
        mismatches.append(
            f"{DBUS_HELPER}: built {helper}, expected "
            f"('4754', 0, 101) (root:messagebus)"
        )

    setuid = sum(1 for m, _u, _g in built.values() if int(m[0]) & 4)
    setgid = sum(1 for m, _u, _g in built.values() if int(m[0]) & 2)
    nonroot = sum(1 for _m, u, g in built.values()
                  if (u, g) != (0, 0))
    print(f"ownership gate: {len(expected)} map paths compared, "
          f"{len(built)} paths in built squashfs, "
          f"{nonroot} non-root, {setuid} setuid, {setgid} setgid, "
          f"{len(mismatches)} mismatches", file=sys.stderr)
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    if mismatches:
        for m in mismatches[:50]:
            print(f"  MISMATCH {m}", file=sys.stderr)
        if len(mismatches) > 50:
            print(f"  ... and {len(mismatches) - 50} more",
                  file=sys.stderr)
        return 1
    print("ownership gate: PASS", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
