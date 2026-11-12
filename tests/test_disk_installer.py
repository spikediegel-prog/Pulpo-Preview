"""Disk installer (Calamares): settings, layered-squashfs copy,
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
# the base ISO; see installer/DISK-INSTALLER.md for why the order
# reproduces the live session's overlay).
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
            "shellprocess@pulpo-config", "initramfscfg", "initramfs",
            "grubcfg", "bootloader", "umount",
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
    def test_all_casper_layers_listed_in_alphabetical_order(self):
        sources, fss, dests = _unpackfs_sources()
        self.assertEqual(len(sources), len(CASPER_LAYERS))
        self.assertEqual(
            [s.removeprefix("/cdrom/casper/") for s in sources],
            CASPER_LAYERS,
        )
        self.assertTrue(all(fs == "squashfs" for fs in fss), fss)
        self.assertTrue(all(d == "" for d in dests), dests)

    def test_no_single_filesystem_squashfs_reference(self):
        # Ubuntu 24.04.5 has no casper/filesystem.squashfs; the
        # flavour settings' reference to it would fail the install.
        text = _read(CALAMARES / "modules" / "unpackfs.conf")
        self.assertNotIn("filesystem.squashfs", text)


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


if __name__ == "__main__":
    unittest.main()
