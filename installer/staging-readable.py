#!/usr/bin/env python3
"""Make layer paths owner-readable in the staging rootfs before packing.

Usage: staging-readable.py <ownership.txt> <rootfs-dir>

mksquashfs packs a directory by listing it and a file by reading
it, as the build user. A layer path whose true mode gives its
owner no read permission cannot be listed or read by the
non-root user running the build, so mksquashfs silently drops it
from the image. The only such path in the Ubuntu 24.04.5 image
is /var/lib/snapd/void, mode 0111 (snapd's mountpoint): build
#13's first attempt failed the ownership gate on exactly that
one missing path — and the same path was already missing from
the build #12 image, which no gate yet existed to catch.

This script chmods u+r every map path whose staging mode lacks
owner-read, so mksquashfs can pack it. It touches only paths in
the ownership map (build-added files are untouched), never
chmods a symlink (chmod would follow the link), and only the
staging copy is changed — the layers are untouched. The true
mode is restored in the image by installer/ownership-pseudo.py,
which emits a mode-correction entry for any path whose staging
mode differs from the map; the ownership gate verifies the
result, so a path this script misses still fails the build
loudly instead of shipping wrong.
"""

import os
import stat
import sys


def main(argv):
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    map_path, rootfs = argv[1], argv[2]

    changed = []
    missing = []
    with open(map_path, encoding="utf-8") as f:
        for line in f:
            path = line.rstrip("\n").split("\t")[0]
            full = os.path.join(rootfs, path)
            try:
                st = os.lstat(full)
            except OSError:
                missing.append(path)
                continue
            if stat.S_ISLNK(st.st_mode):
                continue  # never chmod through a symlink
            mode = stat.S_IMODE(st.st_mode)
            if mode & 0o400:
                continue
            os.chmod(full, mode | 0o400)
            changed.append(path)

    for path in missing:
        print(f"warning: map path missing from staging: {path}",
              file=sys.stderr)
    print(f"staging readable: {len(changed)} paths made "
          f"owner-readable, {len(missing)} map paths missing "
          f"from staging", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
