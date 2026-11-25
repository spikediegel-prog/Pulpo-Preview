#!/usr/bin/env python3
"""Build the merge plan for the layers given on the command line.

The build passes the boot chain only (minimal -> minimal.standard ->
minimal.standard.live, in dependency order); see installer/build-iso.sh.
The plan is order-agnostic — it takes the layers in the order given
and the last layer wins per path — so the caller, not this script,
decides precedence. (Run 6, 2026-11-12: merging all 21 layers
alphabetically let a language layer override the live layer's
debconf database, so no live user was created.)

The build merges the layers with a FUSE overlay (squashfuse +
fuse-overlayfs) and copies the merged view to a plain directory with
rsync. Two things rsync cannot do through the overlay as a non-root
user, so they are planned here from the layers' own metadata
(`unsquashfs -ll`, which reads the archives and bypasses the
permission checks):

1. Unreadable paths (root-owned, no other-read, group not in the
   build user's groups, e.g. /etc/shadow, /boot/vmlinuz, the snap
   files, /root). A directory counts as unreadable unless the
   build user can BOTH list it (read) and traverse it (execute):
   a dir with execute but no read (drwx--x--x /etc/sssd) fails
   rsync exactly like an unreadable one. rsync excludes them;
   the build extracts them directly from the archives
   (unsquashfs reads the archive bytes).
2. Whiteouts under those excluded directories, which the fixup must
   apply in layer order or it would resurrect files a higher layer
   deleted.
3. Real device nodes (char/block with a real major/minor, the
   static /dev nodes): rsync skips them and neither unsquashfs
   nor mknod can create them as the build user, so they are
   excluded from the rsync and from the expected list and never
   fixed up. The squashfs therefore carries no static /dev
   nodes; /dev is a devtmpfs at runtime, exactly as in the old
   unsquashfs-built image.

Also emits the expected merged file list (topmost non-whiteout entry
per path), which the build diffs against the merged directory as the
definitive merge verification.

Usage: merge-plan.py <outdir> <layer.squashfs ...>
Writes into <outdir>:
  excludes.txt        rsync --exclude-from patterns (leading-slash anchored)
  fixup-files.txt     path<TAB>providing-layer (excluded files)
  fixup-dirs.txt      path<TAB>mode<TAB>layer,layer,... (excluded dirs;
                      layers containing entries under the dir, in order)
  fixup-whiteouts.txt layer<TAB>path (whiteout targets under an excluded dir)
  expected-list.txt   sorted relative paths of the merged view
  ownership.txt       path<TAB>uid<TAB>gid<TAB>mode (4-digit octal)
                      for every merged path — the topmost
                      layer's numeric owner/group/mode, for
                      the ownership pseudo-file and gate
                      (run 7, 2026-11-13).
"""
import grp
import os
import pwd
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from squashfs_meta import (mode_octal, parse_ll, resolve_gid,
                           resolve_uid)

OUTDIR = sys.argv[1]
LAYERS = sys.argv[2:]
USER = pwd.getpwuid(os.getuid()).pw_name
USER_GROUPS = {g.gr_gid for g in grp.getgrall() if USER in g.gr_mem}
USER_GROUPS.add(pwd.getpwnam(USER).pw_gid)


def _exec_bit(ch):
    return ch in ("x", "s", "t")


def readable(mode, owner, group, is_dir):
    """Can the build user read (file) / list+traverse (dir) this entry?

    A directory needs BOTH read (to list it) and execute (to
    traverse it): a dir with execute but no read (e.g. drwx--x--x
    /etc/sssd) can be entered but not listed, and rsync fails on
    it exactly as if it were unreadable. That is the class of
    directory the first rsync run missed (etc/sssd, run/sudo,
    var/lib/gdm3, var/lib/snapd/void, var/lib/sss/deskprofile).
    """
    if owner == USER:
        return True
    if is_dir:
        # group needs r AND x (mode[4] and mode[6]); other needs
        # r AND x (mode[7] and mode[9]); 's'/'t' also mean x.
        group_ok = mode[4] == "r" and _exec_bit(mode[6])
        other_ok = mode[7] == "r" and _exec_bit(mode[9])
    else:
        group_ok = mode[4] == "r"
        other_ok = mode[7] == "r"
    if group_ok:
        try:
            if grp.getgrnam(group).gr_gid in USER_GROUPS:
                return True
        except KeyError:
            pass
    return other_ok


# Per-layer entries, and the topmost entry per path (layers in
# the given order; last wins — the caller passes the boot chain
# in dependency order, live layer last/topmost). A whiteout (char device 0,0)
# removes the path from the merged view. A real device node
# (char/block with a real major/minor, e.g. /dev/null 1,3) is in
# the merged view but cannot be reproduced rootlessly — rsync
# skips it ("skipping non-regular file") and neither unsquashfs
# nor mknod can create it as the build user — so it is excluded
# from the rsync and from the expected list, and never fixed up.
# The squashfs therefore carries no static /dev nodes; /dev is a
# devtmpfs at runtime (live and installed), exactly as in the
# old unsquashfs-built image, which skipped them the same way.
per_layer = []  # [(layer_name, [(mode, owner, group, path, rdev), ...]), ...]
topmost = {}    # path -> (mode, owner, group, layer, idx, is_whiteout, is_device)
for layer_idx, layer in enumerate(LAYERS):
    entries = list(parse_ll(layer))
    per_layer.append((os.path.basename(layer), entries))
    for mode, owner, group, path, rdev in entries:
        is_whiteout = mode[0] == "c" and rdev == ("0,", "0")
        is_device = mode[0] in "bc" and not is_whiteout
        topmost[path] = (mode, owner, group, os.path.basename(layer),
                         layer_idx, is_whiteout, is_device)

# Ancestor whiteouts: a whiteout at a DIRECTORY hides the whole
# subtree under it from lower layers (e.g. the no-languages
# layer whiteouts usr/lib/libreoffice/program/resource/de, which
# deletes every .mo file under it from the language layers
# below). A path is visible only if its topmost real entry sits
# ABOVE the topmost whiteout at the path or any ancestor of it.
# Without this, the expected list wrongly includes files the
# overlay hides — build #8's file-list diff failed on 35,389
# lines of them (LibreOffice language files and the like).
whiteout_top = {}  # path -> highest layer index with a whiteout there
for layer_idx, layer in enumerate(LAYERS):
    for mode, owner, group, path, rdev in per_layer[layer_idx][1]:
        if mode[0] == "c" and rdev == ("0,", "0"):
            if layer_idx > whiteout_top.get(path, -1):
                whiteout_top[path] = layer_idx


def visible(path, real_idx):
    """True if the real entry at path (layer real_idx) is above
    the topmost whiteout at the path or any ancestor of it."""
    wo = -1
    p = path
    while p:
        wo = max(wo, whiteout_top.get(p, -1))
        p = os.path.dirname(p)
    return wo < real_idx


# Real device nodes in the merged view (excluded, never fixed up).
devices = {p for p, v in topmost.items()
           if v[6] and visible(p, v[4])}

# Unreadable paths present in the merged view.
unreadable = {}
for path, (mode, owner, group, layer, idx, is_whiteout, is_device) in topmost.items():
    if is_whiteout or is_device or not path:
        continue
    if not visible(path, idx):
        continue
    if not readable(mode, owner, group, mode[0] == "d"):
        unreadable[path] = (mode, owner, group, layer)

# Minimal exclude set: drop any path covered by an unreadable ancestor.
minimal = {}
for path in sorted(unreadable):
    parent = os.path.dirname(path)
    covered = False
    while parent:
        if parent in unreadable and unreadable[parent][0][0] == "d":
            covered = True
            break
        parent = os.path.dirname(parent)
    if not covered:
        minimal[path] = unreadable[path]

excluded_dirs = {p for p, v in minimal.items() if v[0][0] == "d"}
excluded_files = {p: v for p, v in minimal.items() if v[0][0] != "d"}

# Whiteouts under an excluded dir, per layer (for the ordered fixup).
whiteouts = []  # (layer, path)
for layer_name, entries in per_layer:
    for mode, owner, group, path, rdev in entries:
        if not (mode[0] == "c" and rdev == ("0,", "0")):
            continue
        for d in excluded_dirs:
            if path == d or path.startswith(d + "/"):
                whiteouts.append((layer_name, path))
                break

# For each excluded dir: layers containing entries under it, in order.
dir_layers = {}
for path in sorted(excluded_dirs):
    layers = []
    for layer_name, entries in per_layer:
        for mode, owner, group, p, rdev in entries:
            if p.startswith(path + "/"):
                layers.append(layer_name)
                break
    dir_layers[path] = layers

# Expected merged list: topmost non-whiteout, non-device entry per
# path, that is actually visible (not hidden by an ancestor
# whiteout — see visible() above). (Devices are excluded: the
# plain directory cannot hold them, and the rsync excludes them
# too, so the diff must not expect them.)
expected = sorted(p for p, v in topmost.items()
                  if p and not v[5] and not v[6] and visible(p, v[4]))

os.makedirs(OUTDIR, exist_ok=True)
with open(os.path.join(OUTDIR, "excludes.txt"), "w") as f:
    for path in sorted(minimal):
        f.write("/" + path + "\n")
    for path in sorted(devices):
        f.write("/" + path + "\n")
with open(os.path.join(OUTDIR, "fixup-files.txt"), "w") as f:
    for path in sorted(excluded_files):
        f.write(f"{path}\t{excluded_files[path][3]}\n")
with open(os.path.join(OUTDIR, "fixup-dirs.txt"), "w") as f:
    for path in sorted(excluded_dirs):
        mode = mode_octal(minimal[path][0][1:])  # 4-digit octal, e.g. 0700
        f.write(f"{path}\t{mode}\t{','.join(dir_layers[path])}\n")
with open(os.path.join(OUTDIR, "fixup-whiteouts.txt"), "w") as f:
    for layer_name, path in sorted(whiteouts):
        f.write(f"{layer_name}\t{path}\n")
with open(os.path.join(OUTDIR, "expected-list.txt"), "w") as f:
    for path in expected:
        f.write(path + "\n")
# Ownership map: the topmost layer's numeric owner/group/
# mode per merged path (run 7, 2026-11-13: mksquashfs
# -all-root flattened every file to root:root, so the
# D-Bus launch helper lost its messagebus group and
# Calamares saw no disk). The build restores true
# ownership from this map with a pseudo-file (see
# installer/ownership-pseudo.py) and the gate
# (installer/ownership-gate.py) compares the built
# squashfs against it. Names resolve through the host
# NSS — the same namespace unsquashfs -ll displays them
# in — so a displayed name maps back to the stored id.
# An unresolvable name fails the build here, loudly,
# rather than silently assigning a wrong owner.
with open(os.path.join(OUTDIR, "ownership.txt"), "w") as f:
    for path in expected:
        mode, owner, group, _layer, _idx, _w, _d = topmost[path]
        uid = resolve_uid(owner)
        gid = resolve_gid(group)
        f.write(f"{path}\t{uid}\t{gid}\t{mode_octal(mode[1:])}\n")

print(f"layers: {len(LAYERS)}; merged paths: {len(expected)}; "
      f"ownership: {len(expected)} paths; "
      f"unreadable: {len(unreadable)}; excludes: {len(minimal)} "
      f"({len(excluded_files)} files, {len(excluded_dirs)} dirs); "
      f"devices excluded (no static /dev nodes): {len(devices)}; "
      f"whiteouts under excluded dirs: {len(whiteouts)}", file=sys.stderr)
