#!/usr/bin/env python3
"""Generate a mksquashfs pseudo-file restoring true ownership.

Usage: ownership-pseudo.py <ownership.txt> <rootfs-dir> <out.pseudo>

ownership.txt (from installer/merge-plan.py) maps every merged
path to the topmost layer's numeric uid/gid/mode. The staging
rootfs holds those files owned by the build user (a non-root
rsync cannot chown), and mksquashfs -all-root would flatten them
all to root:root — which broke run 7 (2026-11-13): the D-Bus
launch helper lost its messagebus group, so the system bus could
not spawn the KPMCore helper and Calamares saw no disk.

This script walks the staging tree and emits "m" (modify) pseudo
entries for every path whose true owner:group is not root:root,
plus a mode-correction entry for any path whose true mode (from
the map) differs from its staging mode. The mode in every entry
is the map's mode — the layers are authoritative; the staging
mode is only compared, never trusted. Mode corrections exist
because installer/staging-readable.py chmods u+r any layer path
whose true mode denies owner-read (build #13: /var/lib/snapd/void,
mode 0111 — mksquashfs silently drops a directory it cannot list),
and the packed entry must carry the true mode, not the readable
staging mode. Files the build added (not in any layer) are not
listed, so they stay root:root via -all-root, as they should.
The build passes the file with -pseudo-override, which is what
makes the entries win over -all-root (proven by hand: without it
the entries are ignored).

Paths are double-quoted so filenames with spaces work. A path
containing a double quote, a backslash or a newline is skipped
with a warning — the ownership gate fails the build if that
path's ownership mattered, so nothing is silently wrong.

Hardlinked paths share one inode, so they share one ownership in
the squashfs. If the map disagrees within a hardlink group (the
paths came from different layers), the first path in sorted
order wins and the disagreement is reported: the gate checks
the same collapsed value, so the build still fails loudly if
the collapse was wrong.
"""

import os
import stat
import sys


def iter_entries(rootfs):
    """Yield (relpath, st_mode) for every entry under rootfs.

    Every path appears exactly once, as a child of its parent;
    the staging root itself is never yielded. Symlinked
    directories are listed but not followed (os.walk default).
    """
    for dirpath, dirnames, filenames in os.walk(rootfs):
        rel_dir = os.path.relpath(dirpath, rootfs)
        for name in dirnames + filenames:
            full = os.path.join(dirpath, name)
            rel = name if rel_dir == "." else rel_dir + "/" + name
            yield rel, os.lstat(full)


def main(argv):
    if len(argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2
    map_path, rootfs, out_path = argv[1], argv[2], argv[3]

    own = {}  # relpath -> (uid, gid)
    map_mode = {}  # relpath -> mode int (the layers are authoritative)
    with open(map_path, encoding="utf-8") as f:
        for line in f:
            path, uid, gid, mode = line.rstrip("\n").split("\t")
            own[path] = (int(uid), int(gid))
            map_mode[path] = int(mode, 8)

    # Collapse hardlink groups first: one inode, one ownership.
    by_inode = {}  # (st_dev, st_ino) -> [relpath, ...]
    stats = {}  # relpath -> os.stat_result
    for rel, st in iter_entries(rootfs):
        stats[rel] = st
        by_inode.setdefault((st.st_dev, st.st_ino), []).append(rel)
    collapsed = {}  # relpath -> (uid, gid) after hardlink collapse
    warnings = []
    for key, paths in by_inode.items():
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
    for rel, (uid, gid) in own.items():
        collapsed.setdefault(rel, (uid, gid))

    entries = []
    skipped = []
    nonroot = 0
    modecorr = 0
    for rel in sorted(stats):
        if rel not in collapsed:
            continue  # build-added file: stays root:root via -all-root
        uid, gid = collapsed[rel]
        staging_mode = stat.S_IMODE(stats[rel].st_mode)
        true_mode = map_mode[rel]
        is_nonroot = not (uid == 0 and gid == 0)
        is_modecorr = true_mode != staging_mode
        if not is_nonroot and not is_modecorr:
            continue
        if any(c in rel for c in ('"', "\\", "\n")):
            skipped.append(rel)
            continue
        mode = "%04o" % true_mode
        entries.append((rel, mode, uid, gid))
        nonroot += is_nonroot
        modecorr += is_modecorr
    entries.sort()

    with open(out_path, "w", encoding="utf-8") as f:
        for rel, mode, uid, gid in entries:
            f.write(f'"{rel}" m {mode} {uid} {gid}\n')

    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    for rel in skipped:
        print(f"warning: skipping ownership entry for {rel!r} "
              f"(unquotable path)", file=sys.stderr)
    print(f"ownership pseudo-file: {len(entries)} entries "
          f"({nonroot} non-root, {modecorr} mode corrections), "
          f"{len(skipped)} skipped", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
