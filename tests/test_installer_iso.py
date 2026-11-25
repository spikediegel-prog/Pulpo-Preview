"""Live ISO build: manifest integrity, GRUB menu honesty, scripts present.

The live ISO is a rootless remaster of an Ubuntu 24.04 LTS desktop
ISO (see installer/build-iso.sh). These tests check only what the
repo itself can prove: the installer images match the manifest, the
GRUB menu does not offer an installer that does not exist, and the
build / boot-test scripts are present and executable.

These tests use ``unittest`` so the repo's CI
(``python -m unittest discover -s tests``) runs them; pytest is not
installed in this repo and no workflow runs it.
"""

import hashlib
import json
import os
import stat
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = REPO_ROOT / "installer"


class ManifestIntegrityTests(unittest.TestCase):
    def test_every_manifest_image_matches_disk(self):
        manifest = json.loads(
            (INSTALLER / "installer-manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["schema"], "pulpo.preview-installer-manifest.v1")
        images = manifest["images"]
        self.assertGreaterEqual(len(images), 5)
        roles = {img["role"] for img in images}
        self.assertIn("boot-splash-bmp", roles)
        for img in images:
            path = REPO_ROOT / img["file"]
            self.assertTrue(path.is_file(), f"missing manifest image: {img['file']}")
            data = path.read_bytes()
            self.assertEqual(len(data), img["bytes"], img["file"])
            self.assertEqual(
                hashlib.sha256(data).hexdigest(), img["sha256"], img["file"]
            )

    def test_boot_splash_bmp_is_24bit_1920x1080(self):
        bmp = INSTALLER / "assets" / "pulpo-uefi-boot-splash.bmp"
        data = bmp.read_bytes()
        self.assertEqual(data[:2], b"BM")
        width = int.from_bytes(data[18:22], "little")
        height = int.from_bytes(data[22:26], "little")
        bits = int.from_bytes(data[28:30], "little")
        self.assertEqual((width, height, bits), (1920, 1080, 24))


class GrubMenuTests(unittest.TestCase):
    def _grub(self):
        return (INSTALLER / "grub.cfg").read_text(encoding="utf-8")

    def test_live_entry_is_default_and_first(self):
        grub = self._grub()
        self.assertIn('menuentry "Try Pulpo Preview 0.1.0 (live, no install)"', grub)
        self.assertIn("set default=0", grub)
        entries = [line for line in grub.splitlines() if "menuentry" in line]
        self.assertTrue(entries[0].startswith('menuentry "Try Pulpo Preview'))

    def test_no_install_entry_without_an_installer(self):
        # The GRUB menu deliberately has no "Install" entry: the
        # install is a click on the "Install Pulpo Preview" desktop
        # icon in the live session (Calamares), not a boot-menu
        # choice. The menu must not offer "Install" — the desktop
        # launcher is the entry point, and it exists in the repo.
        grub = self._grub()
        for line in grub.splitlines():
            if "menuentry" in line:
                self.assertNotIn("Install Pulpo", line)
        launcher = INSTALLER / "calamares" / "install-pulpo.desktop"
        self.assertTrue(launcher.is_file(), "missing desktop launcher")
        self.assertIn("Exec=sudo -E calamares", launcher.read_text())

    def test_splash_and_serial_console(self):
        grub = self._grub()
        self.assertIn("pulpo-uefi-boot-splash.bmp", grub)
        # Serial console: the QEMU boot test reads the kernel log from
        # ttyS0; tty0 keeps it on screen too.
        self.assertIn("console=ttyS0 console=tty0", grub)
        self.assertIn("/casper/vmlinuz", grub)
        self.assertIn("/casper/initrd", grub)
        # The base ISO boots with `--- quiet splash` and no
        # boot=casper; the live menu keeps the base's kernel lines.
        self.assertIn("--- quiet splash", grub)
        self.assertIn('menuentry "Check installer media"', grub)

    def test_kernel_lines_carry_layerfs_path(self):
        # The live system is a single merged filesystem.squashfs,
        # not the base's 21 layers. The stock initrd sets
        # LAYERFS_PATH=minimal.standard.live.squashfs by default and
        # casper's setup_overlay() then demands all three dot-suffix
        # parent layers; without the override the ISO panics to the
        # initramfs shell (run 3, 2026-11-12). Every kernel line
        # must therefore carry layerfs-path=filesystem.squashfs
        # BEFORE the `---` (an initramfs option), and the name must
        # have no dot so casper requires only that one file.
        grub = self._grub()
        linux_lines = [
            line for line in grub.splitlines()
            if line.strip().startswith("linux") and "/casper/vmlinuz" in line
        ]
        self.assertEqual(len(linux_lines), 3)
        for line in linux_lines:
            before, _, _ = line.partition(" --- ")
            self.assertIn("layerfs-path=filesystem.squashfs", before)

    def test_secure_boot_is_reuse_not_a_claim(self):
        # The build reuses Ubuntu's signed shim/grub unchanged; no
        # Pulpo key is generated or enrolled. The header comment says
        # so in words; the boot lines must not claim otherwise.
        grub = self._grub()
        self.assertIn("reused", grub)
        self.assertIn("unchanged", grub)
        for line in grub.splitlines():
            if line.lstrip().startswith("#"):
                continue
            self.assertNotIn("MOK", line)
            self.assertNotIn("Pulpo key", line)


class BuildScriptTests(unittest.TestCase):
    def test_build_and_boot_test_scripts_present_and_executable(self):
        for name in ("build-iso.sh", "boot-test.sh"):
            path = INSTALLER / name
            self.assertTrue(path.is_file(), f"missing: {name}")
            mode = path.stat().st_mode
            self.assertTrue(mode & stat.S_IXUSR, f"not executable: {name}")
            text = path.read_text(encoding="utf-8")
            self.assertIn("0.1.0", text)

    def test_build_script_names_the_volume_id(self):
        text = (INSTALLER / "build-iso.sh").read_text(encoding="utf-8")
        self.assertIn("PULPO-PREVIEW-0.1.0", text)
        self.assertIn("ubuntu-24.04", text)
        # The build integrates the disk installer (Calamares); it
        # must not claim the ISO is live-only any more.
        self.assertIn("Calamares disk installer", text)
        self.assertNotIn("no disk installer", text.lower())

    def test_boot_test_script_is_uefi_and_tcg(self):
        text = (INSTALLER / "boot-test.sh").read_text(encoding="utf-8")
        self.assertIn("OVMF", text)
        self.assertIn("qemu-system-x86_64", text)
        self.assertIn("screendump", text)


if __name__ == "__main__":
    unittest.main()
