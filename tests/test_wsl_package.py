"""Isolated lifecycle/adversarial checks; no personal installation is changed."""
import hashlib
import contextlib
import io
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[1] / "scripts" / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


manager = module("wsl_package_manager", "wsl_package_manager.py")
builder = module("build_wsl_package", "build_wsl_package.py")


@unittest.skipUnless(os.name == "posix", "WSL maintenance uses POSIX locks and directory semantics")
class WslPackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="pulpo-package-test-")
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.root = self.folder / manager.NAME
        self.bundle = self.folder / "setup.pyz"
        self.files = {"app/pulpo/__init__.py": b"", "app/pulpo/cli.py": b"def main():\n    return 0\n"}
        self.write_bundle()
        self.package = manager.Package(self.bundle)
        self.environment = patch.object(manager, "environment")
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def write_bundle(self, files=None, extra=None, wrong_hash=False):
        files = self.files if files is None else files
        document = {"schema": 1, "version": "test.1", "source_revision": "fixture",
                    "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
        if wrong_hash:
            document["files"][next(iter(files))] = "0" * 64
        with zipfile.ZipFile(self.bundle, "w") as archive:
            archive.writestr("__main__.py", "# fixture; not executed")
            archive.writestr("package.json", json.dumps(document))
            for name, data in files.items():
                archive.writestr(name, data)
            if extra:
                archive.writestr(*extra)

    def install(self):
        return manager.install(self.package, self.root)

    def test_full_lifecycle_preserves_external_data(self):
        canaries = [self.folder / ".config/PulpoPreview/evidence-performance.json", self.folder / "evidence/audit.db",
                    self.folder / "checkout/local-change.txt"]
        for path in canaries:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"retain exactly")
        self.install()
        (self.root / "app/pulpo/cli.py").write_text("damaged", encoding="utf-8")
        (self.root / "launch.py").unlink()
        for _ in range(2):
            manager.install(self.package, self.root, repair=True)
            self.assertEqual((self.root / "app/pulpo/cli.py").read_bytes(), self.files["app/pulpo/cli.py"])
        manager.uninstall(self.root)
        manager.uninstall(self.root)
        manager.install(self.package, self.root, repair=True)
        for path in canaries:
            self.assertEqual(path.read_bytes(), b"retain exactly")

    def test_existing_install_requires_explicit_repair(self):
        self.install()
        with self.assertRaisesRegex(ValueError, "Already installed"):
            self.install()

    def test_unowned_directory_is_not_overwritten_or_removed(self):
        self.root.mkdir()
        canary = self.root / "important.txt"
        canary.write_text("keep")
        for action in (lambda: self.install(), lambda: manager.uninstall(self.root)):
            with self.assertRaises(ValueError):
                action()
            self.assertEqual(canary.read_text(), "keep")

    def test_unexpected_files_block_repair_and_uninstall(self):
        self.install()
        canary = self.root / "personal-export.json"
        canary.write_text("keep")
        for action in (lambda: manager.install(self.package, self.root, True), lambda: manager.uninstall(self.root)):
            with self.assertRaisesRegex(ValueError, "Unexpected files"):
                action()
        self.assertEqual(canary.read_text(), "keep")

    def test_symlink_root_and_parent_rejected(self):
        outside = self.folder / "outside"
        outside.mkdir()
        self.root.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symbolic"):
            self.install()
        self.root.unlink()
        alias = self.folder / "alias"
        alias.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symbolic"):
            manager.install(self.package, alias / manager.NAME)

    def test_owned_file_replaced_by_symlink_blocks_removal(self):
        self.install()
        victim = self.folder / "evidence.json"
        victim.write_text("keep")
        target = self.root / "app/pulpo/cli.py"
        target.unlink()
        target.symlink_to(victim)
        with self.assertRaises(ValueError):
            manager.uninstall(self.root)
        self.assertEqual(victim.read_text(), "keep")

    def test_bad_root_names_are_rejected(self):
        for path in (self.folder, Path("/"), Path("/pulpo-control-center")):
            with self.assertRaises(ValueError):
                manager.safe_root(path)

    def test_manifest_wrong_root_blocks_removal(self):
        self.install()
        path = self.root / "install.json"
        document = json.loads(path.read_text())
        document["root"] = "/somewhere/else"
        path.write_text(json.dumps(document))
        with self.assertRaises(ValueError):
            manager.uninstall(self.root)
        self.assertTrue(path.exists())

    def test_tampered_package_does_not_touch_install(self):
        self.install()
        before = (self.root / "install.json").read_bytes()
        self.write_bundle(wrong_hash=True)
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            manager.install(self.package, self.root, True)
        self.assertEqual((self.root / "install.json").read_bytes(), before)

    def test_traversal_absolute_and_noncanonical_paths_rejected(self):
        for name in ("app/pulpo/../../escape", "/app/pulpo/escape", "app/pulpo//escape", "app/pulpo/\\escape"):
            self.write_bundle(files=self.files | {name: b"bad"})
            with self.assertRaises(ValueError):
                self.install()
            self.assertFalse(self.root.exists())

    def test_unlisted_and_duplicate_members_rejected(self):
        self.write_bundle(extra=("unexpected", "bad"))
        with self.assertRaises(ValueError):
            self.install()
        self.write_bundle()
        with zipfile.ZipFile(self.bundle, "a") as archive:
            with self.assertWarns(UserWarning):
                archive.writestr("package.json", "{}")
        with self.assertRaises(ValueError):
            self.install()

    def test_package_symlink_rejected(self):
        info = zipfile.ZipInfo("app/pulpo/evil")
        info.create_system = 3
        info.external_attr = 0o120777 << 16
        self.write_bundle(files=self.files | {info.filename: b"target"})
        # Preserve the hash but substitute the member type.
        with zipfile.ZipFile(self.bundle) as archive:
            contents = {i.filename: archive.read(i) for i in archive.infolist()}
        with zipfile.ZipFile(self.bundle, "w") as archive:
            for name, data in contents.items():
                archive.writestr(info if name == info.filename else name, data)
        with self.assertRaises(ValueError):
            self.install()

    def test_failed_construction_preserves_previous_version(self):
        self.install()
        before = (self.root / "install.json").read_bytes()
        with patch.object(manager.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "check")):
            with self.assertRaises(subprocess.CalledProcessError):
                manager.install(self.package, self.root, True)
        self.assertEqual((self.root / "install.json").read_bytes(), before)
        self.assertFalse(list(self.folder.glob(".*-stage-*")))

    def test_failed_switch_restores_previous_version(self):
        self.install()
        before = (self.root / "install.json").read_bytes()
        original = Path.rename

        def fail_stage(path, target):
            if path.name.startswith("." + manager.NAME + "-stage-"):
                raise OSError("simulated interrupted switch")
            return original(path, target)

        with patch.object(Path, "rename", fail_stage):
            with self.assertRaises(OSError):
                manager.install(self.package, self.root, True)
        self.assertEqual((self.root / "install.json").read_bytes(), before)

    def test_interruption_after_old_directory_rename_recovers(self):
        self.install()
        self.root.rename(self.root.with_name(manager.NAME + ".previous"))
        manager.install(self.package, self.root, True)
        self.assertEqual((self.root / "app/pulpo/cli.py").read_bytes(), self.files["app/pulpo/cli.py"])

    def test_two_surviving_versions_are_retained_until_explicit_choice(self):
        self.install()
        previous = self.root.with_name(manager.NAME + ".previous")
        import shutil
        shutil.copytree(self.root, previous)
        with self.assertRaisesRegex(ValueError, "Interrupted repair"):
            manager.install(self.package, self.root, True)
        self.assertTrue(previous.exists())
        self.assertTrue(self.root.exists())
        manager.uninstall(self.root)
        manager.install(self.package, self.root, True)
        self.assertFalse(previous.exists())

    def test_concurrent_maintenance_and_running_app_lock(self):
        import fcntl
        self.install()
        lock = self.folder / ("." + manager.NAME + ".lock")
        with lock.open("r+") as handle:
            for mode in (fcntl.LOCK_EX, fcntl.LOCK_SH):
                fcntl.flock(handle, mode | fcntl.LOCK_NB)
                with self.assertRaisesRegex(ValueError, "another setup"):
                    manager.install(self.package, self.root, True)
                fcntl.flock(handle, fcntl.LOCK_UN)

    def test_symlink_lock_is_not_followed(self):
        victim = self.folder / "important.txt"
        victim.write_text("keep")
        (self.folder / ("." + manager.NAME + ".lock")).symlink_to(victim)
        with self.assertRaises(OSError):
            self.install()
        self.assertEqual(victim.read_text(), "keep")

    def test_actual_launcher_holds_lifetime_lock(self):
        self.install()
        (self.root / "app/pulpo/cli.py").write_text("import time\ndef main():\n    time.sleep(15)\n    return 0\n")
        child = subprocess.Popen([sys.executable, "-I", "-B", str(self.root / "launch.py"), "tune"])
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                try:
                    with manager.locked(self.root):
                        pass
                except ValueError:
                    break
                time.sleep(0.02)
            else:
                self.fail("Launcher did not retain its shared lock")
            with self.assertRaisesRegex(ValueError, "another setup"):
                manager.uninstall(self.root)
        finally:
            child.terminate()
            child.wait(timeout=5)

    def test_cli_uninstall_requires_confirmation_flag(self):
        self.install()
        with patch.object(sys, "argv", [str(self.bundle), "uninstall", "--root", str(self.root)]):
            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                with self.assertRaises(SystemExit) as caught:
                    manager.main()
            self.assertIn("uninstall requires --yes", stderr.getvalue())
        self.assertEqual(caught.exception.code, 2)
        self.assertTrue(self.root.exists())

    def test_launcher_ignores_interpreter_path_in_install_metadata(self):
        self.install()
        marker = self.root / "install.json"
        record = json.loads(marker.read_text())
        record["python"] = "/somewhere/untrusted-program"
        marker.write_text(json.dumps(record))
        with patch.object(manager.subprocess, "Popen") as spawn:
            manager.launch(self.root)
        self.assertNotEqual(spawn.call_args.args[0][0], record["python"])

    def test_independent_setup_window_construction_has_no_install_side_effect(self):
        import tkinter as tk
        from tkinter import ttk
        try:
            window = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Graphical display unavailable: {error}")
        errors = []

        def inspect():
            try:
                def descend(widget):
                    return [widget] + [child for w in widget.winfo_children() for child in descend(w)]
                widgets = descend(window)
                labels = {w.cget("text") for w in widgets if isinstance(w, ttk.Button)}
                self.assertEqual(labels, {"Install", "Repair / Reinstall", "Open", "Uninstall", "Check setup"})
                self.assertTrue(any("Package test.1" in str(w.cget("text")) for w in widgets if isinstance(w, ttk.Label)))
                self.assertFalse(self.root.exists())
            except Exception as error:
                errors.append(error)
            finally:
                window.destroy()

        window.after(100, inspect)
        with patch.object(tk, "Tk", return_value=window):
            manager.gui(self.package, self.root)
        if errors:
            raise errors[0]

    def test_diagnose_does_not_load_sources_or_settings(self):
        self.install()
        with patch.dict(os.environ, {}, clear=True):
            report = manager.diagnose(self.root)
        self.assertIn("No DISPLAY", report)
        self.assertIn("Installed version: test.1", report)
        self.assertIn("No settings, evidence", report)

    def test_diagnose_reports_corruption_and_missing_files(self):
        self.install()
        (self.root / "app/pulpo/cli.py").write_text("damaged")
        (self.root / "app/pulpo/__init__.py").unlink()
        self.assertIn("files differing from package: 2", manager.diagnose(self.root))

    def test_environment_rejects_non_wsl_and_root(self):
        self.environment.stop()
        with patch.object(manager.platform, "system", return_value="Windows"):
            with self.assertRaisesRegex(ValueError, "WSL only"):
                manager.environment()
        with patch.object(manager.platform, "system", return_value="Linux"), patch.object(manager.platform, "release", return_value="microsoft-test"), patch.object(manager.os, "geteuid", return_value=0):
            with self.assertRaisesRegex(ValueError, "without sudo"):
                manager.environment()

    def test_build_real_package_and_manifest(self):
        repo = Path(__file__).resolve().parents[1]
        document = builder.build(repo, self.bundle, "test.1")
        self.assertTrue(self.bundle.read_bytes().startswith(b"#!/usr/bin/env python3\n"))
        with manager.Package(self.bundle).validated() as (_, manifest):
            self.assertEqual(manifest, document)
            self.assertTrue(any(name.endswith(".png") for name in manifest["files"]))
        checksum = self.bundle.with_suffix(".pyz.sha256").read_text().split()[0]
        self.assertEqual(checksum, hashlib.sha256(self.bundle.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
