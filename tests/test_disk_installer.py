"""Disk installer (Calamares): settings, single merged squashfs,
branding, config carry-through script, and build integration.

These tests use ``unittest`` so the repo's CI
(``python -m unittest discover -s tests``) runs them; pytest is not
installed in this repo and no workflow runs it.

The YAML files are checked structurally (no PyYAML dependency):
the settings / module configs are simple enough that a small
line parser proves the module lists, the unpackfs sources, and
the key values. The real YAML parse happens when Calamares loads
the config in the install test (see installer/INSTALL-TEST.md).
"""

import json
import os
import re
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = REPO_ROOT / "installer"
CALAMARES = INSTALLER / "calamares"

# The 21 casper squashfs layers of the Ubuntu 24.04.5.1 base ISO,
# in alphabetical order (verified with xorriso -find /casper on
# the base ISO). These are the PRESENCE check in build-iso.sh
# step 2 only: every layer must be present in the base ISO.
# They are NOT the merge inputs. The merge inputs are
# MERGE_LAYERS below: the boot chain only (minimal ->
# minimal.standard -> minimal.standard.live, in dependency
# order, live layer topmost) — exactly what casper mounts at
# boot. (Run 6, 2026-11-12: merging all 21 alphabetically let
# minimal.standard.zh's debconf database override the live
# layer's, so no live user was created.) Build-iso.sh step 3
# mounts the chain (squashfuse) and composes it
# (fuse-overlayfs), then copies the merged view with rsync
# into a plain directory and customises that — the overlay is
# read-only for a non-root user (its lower layers are
# root-owned; the kernel rejects writes into them), so the
# plain directory is the rootfs from step 3 on. See
# installer/DISK-INSTALLER.md for why the merge exists (rsync
# cannot copy overlay whiteouts).
CASPER_LAYERS = [
    "minimal.de.squashfs",
    "minimal.en.squashfs",
    "minimal.es.squashfs",
    "minimal.fr.squashfs",
    "minimal.it.squashfs",
    "minimal.no-languages.squashfs",
    "minimal.pt.squashfs",
    "minimal.ru.squashfs",
    "minimal.squashfs",
    "minimal.standard.de.squashfs",
    "minimal.standard.en.squashfs",
    "minimal.standard.es.squashfs",
    "minimal.standard.fr.squashfs",
    "minimal.standard.it.squashfs",
    "minimal.standard.live.squashfs",
    "minimal.standard.no-languages.squashfs",
    "minimal.standard.pt.squashfs",
    "minimal.standard.ru.squashfs",
    "minimal.standard.squashfs",
    "minimal.standard.zh.squashfs",
    "minimal.zh.squashfs",
]

# The merge inputs: the boot chain ONLY, in dependency order
# (lowest first) — what casper mounts at boot. The 18 language
# layers are excluded; see installer/build-iso.sh.
MERGE_LAYERS = [
    "minimal.squashfs",
    "minimal.standard.squashfs",
    "minimal.standard.live.squashfs",
]

# Module names shipped in calamares 3.3.5-0ubuntu4 (Ubuntu 24.04),
# listed from the .deb's /usr/lib/x86_64-linux-gnu/calamares/modules/.
CALAMARES_MODULES = {
    "bootloader", "contextualprocess", "displaymanager", "dracut",
    "dracutlukscfg", "dummycpp", "dummyprocess", "dummypython",
    "finished", "finishedq", "fsresizer", "fstab", "grubcfg",
    "hostinfo", "hwclock", "initcpio", "initcpiocfg", "initramfs",
    "initramfscfg", "interactiveterminal", "keyboard", "keyboardq",
    "license", "locale", "localecfg", "localeq", "luksbootkeyfile",
    "luksopenswaphookcfg", "machineid", "mkinitfs", "mount",
    "netinstall", "networkcfg", "notesqml", "oemid",
    "openrcdmcryptcfg", "packagechooser", "packagechooserq",
    "packages", "partition", "plasmalnf", "plymouthcfg",
    "preservefiles", "rawfs", "removeuser", "services-openrc",
    "services-systemd", "shellprocess", "summary", "summaryq",
    "tracking", "umount", "unpackfs", "users", "usersq",
    "welcome", "welcomeq", "zfs", "zfshostid",
}


def _read(path):
    return path.read_text(encoding="utf-8")


def _settings_sections():
    """Parse installer/calamares/settings.conf's show/exec lists."""
    sections = {"show": [], "exec": []}
    instances = {}
    current = None
    current_id = None
    for line in _read(CALAMARES / "settings.conf").splitlines():
        m = re.match(r"^- (show|exec):\s*$", line)
        if m:
            current = m.group(1)
            continue
        m = re.match(r"^- id: (\S+)\s*$", line)
        if m:
            current_id = m.group(1)
            current = None
            continue
        m = re.match(r"^\s+config: (\S+)\s*$", line)
        if m and current_id:
            instances[current_id] = m.group(1)
            current_id = None
            continue
        m = re.match(r"^  - ([a-z0-9@_-]+)\s*$", line)
        if m and current:
            sections[current].append(m.group(1))
    return sections, instances


def _unpackfs_sources():
    """(sources, sourcefs values, destinations) from unpackfs.conf."""
    text = _read(CALAMARES / "modules" / "unpackfs.conf")
    sources = re.findall(r'source: "([^"]+)"', text)
    fss = re.findall(r'sourcefs: "([^"]+)"', text)
    dests = re.findall(r'destination: "([^"]*)"', text)
    return sources, fss, dests


class CalamaresSettingsTests(unittest.TestCase):
    def test_settings_selects_pulpo_branding(self):
        text = _read(CALAMARES / "settings.conf")
        self.assertIn("branding: pulpo", text)
        self.assertIn("prompt-install: true", text)

    def test_show_sequence_is_the_install_surface(self):
        sections, _ = _settings_sections()
        self.assertEqual(
            sections["show"],
            ["welcome", "keyboard", "partition", "users", "summary", "finished"],
        )

    def test_exec_sequence_runs_pulpo_config_after_users(self):
        sections, _ = _settings_sections()
        expected = [
            "partition", "mount", "unpackfs", "machineid", "fstab",
            "keyboard", "users", "displaymanager", "hwclock",
            "shellprocess@pulpo-config", "shellprocess@install-cc-deb",
            "shellprocess@remove-live",
            "initramfscfg", "initramfs", "shellprocess@verify-initramfs",
            "grubcfg", "bootloader", "shellprocess@grub-prefix-stub",
            "umount",
        ]
        self.assertEqual(sections["exec"], expected)
        # The config module must run after the user exists and
        # before the bootloader is written.
        self.assertLess(
            sections["exec"].index("users"),
            sections["exec"].index("shellprocess@pulpo-config"),
        )
        self.assertLess(
            sections["exec"].index("shellprocess@pulpo-config"),
            sections["exec"].index("grubcfg"),
        )
        # Run 10: the live packages must be stripped before the
        # initramfs step regenerates the target's initrd, the
        # built initrd must be gated before the bootloader is
        # written, and the GRUB stub must be written after the
        # bootloader installs the ESP layout.
        self.assertLess(
            sections["exec"].index("shellprocess@remove-live"),
            sections["exec"].index("initramfs"),
        )
        self.assertLess(
            sections["exec"].index("initramfs"),
            sections["exec"].index("shellprocess@verify-initramfs"),
        )
        self.assertLess(
            sections["exec"].index("bootloader"),
            sections["exec"].index("shellprocess@grub-prefix-stub"),
        )

    def test_every_referenced_module_exists_in_calamares(self):
        sections, instances = _settings_sections()
        names = set(sections["show"]) | {
            n.split("@")[0] for n in sections["exec"]
        }
        for name in names:
            self.assertIn(name, CALAMARES_MODULES, f"unknown module: {name}")
        for instance_id, config in instances.items():
            self.assertTrue(
                (CALAMARES / "modules" / config).is_file(),
                f"missing instance config: {config} (for {instance_id})",
            )

    def test_deliberate_skips_are_absent(self):
        # locale (English-only v1, UTC by design), networkcfg (the
        # Pulpo config is the network authority), packages /
        # pkgselect (nothing to install post-install; offline).
        sections, _ = _settings_sections()
        all_names = sections["show"] + sections["exec"]
        for skipped in ("locale", "networkcfg", "packages", "pkgselect",
                        "automirror", "oemid"):
            self.assertNotIn(skipped, all_names, f"should be skipped: {skipped}")


class UnpackfsTests(unittest.TestCase):
    def test_unpackfs_copies_the_single_merged_squashfs(self):
        # The build merges the 21 base layers into one
        # filesystem.squashfs (Lubuntu-style); unpackfs copies
        # exactly that one file. Listing the layers here would
        # reintroduce the whiteout failure (rsync error 13 — see
        # installer/DISK-INSTALLER.md "The whiteout failure").
        sources, fss, dests = _unpackfs_sources()
        self.assertEqual(sources, ["/cdrom/casper/filesystem.squashfs"])
        self.assertEqual(fss, ["squashfs"])
        self.assertEqual(dests, [""])

    def test_build_checks_exactly_the_21_base_layers_present(self):
        # The presence check in build-iso.sh step 2 must list
        # exactly the 21 layers of the base ISO, in alphabetical
        # order: a missing layer means the base ISO is not the
        # one the build was written for. This list is NOT the
        # merge order (see the next test).
        text = _read(INSTALLER / "build-iso.sh")
        block = text.split("CASPER_LAYERS=(", 1)[1].split(")", 1)[0]
        layers = re.findall(r"^\s+(\S+\.squashfs)\s*$", block, re.M)
        self.assertEqual(layers, CASPER_LAYERS)

    def test_build_merges_only_the_boot_chain_in_dependency_order(self):
        # Regression (run 6, 2026-11-12): merging all 21 layers
        # alphabetically let minimal.standard.zh's debconf
        # database override the live layer's, so no live user
        # was created. The merge inputs must be exactly the boot
        # chain (minimal -> minimal.standard ->
        # minimal.standard.live), in dependency order, live
        # layer topmost — what casper mounts at boot. And every
        # merge step (mount loop, merge-plan inputs, both fixup
        # loops) must use MERGE_LAYERS, not CASPER_LAYERS.
        text = _read(INSTALLER / "build-iso.sh")
        block = text.split("MERGE_LAYERS=(", 1)[1].split(")", 1)[0]
        layers = re.findall(r"^\s+(\S+\.squashfs)\s*$", block, re.M)
        self.assertEqual(layers, MERGE_LAYERS)
        self.assertIn('for layer in "${MERGE_LAYERS[@]}"; do\n  i=$((i + 1))', text)
        self.assertIn('for layer in "${MERGE_LAYERS[@]}"; do LAYER_PATHS+=', text)
        self.assertIn('for layer in "${MERGE_LAYERS[@]}"; do\n  files=$(awk', text)
        self.assertIn('  for layer in "${MERGE_LAYERS[@]}"; do\n    # Whiteouts this layer places', text)
        # The presence check is the only remaining CASPER_LAYERS loop.
        self.assertEqual(text.count('for layer in "${CASPER_LAYERS[@]}"'), 1)

    def test_build_does_not_claim_alphabetical_order_is_casper(self):
        # The run-6 root cause was the claim that casper mounts
        # the layers alphabetically, last wins. That claim must
        # not survive anywhere in the build script.
        text = _read(INSTALLER / "build-iso.sh")
        self.assertNotIn("as casper does", text)
        self.assertNotIn("Alphabetical order reproduces", text)

    def test_build_verifies_the_merge_resolved_whiteouts(self):
        # Regression: the merged view must hold no overlay
        # whiteout (char device 0/0) — otherwise the install dies
        # the same way the layered copy did. The count must be
        # 0/0 devices ONLY: the view legitimately holds the static
        # /dev nodes (null, zero, console, ...). The same check
        # must run on the PLAIN directory the build customises
        # (ROOTFS_WHITEOUTS), plus the file-list diff against the
        # expected composition from the layers' metadata — the
        # plain directory is what ships, so it is the one that
        # must be proven. There is deliberately NO help-langpack
        # check any more: the chain-only merge (run 6 fix) never
        # merges the no-languages layer whose whiteout deleted
        # it, and the chain's bottom layer (minimal) legitimately
        # holds 3,917 help-langpack files.
        text = _read(INSTALLER / "build-iso.sh")
        self.assertIn("squashfuse", text)
        self.assertIn("fuse-overlayfs", text)
        self.assertIn("MERGED_WHITEOUTS", text)
        self.assertIn("ROOTFS_WHITEOUTS", text)
        self.assertIn("^0,0$", text)
        self.assertIn("expected-list.txt", text)
        self.assertIn("new-filesystem.squashfs", text)
        self.assertNotIn("new-minimal.standard.live.squashfs", text)
        self.assertNotIn("minimal.standard.live.size", text)

    def test_build_gates_on_the_live_layer_debconf_database(self):
        # Regression (run 6, 2026-11-12): the alphabetical merge
        # took minimal.standard.zh's debconf database (152
        # templates, no passwd/*), so casper created no live user
        # and GDM fell back to the initial-setup session. The
        # build must gate on the merged templates.dat holding the
        # live layer's templates (>=300 names) including the
        # passwd/* templates casper's user creation needs.
        text = _read(INSTALLER / "build-iso.sh")
        self.assertIn("var/cache/debconf/templates.dat", text)
        self.assertIn("TEMPLATE_NAMES", text)
        self.assertIn("PASSWD_NAMES", text)
        self.assertIn("'^Name: passwd/'", text)
        self.assertIn("debconf database is not the live layer's", text)

    def test_build_copies_the_merge_to_a_plain_directory(self):
        # Regression (build #2, 2026-11-12): a non-root user
        # cannot write through a FUSE overlay whose lower layers
        # are root-owned — dpkg-deb -x into the overlay died with
        # "Cannot mkdir: Permission denied". The overlay is
        # therefore read-only in this build: the merged view is
        # rsynced into a plain directory, ROOTFS is reassigned
        # to it AFTER the view is verified and BEFORE the
        # customisation, and the mounts are released before
        # step 4. If any of that regresses, the customisation
        # writes into the overlay again and dies the same way.
        text = _read(INSTALLER / "build-iso.sh")
        self.assertIn('rsync -aH --exclude-from="$PLAN/excludes.txt"', text)
        self.assertIn('ROOTFS="$WORK/rootfs"', text)
        self.assertLess(text.find("MERGED_WHITEOUTS"),
                        text.find('ROOTFS="$WORK/rootfs"'))
        self.assertLess(text.find('ROOTFS="$WORK/rootfs"'),
                        text.find("# 4. Customise"))
        # The FUSE mounts are released in step 3, not step 5.
        self.assertLess(text.find("cleanup_merge\ntrap - EXIT"),
                        text.find("# 4. Customise"))

    def test_build_fixes_up_root_only_paths_from_the_archives(self):
        # rsync cannot read 101 root-only paths (60 files, 41 dirs) through the
        # overlay (/etc/shadow, /boot/vmlinuz, the snap files,
        # /root, ...). installer/merge-plan.py enumerates them
        # from the layers' metadata; the build excludes them
        # from the rsync and extracts them directly from the
        # archives with unsquashfs (which reads the archive
        # bytes). Files are verified present afterwards, and
        # directories are merged layer by layer (a whiteout in
        # a layer must be applied before that layer's files
        # land, and targeted extraction skips a directory that
        # already exists, so each layer goes through staging).
        # Files go through staging too: targeted extraction
        # creates NOTHING when the file's parent directory
        # already exists in the destination (proven by hand),
        # and the rootfs already holds the parents from the
        # rsync — so each layer is extracted into a fresh
        # staging directory and merged with cp -a.
        text = _read(INSTALLER / "build-iso.sh")
        self.assertIn("merge-plan.py", text)
        self.assertIn("fixup-files.txt", text)
        self.assertIn("fixup-dirs.txt", text)
        self.assertIn("fixup-whiteouts.txt", text)
        self.assertIn('unsquashfs -ignore-errors -d "$STAGE_FILES"', text)
        self.assertIn('cp -a "$STAGE_FILES/." "$ROOTFS/"', text)
        self.assertIn("fixup file missing after extraction", text)
        self.assertIn("fixup directory missing after extraction", text)
        self.assertIn('cp -a "$STAGE/$dpath/." "$ROOTFS/$dpath/"', text)

    def test_merge_plan_helper_is_valid_python(self):
        # The helper the build depends on must at least parse;
        # its real test is the build itself (the file-list diff
        # in step 3 fails the build if the plan is wrong).
        import py_compile
        py_compile.compile(str(INSTALLER / "merge-plan.py"),
                           doraise=True)


class OwnershipTests(unittest.TestCase):
    """Run-7 ownership fix: true owner:group must survive the repack.

    Regression (run 7, 2026-11-13): mksquashfs -all-root flattened
    every file to root:root, so the D-Bus launch helper lost its
    messagebus group (gid 101) and the system bus could not spawn
    the KPMCore helper — Calamares saw no disk. The build now
    restores the layers' true ownership with a pseudo-file
    (installer/ownership-pseudo.py, from merge-plan.py's
    ownership.txt) passed with -pseudo-override, and gates the
    built squashfs against the layers' metadata
    (installer/ownership-gate.py).

    Build #13, first attempt: the gate caught a second defect —
    mksquashfs silently drops a staging directory it cannot list
    (/var/lib/snapd/void, mode 0111, the only owner-unreadable
    path in the image), so staging-readable.py chmods such layer
    paths u+r before the pack and the pseudo-file carries a
    mode-correction entry restoring the true mode.
    """

    @staticmethod
    def _load_meta():
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "squashfs_meta", INSTALLER / "squashfs_meta.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_merge_plan_emits_ownership_map(self):
        text = _read(INSTALLER / "merge-plan.py")
        self.assertIn("ownership.txt", text)
        self.assertIn("resolve_uid", text)
        self.assertIn("resolve_gid", text)
        self.assertIn("from squashfs_meta import", text)

    def test_ownership_helpers_are_valid_python(self):
        import py_compile
        for name in ("squashfs_meta.py", "ownership-pseudo.py",
                     "ownership-gate.py", "staging-readable.py"):
            py_compile.compile(str(INSTALLER / name), doraise=True)

    def test_build_restores_true_ownership_with_pseudo_file(self):
        # The pack must carry -pseudo-override (without it the
        # pseudo entries are ignored — proven by hand) and the
        # pseudo file generated from the ownership map.
        text = _read(INSTALLER / "build-iso.sh")
        self.assertIn("ownership-pseudo.py", text)
        self.assertIn('"$PLAN/ownership.txt"', text)
        self.assertIn("-pseudo-override", text)
        self.assertIn('-pf "$WORK/ownership.pseudo"', text)
        self.assertIn("-all-root", text)
        # The old claim that -all-root alone carries the files
        # "as root-owned, as it should" is the run-7 bug: it must
        # not survive anywhere in the build script.
        self.assertNotIn("as root-owned, as it should", text)

    def test_build_gates_on_built_squashfs_ownership(self):
        text = _read(INSTALLER / "build-iso.sh")
        self.assertIn("ownership-gate.py", text)
        self.assertIn("ownership gate failed", text)
        gate = _read(INSTALLER / "ownership-gate.py")
        self.assertIn("usr/lib/dbus-1.0/dbus-daemon-launch-helper", gate)
        self.assertIn('("4754", 0, 101)', gate)

    def test_mode_octal(self):
        meta = self._load_meta()
        self.assertEqual(meta.mode_octal("rwsr-xr--"), "4754")
        self.assertEqual(meta.mode_octal("rwxr-s---"), "2750")
        self.assertEqual(meta.mode_octal("rw-r--r--"), "0644")
        self.assertEqual(meta.mode_octal("rwxrwxrwt"), "1777")
        # mode_octal takes the 9-char string WITHOUT the type
        # char (callers pass mode[1:]); "rwx--x---" is 0710.
        self.assertEqual(meta.mode_octal("rwx--x---"), "0710")

    def test_resolve_uid_gid(self):
        # Names resolve through the host NSS (the same namespace
        # unsquashfs -ll displays them in); numbers pass through;
        # an unresolvable name fails loudly instead of guessing.
        meta = self._load_meta()
        self.assertEqual(meta.resolve_uid("root"), 0)
        self.assertEqual(meta.resolve_gid("root"), 0)
        self.assertEqual(meta.resolve_uid("0"), 0)
        self.assertEqual(meta.resolve_gid("101"), 101)
        with self.assertRaises(ValueError):
            meta.resolve_uid("no-such-user-xyz")
        with self.assertRaises(ValueError):
            meta.resolve_gid("no-such-group-xyz")

    def test_parse_ll_lines(self):
        meta = self._load_meta()
        lines = [
            "drwxr-xr-x root/root 65 2026-11-13 04:41 squashfs-root",
            "-rwsr-xr-- root/101 3 2026-11-13 04:41 "
            "squashfs-root/usr/lib/dbus-1.0/dbus-daemon-launch-helper",
            "lrwxrwxrwx root/root 5 2026-11-13 04:41 "
            "squashfs-root/usr/lib/link -> target",
            "crw------- root/root 0, 0 2026-11-13 04:41 "
            "squashfs-root/dev/whiteout",
            "crw-rw-rw- root/root 1, 3 2026-11-13 04:41 "
            "squashfs-root/dev/null",
        ]
        got = list(meta.parse_ll_lines(lines))
        # The bare squashfs-root line itself is not an entry.
        self.assertEqual(len(got), 4)
        self.assertEqual(got[0][3],
                         "usr/lib/dbus-1.0/dbus-daemon-launch-helper")
        self.assertEqual(got[0][4], None)
        # A symlink is recorded under its own path, not its target.
        self.assertEqual(got[1][3], "usr/lib/link")
        # A char device 0,0 is a whiteout; 1,3 is a real node.
        self.assertEqual(got[2][4], ("0,", "0"))
        self.assertEqual(got[3][4], ("1,", "3"))

    def test_ownership_pseudo_emits_non_root_entries(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "root"
            (root / "etc").mkdir(parents=True)
            (root / "usr" / "lib").mkdir(parents=True)
            helper = root / "usr" / "lib" / "helper"
            helper.write_text("x")
            helper.chmod(0o4754)
            shadow = root / "etc" / "shadow"
            shadow.write_text("x")
            shadow.chmod(0o640)
            link = root / "usr" / "lib" / "link"
            link.symlink_to("helper")
            plain = root / "etc" / "plain"
            plain.write_text("x")
            plain.chmod(0o644)  # match the map: no mode drift
            added = root / "etc" / "added"
            added.write_text("x")
            map_path = Path(td) / "ownership.txt"
            map_path.write_text(
                "etc/shadow\t0\t42\t0640\n"
                "usr/lib/helper\t0\t101\t4754\n"
                "usr/lib/link\t0\t101\t0777\n"
                "etc/plain\t0\t0\t0644\n"
            )
            out = Path(td) / "out.pseudo"
            r = subprocess.run(
                ["python3", str(INSTALLER / "ownership-pseudo.py"),
                 str(map_path), str(root), str(out)],
                capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            lines = out.read_text().splitlines()
            self.assertIn('"etc/shadow" m 0640 0 42', lines)
            self.assertIn('"usr/lib/helper" m 4754 0 101', lines)
            self.assertIn('"usr/lib/link" m 0777 0 101', lines)
            # root:root map entries and build-added files (not in
            # the map) are omitted: they stay root:root via
            # -all-root.
            self.assertEqual(len(lines), 3)

    def test_build_makes_unreadable_layer_paths_readable_before_packing(self):
        # Build #13, first attempt: mksquashfs silently drops a
        # staging directory it cannot list (/var/lib/snapd/void,
        # mode 0111), and the ownership gate failed on that one
        # missing path. The build must make such layer paths
        # owner-readable BEFORE generating the pseudo-file (the
        # pseudo-file then restores the true mode), and the gate
        # still verifies the result.
        text = _read(INSTALLER / "build-iso.sh")
        self.assertIn("staging-readable.py", text)
        self.assertIn("var/lib/snapd/void", text)
        self.assertIn("0111", text)
        self.assertLess(
            text.index('python3 "$REPO_ROOT/installer/staging-readable.py"'),
            text.index('python3 "$REPO_ROOT/installer/ownership-pseudo.py"'))

    def test_ownership_pseudo_emits_mode_correction(self):
        # A root:root path whose staging mode differs from the map
        # (staging was made readable by staging-readable.py) gets
        # a mode-correction entry carrying the MAP mode; a
        # non-root entry likewise carries the map mode, not a
        # drifted staging mode; a root:root path with no drift is
        # still omitted.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "root"
            (root / "var" / "lib" / "snapd").mkdir(parents=True)
            void = root / "var" / "lib" / "snapd" / "void"
            void.mkdir()
            void.chmod(0o511)  # staging made readable; map says 0111
            helper = root / "usr" / "lib" / "helper"
            helper.parent.mkdir(parents=True)
            helper.write_text("x")
            helper.chmod(0o4754)
            plain = root / "etc" / "plain"
            plain.parent.mkdir(parents=True)
            plain.write_text("x")
            plain.chmod(0o644)
            drifted = root / "etc" / "drifted"
            drifted.write_text("x")
            drifted.chmod(0o660)  # staging drifted; map says 0640
            map_path = Path(td) / "ownership.txt"
            map_path.write_text(
                "etc/drifted\t0\t42\t0640\n"
                "etc/plain\t0\t0\t0644\n"
                "usr/lib/helper\t0\t101\t4754\n"
                "var/lib/snapd/void\t0\t0\t0111\n"
            )
            out = Path(td) / "out.pseudo"
            r = subprocess.run(
                ["python3", str(INSTALLER / "ownership-pseudo.py"),
                 str(map_path), str(root), str(out)],
                capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            lines = out.read_text().splitlines()
            self.assertIn('"var/lib/snapd/void" m 0111 0 0', lines)
            self.assertIn('"etc/drifted" m 0640 0 42', lines)
            self.assertIn('"usr/lib/helper" m 4754 0 101', lines)
            self.assertNotIn('"etc/plain" m 0644 0 0', lines)
            self.assertEqual(len(lines), 3)
            # void and drifted are both mode corrections.
            self.assertIn("2 mode corrections", r.stderr)

    def test_staging_readable_chmods_only_map_paths(self):
        # Only map paths lacking owner-read are chmodded u+r;
        # build-added paths are untouched; symlinks are never
        # chmodded through.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "root"
            void = root / "var" / "lib" / "snapd" / "void"
            void.mkdir(parents=True)
            void.chmod(0o111)
            other = root / "other"
            other.mkdir()
            other.chmod(0o111)  # build-added: must stay 0111
            link = root / "link"
            link.symlink_to("other")
            wronly = root / "wronly"
            wronly.write_text("x")
            wronly.chmod(0o200)
            map_path = Path(td) / "ownership.txt"
            map_path.write_text(
                "link\t0\t0\t0777\n"
                "var/lib/snapd/void\t0\t0\t0111\n"
                "wronly\t0\t0\t0200\n"
            )
            r = subprocess.run(
                ["python3", str(INSTALLER / "staging-readable.py"),
                 str(map_path), str(root)],
                capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(oct(void.stat().st_mode & 0o7777), "0o511")
            self.assertEqual(oct(other.stat().st_mode & 0o7777), "0o111")
            self.assertTrue(link.is_symlink())
            self.assertEqual(oct(wronly.stat().st_mode & 0o7777), "0o600")
            self.assertIn("2 paths made owner-readable", r.stderr)

    def test_ownership_gate_passes_and_fails(self):
        ll_ok = (
            "drwxr-xr-x root/root 65 2026-11-13 04:41 squashfs-root\n"
            "-rwsr-xr-- 0/101 3 2026-11-13 04:41 "
            "squashfs-root/usr/lib/dbus-1.0/dbus-daemon-launch-helper\n"
            "-rw-r----- 0/42 2 2026-11-13 04:41 "
            "squashfs-root/etc/shadow\n"
            "-rw-r--r-- root/root 2 2026-11-13 04:41 "
            "squashfs-root/etc/added\n"
        )
        map_ok = (
            "etc/shadow\t0\t42\t0640\n"
            "usr/lib/dbus-1.0/dbus-daemon-launch-helper\t0\t101\t4754\n"
        )
        with tempfile.TemporaryDirectory() as td:
            ll_path = Path(td) / "ll.txt"
            ll_path.write_text(ll_ok)
            map_path = Path(td) / "ownership.txt"
            map_path.write_text(map_ok)
            gate = ["python3", str(INSTALLER / "ownership-gate.py"),
                    "built.squashfs", str(map_path),
                    "--ll-file", str(ll_path)]
            r = subprocess.run(gate, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            # A map that claims the helper is root:root must fail:
            # the explicit run-7 check and the per-path compare
            # both catch it.
            map_path.write_text(
                "etc/shadow\t0\t42\t0640\n"
                "usr/lib/dbus-1.0/dbus-daemon-launch-helper\t0\t0\t4754\n"
            )
            r = subprocess.run(gate, capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("dbus-daemon-launch-helper", r.stderr)


class BrandingTests(unittest.TestCase):
    def test_branding_is_pulpo_and_version_is_real(self):
        text = _read(CALAMARES / "branding" / "pulpo" / "branding.desc")
        self.assertIn("productName:         Pulpo Preview", text)
        self.assertIn("version:             0.1.0", text)
        self.assertIn("bootloaderEntryName: Pulpo", text)
        self.assertIn('productLogo:         "logo.png"', text)
        self.assertIn('productWelcome:      "welcome.png"', text)
        self.assertIn('slideshow:               "show.qml"', text)
        self.assertIn('SidebarBackground:    "#1E1A26"', text)
        self.assertIn('SidebarTextCurrent:   "#39FF14"', text)

    def test_no_invented_version_or_internet_copy_in_branding(self):
        # The installer-welcome mockup carries "1.0.0-preview" and
        # "Connect to internet" copy; neither may ship in branding.
        for name in ("branding.desc", "show.qml"):
            text = _read(CALAMARES / "branding" / "pulpo" / name)
            self.assertNotIn("1.0.0-preview", text, name)
            self.assertNotIn("Connect to internet", text, name)
            self.assertNotIn("24.10 Preview", text, name)

    def test_slideshow_uses_the_clean_splash(self):
        text = _read(CALAMARES / "branding" / "pulpo" / "show.qml")
        self.assertIn('source: "welcome.png"', text)


class ModuleConfigTests(unittest.TestCase):
    def test_partition_is_erase_disk_no_luks(self):
        text = _read(CALAMARES / "modules" / "partition.conf")
        self.assertIn('efiSystemPartition: "/boot/efi"', text)
        self.assertIn("enableLuksAutomatedPartitioning: false", text)
        self.assertIn('initialPartitioningChoice: "erase"', text)
        self.assertIn('defaultFileSystemType: "ext4"', text)

    def test_partition_layout_has_root_taking_remaining_space(self):
        # Regression: without a partitionLayout entry for "/",
        # erase-disk creates only the EFI system partition and
        # leaves the rest as free space — the mount module then has
        # no root partition, unpackfs rsyncs into a directory on
        # the live session's RAM overlay, and the install fails
        # (rsync error 13 once the overlay fills).
        # See installer/DISK-INSTALLER.md.
        text = _read(CALAMARES / "modules" / "partition.conf")
        self.assertIn("partitionLayout:", text)
        # Parse just the layout block: entries start with
        # "    - name:" and end at the next top-level key.
        entries = []
        current = None
        in_layout = False
        for line in text.splitlines():
            if line.startswith("partitionLayout:"):
                in_layout = True
                continue
            if in_layout:
                if re.match(r"^[a-zA-Z]", line):
                    break
                m = re.match(r'^\s+- name: "([^"]+)"', line)
                if m:
                    current = {"name": m.group(1)}
                    entries.append(current)
                    continue
                m = re.match(r"^\s+(mountPoint|size|filesystem):\s*(\S+)",
                             line)
                if m and current is not None:
                    current[m.group(1)] = m.group(2).strip('"')
        roots = [e for e in entries if e.get("mountPoint") == "/"]
        self.assertEqual(len(roots), 1, entries)
        self.assertEqual(roots[0].get("size"), "100%")

    def test_welcome_has_no_internet_check(self):
        text = _read(CALAMARES / "modules" / "welcome.conf")
        self.assertIn("requiredStorage:    16", text)
        self.assertNotIn("internetCheckUrl", text)
        # The check list must not contain an internet item.
        check = text.split("check:")[1].split("required:")[0]
        self.assertNotIn("internet", check)

    def test_bootloader_is_grub_with_pulpo_entry(self):
        text = _read(CALAMARES / "modules" / "bootloader.conf")
        self.assertIn('efiBootLoader: "grub"', text)
        self.assertIn('efiBootloaderId: "pulpo"', text)
        self.assertIn('grubInstall: "grub-install"', text)

    def test_users_is_one_admin_no_autologin(self):
        text = _read(CALAMARES / "modules" / "users.conf")
        self.assertIn("doAutologin: false", text)
        self.assertIn("sudoersGroup: sudo", text)

    def test_displaymanager_is_gdm_ubuntu_session(self):
        text = _read(CALAMARES / "modules" / "displaymanager.conf")
        self.assertIn("gdm", text)
        self.assertIn('desktopFile: "ubuntu"', text)

    def test_pulpo_config_instance_runs_in_live_session(self):
        text = _read(
            CALAMARES / "modules" / "shellprocess_pulpo-config.conf"
        )
        self.assertIn("dontChroot: true", text)
        self.assertIn("pulpo-config-install.sh ${ROOT}", text)

    def test_reference_configs_present(self):
        for name in ("fstab.conf", "finished.conf", "machineid.conf",
                     "mount.conf", "umount.conf", "grubcfg.conf"):
            self.assertTrue(
                (CALAMARES / "modules" / name).is_file(), name
            )


class DesktopLauncherTests(unittest.TestCase):
    def test_install_desktop_runs_calamares_via_sudo(self):
        text = _read(CALAMARES / "install-pulpo.desktop")
        self.assertIn("Name=Install Pulpo Preview", text)
        self.assertIn("Exec=sudo -E calamares", text)
        self.assertIn("Icon=pulpo", text)


class PulpoConfigScriptTests(unittest.TestCase):
    SCRIPT = CALAMARES / "pulpo-config-install.sh"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.target = self.root / "target"
        self.live = self.root / "live"
        self.target.mkdir()
        self.live.mkdir()
        # Fake target /etc/passwd: root + the UID-1000 user.
        etc = self.target / "etc"
        etc.mkdir()
        (etc / "passwd").write_text(
            "root:x:0:0:root:/root:/bin/bash\n"
            "testuser:x:1000:1000:Test User:/home/testuser:/bin/bash\n",
            encoding="utf-8",
        )
        # The wizard's config (the repo's example document).
        self.config = json.loads(
            (INSTALLER / "pulpo-preview-config.example.json")
            .read_text(encoding="utf-8")
        )
        self.src = self.live / "control-center-customer-config.json"
        self.src.write_text(json.dumps(self.config), encoding="utf-8")
        self.calls = self.root / "calls.txt"
        self.stub = self.root / "stub-cc"
        self.stub.write_text(
            "#!/bin/bash\n"
            'echo "$@" >> "$STUB_CALLS"\n'
            'mode="${STUB_MODE:-ok}"\n'
            'count=$(wc -l < "$STUB_CALLS")\n'
            'case "$mode" in\n'
            "  ok) exit 0;;\n"
            "  noiface)\n"
            '    if [ "$count" -eq 1 ]; then\n'
            '      echo "ValueError: no_network_interface_found" >&2\n'
            "      exit 1\n"
            "    else exit 0; fi;;\n"
            "  badconfig)\n"
            '    echo "ValueError: bad timezone" >&2\n'
            "    exit 1;;\n"
            "esac\n",
            encoding="utf-8",
        )
        self.stub.chmod(0o755)

    def _env(self, mode="ok"):
        env = dict(os.environ)
        env["PULPO_CC_BIN"] = str(self.stub)
        env["PULPO_LIVE_CONFIG_GLOB"] = str(self.src)
        env["PULPO_IFACE"] = "eth0"
        env["STUB_CALLS"] = str(self.calls)
        env["STUB_MODE"] = mode
        return env

    def _run(self, mode="ok"):
        return subprocess.run(
            [str(self.SCRIPT), str(self.target)],
            env=self._env(mode),
            capture_output=True, text=True, timeout=60,
        )

    def test_script_is_executable(self):
        mode = self.SCRIPT.stat().st_mode
        self.assertTrue(mode & stat.S_IXUSR, "pulpo-config-install.sh")

    def test_no_config_warns_and_proceeds(self):
        self.src.unlink()
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("no customer config", result.stdout)
        self.assertFalse(
            (self.target / "etc" / "pulpo" / "customer-config.json").exists()
        )

    def test_config_is_copied_and_imported(self):
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        system = self.target / "etc" / "pulpo" / "customer-config.json"
        self.assertTrue(system.is_file())
        self.assertEqual(json.loads(system.read_text()), self.config)
        profile = (
            self.target / "home" / "testuser" / ".config" / "PulpoPreview"
            / "control-center-customer-config.json"
        )
        self.assertTrue(profile.is_file())
        self.assertEqual(json.loads(profile.read_text()), self.config)
        calls = self.calls.read_text().splitlines()
        self.assertEqual(len(calls), 1)
        self.assertIn("config import", calls[0])
        self.assertIn(f"--root {self.target}", calls[0])
        self.assertIn("--apply-network", calls[0])
        self.assertIn(str(self.src), calls[0])

    def test_no_interface_retries_with_fallback_and_proceeds(self):
        result = self._run(mode="noiface")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = self.calls.read_text().splitlines()
        self.assertEqual(len(calls), 2)
        self.assertNotIn("--interface", calls[0])
        self.assertIn("--interface eth0", calls[1])
        self.assertTrue(
            (self.target / "etc" / "pulpo" / "customer-config.json").is_file()
        )

    def test_bad_config_fails_the_install(self):
        result = self._run(mode="badconfig")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("config import failed", result.stdout)

    def test_import_runs_as_non_root_user(self):
        # Run 8: Calamares runs this script as root, and the CLI's
        # scratch-root guard refuses root for --root != /. The
        # import must go through runuser to the import user, never
        # directly, and there must be no fallback to running it as
        # root (the guard would refuse it and the failure would
        # look like a config error instead of a privilege error).
        text = _read(self.SCRIPT)
        self.assertIn('runuser -u "$IMPORT_USER"', text)
        self.assertEqual(
            text.count('run_import --root "$TARGET" --apply-network'), 2,
            "both import attempts (first try and --interface retry) "
            "must go through run_import",
        )
        self.assertNotIn('"$CC_BIN" config import --root', text)

    def test_real_cli_import_as_non_root(self):
        """The run-8 gap, closed: the REAL CLI + non-root +
        scratch root, with no stub in the loop. The script's tests
        used to stub PULPO_CC_BIN and the CLI's own scratch-root
        tests run non-root, so the real-CLI + root + scratch-root
        combination was never exercised — until run 8 hit the
        guard live. Run 9 extended it: the scratch target now
        also carries pre-existing 0600 files under lib/netplan/
        (mirroring the image), which netplan generate must be
        able to read. Skipped where the real Control Center is not
        installed (CI) or where the tests run as root (the guard
        refuses root for a scratch root — that is the run-8
        failure, not a test setup)."""
        import shutil
        if os.geteuid() == 0:
            self.skipTest("real-CLI import test needs a non-root runner")
        cc = shutil.which("pulpo-control-center") or "/usr/bin/pulpo-control-center"
        if not os.path.isfile(cc) or not os.access(cc, os.X_OK):
            self.skipTest("real Control Center CLI not installed")
        if not shutil.which("netplan"):
            self.skipTest("netplan not installed (the import runs netplan generate)")
        home = self.root / "fake-home"
        home.mkdir()
        env = dict(os.environ)
        # Keep the import's profile record (best-effort) out of the
        # runner's real home: default_profile_path() uses $HOME.
        env["HOME"] = str(home)
        env.pop("PULPO_CC_BIN", None)  # the real CLI, not the stub
        env["PULPO_LIVE_CONFIG_GLOB"] = str(self.src)
        env["PULPO_IFACE"] = "eth0"
        # Run 9: pre-existing 0600 files under lib/netplan/ in
        # the scratch target, mirroring the image (the real
        # 00-network-manager-all.yaml is 49 bytes, 0600
        # root:root; 01-extra.yaml covers the general case — any
        # pre-existing 0600 file under lib/netplan/, not just the
        # one filename run 9 hit). netplan generate reads every
        # YAML under the root, so the import must succeed with
        # these present.
        lib_netplan = self.target / "lib" / "netplan"
        lib_netplan.mkdir(parents=True)
        (lib_netplan / "00-network-manager-all.yaml").write_text(
            "network:\n  version: 2\n  renderer: NetworkManager\n",
            encoding="utf-8",
        )
        (lib_netplan / "01-extra.yaml").write_text(
            "network:\n  version: 2\n  ethernets:\n"
            "    eth99:\n      dhcp4: true\n",
            encoding="utf-8",
        )
        for preexisting in lib_netplan.iterdir():
            preexisting.chmod(0o600)
        result = subprocess.run(
            [str(self.SCRIPT), str(self.target)],
            env=env, capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("config import applied", result.stdout)
        timesyncd = self.target / "etc" / "systemd" / "timesyncd.conf"
        self.assertTrue(timesyncd.is_file())
        self.assertIn("NTP=ntp.ubuntu.com pool.ntp.org", timesyncd.read_text())
        netplan_file = self.target / "etc" / "netplan" / "60-pulpo.yaml"
        self.assertTrue(netplan_file.is_file())
        self.assertEqual(stat.S_IMODE(netplan_file.stat().st_mode), 0o600)
        self.assertIn("dhcp4: true", netplan_file.read_text())
        generated = list(
            (self.target / "run" / "NetworkManager" / "system-connections")
            .glob("*.nmconnection")
        )
        # The fixture's 00-network-manager-all.yaml sets the
        # renderer to NetworkManager (as in the real image), so
        # generate writes NetworkManager keyfiles, not systemd
        # .network units — the old *.network assertion only held
        # while the fixture lacked the renderer file.
        self.assertTrue(generated, "netplan generate wrote nothing under the target")
        self.assertTrue(
            (self.target / "run" / "NetworkManager" / "system-connections"
             / "netplan-eth0.nmconnection").is_file(),
            "no keyfile for the config interface",
        )
        # The import ran as the invoking (non-root) user: the files
        # it created carry that ownership. In production the script
        # restores root ownership afterwards (see the fakeroot test
        # below); here there is nothing to restore from, because
        # the script itself is already non-root.
        self.assertEqual(timesyncd.stat().st_uid, os.getuid())
        self.assertEqual(netplan_file.stat().st_uid, os.getuid())
        # Run 9: the pre-existing lib/netplan/ files are still
        # there, still 0600, and the 00 file's content is
        # untouched — the import read them, it did not rewrite or
        # loosen them. (Root ownership afterwards is the
        # fakeroot test's job: this test runs non-root, so the
        # script's restore is a no-op here and the files stay
        # owned by the runner.)
        for name in ("00-network-manager-all.yaml", "01-extra.yaml"):
            preexisting = lib_netplan / name
            self.assertTrue(preexisting.is_file(), name)
            self.assertEqual(
                stat.S_IMODE(preexisting.stat().st_mode), 0o600, name
            )
        self.assertEqual(
            (lib_netplan / "00-network-manager-all.yaml").read_text(),
            "network:\n  version: 2\n  renderer: NetworkManager\n",
        )

    def test_import_ownership_prepare_and_restore(self):
        """The ownership dance, under fakeroot (skipped where
        fakeroot is missing): prepare hands the import dirs to
        the import user, restore returns the applied files and
        the dirs to root. stat is read inside the same fakeroot
        session, because the faked ownership does not survive
        outside it. The import user is the current user here —
        chown by name needs a user that exists on this machine."""
        import shutil
        if not shutil.which("fakeroot"):
            self.skipTest("fakeroot not installed")
        import getpass
        user = getpass.getuser()
        check = (
            "set -u\n"
            'source "$1"\n'
            'TARGET="$2"\n'
            'IMPORT_USER="$3"\n'
            'LOGFILE="$TARGET/ownership-check.log"\n'
            'touch "$LOGFILE"\n'
            "resolve_import_ids\n"
            "# Run 9: pre-existing files under lib/netplan/ with\n"
            "# the image's modes (00-... 0600, a second 0600 file\n"
            "# for the general case, and a 0640 file to prove the\n"
            "# mode restore is general, not just 0600).\n"
            'mkdir -p "$TARGET/lib/netplan"\n'
            'chmod 755 "$TARGET/lib/netplan"\n'
            'touch "$TARGET/lib/netplan/00-network-manager-all.yaml" '
            '"$TARGET/lib/netplan/01-extra.yaml" '
            '"$TARGET/lib/netplan/02-restricted.yaml"\n'
            'chmod 600 "$TARGET/lib/netplan/00-network-manager-all.yaml" '
            '"$TARGET/lib/netplan/01-extra.yaml"\n'
            'chmod 640 "$TARGET/lib/netplan/02-restricted.yaml"\n'
            "prepare_import_dirs\n"
            '[ "$(stat -c %u "$TARGET/etc/systemd")" = "$IMPORT_UID" ] '
            '|| { echo "prepare did not hand etc/systemd to the import user"; exit 1; }\n'
            '[ "$(stat -c %u "$TARGET/run/systemd/network")" = "$IMPORT_UID" ] '
            '|| { echo "prepare did not hand run/systemd/network to the import user"; exit 1; }\n'
            "# Run 9: prepare hands lib/netplan/ and its files to\n"
            "# the import user WITHOUT changing their modes.\n"
            '[ "$(stat -c %u "$TARGET/lib/netplan")" = "$IMPORT_UID" ] '
            '|| { echo "prepare did not hand lib/netplan to the import user"; exit 1; }\n'
            '[ "$(stat -c %u "$TARGET/lib/netplan/00-network-manager-all.yaml")" = "$IMPORT_UID" ] '
            '|| { echo "prepare did not hand 00-network-manager-all.yaml to the import user"; exit 1; }\n'
            '[ "$(stat -c %a "$TARGET/lib/netplan/00-network-manager-all.yaml")" = "600" ] '
            '|| { echo "prepare changed the mode of 00-network-manager-all.yaml"; exit 1; }\n'
            '[ "$(stat -c %a "$TARGET/lib/netplan/02-restricted.yaml")" = "640" ] '
            '|| { echo "prepare changed the mode of 02-restricted.yaml"; exit 1; }\n'
            "# Simulate the import (running as the import user) writing.\n"
            'touch "$TARGET/etc/systemd/timesyncd.conf" '
            '"$TARGET/etc/netplan/60-pulpo.yaml"\n'
            'chown "$IMPORT_UID:$IMPORT_GID" '
            '"$TARGET/etc/systemd/timesyncd.conf" "$TARGET/etc/netplan/60-pulpo.yaml"\n'
            "restore_import_ownership\n"
            '[ "$(stat -c %u "$TARGET/etc/systemd/timesyncd.conf")" = "0" ] '
            '|| { echo "restore did not return timesyncd.conf to root"; exit 1; }\n'
            '[ "$(stat -c %u "$TARGET/etc/netplan/60-pulpo.yaml")" = "0" ] '
            '|| { echo "restore did not return 60-pulpo.yaml to root"; exit 1; }\n'
            '[ "$(stat -c %u "$TARGET/etc/systemd")" = "0" ] '
            '|| { echo "restore did not return etc/systemd to root"; exit 1; }\n'
            '[ "$(stat -c %u "$TARGET/run/systemd/network")" = "0" ] '
            '|| { echo "restore did not return run/systemd/network to root"; exit 1; }\n'
            "# Run 9: restore returns lib/netplan/ and its files\n"
            "# to root:root AND to their recorded modes.\n"
            '[ "$(stat -c %u "$TARGET/lib/netplan")" = "0" ] '
            '|| { echo "restore did not return lib/netplan to root"; exit 1; }\n'
            '[ "$(stat -c %a "$TARGET/lib/netplan")" = "755" ] '
            '|| { echo "restore did not return lib/netplan mode 755"; exit 1; }\n'
            '[ "$(stat -c %u "$TARGET/lib/netplan/00-network-manager-all.yaml")" = "0" ] '
            '|| { echo "restore did not return 00-network-manager-all.yaml to root"; exit 1; }\n'
            '[ "$(stat -c %g "$TARGET/lib/netplan/00-network-manager-all.yaml")" = "0" ] '
            '|| { echo "restore did not return 00-network-manager-all.yaml group root"; exit 1; }\n'
            '[ "$(stat -c %a "$TARGET/lib/netplan/00-network-manager-all.yaml")" = "600" ] '
            '|| { echo "restore did not return 00-network-manager-all.yaml mode 600"; exit 1; }\n'
            '[ "$(stat -c %a "$TARGET/lib/netplan/01-extra.yaml")" = "600" ] '
            '|| { echo "restore did not return 01-extra.yaml mode 600"; exit 1; }\n'
            '[ "$(stat -c %a "$TARGET/lib/netplan/02-restricted.yaml")" = "640" ] '
            '|| { echo "restore did not return 02-restricted.yaml mode 640"; exit 1; }\n'
            'echo OWNERSHIP-OK\n'
        )
        result = subprocess.run(
            ["fakeroot", "bash", "-c", check, "ownership-check",
             str(self.SCRIPT), str(self.target), user],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("OWNERSHIP-OK", result.stdout)


class RemoveLivePackagesTests(unittest.TestCase):
    SCRIPT = CALAMARES / "remove-live-packages.sh"
    CONF = CALAMARES / "modules" / "shellprocess_remove-live.conf"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.target = self.root / "target"
        self.target.mkdir()
        # Fake target with casper installed: dpkg status + hook files.
        status_dir = self.target / "var" / "lib" / "dpkg"
        status_dir.mkdir(parents=True)
        (status_dir / "status").write_text(
            "Package: casper\nStatus: install ok installed\nPriority: optional\n\n"
            "Package: grub-efi-amd64-signed\nStatus: install ok installed\n",
            encoding="utf-8",
        )
        hook_dir = self.target / "usr" / "share" / "initramfs-tools" / "hooks"
        hook_dir.mkdir(parents=True)
        (hook_dir / "casper").write_text("#!/bin/sh\n", encoding="utf-8")
        scripts_dir = self.target / "usr" / "share" / "initramfs-tools" / "scripts"
        scripts_dir.mkdir(parents=True)
        (scripts_dir / "casper").write_text("#!/bin/sh\n", encoding="utf-8")
        # Run 11 leftover: /etc/initramfs-tools/conf.d/casperize.conf,
        # owned by no package, plus two non-casper conf files that
        # must survive the removal.
        confd = self.target / "etc" / "initramfs-tools" / "conf.d"
        confd.mkdir(parents=True)
        (confd / "casperize.conf").write_text(
            "export CASPER_GENERATE_UUID=1\n", encoding="utf-8")
        (confd / "default-layer.conf").write_text(
            "LAYERFS_PATH=filesystem.squashfs\n", encoding="utf-8")
        (confd / "calamares-safe-initramfs.conf").write_text(
            "MODULES=most\n", encoding="utf-8")

    def _remove_all_casper(self):
        # Simulate a complete removal: status entry, hook/scripts
        # files, and the conf.d leftover all gone.
        status = self.target / "var" / "lib" / "dpkg" / "status"
        status.write_text(
            "Package: grub-efi-amd64-signed\nStatus: install ok installed\n",
            encoding="utf-8",
        )
        (self.target / "usr" / "share" / "initramfs-tools" / "hooks" / "casper").unlink()
        (self.target / "usr" / "share" / "initramfs-tools" / "scripts" / "casper").unlink()
        (self.target / "etc" / "initramfs-tools" / "conf.d" / "casperize.conf").unlink()

    def _source(self, snippet):
        return subprocess.run(
            ["bash", "-c", snippet, "remove-live-check",
             str(self.SCRIPT), str(self.target)],
            capture_output=True, text=True, timeout=60,
        )

    def test_script_is_executable(self):
        self.assertTrue(self.SCRIPT.stat().st_mode & stat.S_IXUSR)

    def test_live_packages_is_casper_only(self):
        # Run 10: casper is the only live-only package in the
        # 1,823-package image (checked against the built squashfs
        # dpkg status: no ubiquity, lupin-casper or live-boot).
        # The list must stay exactly that until another package is
        # proven live-only the same way.
        result = self._source('source "$1"\nprintf "%s" "$LIVE_PACKAGES"')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "casper")

    def test_casper_present_detects_installed(self):
        result = self._source('source "$1"\ncasper_present "$2"')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_casper_present_false_when_absent(self):
        # Remove the status entry, the hook files, and the conf
        # leftover: nothing left for the check to find.
        self._remove_all_casper()
        result = self._source('source "$1"\ncasper_present "$2"')
        self.assertNotEqual(result.returncode, 0)

    def test_verify_casper_removed_passes_after_removal(self):
        # Simulate the purge: status entry, hook files, and the
        # conf leftover all gone.
        self._remove_all_casper()
        result = self._source('source "$1"\nverify_casper_removed "$2"')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_casper_present_detects_confd_leftover(self):
        # Run 11: the package is purged and the hook/scripts are
        # gone, but casperize.conf (owned by no package) remains —
        # there is still something to remove.
        self._remove_all_casper()
        (self.target / "etc" / "initramfs-tools" / "conf.d" / "casperize.conf").write_text(
            "export CASPER_GENERATE_UUID=1\n", encoding="utf-8")
        result = self._source('source "$1"\ncasper_present "$2"')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_verify_casper_removed_fails_on_confd_leftover(self):
        # Same state: the verify must fail while the conf file
        # survives, or the install would ship the leftover.
        self._remove_all_casper()
        (self.target / "etc" / "initramfs-tools" / "conf.d" / "casperize.conf").write_text(
            "export CASPER_GENERATE_UUID=1\n", encoding="utf-8")
        result = self._source('source "$1"\nverify_casper_removed "$2"')
        self.assertNotEqual(result.returncode, 0)

    def test_remove_casper_confd_files_deletes_only_casper_named(self):
        # The removal deletes casperize.conf and leaves the
        # installer's own conf files alone.
        result = self._source('source "$1"\nremove_casper_confd_files "$2"')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        confd = self.target / "etc" / "initramfs-tools" / "conf.d"
        self.assertFalse((confd / "casperize.conf").exists())
        self.assertTrue((confd / "default-layer.conf").exists())
        self.assertTrue((confd / "calamares-safe-initramfs.conf").exists())

    def test_remove_casper_confd_files_noop_when_absent(self):
        (self.target / "etc" / "initramfs-tools" / "conf.d" / "casperize.conf").unlink()
        result = self._source('source "$1"\nremove_casper_confd_files "$2"')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.target / "etc" / "initramfs-tools" / "conf.d" / "default-layer.conf").exists())

    def test_verify_casper_removed_fails_while_present(self):
        result = self._source('source "$1"\nverify_casper_removed "$2"')
        self.assertNotEqual(result.returncode, 0)

    def _add_live_launchers(self):
        # Hyper-V run: install-pulpo.desktop rode into the target
        # via /etc/skel/Desktop (user creation copies skel) and
        # /usr/share/applications, and Ubuntu's installer icon the
        # same way. A keeper .desktop and a text file must survive.
        skel = self.target / "etc" / "skel" / "Desktop"
        skel.mkdir(parents=True)
        (skel / "install-pulpo.desktop").write_text(
            "[Desktop Entry]", encoding="utf-8")
        (skel / "ubuntu-desktop-bootstrap_ubuntu.desktop").write_text(
            "[Desktop Entry]", encoding="utf-8")
        home = self.target / "home" / "pulpo" / "Desktop"
        home.mkdir(parents=True)
        (home / "install-pulpo.desktop").write_text(
            "[Desktop Entry]", encoding="utf-8")
        (home / "firefox.desktop").write_text(
            "[Desktop Entry]", encoding="utf-8")
        (home / "notes.txt").write_text("keep me", encoding="utf-8")
        apps = self.target / "usr" / "share" / "applications"
        apps.mkdir(parents=True)
        (apps / "install-pulpo.desktop").write_text(
            "[Desktop Entry]", encoding="utf-8")

    def test_remove_live_desktop_launchers_deletes_only_launchers(self):
        self._add_live_launchers()
        result = self._source('source "$1"; remove_live_desktop_launchers "$2"')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.target / "etc" / "skel" / "Desktop" / "install-pulpo.desktop").exists())
        self.assertFalse((self.target / "etc" / "skel" / "Desktop" / "ubuntu-desktop-bootstrap_ubuntu.desktop").exists())
        self.assertFalse((self.target / "home" / "pulpo" / "Desktop" / "install-pulpo.desktop").exists())
        self.assertFalse((self.target / "usr" / "share" / "applications" / "install-pulpo.desktop").exists())
        self.assertTrue((self.target / "home" / "pulpo" / "Desktop" / "firefox.desktop").exists())
        self.assertTrue((self.target / "home" / "pulpo" / "Desktop" / "notes.txt").exists())

    def test_remove_live_desktop_launchers_noop_when_absent(self):
        result = self._source('source "$1"; remove_live_desktop_launchers "$2"')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_main_removes_launchers_even_without_casper(self):
        # The launcher removal is files, not packages: it must run
        # even on a target where casper was never installed (main
        # returns 0 early in that case for the package purge).
        self._add_live_launchers()
        self._remove_all_casper()
        result = self._source('source "$1"; main "$2"')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.target / "etc" / "skel" / "Desktop" / "install-pulpo.desktop").exists())
        self.assertFalse((self.target / "home" / "pulpo" / "Desktop" / "install-pulpo.desktop").exists())

    def test_purge_is_chroot_dpkg_not_file_deletion(self):
        # The removal must be a package purge inside the target
        # chroot (so maintainer scripts run against the target),
        # not a file deletion — deleting the hook files would
        # leave dpkg believing casper is installed. And it must
        # not use apt (offline install; apt would resolve and
        # could pull triggers against the live session).
        text = _read(self.SCRIPT)
        self.assertIn('chroot "$target" dpkg --purge', text)
        self.assertNotIn("apt-get", text)
        self.assertNotIn("rm -rf", text)

    def test_conf_exists_and_runs_the_script(self):
        text = _read(self.CONF)
        self.assertIn("dontChroot: true", text)
        self.assertIn("remove-live-packages.sh ${ROOT}", text)

    def test_settings_order(self):
        sections, _ = _settings_sections()
        exec_list = sections["exec"]
        self.assertLess(exec_list.index("shellprocess@pulpo-config"),
                        exec_list.index("shellprocess@remove-live"))
        self.assertLess(exec_list.index("shellprocess@remove-live"),
                        exec_list.index("initramfscfg"))
        self.assertLess(exec_list.index("shellprocess@remove-live"),
                        exec_list.index("initramfs"))


class InstallCcDebTests(unittest.TestCase):
    SCRIPT = CALAMARES / "install-cc-deb.sh"
    CONF = CALAMARES / "modules" / "shellprocess_install-cc-deb.conf"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.target = self.root / "target"
        self.target.mkdir()
        # Fake release bundle: a couple of .deb files (empty files
        # are enough for the listing path; verification fails on
        # them, which is what the failure-path tests assert).
        self.bundle = self.root / "bundle"
        self.bundle.mkdir()
        (self.bundle / "pulpo-control-center_0.1.0~ubuntu.preview.48+e3.2077631_amd64.deb").write_bytes(b"")
        (self.bundle / "python3-tk_3.12.3-1_amd64.deb").write_bytes(b"")

    def _source(self, snippet):
        return subprocess.run(
            ["bash", "-c", snippet, "install-cc-deb-check",
             str(self.SCRIPT), str(self.target)],
            capture_output=True, text=True, timeout=60,
        )

    def test_script_is_executable(self):
        self.assertTrue(self.SCRIPT.stat().st_mode & stat.S_IXUSR)

    def test_pinned_release_values(self):
        # The expected version, source revision and publisher
        # fingerprint are pinned in the script, not read from the
        # statement -- verify() checks the statement against
        # them. A release change must update all three together.
        text = _read(self.SCRIPT)
        self.assertIn('EXPECTED_VERSION="0.1.0~ubuntu.preview.48+e3.2077631"', text)
        self.assertIn('EXPECTED_REVISION="20776311d4c39c1f6ddebe08ddc5880cb2a9c131"', text)
        self.assertIn('PUBLISHER_FINGERPRINT="19B555C6055FD7B64B848DA67F7B8449ED6FEB20"', text)
        self.assertIn('CC_DEB_NAME="pulpo-control-center_0.1.0~ubuntu.preview.48+e3.2077631_amd64.deb"', text)

    def test_verify_invocation(self):
        # The step must verify with the Control Center's own
        # ubuntu_release.py verify, passing every input it needs.
        text = _read(self.SCRIPT)
        self.assertIn('python3 "$script" verify', text)
        self.assertIn('--artifact "$deb"', text)
        self.assertIn('--manifest "$manifest"', text)
        self.assertIn('--signature "$signature"', text)
        self.assertIn('--public-key "$key"', text)
        self.assertIn('--fingerprint "$PUBLISHER_FINGERPRINT"', text)

    def test_install_uses_chroot_dpkg_and_configure(self):
        text = _read(self.SCRIPT)
        self.assertIn('chroot "$target" dpkg -i', text)
        self.assertIn('chroot "$target" dpkg --configure -a', text)
        self.assertIn('dpkg -s "$pkg"', text)
        self.assertIn("install ok installed", text)

    def test_bundle_debs_lists_debs(self):
        result = self._source(
            'source "$1"; bundle_debs "%s"' % self.bundle)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("pulpo-control-center_0.1.0~ubuntu.preview.48+e3.2077631_amd64.deb", result.stdout)
        self.assertIn("python3-tk_3.12.3-1_amd64.deb", result.stdout)

    def test_verify_release_fails_on_missing_bundle(self):
        # No statement, signature, key or verify scripts in the
        # fake bundle: verification must fail, never pass.
        result = self._source(
            'source "$1"; verify_release "%s"' % self.bundle)
        self.assertNotEqual(result.returncode, 0)

    def test_main_fails_when_bundle_missing(self):
        # The live image's bundle dir does not exist in the test
        # environment, so main() must fail loudly rather than
        # install anything.
        result = self._source('source "$1"; main "$2"')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("verification failed", result.stdout + result.stderr)

    def test_conf_exists_and_runs_the_script(self):
        text = _read(self.CONF)
        self.assertIn("dontChroot: true", text)
        self.assertIn("install-cc-deb.sh ${ROOT}", text)

    def test_settings_order(self):
        sections, _ = _settings_sections()
        exec_list = sections["exec"]
        self.assertLess(exec_list.index("shellprocess@pulpo-config"),
                        exec_list.index("shellprocess@install-cc-deb"))
        self.assertLess(exec_list.index("shellprocess@install-cc-deb"),
                        exec_list.index("shellprocess@remove-live"))
        self.assertLess(exec_list.index("shellprocess@install-cc-deb"),
                        exec_list.index("initramfscfg"))


class VerifyInitramfsTests(unittest.TestCase):
    SCRIPT = CALAMARES / "verify-initramfs.sh"
    CONF = CALAMARES / "modules" / "shellprocess_verify-initramfs.conf"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.target = self.root / "target"
        (self.target / "boot").mkdir(parents=True)

    def _make_initrd(self, path, with_casper):
        # Build a small gzip-compressed cpio initrd. The casper
        # one carries the paths a real casper initrd has
        # (scripts/casper* at the image root — run 3 — plus the
        # usr/share/initramfs-tools/... layout); the clean one
        # carries a non-casper hook, to prove the gate matches
        # casper specifically, not any hook.
        entries = {"init": "#!/bin/sh\n"}
        if with_casper:
            for rel in ("usr/share/initramfs-tools/hooks/casper",
                        "usr/share/initramfs-tools/scripts/casper",
                        "scripts/casper",
                        "scripts/casper-functions",
                        "hooks/casper"):
                entries[rel] = "#!/bin/sh\n"
        else:
            entries["usr/share/initramfs-tools/hooks/zz-plain"] = "#!/bin/sh\n"
        self._make_initrd_from(path, entries)

    def _make_initrd_from(self, path, entries):
        # Build a small gzip-compressed cpio initrd from a
        # {relative path: content} mapping.
        import shutil
        if not shutil.which("cpio"):
            self.skipTest("cpio not installed")
        src = Path(tempfile.mkdtemp(dir=self.root))
        for rel, content in entries.items():
            target = src / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        files = subprocess.run(
            ["find", ".", "-type", "f"], cwd=src,
            capture_output=True, text=True, timeout=30,
        ).stdout
        cpio = subprocess.run(
            ["cpio", "-o", "-H", "newc"], input=files, cwd=src,
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(cpio.returncode, 0, cpio.stderr)
        gz = subprocess.run(
            ["gzip", "-c"], input=cpio.stdout.encode(),
            capture_output=True, timeout=30,
        )
        path.write_bytes(gz.stdout)

    def _source(self, snippet):
        return subprocess.run(
            ["bash", "-c", snippet, "verify-initramfs-check",
             str(self.SCRIPT), str(self.target)],
            capture_output=True, text=True, timeout=60,
        )

    def test_script_is_executable(self):
        self.assertTrue(self.SCRIPT.stat().st_mode & stat.S_IXUSR)

    def test_gate_detects_casper_initrd(self):
        initrd = self.target / "boot" / "initrd.img-7.0.0-31-generic"
        self._make_initrd(initrd, with_casper=True)
        result = self._source(
            'source "$1"\n'
            'initramfs_contains_casper "$2/boot/initrd.img-7.0.0-31-generic"'
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_gate_passes_clean_initrd(self):
        initrd = self.target / "boot" / "initrd.img-7.0.0-31-generic"
        self._make_initrd(initrd, with_casper=False)
        result = self._source(
            'source "$1"\n'
            'initramfs_contains_casper "$2/boot/initrd.img-7.0.0-31-generic"'
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_gate_passes_initrd_with_only_casperize_conf(self):
        # Run 11: the rebuilt initrd contained exactly one
        # casper-named path, conf/conf.d/casperize.conf — an inert
        # config line, not boot logic. The gate must pass it.
        initrd = self.target / "boot" / "initrd.img-7.0.0-31-generic"
        self._make_initrd_from(initrd, {
            "init": "#!/bin/sh\n",
            "conf/conf.d/casperize.conf": "export CASPER_GENERATE_UUID=1\n",
            "conf/conf.d/default-layer.conf": "LAYERFS_PATH=filesystem.squashfs\n",
        })
        result = self._source(
            'source "$1"\n'
            'initramfs_contains_casper "$2/boot/initrd.img-7.0.0-31-generic"'
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_gate_detects_top_level_scripts_casper(self):
        # The real layout (run 3): scripts/casper at the image
        # root, no usr/share prefix.
        initrd = self.target / "boot" / "initrd.img-7.0.0-31-generic"
        self._make_initrd_from(initrd, {
            "init": "#!/bin/sh\n",
            "scripts/casper": "#!/bin/sh\n",
        })
        result = self._source(
            'source "$1"\n'
            'initramfs_contains_casper "$2/boot/initrd.img-7.0.0-31-generic"'
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_gate_lists_initrd_once(self):
        # Run 11: the old gate listed the image twice (once to
        # check, once more to print the matches), 11m28s under
        # TCG. A counting lsinitramfs wrapper must see exactly
        # one invocation, for both verdicts.
        import shutil
        real = shutil.which("lsinitramfs")
        if real is None:
            self.skipTest("lsinitramfs not installed")
        bindir = self.root / "bin"
        bindir.mkdir()
        log = self.root / "lsinitramfs.log"
        wrapper = bindir / "lsinitramfs"
        wrapper.write_text(
            "#!/bin/bash\n"
            f'echo "called $@" >> "{log}"\n'
            f'exec "{real}" "$@"\n',
            encoding="utf-8",
        )
        wrapper.chmod(0o755)
        env = dict(os.environ)
        env["PATH"] = f"{bindir}:{env['PATH']}"
        for with_casper in (True, False):
            initrd = self.target / "boot" / "initrd.img-7.0.0-31-generic"
            self._make_initrd(initrd, with_casper=with_casper)
            if log.exists():
                log.unlink()
            result = subprocess.run(
                [str(self.SCRIPT), str(self.target)],
                capture_output=True, text=True, timeout=60, env=env,
            )
            self.assertEqual(result.returncode == 0, not with_casper,
                             result.stdout + result.stderr)
            calls = (log.read_text(encoding="utf-8").strip().splitlines()
                     if log.exists() else [])
            self.assertEqual(len(calls), 1,
                             f"lsinitramfs called {len(calls)} times: {calls}")

    def test_conf_timeout_covers_tcg_cost(self):
        # Run 11: the old 60 s timeout killed the gate mid-run —
        # one lsinitramfs pass takes ~5.7 min under TCG. The
        # timeout must be well above that (1200 s, ~3.5x).
        text = _read(self.CONF)
        match = re.search(r"^timeout:\s*(\d+)\s*$", text, re.MULTILINE)
        self.assertIsNotNone(match, text)
        self.assertGreaterEqual(int(match.group(1)), 900)

    def test_main_fails_on_casper_initrd(self):
        import shutil
        if not shutil.which("lsinitramfs"):
            self.skipTest("lsinitramfs not installed")
        initrd = self.target / "boot" / "initrd.img-7.0.0-31-generic"
        self._make_initrd(initrd, with_casper=True)
        result = subprocess.run(
            [str(self.SCRIPT), str(self.target)],
            capture_output=True, text=True, timeout=60,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("contains casper", result.stdout + result.stderr)

    def test_main_passes_clean_initrd(self):
        import shutil
        if not shutil.which("lsinitramfs"):
            self.skipTest("lsinitramfs not installed")
        initrd = self.target / "boot" / "initrd.img-7.0.0-31-generic"
        self._make_initrd(initrd, with_casper=False)
        result = subprocess.run(
            [str(self.SCRIPT), str(self.target)],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("gate passed", result.stdout)

    def test_main_fails_with_no_initrd(self):
        result = subprocess.run(
            [str(self.SCRIPT), str(self.target)],
            capture_output=True, text=True, timeout=60,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no initrd", result.stdout + result.stderr)

    def test_conf_exists_and_runs_the_script(self):
        text = _read(self.CONF)
        self.assertIn("dontChroot: true", text)
        self.assertIn("verify-initramfs.sh ${ROOT}", text)

    def test_settings_order(self):
        sections, _ = _settings_sections()
        exec_list = sections["exec"]
        self.assertLess(exec_list.index("initramfs"),
                        exec_list.index("shellprocess@verify-initramfs"))
        self.assertLess(exec_list.index("shellprocess@verify-initramfs"),
                        exec_list.index("grubcfg"))


class GrubPrefixStubTests(unittest.TestCase):
    SCRIPT = CALAMARES / "grub-prefix-stub.sh"
    CONF = CALAMARES / "modules" / "shellprocess_grub-prefix-stub.conf"
    UUID = "c7f3d0b7-6b33-4883-a26a-a115f37c1148"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.target = self.root / "target"
        etc = self.target / "etc"
        etc.mkdir(parents=True)
        (etc / "fstab").write_text(
            f"UUID={self.UUID} / ext4 defaults 0 1\n"
            "UUID=5E44-1A2B /boot/efi vfat umask=0077 0 1\n",
            encoding="utf-8",
        )
        (self.target / "boot" / "efi").mkdir(parents=True)

    def _source(self, snippet):
        return subprocess.run(
            ["bash", "-c", snippet, "grub-stub-check",
             str(self.SCRIPT), str(self.target)],
            capture_output=True, text=True, timeout=60,
        )

    def test_script_is_executable(self):
        self.assertTrue(self.SCRIPT.stat().st_mode & stat.S_IXUSR)

    def test_stub_content_redirects_to_boot_grub(self):
        # The stub must point the signed GRUB (prefix /EFI/ubuntu)
        # at the real menu in /boot/grub, by device-independent
        # UUID search — never at an ESP path, and never at a
        # hard-coded (hd0,gpt1).
        result = self._source(
            'source "$1"\ngrub_stub_content "c7f3d0b7-6b33-4883-a26a-a115f37c1148"'
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            "search --no-floppy --fs-uuid --set=root c7f3d0b7-6b33-4883-a26a-a115f37c1148",
            result.stdout,
        )
        self.assertIn("set prefix=($root)/boot/grub", result.stdout)
        self.assertIn("configfile $prefix/grub.cfg", result.stdout)
        self.assertNotIn("(hd0,gpt1)", result.stdout)
        self.assertNotIn("EFI/pulpo", result.stdout)

    def test_root_uuid_parsed_from_fstab(self):
        result = self._source('source "$1"\nroot_uuid "$2"')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), self.UUID)

    def test_root_uuid_fails_without_uuid_for_root(self):
        (self.target / "etc" / "fstab").write_text(
            "/dev/vda2 / ext4 defaults 0 1\n", encoding="utf-8",
        )
        result = self._source('source "$1"\nroot_uuid "$2"')
        self.assertEqual(result.stdout.strip(), "")

    def test_main_writes_stub(self):
        result = subprocess.run(
            [str(self.SCRIPT), str(self.target)],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        stub = self.target / "boot" / "efi" / "EFI" / "ubuntu" / "grub.cfg"
        self.assertTrue(stub.is_file())
        text = stub.read_text(encoding="utf-8")
        self.assertIn(f"--set=root {self.UUID}", text)
        self.assertIn("configfile $prefix/grub.cfg", text)

    def test_main_fails_without_esp(self):
        import shutil
        shutil.rmtree(self.target / "boot" / "efi")
        result = subprocess.run(
            [str(self.SCRIPT), str(self.target)],
            capture_output=True, text=True, timeout=60,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ESP is not mounted", result.stdout + result.stderr)

    def test_main_fails_without_uuid(self):
        (self.target / "etc" / "fstab").write_text(
            "/dev/vda2 / ext4 defaults 0 1\n", encoding="utf-8",
        )
        result = subprocess.run(
            [str(self.SCRIPT), str(self.target)],
            capture_output=True, text=True, timeout=60,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no UUID for /", result.stdout + result.stderr)

    def test_conf_exists_and_runs_the_script(self):
        text = _read(self.CONF)
        self.assertIn("dontChroot: true", text)
        self.assertIn("grub-prefix-stub.sh ${ROOT}", text)

    def test_settings_order(self):
        sections, _ = _settings_sections()
        exec_list = sections["exec"]
        self.assertLess(exec_list.index("bootloader"),
                        exec_list.index("shellprocess@grub-prefix-stub"))
        self.assertLess(exec_list.index("shellprocess@grub-prefix-stub"),
                        exec_list.index("umount"))


class BuildIntegrationTests(unittest.TestCase):
    def test_build_uses_the_release_cc_deb(self):
        text = _read(INSTALLER / "build-iso.sh")
        self.assertIn("2077631", text)
        self.assertIn("Preview48-release", text)
        self.assertNotIn("b17b654", text)

    def test_build_adds_calamares_and_excludes_gles(self):
        text = _read(INSTALLER / "build-iso.sh")
        self.assertIn("[4f] Calamares disk installer", text)
        self.assertIn("libqt5gui5-gles|libqt5quick5-gles", text)
        self.assertIn("installer/calamares/settings.conf", text)
        self.assertIn("install-pulpo.desktop", text)
        self.assertIn("pulpo-config-install.sh", text)
        self.assertIn("branding/pulpo/logo.png", text)

    def test_build_marks_live_desktop_launcher_executable(self):
        # Hyper-V run: the launcher shipped 0644, so GNOME showed
        # a red-X "untrusted" icon and double-click did nothing
        # until it was right-clicked to "Allow Launching" (chmod
        # +x). The build must set +x on the /etc/skel copy and
        # gate on it, so a regression fails the build loudly.
        text = _read(INSTALLER / "build-iso.sh")
        self.assertIn('chmod +x "$ROOTFS/etc/skel/Desktop/install-pulpo.desktop"', text)
        self.assertIn('[ -x "$ROOTFS/etc/skel/Desktop/install-pulpo.desktop" ]', text)

    def test_build_copies_signed_release_bundle(self):
        # The installer must install the signed release .deb
        # into the target, so the build copies the whole
        # release bundle into the live image: the .deb, its
        # dependency .debs, the signed statement, the detached
        # signature, the publisher key, and the Control
        # Center's own verify scripts.
        text = _read(INSTALLER / "build-iso.sh")
        self.assertIn('cp "$CC_DEB" "$ROOTFS/usr/share/pulpo-installer/control-center/"', text)
        self.assertIn('for deb in ${UNPACKED:-}; do', text)
        self.assertIn('cp "$deb" "$ROOTFS/usr/share/pulpo-installer/control-center/"', text)
        self.assertIn('cp "$CC_RELEASE_JSON" "$ROOTFS/usr/share/pulpo-installer/control-center/release.json"', text)
        self.assertIn('cp "$CC_RELEASE_SIG" "$ROOTFS/usr/share/pulpo-installer/control-center/release.json.asc"', text)
        self.assertIn('cp "$CC_PUBLISHER_KEY" "$ROOTFS/usr/share/pulpo-installer/control-center/publisher.gpg"', text)
        self.assertIn('cp "$CC_VERIFY_SCRIPTS/ubuntu_release.py" "$CC_VERIFY_SCRIPTS/check_ubuntu_deb.py"', text)
        self.assertIn("control-center bundle holds", text)

    def test_build_copies_install_cc_deb_script_and_gates_on_it(self):
        text = _read(INSTALLER / "build-iso.sh")
        self.assertIn("install-cc-deb", text)
        self.assertIn("usr/share/pulpo-installer/calamares/install-cc-deb.sh", text)
        self.assertIn("etc/calamares/modules/shellprocess_install-cc-deb.conf", text)
        self.assertIn('shellprocess@install-cc-deb', text)

    def test_build_rebuilds_iso_with_the_single_squashfs(self):
        # The xorriso rebuild must remove the 21 layered files
        # (listed from the base ISO itself, so the removal cannot
        # drift from the base) and map in the merged
        # filesystem.squashfs — and the output check must prove
        # the single file is there and no layered file remains.
        text = _read(INSTALLER / "build-iso.sh")
        self.assertIn("-map \"$NEW_SQUASHFS\" /casper/filesystem.squashfs", text)
        self.assertIn("REMOVE_ARGS", text)
        self.assertIn("-find /casper -name 'minimal.*'", text)
        self.assertIn("-find /casper -name 'filesystem.squashfs'", text)
        self.assertIn("output ISO still holds layered minimal.* files", text)
        self.assertNotIn("/casper/minimal.standard.live.squashfs", text)

    def test_build_no_longer_claims_live_only(self):
        text = _read(INSTALLER / "build-iso.sh")
        self.assertNotIn("no disk installer", text.lower())
        self.assertIn("Calamares disk installer", text)

    def test_install_test_script_exists_and_is_uefi(self):
        path = INSTALLER / "install-test.sh"
        self.assertTrue(path.is_file())
        self.assertTrue(path.stat().st_mode & stat.S_IXUSR)
        text = _read(path)
        self.assertIn("OVMF", text)
        self.assertIn("qemu-system-x86_64", text)
        self.assertIn("--phase verify", text)
        self.assertIn("user", text)  # user-mode NIC, not -net none
        self.assertIn("pulpo-test.qcow2", text)

    def test_install_test_checks_qemu_img_up_front(self):
        # Regression: qemu-img was missing from the tools prefix
        # and the run died at disk creation instead of failing
        # fast. The pre-flight check must cover qemu-img.
        text = _read(INSTALLER / "install-test.sh")
        self.assertIn('"$QEMU_IMG"', text)
        self.assertIn('for f in "$QEMU" "$QEMU_IMG"', text)

    def test_install_test_type_handles_uppercase(self):
        # Regression: --type passed uppercase through as a
        # literal QEMU key name, which QEMU rejects, so
        # "PulpoPreview" was typed as "ulporeview" and the
        # config copy landed in a wrong-case directory. Uppercase
        # must map to shift-<lower>.
        text = _read(INSTALLER / "install-test.sh")
        self.assertIn('[A-Z]) key="shift-${ch,,}"', text)

    def test_install_test_type_uses_single_monitor_connection(self):
        # Regression: one nc per character let connections
        # overlap when the monitor was slow, and the guest
        # received the characters scrambled. --type must send
        # all keys through a single nc connection, in order.
        text = _read(INSTALLER / "install-test.sh")
        self.assertIn("printf 'sendkey %s\\n'", text)
        self.assertIn("} | nc -w", text)

    def test_install_test_attaches_usb_tablet(self):
        # The usb-tablet is the active mouse (QEMU monitor
        # 'info mice' shows it starred) and provides the button
        # events --mouse clicks with. Both phases need it.
        # Correction (2026-11-12 probe): the old claim that a
        # tablet makes "monitor coordinates map 1:1 to the
        # screen" is FALSE. mouse_move is a no-op for the
        # usb-tablet — confirmed delivered to the monitor five
        # times, the pointer never moved. --mouse is click-only
        # now (see test_install_test_mouse_does_not_position).
        # The tablet also needs a USB bus: -machine q35 creates
        # none by default, so a bare -device usb-tablet makes
        # QEMU exit immediately with "No 'usb-bus' bus found".
        # A qemu-xhci controller provides the bus, in both phases.
        text = _read(INSTALLER / "install-test.sh")
        self.assertEqual(text.count("-device usb-tablet"), 2)
        self.assertEqual(text.count("-device qemu-xhci"), 2)

    def test_install_test_mouse_does_not_position(self):
        # Probed 2026-11-12 (build #10): QEMU monitor mouse_move
        # is a no-op for the usb-tablet (absolute) — five
        # confirmed-delivery attempts, the pointer never moved
        # (screendumps byte-identical). --mouse must therefore NOT
        # send mouse_move; it is a click at the current pointer
        # position only, and the keyboard (--key/--type) is the
        # driver. Pins the finding so nobody re-adds positioning.
        text = _read(INSTALLER / "install-test.sh")
        self.assertNotIn('mon "mouse_move', text)
        self.assertIn("--mouse", text)
        self.assertIn('mon "mouse_button 1"', text)
        self.assertIn("no positioning", text)

    def test_install_test_trap_does_not_kill_qemu_on_exit(self):
        # Regression: the script's sampling loops end long before a
        # full install finishes, and the closing message promises
        # the VM stays running for the operator to drive. An EXIT
        # trap would kill QEMU mid-install as soon as the script
        # finished sampling. Clean up only on abort (INT/TERM).
        text = _read(INSTALLER / "install-test.sh")
        self.assertIn("trap cleanup INT TERM", text)
        self.assertNotIn("trap cleanup EXIT", text)

    def test_install_test_guest_memory_at_least_3072(self):
        # Regression: run 4 stalled for 5+ hours with zero progress
        # at -m 2048 on a 3.8 Gi host — guest and host both starving.
        # The test VM needs at least 3072 MiB (4096 on the 5.8 Gi
        # host); both QEMU invocations must take it from MEM_MB.
        text = _read(INSTALLER / "install-test.sh")
        m = re.search(r"^MEM_MB=(\d+)$", text, re.M)
        self.assertIsNotNone(m, "MEM_MB not defined in install-test.sh")
        self.assertGreaterEqual(int(m.group(1)), 3072)
        self.assertEqual(text.count("-m $MEM_MB"), 2)

    def test_build_populates_apt_lists_and_guards_empty_closure(self):
        # Regression: the build died silently at step 4f after a
        # reboot wiped /tmp/apt-state/lists, because the closure
        # computation assumed a previous run had populated them and
        # an empty closure killed the script via pipefail with no
        # message. The build must populate the lists itself and
        # fail loudly on an empty closure.
        text = _read(INSTALLER / "build-iso.sh")
        self.assertIn("apt-get update", text)
        self.assertIn("/tmp/apt-state/lists", text)
        self.assertIn("apt closure for calamares is empty", text)
        self.assertIn("apt closure for $MISSING is empty", text)
    def test_unpack_check_accepts_symlinks(self):
        # Regression: dbus-x11/AUTHORS.gz is a symlink into
        # libdbus-1-3, whose target only arrives with a later
        # .deb in the same step. The old [ -e ] check followed
        # the link and failed the build on a correctly installed
        # symlink. The check must accept a symlink entry.
        text = _read(INSTALLER / "build-iso.sh")
        self.assertIn('[ -L "$ROOTFS/$f" ]', text)

    def test_build_suppresses_gnome_initial_setup(self):
        # Regression (run 5): the live session autostarts
        # gnome-initial-setup, whose Welcome page covers the desktop
        # and never lets go, so Calamares is never reached. Stock
        # casper's 52gnome_initial_setup is supposed to create the
        # done-marker at boot, but in run 5 the marker was absent at
        # session start. The build must not rely on casper-bottom:
        # bake the marker into /etc/skel AND disable the autostart
        # entry, and verify both in the plain rootfs (step 4g) and
        # in the new squashfs (step 5).
        text = _read(INSTALLER / "build-iso.sh")
        self.assertIn("etc/skel/.config/gnome-initial-setup-done", text)
        self.assertIn("gnome-initial-setup-first-login.desktop", text)
        self.assertIn("Hidden=true", text)
        self.assertIn("GIS marker missing from skel", text)
        self.assertIn("GIS autostart entry not disabled", text)
        self.assertIn("GIS marker missing from new squashfs", text)
        self.assertIn("GIS autostart not disabled in new squashfs", text)

    def test_build_copies_boot_chain_scripts(self):
        # Regression (run 10): the installed initrd was casper-
        # flavoured and the fallback GRUB had the wrong prefix,
        # because nothing removed the live packages or redirected
        # the signed GRUB. The build must stage the three boot-
        # chain fixup scripts and check them in step 4f, and the
        # settings greps must cover their shellprocess instances.
        text = _read(INSTALLER / "build-iso.sh")
        for name in ("remove-live-packages", "verify-initramfs",
                     "grub-prefix-stub"):
            self.assertIn(f"installer/calamares/{name}.sh", text)
            self.assertIn(
                f"usr/share/pulpo-installer/calamares/{name}.sh", text)
        self.assertIn("shellprocess_remove-live.conf", text)
        self.assertIn("shellprocess_verify-initramfs.conf", text)
        self.assertIn("shellprocess_grub-prefix-stub.conf", text)
        self.assertIn('grep -q "shellprocess@remove-live"', text)
        self.assertIn('grep -q "shellprocess@verify-initramfs"', text)
        self.assertIn('grep -q "shellprocess@grub-prefix-stub"', text)

    def test_install_test_preserves_install_nvram(self):
        # Regression (run 10): the verify phase copied the
        # pristine OVMF vars at every launch, destroying the
        # NVRAM boot entry the install had just created — so the
        # verify boot could only ever exercise the fallback path
        # and the efibootmgr "pulpo" check was untestable. The
        # install phase must preserve its vars when it ends, and
        # the verify phase must reuse them when they exist.
        text = _read(INSTALLER / "install-test.sh")
        self.assertIn("OVMF_VARS_4M-install.fd", text)
        self.assertIn('cp "$BTDIR/OVMF_VARS_4M-install.fd" "$BTDIR/OVMF_VARS_4M.fd"', text)
        self.assertIn('cp "$BTDIR/OVMF_VARS_4M.fd" "$BTDIR/OVMF_VARS_4M-install.fd"', text)
        self.assertIn("no install-phase NVRAM found", text)

    def test_settings_names_casper_removal(self):
        # Regression (run 10): settings.conf claimed "nothing to
        # install or remove post-install", which was wrong — the
        # casper package had to be removed or the install's
        # initramfs step regenerated a live initrd. The comment
        # must now say casper is removed, and the exec list must
        # carry the three boot-chain steps in order.
        text = _read(CALAMARES / "settings.conf")
        self.assertIn("casper", text)
        self.assertIn("remove-live", text)
        sections, _ = _settings_sections()
        exec_list = sections["exec"]
        self.assertLess(exec_list.index("shellprocess@pulpo-config"),
                        exec_list.index("shellprocess@remove-live"))
        self.assertLess(exec_list.index("shellprocess@remove-live"),
                        exec_list.index("initramfs"))
        self.assertLess(exec_list.index("initramfs"),
                        exec_list.index("shellprocess@verify-initramfs"))
        self.assertLess(exec_list.index("bootloader"),
                        exec_list.index("shellprocess@grub-prefix-stub"))
        self.assertLess(exec_list.index("shellprocess@grub-prefix-stub"),
                        exec_list.index("umount"))

if __name__ == "__main__":
    unittest.main()
