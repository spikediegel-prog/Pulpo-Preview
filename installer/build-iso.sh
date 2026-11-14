#!/bin/bash
# Pulpo Preview live ISO builder — ROOTLESS remaster of an Ubuntu
# 24.04 LTS desktop ISO. No sudo, no chroot (the build VM has
# neither: sudo needs a password, unprivileged user namespaces are
# blocked). Everything below runs as the build user:
#   - ISO tooling (xorriso, qemu, ovmf) is fetched as .debs and
#     extracted with dpkg-deb -x into a prefix; nothing is installed
#     system-wide. (See installer/README.md for how to fetch them.)
#   - The live rootfs is the base ISO's 21 layered squashfs files,
#     merged at build time into ONE filesystem.squashfs
#     (Lubuntu-style). The merge is FUSE (squashfuse +
#     fuse-overlayfs, rootless) for the COMPOSITION, then an rsync
#     copy of the merged view into a plain directory, then the
#     customisation on that plain directory, then mksquashfs.
#     The plain-directory step is not optional: a non-root user
#     CANNOT write through a FUSE overlay whose lower layers are
#     root-owned — the kernel's permission checks reject mkdir/open
#     in the root-owned 0755 lower directories (proven by build
#     #2, 2026-11-12: dpkg-deb -x into the overlay died with
#     "Cannot mkdir: Permission denied" / "Cannot utime: Operation
#     not permitted"). The overlay is therefore read-only in this
#     build; all writes go to the plain directory the build user
#     owns. rsync cannot read a handful of root-only paths through
#     the overlay either (/etc/shadow, /boot/vmlinuz, the snap
#     files, /root, ... — 101 paths (60 files, 41 dirs), enumerated from the layers'
#     own metadata by installer/merge-plan.py); those are excluded
#     from the rsync and extracted directly from the archives
#     with unsquashfs, which reads the archive bytes and bypasses
#     the permission checks. The 8 static /dev nodes are also
#     excluded (rsync cannot copy devices as non-root, and
#     neither can unsquashfs/mknod) — the squashfs carries no
#     static /dev nodes; /dev is a devtmpfs at runtime, exactly
#     as in the old unsquashfs-built image. The merge is not cosmetic:
#     Calamares' unpackfs rsyncs the layers one by one and rsync
#     cannot copy overlay whiteouts (error 13 — see
#     installer/DISK-INSTALLER.md "The whiteout failure"). The
#     overlay resolves the whiteouts (and opaque dirs) during the
#     merge, so the single squashfs has none. No package is
#     installed inside the image with dpkg/apt; .debs are unpacked
#     with dpkg-deb -x (the Control Center .deb has no maintainer
#     scripts, so extraction is exact).
#   - The merge runs rootless: squashfuse and fuse-overlayfs are
#     FUSE tools, fetched as .debs and extracted into a prefix
#     like the other ISO tooling. No sudo, no chroot, no user
#     namespace (unprivileged user namespaces are blocked on the
#     build VM, so a kernel overlay mount is not available).
#   - The ISO is rebuilt with xorriso -indev/-outdev, replaying the
#     base image's boot chain verbatim (BIOS eltorito + appended EFI
#     system partition). Only the files listed in step 7 change.
#   - Secure Boot: Ubuntu's signed shim/grub from the base ISO are
#     reused unchanged, so the ISO boots under Secure Boot via
#     Microsoft's key. No Pulpo key is generated, enrolled, or used
#     for signing.
#
# Base ISO facts (verified 2026-11-11, see installer/BOOT-TEST.md):
#   - Ubuntu 24.04.5.1 desktop amd64, SHA-256
#     4da4a0c9035da8e68a59a838674f403f0a54472c78a83b4fb7f78d03588f85a7
#   - There is NO casper/filesystem.squashfs in 24.04.5: the live
#     system is 21 layered squashfs files (minimal + minimal.standard
#     + minimal.standard.live + language layers, listed in
#     CASPER_LAYERS below — verified with xorriso -find /casper on
#     the base ISO). The build merges the BOOT CHAIN only
#     (minimal -> minimal.standard -> minimal.standard.live,
#     MERGE_LAYERS below) into one casper/filesystem.squashfs;
#     the live session boots from that single file and Calamares
#     unpackfs copies that single file. The other 18 layers are
#     language layers casper never mounts at boot (run 6,
#     2026-11-12: merging all 21 alphabetically let
#     minimal.standard.zh's debconf database override the live
#     layer's, so no live user was created). The installed system
#     therefore carries no language packs — exactly as a stock
#     live session, which mounts the same three layers.
#     BUT the boot path needs the new name explicitly: casper's
#     find_livefs() only finds the DEVICE (by the presence of
#     casper/*.squashfs); the layer selection is setup_overlay(),
#     which takes the multi-layer branch whenever LAYERFS_PATH is
#     set — and the stock initrd always sets it
#     (default-layer.conf: minimal.standard.live.squashfs), demanding
#     all three dot-suffix parent layers. The merged file is never
#     looked for in that branch (run 3 boot failure, 2026-11-12:
#     casper panicked, "File system layers are missing"). The GRUB
#     kernel lines therefore carry layerfs-path=filesystem.squashfs
#     (added by make_live_grub_cfg.py); a dotless name has no parent
#     layers, so casper requires only that one file.
#   - The stock GRUB menu boots with `linux /casper/vmlinuz ---
#     quiet splash` (no boot=casper); the initramfs auto-detects the
#     live media. Verified from the shipped initrd: casper's
#     find_livefs() matches a device by the presence of
#     casper/*.squashfs, not by volume label or UUID (the UUID check
#     only applies when a uuid= kernel parameter is passed, which
#     this ISO does not). Changing the volume ID is therefore safe.
#   - python3-tk is NOT in the base image (checked in
#     filesystem.manifest); the build adds it (step 4e).
#
# Usage:
#   installer/build-iso.sh [--base-iso PATH] [--work-dir PATH]
#                          [--out PATH] [--cc-deb PATH]
#     --base-iso   Ubuntu 24.04 desktop ISO (default: $WORK/ubuntu-*.iso)
#     --work-dir   scratch dir, needs ~20G free (default: ~/pulpo-workspace/iso-build)
#     --out        output ISO path (default: $WORK/pulpo-preview-0.1.0-live-amd64.iso)
#     --cc-deb     Control Center .deb (default: the preview.48 release .deb from merged CC main 2077631)
#
# Inputs (all from the repo / already-built artefacts — nothing invented):
#   - Control Center .deb: the preview.48 RELEASE .deb, built from
#     merged Control Center main 2077631 (PR #66 merged) and
#     installed + signed + verified on the VM. It vendors PySide6
#     6.9.3 (the newest PySide6 that still starts on x86-64-v1) and
#     a launcher that probes Qt in a child and falls back to
#     Tkinter if Qt cannot start. SHA-256
#     60e65c1048493b57701497f028788ddf23f0a9c74d65965d5743537f29cc4921.
#     The pre-merge branch .deb must NOT be used; the default
#     below points at the release .deb.
#   - pulpo package: installed from this worktree with
#     pip install --target=<rootfs>/usr/local/lib/python3.12/dist-packages
#     --no-deps --no-build-isolation .  plus the entry-point scripts
#     moved to /usr/local/bin/. No new packaging system.
#   - installer/ skeleton from this repo (PR #121): GRUB menu (via
#     make_live_grub_cfg.py), BMP boot splash, manifest,
#     validate_config.py, example config.
#
# Outputs:
#   - pulpo-preview-0.1.0-live-amd64.iso + .sha256 (default name;
#     pass --out for a distinct build, e.g. the disk-install ISO)
#   - Live session: first boot autologs into GNOME and autostarts
#     Pulpo Control Center; Guided Setup is the button on the System
#     page (Diagnostics tab). The live session also carries the
#     Calamares disk installer (desktop icon "Install Pulpo
#     Preview"): erase-disk install, UEFI GRUB + Ubuntu shim, and
#     the wizard's config carried through to the installed system.
#     See installer/DISK-INSTALLER.md.
set -euo pipefail

VERSION="0.1.0"
VOLID="PULPO-PREVIEW-0.1.0"
WORK="${WORK:-$HOME/pulpo-workspace/iso-build}"
TOOLS="${TOOLS:-$HOME/pulpo-workspace/iso-tools}"
BASE_ISO=""
OUT=""
CC_DEB="${CC_DEB:-$HOME/pulpo-workspace/Pulpo-Control-Center-Preview48-release/dist/pulpo-control-center_0.1.0~ubuntu.preview.48+e3.2077631_amd64.deb}"
# Release bundle for the install-cc-deb step: the signed
# statement, its detached signature, and the publisher
# public key for the release above, plus the Control
# Center's own verify scripts. Defaults point at the
# preview.48 release on this machine; update them together
# with CC_DEB when the release changes.
CC_RELEASE_JSON="${CC_RELEASE_JSON:-$HOME/pulpo-workspace/pulpo-control-center-preview48-release.json}"
CC_RELEASE_SIG="${CC_RELEASE_SIG:-$HOME/pulpo-workspace/pulpo-control-center-preview48-release.json.asc}"
CC_PUBLISHER_KEY="${CC_PUBLISHER_KEY:-$HOME/pulpo-workspace/publisher.gpg}"
CC_VERIFY_SCRIPTS="${CC_VERIFY_SCRIPTS:-$HOME/pulpo-workspace/Pulpo-Control-Center-Preview48-release/scripts}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

while [ $# -gt 0 ]; do
  case "$1" in
    --base-iso) BASE_ISO="$2"; shift 2;;
    --work-dir) WORK="$2"; shift 2;;
    --out) OUT="$2"; shift 2;;
    --cc-deb) CC_DEB="$2"; shift 2;;
    *) echo "unknown option: $1" >&2; exit 2;;
  esac
done

[ -n "$BASE_ISO" ] || BASE_ISO="$(ls "$WORK"/ubuntu-24.04.*-desktop-amd64.iso | head -1)"
[ -n "$OUT" ] || OUT="$WORK/pulpo-preview-$VERSION-live-amd64.iso"

# xorriso and its libs (libburn, libisofs) live in the extracted
# prefix, not on the loader path — pass LD_LIBRARY_PATH only to
# xorriso so the system python/pip are unaffected.
xorriso() { env LD_LIBRARY_PATH="$TOOLS/usr/lib/x86_64-linux-gnu" "$TOOLS/usr/bin/xorriso" "$@"; }

# The 21 casper squashfs layers of the Ubuntu 24.04.5.1 base ISO,
# in alphabetical order (verified with xorriso -find /casper on
# the base ISO). This list is ONLY the presence check in step 2:
# every layer must be present in the base ISO. It is NOT the
# merge order. (Run 6, 2026-11-12: the build used to merge all 21
# alphabetically, last wins, on the assumption that casper does
# the same — that assumption is WRONG. Casper mounts only the
# dependency chain of LAYERFS_PATH, derived by stripping
# dot-suffixes (minimal -> minimal.standard ->
# minimal.standard.live); the language layers are never mounted
# at boot, so they must never override the live layer in the
# merge. The alphabetical merge let minimal.standard.zh's debconf
# database (152 templates, no passwd/*) override the live
# layer's (319 templates incl. passwd/*), so casper created no
# live user and GDM fell back to the initial-setup session.)
# The merge order is MERGE_LAYERS below: the boot chain in
# dependency order, live layer topmost.
CASPER_LAYERS=(
    minimal.de.squashfs
    minimal.en.squashfs
    minimal.es.squashfs
    minimal.fr.squashfs
    minimal.it.squashfs
    minimal.no-languages.squashfs
    minimal.pt.squashfs
    minimal.ru.squashfs
    minimal.squashfs
    minimal.standard.de.squashfs
    minimal.standard.en.squashfs
    minimal.standard.es.squashfs
    minimal.standard.fr.squashfs
    minimal.standard.it.squashfs
    minimal.standard.live.squashfs
    minimal.standard.no-languages.squashfs
    minimal.standard.pt.squashfs
    minimal.standard.ru.squashfs
    minimal.standard.squashfs
    minimal.standard.zh.squashfs
    minimal.zh.squashfs
)

# The merge inputs: the boot chain ONLY, in dependency order
# (lowest first). This is exactly what casper mounts at boot in
# a stock live session (setup_overlay() derives the chain from
# LAYERFS_PATH by stripping dot-suffixes — proven in run 3's
# initrd analysis). The 18 language layers are excluded: they
# are never mounted at boot, so including them can only let a
# language layer override the live layer on a shared path
# (run 6: debconf). The installed system therefore has no
# language packs; that matches the stock live session, which
# mounts the same three layers. The merge feeds fuse-overlayfs
# the REVERSE order as lowerdir, so the live layer is the
# topmost lower layer, and merge-plan.py takes the same list
# in the same order (last wins) — the plan and the overlay
# must agree, or the file-list diff fails the build.
MERGE_LAYERS=(
    minimal.squashfs
    minimal.standard.squashfs
    minimal.standard.live.squashfs
)

need() { command -v "$1" >/dev/null 2>&1 || [ -x "$1" ] || { echo "missing: $1" >&2; exit 1; }; }

need "$TOOLS/usr/bin/xorriso"
need mksquashfs
need unsquashfs
need rsync
need dpkg-deb
need python3
need sha256sum
need md5sum
need fusermount3

for f in "$BASE_ISO" "$CC_DEB" "$CC_RELEASE_JSON" "$CC_RELEASE_SIG" \
         "$CC_PUBLISHER_KEY" "$CC_VERIFY_SCRIPTS/ubuntu_release.py" \
         "$CC_VERIFY_SCRIPTS/check_ubuntu_deb.py" \
         "$REPO_ROOT/installer/grub.cfg" \
         "$REPO_ROOT/installer/assets/pulpo-uefi-boot-splash.bmp"; do
  [ -f "$f" ] || { echo "missing input: $f" >&2; exit 1; }
done

echo "== Pulpo Preview live ISO build =="
echo "base ISO : $BASE_ISO"
echo "work dir : $WORK"
echo "output   : $OUT"
echo "repo     : $REPO_ROOT"

mkdir -p "$WORK"
cd "$WORK"

# 1. Verify the base ISO against Ubuntu's published SHA256SUMS.
echo "== [1/8] verifying base ISO =="
grep "$(basename "$BASE_ISO")" "$WORK/SHA256SUMS" | (cd "$WORK" && sha256sum -c -)

# 2. Extract the ISO tree (boot files + squashfs layers). The tree is
#    only a source for the files the build changes; the rebuild
#    (step 7) copies everything else straight from the base ISO.
echo "== [2/8] extracting base ISO =="
ISO_ROOT="$WORK/iso-root"
# The extracted tree is read-only (dirs 0555, files 0444, as on the
# ISO); make any previous tree writable before removing it, and the
# fresh tree writable so later steps can patch and delete files.
[ -d "$ISO_ROOT" ] && { chmod -R u+w "$ISO_ROOT" 2>/dev/null || true; rm -rf "$ISO_ROOT"; }
mkdir -p "$ISO_ROOT"
xorriso -osirrox on -indev "$BASE_ISO" -extract / "$ISO_ROOT"
chmod -R u+w "$ISO_ROOT"
# Record the base boot chain for the build log (the rebuild replays
# it verbatim; this is evidence, not an input to the rebuild).
xorriso -indev "$BASE_ISO" -report_el_torito as_mkisofs > "$WORK/eltorito.txt"
for layer in "${CASPER_LAYERS[@]}"; do
  [ -s "$ISO_ROOT/casper/$layer" ] || { echo "layer missing from base ISO: $layer" >&2; exit 1; }
done
# filesystem.size is the installed-size record for the whole live
# system (sum of the layers); step 5 updates it by DELTA.
OLD_FS_SIZE=$(cat "$ISO_ROOT/casper/filesystem.size")
echo "layers: ${#CASPER_LAYERS[@]} present; filesystem.size: $OLD_FS_SIZE"

# 3. Merge the boot chain (3 layers) into one rootfs (plain directory).
#    The layers are diffs; only the overlay composition is a
#    coherent filesystem, and only the overlay resolves the
#    whiteouts that break Calamares' rsync (error 13 — see
#    installer/DISK-INSTALLER.md "The whiteout failure"). A kernel
#    overlay mount is not available (unprivileged user namespaces
#    are blocked on the build VM), so the composition uses FUSE:
#    squashfuse mounts each layer, fuse-overlayfs composes them.
#    Both are fetched as .debs and extracted into a prefix, the
#    same rootless pattern as the other ISO tooling.
#    The overlay is READ-ONLY in this build. A non-root user
#    cannot write through a FUSE overlay whose lower layers are
#    root-owned (the kernel rejects mkdir/open in root-owned 0755
#    lower dirs — build #2 died on exactly that), so the merged
#    view is copied with rsync into a plain directory the build
#    user owns, and the customisation (step 4) runs on that.
#    rsync cannot read the root-only paths through the overlay
#    (/etc/shadow, /boot/vmlinuz, the snap files, /root, ...);
#    installer/merge-plan.py enumerates them from the layers'
#    metadata and the build extracts them directly from the
#    archives (unsquashfs reads the archive bytes). The merge is
#    verified four ways: the overlay holds zero whiteouts, the
#    plain directory holds zero whiteouts, the plain directory's
#    file list matches the expected composition from the layers'
#    metadata exactly, and the debconf database is the live
#    layer's (templates.dat holds the passwd/* templates).
#    Proven by hand 2026-11-12: the two-layer overlay
#    (minimal.no-languages over minimal.en) drops
#    usr/share/help-langpack, the directory the fatal whiteout
#    deletes, and the merged view holds zero 0/0 whiteouts.
echo "== [3/8] merging the boot chain (3 layers) into one rootfs =="
# The apt package lists live in /tmp, so a reboot wipes them; a
# build that assumes a previous run populated them dies silently
# at the closure computations below (empty closure -> grep finds
# nothing -> pipefail under set -e). Populate them here when
# missing instead of assuming. (Moved here from step 4e: the
# FUSE fetch below needs the lists too.)
EXTRA_DEBS="$WORK/extra-debs"
mkdir -p "$EXTRA_DEBS"
APT_GET="apt-get -o Dir::State=/tmp/apt-state -o Dir::Cache=/tmp/apt-cache -o Dir::Etc::sourcelist=/dev/null -o Dir::Etc::sourceparts=/etc/apt/sources.list.d"
APT_CACHE="apt-cache -o Dir::State=/tmp/apt-state -o Dir::Cache=/tmp/apt-cache -o Dir::Etc::sourcelist=/dev/null -o Dir::Etc::sourceparts=/etc/apt/sources.list.d"
if [ ! -d /tmp/apt-state/lists ] || [ -z "$(ls -A /tmp/apt-state/lists 2>/dev/null)" ]; then
  echo "  [apt] populating package lists (apt-get update)"
  mkdir -p /tmp/apt-state/lists/partial /tmp/apt-cache/archives/partial
  $APT_GET update > /tmp/apt-update.log 2>&1 || { echo "apt-get update failed; see /tmp/apt-update.log" >&2; exit 1; }
fi
# Fetch + extract the FUSE merge tools (cached in $WORK; the
# download is skipped when the .debs are already there).
FUSE_DEBS="$WORK/fuse-debs"
FUSE_ROOT="$WORK/fuse-tools"
mkdir -p "$FUSE_DEBS" "$FUSE_ROOT"
for pkg in squashfuse fuse-overlayfs fuse3; do
  deb=$(ls "$FUSE_DEBS/${pkg}_"*.deb 2>/dev/null | head -1 || true)
  if [ -z "$deb" ]; then
    (cd "$FUSE_DEBS" && $APT_GET download "$pkg" > /dev/null 2>&1) \
      || { echo "could not fetch $pkg .deb (needs network + apt lists)" >&2; exit 1; }
    deb=$(ls "$FUSE_DEBS/${pkg}_"*.deb 2>/dev/null | head -1 || true)
  fi
  [ -n "$deb" ] || { echo "missing .deb for $pkg" >&2; exit 1; }
  dpkg-deb -x "$deb" "$FUSE_ROOT"
done
[ -x "$FUSE_ROOT/usr/bin/squashfuse" ] || { echo "squashfuse missing after unpack" >&2; exit 1; }
[ -x "$FUSE_ROOT/usr/bin/fuse-overlayfs" ] || { echo "fuse-overlayfs missing after unpack" >&2; exit 1; }
# fusermount3 ships with the system fuse3 package; fall back to
# the extracted one if the system one is absent.
FUSERMOUNT="$(command -v fusermount3 || echo "$FUSE_ROOT/usr/bin/fusermount3")"
[ -x "$FUSERMOUNT" ] || { echo "fusermount3 missing" >&2; exit 1; }
export PATH="$FUSE_ROOT/usr/bin:$PATH"
MERGE="$WORK/merge"
rm -rf "$MERGE"
mkdir -p "$MERGE/layers" "$MERGE/upper" "$MERGE/work" "$MERGE/view"
# Unmount everything on exit (success or failure under set -e),
# so a failed build never leaves FUSE mounts behind. fusermount
# on a non-mount fails harmlessly; the || true keeps the trap
# from failing the build.
cleanup_merge() {
  "$FUSERMOUNT" -u "$MERGE/view" 2>/dev/null || true
  for d in "$MERGE"/layers/*; do
    [ -d "$d" ] && "$FUSERMOUNT" -u "$d" 2>/dev/null || true
  done
}
trap cleanup_merge EXIT
# Mount the boot chain in dependency order (lowest first); the
# overlay lowerdir is the reverse (live layer first = topmost,
# as casper mounts it at boot).
LOWERDIR=""
i=0
for layer in "${MERGE_LAYERS[@]}"; do
  i=$((i + 1))
  mp="$MERGE/layers/$(printf '%02d' "$i")-${layer%.squashfs}"
  mkdir -p "$mp"
  squashfuse "$ISO_ROOT/casper/$layer" "$mp" \
    || { echo "squashfuse mount failed: $layer" >&2; exit 1; }
  LOWERDIR="$mp:$LOWERDIR"
done
LOWERDIR="${LOWERDIR%:}"
# Count the whiteouts the merge must resolve (overlay whiteouts
# are char devices 0/0 in the layers); the merged view must hold
# none of them. The scan is allowed to hit traversal errors; those
# are logged, not a silent build death (see the merged-view scan
# below for why the stderr must not be discarded).
find "$MERGE"/layers -type c -exec stat -c '%t,%T' {} + > "$WORK/.layer-chardevs.txt" 2>"$WORK/.layer-chardevs.err" || true
if [ -s "$WORK/.layer-chardevs.err" ]; then
  echo "warning: layer char-device scan hit errors (see $WORK/.layer-chardevs.err)"
  head -5 "$WORK/.layer-chardevs.err"
fi
WHITEOUTS=$(grep -c '^0,0$' "$WORK/.layer-chardevs.txt" || true)
echo "whiteout char devices in the layers: $WHITEOUTS"
fuse-overlayfs -o "lowerdir=$LOWERDIR,upperdir=$MERGE/upper,workdir=$MERGE/work" "$MERGE/view" \
  || { echo "fuse-overlayfs mount failed" >&2; exit 1; }
ROOTFS="$MERGE/view"
# Verify the merge resolved the whiteouts. Count ONLY overlay
# whiteouts (char devices 0/0): the view legitimately holds the
# static /dev nodes (null, zero, console, tty, ... — real
# major/minor, not whiteouts), so counting every char device
# would fail the build on a correct merge. The scan itself is
# allowed to hit traversal errors (a FUSE read can fail on the
# base image's known-bad hardlink inode); those are logged as a
# warning, not a silent build death — the count is the gate, and
# the boot test + install test are the real verification.
find "$ROOTFS" -type c -exec stat -c '%t,%T' {} + > "$WORK/.chardevs.txt" 2>"$WORK/.chardevs.err" || true
if [ -s "$WORK/.chardevs.err" ]; then
  echo "warning: char-device scan hit errors (see $WORK/.chardevs.err); whiteout count may be incomplete"
  head -5 "$WORK/.chardevs.err"
fi
MERGED_WHITEOUTS=$(grep -c '^0,0$' "$WORK/.chardevs.txt" || true)
[ "$MERGED_WHITEOUTS" -eq 0 ] || { echo "merged view still holds $MERGED_WHITEOUTS whiteouts (not resolved)" >&2; exit 1; }
# NOTE: there is deliberately NO help-langpack check here.
# The old check ("absent or empty") proved the fatal whiteout
# from minimal.no-languages was resolved — but that layer is
# not in the boot chain, so its whiteout never enters this
# merge. The chain's bottom layer (minimal) legitimately holds
# 3,917 help-langpack files, which the stock live session
# mounts too; requiring the directory empty would fail a
# correct chain-only merge. The file-list diff below is the
# gate that proves the merged view is exactly the chain.
echo "merge verified: $WHITEOUTS whiteouts resolved, 0 whiteouts in the merged view"
# Copy the merged view into a plain directory the build user
# owns. The overlay is read-only for a non-root user (see the
# step-3 header): every write in step 4 goes to this directory,
# never to the overlay. rsync -aH preserves permissions and
# hardlinks; ownership is NOT preserved (a non-root rsync cannot
# chown) — the files land owned by the build user. Step 5
# restores the layers' true ownership from
# installer/merge-plan.py's ownership.txt with a mksquashfs
# pseudo-file (see installer/ownership-pseudo.py); -all-root
# alone would flatten every file to root:root, which broke
# run 7 (the D-Bus launch helper lost its messagebus group,
# so the system bus could not spawn the KPMCore helper and
# Calamares saw no disk).
PLAN="$WORK/merge-plan"
rm -rf "$PLAN"
mkdir -p "$PLAN"
LAYER_PATHS=()
for layer in "${MERGE_LAYERS[@]}"; do LAYER_PATHS+=("$ISO_ROOT/casper/$layer"); done
python3 "$REPO_ROOT/installer/merge-plan.py" "$PLAN" "${LAYER_PATHS[@]}" \
  || { echo "merge-plan.py failed" >&2; exit 1; }
ROOTFS="$WORK/rootfs"
rm -rf "$ROOTFS"
mkdir -p "$ROOTFS"
echo "  [3] rsync merged view -> plain directory (excludes: $(wc -l < "$PLAN/excludes.txt") root-only paths)"
rsync -aH --exclude-from="$PLAN/excludes.txt" "$MERGE/view/" "$ROOTFS/" \
  > "$WORK/rsync-merge.log" 2>&1 \
  || { echo "rsync of the merged view failed; see $WORK/rsync-merge.log" >&2; tail -20 "$WORK/rsync-merge.log" >&2; exit 1; }
# A clean rsync is itself a gate: any error (e.g. a path the plan
# missed) lands in the log. The log must be empty apart from the
# summary rsync prints.
if grep -q . "$WORK/rsync-merge.log"; then
  echo "rsync log is not empty (expected a clean copy):" >&2
  cat "$WORK/rsync-merge.log" >&2
  exit 1
fi
# Fix up the root-only paths rsync excluded, straight from the
# archives (unsquashfs reads the archive bytes, bypassing the
# permission checks the overlay enforces). Files: one unsquashfs
# call per providing layer, into a FRESH staging directory, then
# cp -a into the rootfs. Staging is required: targeted
# unsquashfs extraction creates NOTHING when the file's parent
# directory already exists in the destination (proven by hand —
# it skips the whole subtree under an existing directory), and
# the rootfs already holds the parent dirs from the rsync. cp -a
# merges into existing directories, which is what is wanted.
# The exit code is not the gate — unsquashfs returns 2 for
# benign "directory already exists" notes — the existence check
# after each file is.
echo "  [3] fixing up $(wc -l < "$PLAN/fixup-files.txt") root-only files from the archives"
STAGE_FILES="$WORK/fixup-stage-files"
for layer in "${MERGE_LAYERS[@]}"; do
  files=$(awk -v L="$layer" -F'\t' '$2 == L {print $1}' "$PLAN/fixup-files.txt" || true)
  [ -n "$files" ] || continue
  rm -rf "$STAGE_FILES"; mkdir -p "$STAGE_FILES"
  # shellcheck disable=SC2086 (word-splitting the file list is intended)
  unsquashfs -ignore-errors -d "$STAGE_FILES" "$ISO_ROOT/casper/$layer" $files \
    >> "$WORK/fixup.log" 2>&1 || true
  cp -a "$STAGE_FILES/." "$ROOTFS/"
done
rm -rf "$STAGE_FILES"
while IFS="$(printf '\t')" read -r fpath layer; do
  [ -n "$fpath" ] || continue
  [ -e "$ROOTFS/$fpath" ] || [ -L "$ROOTFS/$fpath" ] \
    || { echo "fixup file missing after extraction: $fpath (from $layer)" >&2; exit 1; }
done < "$PLAN/fixup-files.txt"
# Fix up the root-only directories, layer by layer in overlay
# order. For each layer: delete that layer's whiteouts under the
# directory (a whiteout deletes lower-layer content, so it must
# be applied before the layer's own files land), then extract
# the directory from that layer into staging and merge the
# staging tree into the rootfs with cp -a. Staging is required:
# targeted unsquashfs extraction SKIPS a directory that already
# exists in the destination (proven by hand), so the directory
# must not exist in the destination when it is extracted — the
# staging directory is fresh for every layer, and cp -a merges
# into the existing rootfs directory. A directory empty in every
# layer is created explicitly with its stored mode.
echo "  [3] fixing up $(wc -l < "$PLAN/fixup-dirs.txt") root-only directories from the archives"
STAGE="$WORK/fixup-stage"
while IFS="$(printf '\t')" read -r dpath dmode dlayers; do
  [ -n "$dpath" ] || continue
  for layer in "${MERGE_LAYERS[@]}"; do
    # Whiteouts this layer places under the directory.
    while IFS="$(printf '\t')" read -r wlayer wpath; do
      [ "$wlayer" = "$layer" ] || continue
      case "$wpath" in
        "$dpath"|"$dpath"/*) rm -rf "$ROOTFS/$wpath" ;;
      esac
    done < "$PLAN/fixup-whiteouts.txt"
    # Does this layer hold anything under the directory?
    case ",$dlayers," in *",$layer,"*) ;; *) continue ;; esac
    rm -rf "$STAGE"; mkdir -p "$STAGE"
    unsquashfs -ignore-errors -d "$STAGE" "$ISO_ROOT/casper/$layer" "$dpath" \
      >> "$WORK/fixup.log" 2>&1 || true
    if [ -e "$STAGE/$dpath" ]; then
      mkdir -p "$ROOTFS/$dpath"
      cp -a "$STAGE/$dpath/." "$ROOTFS/$dpath/"
    fi
  done
  if [ ! -e "$ROOTFS/$dpath" ]; then
    mkdir -p "$ROOTFS/$dpath"
    chmod "$dmode" "$ROOTFS/$dpath"
  fi
  [ -d "$ROOTFS/$dpath" ] || { echo "fixup directory missing after extraction: $dpath" >&2; exit 1; }
done < "$PLAN/fixup-dirs.txt"
rm -rf "$STAGE"
# Verify the plain directory is the merge, three ways. (a) No
# 0/0 whiteouts. The scan is allowed to hit traversal errors:
# the plain directory holds var/lib/snapd/void at mode 0111
# (execute-only, no read even for the owner — it is an empty
# dir, so nothing hides under it), and find reports that as a
# permission error. The errors are logged as a warning, not a
# silent build death — the count is the gate, and the file-list
# diff below is the definitive check.
find "$ROOTFS" -type c -exec stat -c '%t,%T' {} + > "$WORK/.rootfs-chardevs.txt" 2>"$WORK/.rootfs-chardevs.err" || true
if [ -s "$WORK/.rootfs-chardevs.err" ]; then
  echo "warning: rootfs char-device scan hit errors (see $WORK/.rootfs-chardevs.err); whiteout count may be incomplete"
  head -5 "$WORK/.rootfs-chardevs.err"
fi
ROOTFS_WHITEOUTS=$(grep -c '^0,0$' "$WORK/.rootfs-chardevs.txt" || true)
[ "$ROOTFS_WHITEOUTS" -eq 0 ] || { echo "plain rootfs still holds $ROOTFS_WHITEOUTS whiteouts" >&2; exit 1; }
# (b) The file list must match the expected composition from the
# layers' metadata exactly — this catches a missed fixup, a
# skipped hardlink, or an rsync gap. LC_ALL=C so the byte order
# matches the plan's (UTF-8 byte order == code-point order).
# find's stderr is kept: var/lib/snapd/void (0111, no read) is
# expected to error and hides nothing (it is empty); any other
# traversal error is a warning, not a failure — the diff is the
# gate. The || true is load-bearing: find exits 1 on the void/
# traversal error, and under pipefail + set -e that would kill
# the build SILENTLY right here (builds #6 and #7 died exactly
# this way, after the list file was already written).
(cd "$ROOTFS" && LC_ALL=C find . -printf '%P\n' 2>"$WORK/.merged-list.err" | grep -v '^$' | LC_ALL=C sort > "$WORK/.merged-list.txt") || true
if [ -s "$WORK/.merged-list.err" ]; then
  echo "warning: merged file-list scan hit errors (see $WORK/.merged-list.err)"
  head -5 "$WORK/.merged-list.err"
fi
if ! diff -q "$PLAN/expected-list.txt" "$WORK/.merged-list.txt" > /dev/null 2>&1; then
  echo "plain rootfs file list differs from the expected layer composition:" >&2
  diff "$PLAN/expected-list.txt" "$WORK/.merged-list.txt" | head -20 >&2
  exit 1
fi
# (c) The debconf database must be the live layer's. The boot
# chain's topmost layer (minimal.standard.live) is the only layer
# carrying the passwd/* templates casper's user creation needs
# (live: 319 templates, 16 passwd/*; minimal: 150/0;
# minimal.standard: 161/0 — verified from the base ISO).
# Run 6 died on exactly this: the alphabetical merge took
# minimal.standard.zh's database (152 templates, no passwd/*),
# so no live user was created and GDM fell back to the
# initial-setup session. The count is the gate: the file-list
# diff above already proves the merged file is the topmost
# layer's copy, and this proves that copy is the live layer's
# debconf.
TEMPLATE_NAMES=$(grep -c '^Name: ' "$ROOTFS/var/cache/debconf/templates.dat")
PASSWD_NAMES=$(grep -c '^Name: passwd/' "$ROOTFS/var/cache/debconf/templates.dat")
[ "$TEMPLATE_NAMES" -ge 300 ] && [ "$PASSWD_NAMES" -gt 0 ] \
  || { echo "debconf database is not the live layer's ($TEMPLATE_NAMES templates, $PASSWD_NAMES passwd/*); want >=300 templates and passwd/* present (run 6)" >&2; exit 1; }
echo "plain rootfs verified: 0 whiteouts, file list matches the layers ($(wc -l < "$PLAN/expected-list.txt") paths), debconf is the live layer's ($TEMPLATE_NAMES templates, $PASSWD_NAMES passwd/*)"
# The FUSE mounts are no longer needed (the plain directory is
# the rootfs from here on); release them now, the EXIT trap is
# the safety net, not the plan.
cleanup_merge
trap - EXIT
# Record du of the pristine merged rootfs: the .size records are
# NOT plain du (on 24.04.5.1 filesystem.size is ~2x the du of the
# extracted tree), so step 5 updates them by DELTA, preserving
# whatever convention the image was built with. du on the plain
# directory has no traversal errors (the build user owns
# everything); the exit code is tolerated anyway, and the total
# is parsed out. Both du runs use the same method, so any
# convention cancels out of the delta.
DU_OUT=$(du -sx --block-size=1 "$ROOTFS" 2>/dev/null || true)
OLD_DU=${DU_OUT%%$'\t'*}
[ -n "$OLD_DU" ] || { echo "du produced no total for the merged rootfs" >&2; exit 1; }
echo "pristine merged du: $OLD_DU (filesystem.size file: $OLD_FS_SIZE)"

# 4. Customise the rootfs (files only — no chroot, no apt, no dpkg).
echo "== [4/8] customising live rootfs =="

# 4a. Control Center .deb (no maintainer scripts; dpkg-deb -x is exact).
echo "  [4a] Control Center .deb"
dpkg-deb -x "$CC_DEB" "$ROOTFS"
[ -x "$ROOTFS/usr/bin/pulpo-control-center" ] || { echo "CC launcher missing after unpack" >&2; exit 1; }

# Collect the CC dependencies the base image lacks; step 4e adds
# them from their .debs (python3-tk and libxcb-cursor0 on 24.04.5.1).
echo "  [4a] checking CC dependencies against the base manifest"
DEPS=$(dpkg-deb -f "$CC_DEB" Depends | tr ',' '\n' | sed 's/([^)]*)//g; s/^ *//; s/ *$//' | grep -v '^$')
MISSING=""
for dep in $DEPS; do
  grep -q "^${dep}:\?\(amd64\)\?$(printf '\t')" "$ISO_ROOT/casper/filesystem.manifest" \
    || MISSING="$MISSING $dep"
done
if [ -n "$MISSING" ]; then
  echo "  [4a] base image lacks CC dependencies (added in 4e):$MISSING"
else
  echo "  [4a] all CC dependencies present in the base image"
fi

# 4b. pulpo package from this worktree (pip --target) + entry points.
echo "  [4b] pulpo package from $REPO_ROOT"
python3 -m pip install --target="$ROOTFS/usr/local/lib/python3.12/dist-packages" \
  --no-deps --no-build-isolation "$REPO_ROOT" > "$WORK/pip-pulpo.log" 2>&1
[ -f "$ROOTFS/usr/local/lib/python3.12/dist-packages/pulpo/cli.py" ] \
  || { echo "pulpo install failed; see $WORK/pip-pulpo.log" >&2; exit 1; }
mkdir -p "$ROOTFS/usr/local/bin"
mv "$ROOTFS/usr/local/lib/python3.12/dist-packages/bin/"* "$ROOTFS/usr/local/bin/"
rmdir "$ROOTFS/usr/local/lib/python3.12/dist-packages/bin"
[ -x "$ROOTFS/usr/local/bin/pulpo" ] || { echo "pulpo entry point missing" >&2; exit 1; }

# 4c. installer/ skeleton -> /usr/share/pulpo-installer/ (reference +
#     build docs, so the live image carries how it was made).
echo "  [4c] installer/ skeleton"
mkdir -p "$ROOTFS/usr/share/pulpo-installer"
cp -r "$REPO_ROOT/installer/assets" "$ROOTFS/usr/share/pulpo-installer/assets"
for f in grub.cfg installer-manifest.json validate_config.py \
         pulpo-preview-config.example.json README.md build-iso.sh \
         boot-test.sh install-test.sh make_live_grub_cfg.py BOOT-TEST.md \
         DISK-INSTALLER.md INSTALL-TEST.md; do
  cp "$REPO_ROOT/installer/$f" "$ROOTFS/usr/share/pulpo-installer/$f"
done

# 4d. Autostart Control Center on live login; desktop README in skel.
echo "  [4d] autostart + desktop README"
mkdir -p "$ROOTFS/etc/xdg/autostart" "$ROOTFS/etc/skel/Desktop"
cat > "$ROOTFS/etc/xdg/autostart/pulpo-control-center.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Pulpo Control Center
Exec=/usr/bin/pulpo-control-center
Comment=Pulpo Preview governance control center (live session)
X-GNOME-Autostart-enabled=true
EOF
cat > "$ROOTFS/etc/skel/Desktop/PULPO-PREVIEW-README.txt" <<'EOF'
Pulpo Preview 0.1.0 — live session
===================================
This is a LIVE session: nothing is installed to disk, and nothing
here writes to your hard drive unless you choose to.

- Pulpo Control Center should have opened automatically. If not,
  launch it from the applications menu.
- Guided Setup is the button on the Control Center System page
  (Diagnostics tab). It writes the customer config
  (pulpo.control-center-customer-config.v1).
- Disk installer: the "Install Pulpo Preview" icon on the desktop
  installs to disk (erase-disk install, UEFI). It carries the
  Guided Setup config you made here through to the installed
  system — run Guided Setup first if you want the installed
  system configured, or install without a config and use Guided
  Setup on the installed system instead.
- Network: no gateway is configured by default. An unset gateway
  (no default route, no internet) is a valid, deliberate choice.
- Storage honesty: local evidence is kept at most 24 hours, and
  Pulpo is NOT responsible for your data, backups, or storage.

"Give AI intelligence. Never give it authority."
YOUR HARDWARE. YOUR DATA. YOUR RULES.
EOF

# 4e. CC dependencies missing from the base image, added from
#     their .debs (dpkg-deb -x; no maintainer scripts run, no apt
#     inside the image). The closure of each missing package is
#     computed so a missing dep's own missing deps come along; any
#     package already in the base image is skipped, never
#     overwritten. Fetched with apt-get download if not already in
#     $WORK/extra-debs or the apt cache.
echo "  [4e] missing CC dependencies from .debs"
# The .deb fetch helpers (EXTRA_DEBS, APT_GET, APT_CACHE) are
# defined in step 3, which also populates the package lists.
if [ -n "$MISSING" ]; then
  CLOSURE=$($APT_CACHE depends --recurse --no-recommends --no-suggests --no-conflicts --no-breaks --no-replaces --no-enhances $MISSING 2>/dev/null | grep "^[a-z0-9]" | sort -u || true)
  [ -n "$CLOSURE" ] || { echo "apt closure for $MISSING is empty -- package lists missing?" >&2; exit 1; }
  UNPACKED=""
  for pkg in $CLOSURE; do
    if grep -q "^${pkg}:\?\(amd64\)\?$(printf '\t')" "$ISO_ROOT/casper/filesystem.manifest"; then
      continue  # already in the base image
    fi
    deb=$(ls "$EXTRA_DEBS/${pkg}_"*.deb /tmp/apt-cache/archives/${pkg}_*.deb 2>/dev/null | head -1 || true)
    if [ -z "$deb" ]; then
      (cd "$EXTRA_DEBS" && $APT_GET download "$pkg" > /dev/null 2>&1) \
        || { echo "could not fetch $pkg .deb (needs network + apt lists)" >&2; exit 1; }
      deb=$(ls "$EXTRA_DEBS/${pkg}_"*.deb 2>/dev/null | head -1 || true)
    fi
    [ -n "$deb" ] || { echo "missing .deb for $pkg" >&2; exit 1; }
    echo "  [4e] unpacking $pkg"
    dpkg-deb -x "$deb" "$ROOTFS"
    UNPACKED="$UNPACKED $deb"
  done
  # Verify every file all the .debs claim to install landed. This
  # accepts a symlink entry even if its target does not resolve
  # yet: a .deb may link into a package already in the base image
  # (e.g. dbus-x11/AUTHORS.gz -> ../libdbus-1-3/AUTHORS.gz).
  # The link itself is installed correctly and the target exists
  # in the merged rootfs; only a genuinely absent entry fails.
  # runs AFTER all of them are unpacked: packages cross-reference
  # each other (e.g. blt's changelog is a symlink into
  # tk8.6-blt2.5), so a per-package check would fail on entries
  # whose target only arrives with a later package.
  # (Loop reads from a file, not a pipe, so a failure exits the
  # build instead of only a subshell.)
  for deb in $UNPACKED; do
    dpkg-deb -c "$deb" | awk '{print $6}' | sed 's|^\./||' > "$WORK/.deb-files.txt"
    while read -r f; do
      [ -e "$ROOTFS/$f" ] || [ -L "$ROOTFS/$f" ] || { echo "missing after unpack: $f ($deb)" >&2; exit 1; }
    done < "$WORK/.deb-files.txt"
  done
  # The tkinter extension must be importable: the live session's
  # Control Center falls back to Tkinter if Qt is unavailable.
  [ -f "$ROOTFS/usr/lib/python3.12/lib-dynload/_tkinter.cpython-312-x86_64-linux-gnu.so" ] \
    || { echo "python3-tk did not land _tkinter in the rootfs" >&2; exit 1; }
  echo "  [4e] missing dependencies added"
else
  echo "  [4e] nothing missing"
fi

# 4f. Calamares disk installer (see installer/DISK-INSTALLER.md):
#     the calamares package + its missing dependencies from their
#     .debs (same dpkg-deb -x pattern as 4e; the calamares .deb has
#     no maintainer scripts), plus the Pulpo settings, branding,
#     module configs, the pulpo-config install script, and the
#     desktop launcher. The -gles Qt variants are excluded: the
#     desktop uses GLX, and unpacking both variants would
#     overwrite the same files.
echo "  [4f] Calamares disk installer"
CAL_CLOSURE=$($APT_CACHE depends --recurse --no-recommends --no-suggests --no-conflicts --no-breaks --no-replaces --no-enhances calamares 2>/dev/null | grep "^[a-z0-9]" | sort -u || true)
[ -n "$CAL_CLOSURE" ] || { echo "apt closure for calamares is empty -- package lists missing?" >&2; exit 1; }
CAL_UNPACKED=""
for pkg in $CAL_CLOSURE; do
  case "$pkg" in
    libqt5gui5-gles|libqt5quick5-gles) continue ;;  # GLX variant wins; see above
  esac
  if grep -q "^${pkg}:\?\(amd64\)\?$(printf '\t')" "$ISO_ROOT/casper/filesystem.manifest"; then
    continue  # already in the base image
  fi
  deb=$(ls "$EXTRA_DEBS/${pkg}_"*.deb /tmp/apt-cache/archives/${pkg}_*.deb 2>/dev/null | head -1 || true)
  if [ -z "$deb" ]; then
    (cd "$EXTRA_DEBS" && $APT_GET download "$pkg" > /dev/null 2>&1) \
      || { echo "could not fetch $pkg .deb (needs network + apt lists)" >&2; exit 1; }
    deb=$(ls "$EXTRA_DEBS/${pkg}_"*.deb 2>/dev/null | head -1 || true)
  fi
  [ -n "$deb" ] || { echo "missing .deb for $pkg" >&2; exit 1; }
  dpkg-deb -x "$deb" "$ROOTFS"
  CAL_UNPACKED="$CAL_UNPACKED $deb"
done
# Verify every file all the .debs claim to install landed (same
# reason as 4e: packages cross-reference each other, so the check
# runs after all of them are unpacked).
for deb in $CAL_UNPACKED; do
  dpkg-deb -c "$deb" | awk '{print $6}' | sed 's|^\./||' > "$WORK/.deb-files.txt"
  while read -r f; do
    [ -e "$ROOTFS/$f" ] || [ -L "$ROOTFS/$f" ] || { echo "missing after unpack: $f ($deb)" >&2; exit 1; }
  done < "$WORK/.deb-files.txt"
done
[ -x "$ROOTFS/usr/bin/calamares" ] || { echo "calamares binary missing after unpack" >&2; exit 1; }
echo "  [4f] calamares closure unpacked ($(echo $CAL_UNPACKED | wc -w) .debs)"

# Pulpo Calamares settings + branding + module configs.
echo "  [4f] Pulpo Calamares config + branding"
mkdir -p "$ROOTFS/etc/calamares"
cp "$REPO_ROOT/installer/calamares/settings.conf" "$ROOTFS/etc/calamares/settings.conf"
cp -r "$REPO_ROOT/installer/calamares/modules" "$ROOTFS/etc/calamares/modules"
cp -r "$REPO_ROOT/installer/calamares/branding" "$ROOTFS/etc/calamares/branding"
# Branding images are copies of installer/assets/ (the manifest
# is the source of truth; the welcome mockup is NOT used — see
# installer/calamares/branding/pulpo/branding.desc).
cp "$REPO_ROOT/installer/assets/pulpo-uefi-boot-logo-1024x1024.png" \
   "$ROOTFS/etc/calamares/branding/pulpo/logo.png"
cp "$REPO_ROOT/installer/assets/pulpo-uefi-boot-logo-1024x1024.png" \
   "$ROOTFS/etc/calamares/branding/pulpo/icon.png"
cp "$REPO_ROOT/installer/assets/pulpo-uefi-boot-splash-1920x1080.png" \
   "$ROOTFS/etc/calamares/branding/pulpo/welcome.png"
# The pulpo-config install script (run by the shellprocess module).
mkdir -p "$ROOTFS/usr/share/pulpo-installer/calamares"
cp "$REPO_ROOT/installer/calamares/pulpo-config-install.sh" \
   "$ROOTFS/usr/share/pulpo-installer/calamares/pulpo-config-install.sh"
chmod +x "$ROOTFS/usr/share/pulpo-installer/calamares/pulpo-config-install.sh"
# The boot-chain fixup scripts (run 10: strip the live-only
# casper package before initramfs, gate the built initrd, and
# write the GRUB prefix redirect stub after the bootloader).
# Each is run by its own shellprocess instance in settings.conf.
for s in remove-live-packages verify-initramfs grub-prefix-stub install-cc-deb; do
  cp "$REPO_ROOT/installer/calamares/$s.sh" \
     "$ROOTFS/usr/share/pulpo-installer/calamares/$s.sh"
  chmod +x "$ROOTFS/usr/share/pulpo-installer/calamares/$s.sh"
done
# Desktop launcher (live session): "Install Pulpo Preview".
# Release bundle for the install-cc-deb step: the signed
# Control Center .deb, its dependency .debs (the ones step
# 4e unpacked with dpkg-deb -x, so they exist in the target
# as files but are not registered in dpkg status), the
# signed release statement, its detached signature, the
# publisher public key, and the Control Center's own verify
# scripts. The installer step verifies the release and
# installs the whole bundle into the target, so the
# installed system carries a verifiable signed build
# instead of loose files.
mkdir -p "$ROOTFS/usr/share/pulpo-installer/control-center"
cp "$CC_DEB" "$ROOTFS/usr/share/pulpo-installer/control-center/"
for deb in ${UNPACKED:-}; do
  cp "$deb" "$ROOTFS/usr/share/pulpo-installer/control-center/"
done
cp "$CC_RELEASE_JSON" "$ROOTFS/usr/share/pulpo-installer/control-center/release.json"
cp "$CC_RELEASE_SIG" "$ROOTFS/usr/share/pulpo-installer/control-center/release.json.asc"
cp "$CC_PUBLISHER_KEY" "$ROOTFS/usr/share/pulpo-installer/control-center/publisher.gpg"
cp "$CC_VERIFY_SCRIPTS/ubuntu_release.py" "$CC_VERIFY_SCRIPTS/check_ubuntu_deb.py" \
   "$ROOTFS/usr/share/pulpo-installer/control-center/"
# Gate: the bundle must hold the Control Center .deb plus
# exactly the dependency .debs step 4e unpacked -- a missing
# dep .deb would make the target install fail on unmet
# dependencies, and an extra one would install a package
# the build never unpacked.
BUNDLE_COUNT=$(ls "$ROOTFS/usr/share/pulpo-installer/control-center"/*.deb 2>/dev/null | wc -l)
EXPECTED_COUNT=$((1 + $(echo ${UNPACKED:-} | wc -w)))
[ "$BUNDLE_COUNT" -eq "$EXPECTED_COUNT" ] \
  || { echo "control-center bundle holds $BUNDLE_COUNT .debs, expected $EXPECTED_COUNT" >&2; exit 1; }
mkdir -p "$ROOTFS/usr/share/applications" "$ROOTFS/etc/skel/Desktop"
cp "$REPO_ROOT/installer/calamares/install-pulpo.desktop" \
   "$ROOTFS/usr/share/applications/install-pulpo.desktop"
cp "$REPO_ROOT/installer/calamares/install-pulpo.desktop" \
   "$ROOTFS/etc/skel/Desktop/install-pulpo.desktop"
# The /etc/skel copy is the one GNOME shows on the live desktop,
# and it must be executable: GNOME treats a .desktop file on the
# Desktop as trusted -- and launches it on double-click -- only
# when it is executable. Shipped 0644 it shows a red-X
# "untrusted" icon and double-click does nothing (the Hyper-V
# run: the install never started until the file was right-clicked
# to "Allow Launching", which is exactly chmod +x). The
# /usr/share/applications copy needs no +x -- app-grid launchers
# are trusted by location.
chmod +x "$ROOTFS/etc/skel/Desktop/install-pulpo.desktop"
# Verify the pieces Calamares needs are all in place.
for f in etc/calamares/settings.conf \
         etc/calamares/modules/partition.conf \
         etc/calamares/modules/unpackfs.conf \
         etc/calamares/modules/shellprocess_pulpo-config.conf \
         etc/calamares/modules/shellprocess_remove-live.conf \
         etc/calamares/modules/shellprocess_verify-initramfs.conf \
         etc/calamares/modules/shellprocess_grub-prefix-stub.conf \
         etc/calamares/modules/shellprocess_install-cc-deb.conf \
         etc/calamares/branding/pulpo/branding.desc \
         etc/calamares/branding/pulpo/logo.png \
         etc/calamares/branding/pulpo/welcome.png \
         etc/calamares/branding/pulpo/show.qml \
         usr/share/pulpo-installer/calamares/pulpo-config-install.sh \
         usr/share/pulpo-installer/calamares/remove-live-packages.sh \
         usr/share/pulpo-installer/calamares/verify-initramfs.sh \
         usr/share/pulpo-installer/calamares/grub-prefix-stub.sh \
         usr/share/pulpo-installer/calamares/install-cc-deb.sh \
         usr/share/pulpo-installer/control-center/pulpo-control-center_0.1.0~ubuntu.preview.48+e3.2077631_amd64.deb \
         usr/share/pulpo-installer/control-center/release.json \
         usr/share/pulpo-installer/control-center/release.json.asc \
         usr/share/pulpo-installer/control-center/publisher.gpg \
         usr/share/pulpo-installer/control-center/ubuntu_release.py \
         usr/share/pulpo-installer/control-center/check_ubuntu_deb.py \
         usr/share/applications/install-pulpo.desktop; do
  [ -f "$ROOTFS/$f" ] || { echo "calamares file missing: $f" >&2; exit 1; }
done
[ -x "$ROOTFS/etc/skel/Desktop/install-pulpo.desktop" ] || { echo "live desktop launcher is not executable (GNOME would show it untrusted)" >&2; exit 1; }
grep -q "branding: pulpo" "$ROOTFS/etc/calamares/settings.conf" \
  || { echo "settings.conf does not select the pulpo branding" >&2; exit 1; }
grep -q "shellprocess@pulpo-config" "$ROOTFS/etc/calamares/settings.conf" \
  || { echo "settings.conf does not run the pulpo-config module" >&2; exit 1; }
grep -q "shellprocess@remove-live" "$ROOTFS/etc/calamares/settings.conf" \
  || { echo "settings.conf does not run the remove-live module" >&2; exit 1; }
grep -q "shellprocess@install-cc-deb" "$ROOTFS/etc/calamares/settings.conf" \
  || { echo "settings.conf does not run the install-cc-deb module" >&2; exit 1; }
grep -q "shellprocess@verify-initramfs" "$ROOTFS/etc/calamares/settings.conf" \
  || { echo "settings.conf does not run the verify-initramfs module" >&2; exit 1; }
grep -q "shellprocess@grub-prefix-stub" "$ROOTFS/etc/calamares/settings.conf" \
  || { echo "settings.conf does not run the grub-prefix-stub module" >&2; exit 1; }
echo "  [4f] Calamares config + branding in place"

# 4g. Suppress gnome-initial-setup (GIS) in the live session — and,
#     deliberately, on the installed system too (see below).
#     Run 5 (2026-11-12) proved the live session autostarts GIS
#     (/usr/libexec/gnome-initial-setup --existing-user, from
#     /etc/xdg/autostart/gnome-initial-setup-first-login.desktop),
#     whose Welcome page covers the desktop and never lets go, so
#     the desktop — and Calamares — is never reached. Stock casper
#     is supposed to prevent this: casper-bottom/52gnome_initial_setup
#     touches /home/$USERNAME/.config/gnome-initial-setup-done at
#     boot, and the autostart entry carries
#     AutostartCondition=unless-exists gnome-initial-setup-done.
#     In run 5 the marker was absent at session start (the exact
#     step where 52's touch fails to land is not determined from
#     static evidence — see installer/DISK-INSTALLER.md "The GIS
#     blocker" — so this fix does not rely on casper-bottom at all).
#     Two independent mechanisms, both verified below:
#       (a) bake the marker into /etc/skel, so every live-session
#           home (and every user created from skel) carries it;
#       (b) disable the autostart entry itself (Hidden=true), so
#           even if the marker is somehow absent, GIS cannot start.
#     Consequence (deliberate): the installed system also never
#     runs GIS on first login. That is correct for Pulpo — the
#     Pulpo wizard (Guided Setup) already collects timezone, NTP
#     and network, and GIS's first-run prompts would be redundant
#     and confusing on an appliance. A user can still run
#     gnome-initial-setup by hand; only the autostart is removed.
echo "  [4g] suppressing gnome-initial-setup"
mkdir -p "$ROOTFS/etc/skel/.config"
touch "$ROOTFS/etc/skel/.config/gnome-initial-setup-done"
[ -f "$ROOTFS/etc/skel/.config/gnome-initial-setup-done" ] \
  || { echo "GIS marker missing from skel" >&2; exit 1; }
GIS_DESKTOP="$ROOTFS/etc/xdg/autostart/gnome-initial-setup-first-login.desktop"
if [ -f "$GIS_DESKTOP" ]; then
  grep -q "^Hidden=true" "$GIS_DESKTOP" || printf '%s\n' "Hidden=true" >> "$GIS_DESKTOP"
  grep -q "^Hidden=true" "$GIS_DESKTOP" \
    || { echo "GIS autostart entry not disabled" >&2; exit 1; }
else
  echo "  [4g] warning: GIS autostart entry absent from the base image (marker alone suppresses GIS)"
fi
echo "  [4g] GIS suppressed (skel marker + autostart Hidden=true)"

# 5. Repack the merged rootfs as the single filesystem.squashfs
#    and refresh the size / checksum records.
echo "== [5/8] repacking merged rootfs as filesystem.squashfs =="
NEW_SQUASHFS="$WORK/new-filesystem.squashfs"
# Ownership: most files are root-owned, but a class of files
# depends on a non-root group (run 7, 2026-11-13: the D-Bus
# launch helper must be 4754 root:messagebus, gid 101, or the
# system bus cannot spawn the KPMCore helper and Calamares sees
# no disk). -all-root flattens those to root:root, so the build
# restores the layers' true ownership with a pseudo-file:
# installer/ownership-pseudo.py walks the staging rootfs and
# emits "m" (modify) entries for every path whose true
# owner:group (from installer/merge-plan.py's ownership.txt)
# is not root:root, plus a mode-correction entry for any path
# whose true mode differs from its staging mode. The mode in
# every entry is the map's mode — the layers are authoritative.
# -pseudo-override makes those entries win over -all-root
# (proven by hand: without it the entries are ignored). Files
# the build added (not in any layer) stay root:root via
# -all-root, as they should.
# A staging path whose true mode gives its owner no read
# permission (build #13: /var/lib/snapd/void, mode 0111) cannot
# be listed or read by the non-root user running this build, so
# mksquashfs silently drops it from the image — the first
# build #13 attempt failed the ownership gate on exactly that
# one path (and the path was already missing from the build #12
# image, which no gate yet existed to catch). Make such layer
# paths owner-readable in staging first; ownership-pseudo.py
# restores the true mode in the image, and the gate verifies it.
python3 "$REPO_ROOT/installer/staging-readable.py" "$PLAN/ownership.txt" "$ROOTFS" \
  || { echo "staging-readable.py failed" >&2; exit 1; }
python3 "$REPO_ROOT/installer/ownership-pseudo.py" "$PLAN/ownership.txt" "$ROOTFS" "$WORK/ownership.pseudo" \
  || { echo "ownership-pseudo.py failed" >&2; exit 1; }
mksquashfs "$ROOTFS" "$NEW_SQUASHFS" -comp xz -b 131072 -noappend -all-root -pseudo-override -pf "$WORK/ownership.pseudo" > "$WORK/mksquashfs.log" 2>&1
# Verify the GIS suppression (step 4g) actually landed in the
# squashfs, not just in the plain directory: extract the two
# files and check them. Targeted unsquashfs extraction into a
# fresh directory is reliable — the "skips an existing parent"
# quirk only bites when the parent already exists in the
# destination, and this directory is fresh for every build.
GIS_CHECK="$WORK/gis-check"; rm -rf "$GIS_CHECK"; mkdir -p "$GIS_CHECK"
unsquashfs -ignore-errors -d "$GIS_CHECK" "$NEW_SQUASHFS" \
  etc/skel/.config/gnome-initial-setup-done \
  etc/xdg/autostart/gnome-initial-setup-first-login.desktop \
  > "$WORK/gis-check.log" 2>&1 || true
[ -f "$GIS_CHECK/etc/skel/.config/gnome-initial-setup-done" ] \
  || { echo "GIS marker missing from new squashfs" >&2; exit 1; }
if [ -f "$GIS_CHECK/etc/xdg/autostart/gnome-initial-setup-first-login.desktop" ]; then
  grep -q "^Hidden=true" "$GIS_CHECK/etc/xdg/autostart/gnome-initial-setup-first-login.desktop" \
    || { echo "GIS autostart not disabled in new squashfs" >&2; exit 1; }
else
  echo "  [5] warning: GIS autostart entry absent from new squashfs (marker alone suppresses GIS)"
fi
rm -rf "$GIS_CHECK"
echo "GIS suppression verified in new squashfs (marker + autostart Hidden=true)"
# Ownership gate (run 7): the built squashfs must carry the
# layers' true owner:group:mode — at minimum the D-Bus launch
# helper must be 4754 root:messagebus (gid 101), or Calamares
# sees no disk. The gate compares every path in the ownership
# map against the built squashfs and requires step-4-added
# files to be root:root.
python3 "$REPO_ROOT/installer/ownership-gate.py" "$NEW_SQUASHFS" "$PLAN/ownership.txt" --rootfs "$ROOTFS" \
  || { echo "ownership gate failed" >&2; exit 1; }
# Update filesystem.size by DELTA (see step 3: the .size convention
# is not plain du, so the absolute du must not replace the file).
# Same du tolerance as step 3 (kept even though the plain
# directory has no unreadable dirs — the build user owns it).
DU_OUT=$(du -sx --block-size=1 "$ROOTFS" 2>/dev/null || true)
NEW_DU=${DU_OUT%%$'\t'*}
[ -n "$NEW_DU" ] || { echo "du produced no total for the customised rootfs" >&2; exit 1; }
NEW_FS_SIZE=$((OLD_FS_SIZE + NEW_DU - OLD_DU))
echo "merged du: $OLD_DU -> $NEW_DU; filesystem.size: $OLD_FS_SIZE -> $NEW_FS_SIZE"
# The FUSE mounts were already released at the end of step 3
# (the plain directory is the rootfs from there on); nothing to
# unmount here.

# 6. Pulpo boot menu: transform the base GRUB config (kernel lines
#    stay the base's, verbatim) and stage the splash BMP. This runs
#    before the record patching below because md5sum.txt needs the
#    hashes of these two files.
echo "== [6/8] generating live GRUB menu =="
python3 "$REPO_ROOT/installer/make_live_grub_cfg.py" \
  "$ISO_ROOT/boot/grub/grub.cfg" "$WORK/grub.cfg.new"
cp "$REPO_ROOT/installer/assets/pulpo-uefi-boot-splash.bmp" \
  "$WORK/pulpo-uefi-boot-splash.bmp"
# The repo's installer/grub.cfg should be this transform's output on
# this base; warn (don't fail) if they drifted, the ISO uses the
# generated file.
if ! diff -q "$REPO_ROOT/installer/grub.cfg" "$WORK/grub.cfg.new" > /dev/null 2>&1; then
  echo "WARNING: installer/grub.cfg differs from the generated menu;"
  echo "the ISO uses the generated file — regenerate the repo copy:"
  echo "  python3 installer/make_live_grub_cfg.py <base grub.cfg> installer/grub.cfg"
fi

# Patch the records that describe the changed files. All patched
# files are written to $WORK and mapped into the new ISO in step 7;
# the extracted tree itself is deleted right after.
python3 - "$ISO_ROOT" "$WORK" "$NEW_SQUASHFS" "$NEW_FS_SIZE" <<'PYEOF'
import hashlib, pathlib, sys
iso_root, work, new_sq, new_size = sys.argv[1:5]
new_size = int(new_size)
work = pathlib.Path(work)

def md5(path):
    return hashlib.md5(pathlib.Path(path).read_bytes()).hexdigest()

def sha256(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

# filesystem.size: the installed-size record for the whole live
# system, updated by the build's delta (see step 5).
fs_size_path = pathlib.Path(iso_root) / "casper" / "filesystem.size"
fs_size_path.write_text(str(new_size))

# casper/SHA256SUMS: drop the 21 layer entries, add the single
# merged filesystem.squashfs. Any non-squashfs line is kept.
sha_path = pathlib.Path(iso_root) / "casper" / "SHA256SUMS"
lines = [l for l in sha_path.read_text().splitlines()
         if not l.rsplit(" ", 1)[-1].lstrip("*").endswith(".squashfs")]
lines.append(f"{sha256(new_sq)} *filesystem.squashfs")
sha_path.write_text("\n".join(lines) + "\n")

# md5sum.txt at the ISO root: refresh the changed files, add the
# new splash BMP — and DROP the entries for the files the merge
# removes (the 21 layers and their per-layer .size/.manifest
# records), so the checksum file never references a file that is
# no longer in the ISO. Unchanged entries are copied verbatim.
md5_path = pathlib.Path(iso_root) / "md5sum.txt"
entries = {}
for line in md5_path.read_text().splitlines():
    digest, _, name = line.partition("  ")
    entries[name] = digest
for name in [n for n in entries if n.startswith("./casper/minimal.")]:
    del entries[name]
entries["./casper/filesystem.squashfs"] = md5(new_sq)
entries["./casper/filesystem.size"] = md5(fs_size_path)
entries["./casper/SHA256SUMS"] = md5(sha_path)
entries["./boot/grub/grub.cfg"] = md5(work / "grub.cfg.new")
entries["./boot/grub/pulpo-uefi-boot-splash.bmp"] = md5(
    work / "pulpo-uefi-boot-splash.bmp")
md5_path.write_text("".join(f"{d}  {n}\n" for n, d in sorted(entries.items())))
print("records patched")
PYEOF

# 6 (files) was generated above, before the record patching, so
# md5sum.txt could hash them. Nothing more to do here.

# The patched record files live in the tree; copy them out, then the
# whole extracted tree can go — the rebuild reads everything else
# straight from the base ISO.
for f in casper/SHA256SUMS casper/filesystem.size md5sum.txt; do
  cp "$ISO_ROOT/$f" "$WORK/$(basename "$f").new"
done
rm -rf "$ISO_ROOT"

# 7. Rebuild the ISO: replay the base image's boot chain verbatim
#    (BIOS eltorito + appended EFI system partition), replace the
#    21 layers with the single merged filesystem.squashfs, relabel
#    the volume. xorriso refuses to write -outdev over a file that
#    already holds data, so a previous build's output is removed
#    first.
echo "== [7/8] rebuilding ISO =="
rm -f "$OUT" "$OUT.sha256"
# Every file the merge replaces (the 21 layers + their per-layer
# .size/.manifest records) is listed from the base ISO itself, so
# the removal cannot drift from the base.
REMOVE_ARGS=()
while IFS= read -r f; do
  f="${f#\'}"; f="${f%\'}"
  REMOVE_ARGS+=(-rm "$f" --)
done < <(xorriso -indev "$BASE_ISO" -find /casper -name 'minimal.*' 2>/dev/null)
[ "${#REMOVE_ARGS[@]}" -gt 0 ] || { echo "no minimal.* files found in base ISO" >&2; exit 1; }
xorriso -indev "$BASE_ISO" -outdev "$OUT" \
  -volid "$VOLID" -boot_image any replay \
  "${REMOVE_ARGS[@]}" \
  -map "$NEW_SQUASHFS" /casper/filesystem.squashfs \
  -rm /boot/grub/grub.cfg -- \
  -map "$WORK/grub.cfg.new" /boot/grub/grub.cfg \
  -map "$WORK/pulpo-uefi-boot-splash.bmp" /boot/grub/pulpo-uefi-boot-splash.bmp \
  -rm /casper/SHA256SUMS -- \
  -map "$WORK/SHA256SUMS.new" /casper/SHA256SUMS \
  -rm /casper/filesystem.size -- \
  -map "$WORK/filesystem.size.new" /casper/filesystem.size \
  -rm /md5sum.txt -- \
  -map "$WORK/md5sum.txt.new" /md5sum.txt \
  > "$WORK/xorriso-rebuild.log" 2>&1
echo "rebuild log: $WORK/xorriso-rebuild.log"

# 8. Verify the output and write its checksum.
echo "== [8/8] verifying output =="
xorriso -indev "$OUT" -report_el_torito as_mkisofs > "$WORK/eltorito-out.txt"
grep -q "boot/grub/i386-pc/eltorito.img" "$WORK/eltorito-out.txt" \
  || { echo "output ISO lost its BIOS boot image" >&2; exit 1; }
grep -q "eltorito-alt-boot" "$WORK/eltorito-out.txt" \
  || { echo "output ISO lost its EFI alt boot image" >&2; exit 1; }
xorriso -indev "$OUT" -find /boot/grub -name 'pulpo-uefi-boot-splash.bmp' 2>/dev/null | grep -q splash \
  || { echo "splash BMP not in output ISO" >&2; exit 1; }
# The merged single layer must be there and no layered file may
# remain; the live session boots from the single file.
xorriso -indev "$OUT" -find /casper -name 'filesystem.squashfs' 2>/dev/null | grep -q filesystem \
  || { echo "filesystem.squashfs not in output ISO" >&2; exit 1; }
if xorriso -indev "$OUT" -find /casper -name 'minimal.*' 2>/dev/null | grep -q minimal; then
  echo "output ISO still holds layered minimal.* files" >&2; exit 1
fi
sha256sum "$OUT" > "$OUT.sha256"
echo "== done =="
ls -la "$OUT" "$OUT.sha256"
cat "$OUT.sha256"
echo "Next: installer/boot-test.sh --iso $OUT"
echo "Then: installer/install-test.sh --iso $OUT (disk-install test; see installer/INSTALL-TEST.md)"
echo "Note: the base ISO is kept at $BASE_ISO for rebuilds;"
echo "delete it by hand when the built ISO is no longer needed."
