#!/bin/bash
# Pulpo Preview live ISO builder — ROOTLESS remaster of an Ubuntu
# 24.04 LTS desktop ISO. No sudo, no chroot (the build VM has
# neither: sudo needs a password, unprivileged user namespaces are
# blocked). Everything below runs as the build user:
#   - ISO tooling (xorriso, qemu, ovmf) is fetched as .debs and
#     extracted with dpkg-deb -x into a prefix; nothing is installed
#     system-wide. (See installer/README.md for how to fetch them.)
#   - The live rootfs is the top squashfs layer of the base ISO
#     (casper/minimal.standard.live.squashfs), unpacked with
#     unsquashfs, customised by copying files in, and repacked with
#     mksquashfs. No package is installed inside the image with
#     dpkg/apt; .debs are unpacked with dpkg-deb -x (the Control
#     Center .deb has no maintainer scripts, so extraction is exact).
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
#     system is layered (minimal + minimal.standard +
#     minimal.standard.live + language layers). The live-session
#     layer (minimal.standard.live) is the one this build changes.
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
#     --cc-deb     Control Center .deb (default: the preview.47 .deb)
#
# Inputs (all from the repo / already-built artefacts — nothing invented):
#   - Control Center .deb: the preview.47 .deb, built from Control Center
#     main (945706c); CC origin/main has not moved past it, so the .deb
#     IS the current main build. Rebuild it with scripts/build_ubuntu_deb.py
#     in the Control Center repo if main moves.
#   - pulpo package: installed from this worktree with
#     pip install --target=<rootfs>/usr/local/lib/python3.12/dist-packages
#     --no-deps --no-build-isolation .  plus the entry-point scripts
#     moved to /usr/local/bin/. No new packaging system.
#   - installer/ skeleton from this repo (PR #121): GRUB menu (via
#     make_live_grub_cfg.py), BMP boot splash, manifest,
#     validate_config.py, example config.
#
# Outputs:
#   - pulpo-preview-0.1.0-live-amd64.iso + .sha256
#   - Live session only: first boot autologs into GNOME and autostarts
#     Pulpo Control Center; Guided Setup is the button on the System
#     page (Diagnostics tab). There is NO disk installer in this
#     milestone — the partitioner is still open.
set -euo pipefail

VERSION="0.1.0"
VOLID="PULPO-PREVIEW-0.1.0"
WORK="${WORK:-$HOME/pulpo-workspace/iso-build}"
TOOLS="${TOOLS:-$HOME/pulpo-workspace/iso-tools}"
BASE_ISO=""
OUT=""
CC_DEB="${CC_DEB:-$HOME/pulpo-workspace/Pulpo-Control-Center-Preview47/dist/pulpo-control-center_0.1.0~ubuntu.preview.47+e3.945706c_amd64.deb}"
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
LIVE_SQUASHFS="minimal.standard.live.squashfs"

need() { command -v "$1" >/dev/null 2>&1 || [ -x "$1" ] || { echo "missing: $1" >&2; exit 1; }; }

need "$TOOLS/usr/bin/xorriso"
need unsquashfs
need mksquashfs
need dpkg-deb
need python3
need sha256sum
need md5sum

for f in "$BASE_ISO" "$CC_DEB" "$REPO_ROOT/installer/grub.cfg" \
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
[ -s "$ISO_ROOT/casper/$LIVE_SQUASHFS" ] || { echo "live layer not found in base ISO" >&2; exit 1; }

# 3. Unpack the live-session squashfs layer. Ubuntu's image has a
#    known-bad hardlink inode that makes plain unsquashfs abort at
#    ~92%; -ignore-errors skips it and the build verifies the
#    extraction below instead of trusting the exit code.
echo "== [3/8] unpacking live layer $LIVE_SQUASHFS =="
ROOTFS="$WORK/rootfs-live"
chmod -R u+w "$ROOTFS" 2>/dev/null || true
rm -rf "$ROOTFS"
unsquashfs -ignore-errors -d "$ROOTFS" "$ISO_ROOT/casper/$LIVE_SQUASHFS" > "$WORK/unsquash.log" 2>&1 || true
ARCH_INODES=$(unsquashfs -s "$ISO_ROOT/casper/$LIVE_SQUASHFS" 2>/dev/null | awk '/Number of inodes/{print $NF}')
GOT_INODES=$(find "$ROOTFS" | wc -l)
echo "archive inodes: $ARCH_INODES, extracted entries: $GOT_INODES"
if [ "$GOT_INODES" -lt $((ARCH_INODES * 99 / 100)) ]; then
  echo "extraction too incomplete ($GOT_INODES of $ARCH_INODES); see $WORK/unsquash.log" >&2
  exit 1
fi
if grep -q "failed to create" "$WORK/unsquash.log"; then
  echo "note: unsquashfs skipped some entries (recorded, build continues):"
  grep "failed to create" "$WORK/unsquash.log" | head -5
  echo "(On 24.04.5.1 the skipped entries are the known-harmless"
  echo " tmp/snap-private-tmp and var/cache/apparmor/8eeb6286.0;"
  echo "the boot test is the real check that the layer is intact.)"
fi
# The old live layer is no longer needed once unpacked.
rm -f "$ISO_ROOT/casper/$LIVE_SQUASHFS"
OLD_LIVE_SIZE=$(cat "$ISO_ROOT/casper/minimal.standard.live.size")
# Record du of the pristine layer: the .size files are NOT plain du
# (on 24.04.5.1 the live .size file is ~2x the du of the extracted
# tree), so step 5 updates them by DELTA, preserving whatever
# convention the image was built with.
OLD_DU=$(du -sx --block-size=1 "$ROOTFS" | cut -f1)
echo "old live layer size file: $OLD_LIVE_SIZE, pristine du: $OLD_DU"

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
         boot-test.sh make_live_grub_cfg.py BOOT-TEST.md; do
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
- There is NO disk installer in this image. The partitioner is
  still open work; this ISO is live-only.
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
if [ -n "$MISSING" ]; then
  EXTRA_DEBS="$WORK/extra-debs"
  mkdir -p "$EXTRA_DEBS"
  APT_GET="apt-get -o Dir::State=/tmp/apt-state -o Dir::Cache=/tmp/apt-cache -o Dir::Etc::sourcelist=/dev/null -o Dir::Etc::sourceparts=/etc/apt/sources.list.d"
  APT_CACHE="apt-cache -o Dir::State=/tmp/apt-state -o Dir::Cache=/tmp/apt-cache -o Dir::Etc::sourcelist=/dev/null -o Dir::Etc::sourceparts=/etc/apt/sources.list.d"
  CLOSURE=$($APT_CACHE depends --recurse --no-recommends --no-suggests --no-conflicts --no-breaks --no-replaces --no-enhances $MISSING 2>/dev/null | grep "^[a-z0-9]" | sort -u)
  UNPACKED=""
  for pkg in $CLOSURE; do
    if grep -q "^${pkg}:\?\(amd64\)\?$(printf '\t')" "$ISO_ROOT/casper/filesystem.manifest"; then
      continue  # already in the base image
    fi
    deb=$(ls "$EXTRA_DEBS/${pkg}_"*.deb /tmp/apt-cache/archives/${pkg}_*.deb 2>/dev/null | head -1 || true)
    if [ -z "$deb" ]; then
      (cd "$EXTRA_DEBS" && $APT_GET download "$pkg" > /dev/null 2>&1) \
        || { echo "could not fetch $pkg .deb (needs network + apt lists)" >&2; exit 1; }
      deb=$(ls "$EXTRA_DEBS/${pkg}_"*.deb 2>/dev/null | head -1)
    fi
    [ -n "$deb" ] || { echo "missing .deb for $pkg" >&2; exit 1; }
    echo "  [4e] unpacking $pkg"
    dpkg-deb -x "$deb" "$ROOTFS"
    UNPACKED="$UNPACKED $deb"
  done
  # Verify every file all the .debs claim to install landed. This
  # runs AFTER all of them are unpacked: packages cross-reference
  # each other (e.g. blt's changelog is a symlink into
  # tk8.6-blt2.5), so a per-package check would fail on entries
  # whose target only arrives with a later package.
  # (Loop reads from a file, not a pipe, so a failure exits the
  # build instead of only a subshell.)
  for deb in $UNPACKED; do
    dpkg-deb -c "$deb" | awk '{print $6}' | sed 's|^\./||' > "$WORK/.deb-files.txt"
    while read -r f; do
      [ -e "$ROOTFS/$f" ] || { echo "missing after unpack: $f ($deb)" >&2; exit 1; }
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

# 5. Repack the live layer and refresh the size / checksum records.
echo "== [5/8] repacking live layer =="
NEW_SQUASHFS="$WORK/new-minimal.standard.live.squashfs"
mksquashfs "$ROOTFS" "$NEW_SQUASHFS" -comp xz -b 131072 -noappend > "$WORK/mksquashfs.log" 2>&1
# Update the .size files by DELTA (see step 3: the .size convention
# is not plain du, so the absolute du must not replace the file).
NEW_DU=$(du -sx --block-size=1 "$ROOTFS" | cut -f1)
NEW_LIVE_SIZE=$((OLD_LIVE_SIZE + NEW_DU - OLD_DU))
echo "live layer du: $OLD_DU -> $NEW_DU; size file: $OLD_LIVE_SIZE -> $NEW_LIVE_SIZE"
chmod -R u+w "$ROOTFS" 2>/dev/null || true
rm -rf "$ROOTFS"  # frees ~3.7G before the rebuild

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
python3 - "$ISO_ROOT" "$WORK" "$NEW_SQUASHFS" "$NEW_LIVE_SIZE" "$OLD_LIVE_SIZE" <<'PYEOF'
import hashlib, pathlib, sys
iso_root, work, new_sq, new_size, old_size = sys.argv[1:6]
new_size, old_size = int(new_size), int(old_size)
work = pathlib.Path(work)

def md5(path):
    return hashlib.md5(pathlib.Path(path).read_bytes()).hexdigest()

def sha256(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

# Live layer size + the total (filesystem.size is the sum of the
# three layer sizes).
(pathlib.Path(iso_root) / "casper" / "minimal.standard.live.size").write_text(str(new_size))
fs_size_path = pathlib.Path(iso_root) / "casper" / "filesystem.size"
fs_size = int(fs_size_path.read_text().strip())
fs_size_path.write_text(str(fs_size + (new_size - old_size)))

# casper/SHA256SUMS: new hash for the repacked live layer.
sha_path = pathlib.Path(iso_root) / "casper" / "SHA256SUMS"
lines = sha_path.read_text().splitlines()
lines = [
    (f"{sha256(new_sq)} *minimal.standard.live.squashfs"
     if line.endswith(" *minimal.standard.live.squashfs") else line)
    for line in lines
]
sha_path.write_text("\n".join(lines) + "\n")

# md5sum.txt at the ISO root: refresh the changed files, add the
# new splash BMP. Unchanged entries are copied verbatim.
md5_path = pathlib.Path(iso_root) / "md5sum.txt"
entries = {}
for line in md5_path.read_text().splitlines():
    digest, _, name = line.partition("  ")
    entries[name] = digest
entries["./casper/minimal.standard.live.squashfs"] = md5(new_sq)
entries["./casper/minimal.standard.live.size"] = md5(
    pathlib.Path(iso_root) / "casper" / "minimal.standard.live.size")
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
for f in casper/SHA256SUMS casper/minimal.standard.live.size casper/filesystem.size md5sum.txt; do
  cp "$ISO_ROOT/$f" "$WORK/$(basename "$f").new"
done
rm -rf "$ISO_ROOT"

# 7. Rebuild the ISO: replay the base image's boot chain verbatim
#    (BIOS eltorito + appended EFI system partition), replace only
#    the changed files, relabel the volume.
echo "== [7/8] rebuilding ISO =="
xorriso -indev "$BASE_ISO" -outdev "$OUT" \
  -volid "$VOLID" -boot_image any replay \
  -rm /casper/minimal.standard.live.squashfs -- \
  -map "$NEW_SQUASHFS" /casper/minimal.standard.live.squashfs \
  -rm /boot/grub/grub.cfg -- \
  -map "$WORK/grub.cfg.new" /boot/grub/grub.cfg \
  -map "$WORK/pulpo-uefi-boot-splash.bmp" /boot/grub/pulpo-uefi-boot-splash.bmp \
  -rm /casper/SHA256SUMS -- \
  -map "$WORK/SHA256SUMS.new" /casper/SHA256SUMS \
  -rm /casper/minimal.standard.live.size -- \
  -map "$WORK/minimal.standard.live.size.new" /casper/minimal.standard.live.size \
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
sha256sum "$OUT" > "$OUT.sha256"
echo "== done =="
ls -la "$OUT" "$OUT.sha256"
cat "$OUT.sha256"
echo "Next: installer/boot-test.sh --iso $OUT"
echo "Note: the base ISO is kept at $BASE_ISO for rebuilds;"
echo "delete it by hand when the built ISO is no longer needed."
