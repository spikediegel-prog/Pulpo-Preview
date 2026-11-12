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
# The .deb fetch helpers are shared with step 4f (Calamares).
EXTRA_DEBS="$WORK/extra-debs"
mkdir -p "$EXTRA_DEBS"
APT_GET="apt-get -o Dir::State=/tmp/apt-state -o Dir::Cache=/tmp/apt-cache -o Dir::Etc::sourcelist=/dev/null -o Dir::Etc::sourceparts=/etc/apt/sources.list.d"
APT_CACHE="apt-cache -o Dir::State=/tmp/apt-state -o Dir::Cache=/tmp/apt-cache -o Dir::Etc::sourcelist=/dev/null -o Dir::Etc::sourceparts=/etc/apt/sources.list.d"
# The closure computations below need package lists in the build's
# custom state dir. Those lists live in /tmp, so a reboot wipes them;
# a build that assumes a previous run populated them dies silently
# at step 4f (empty closure -> grep finds nothing -> pipefail under
# set -e). Populate them here when missing instead of assuming.
if [ ! -d /tmp/apt-state/lists ] || [ -z "$(ls -A /tmp/apt-state/lists 2>/dev/null)" ]; then
  echo "  [apt] populating package lists (apt-get update)"
  mkdir -p /tmp/apt-state/lists/partial /tmp/apt-cache/archives/partial
  $APT_GET update > /tmp/apt-update.log 2>&1 || { echo "apt-get update failed; see /tmp/apt-update.log" >&2; exit 1; }
fi
if [ -n "$MISSING" ]; then
  CLOSURE=$($APT_CACHE depends --recurse --no-recommends --no-suggests --no-conflicts --no-breaks --no-replaces --no-enhances $MISSING 2>/dev/null | grep "^[a-z0-9]" | sort -u)
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
      deb=$(ls "$EXTRA_DEBS/${pkg}_"*.deb 2>/dev/null | head -1)
    fi
    [ -n "$deb" ] || { echo "missing .deb for $pkg" >&2; exit 1; }
    echo "  [4e] unpacking $pkg"
    dpkg-deb -x "$deb" "$ROOTFS"
    UNPACKED="$UNPACKED $deb"
  done
  # Verify every file all the .debs claim to install landed. This
  # accepts a symlink entry even if its target does not resolve
  # inside this single live layer: a .deb may link into a package
  # already in the base image whose files live in another squashfs
  # layer (e.g. dbus-x11/AUTHORS.gz -> ../libdbus-1-3/AUTHORS.gz).
  # The link itself is installed correctly and the target exists
  # in the composed live system; only a genuinely absent entry fails.
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
CAL_CLOSURE=$($APT_CACHE depends --recurse --no-recommends --no-suggests --no-conflicts --no-breaks --no-replaces --no-enhances calamares 2>/dev/null | grep "^[a-z0-9]" | sort -u)
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
    deb=$(ls "$EXTRA_DEBS/${pkg}_"*.deb 2>/dev/null | head -1)
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
# Desktop launcher (live session): "Install Pulpo Preview".
mkdir -p "$ROOTFS/usr/share/applications" "$ROOTFS/etc/skel/Desktop"
cp "$REPO_ROOT/installer/calamares/install-pulpo.desktop" \
   "$ROOTFS/usr/share/applications/install-pulpo.desktop"
cp "$REPO_ROOT/installer/calamares/install-pulpo.desktop" \
   "$ROOTFS/etc/skel/Desktop/install-pulpo.desktop"
# Verify the pieces Calamares needs are all in place.
for f in etc/calamares/settings.conf \
         etc/calamares/modules/partition.conf \
         etc/calamares/modules/unpackfs.conf \
         etc/calamares/modules/shellprocess_pulpo-config.conf \
         etc/calamares/branding/pulpo/branding.desc \
         etc/calamares/branding/pulpo/logo.png \
         etc/calamares/branding/pulpo/welcome.png \
         etc/calamares/branding/pulpo/show.qml \
         usr/share/pulpo-installer/calamares/pulpo-config-install.sh \
         usr/share/applications/install-pulpo.desktop; do
  [ -f "$ROOTFS/$f" ] || { echo "calamares file missing: $f" >&2; exit 1; }
done
grep -q "branding: pulpo" "$ROOTFS/etc/calamares/settings.conf" \
  || { echo "settings.conf does not select the pulpo branding" >&2; exit 1; }
grep -q "shellprocess@pulpo-config" "$ROOTFS/etc/calamares/settings.conf" \
  || { echo "settings.conf does not run the pulpo-config module" >&2; exit 1; }
echo "  [4f] Calamares config + branding in place"

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
#    the changed files, relabel the volume. xorriso refuses to
#    write -outdev over a file that already holds data, so a previous
#    build's output is removed first.
echo "== [7/8] rebuilding ISO =="
rm -f "$OUT" "$OUT.sha256"
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
echo "Then: installer/install-test.sh --iso $OUT (disk-install test; see installer/INSTALL-TEST.md)"
echo "Note: the base ISO is kept at $BASE_ISO for rebuilds;"
echo "delete it by hand when the built ISO is no longer needed."
