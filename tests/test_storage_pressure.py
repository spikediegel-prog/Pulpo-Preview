import contextlib
import errno
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import check_storage_pressure as diagnostic


def fixture(**changes):
    return SimpleNamespace(**{**dict(f_frsize=1024, f_blocks=100, f_bfree=100, f_bavail=100,
                                    f_files=10000, f_ffree=10000, f_favail=10000, f_flag=0), **changes})


class CapacityTests(unittest.TestCase):
    def test_percent_thresholds_and_reserved_blocks(self):
        for available, expected in ((16, "ok"), (15, "warning"), (5, "critical"), (0, "critical")):
            with self.subTest(available=available):
                report = diagnostic.capacity_observation(fixture(f_bfree=20, f_bavail=available), diagnostic.Limits())
                self.assertEqual(expected, report["state"])
                self.assertEqual((20 - available) * 1024, report["bytes"]["reserved_free"])
                self.assertEqual(80 * 1024, report["bytes"]["allocated"])

    def test_explicit_byte_and_inode_reserves_are_observations_not_quotas(self):
        limits = diagnostic.Limits(min_free_bytes=200 * 1024)
        self.assertEqual("critical", diagnostic.capacity_observation(fixture(), limits)["state"])
        limits = diagnostic.Limits(min_free_inodes=10001)
        self.assertEqual("critical", diagnostic.capacity_observation(fixture(), limits)["state"])

    def test_inode_exhaustion_with_plenty_of_bytes_is_critical(self):
        report = diagnostic.capacity_observation(fixture(f_ffree=0, f_favail=0), diagnostic.Limits())
        self.assertEqual("ok", report["bytes"]["state"])
        self.assertEqual("critical", report["state"])

    def test_readonly_volume_never_reports_ok(self):
        report = diagnostic.capacity_observation(fixture(f_flag=os.ST_RDONLY), diagnostic.Limits())
        self.assertEqual("critical", report["state"])
        self.assertIn("filesystem_read_only", report["reasons"])

    def test_invalid_accounting_remains_unknown(self):
        for changes in ({"f_blocks": 0}, {"f_bavail": -1}, {"f_bavail": 101}, {"f_frsize": 0},
                        {"f_bavail": True}, {"f_bfree": 10, "f_bavail": 20}):
            with self.subTest(changes=changes):
                report = diagnostic.capacity_observation(fixture(**changes), diagnostic.Limits())
                self.assertEqual("unknown", report["state"])

    def test_missing_inode_accounting_is_unknown_but_does_not_hide_byte_exhaustion(self):
        for changes in ({"f_files": 0}, {"f_files": 2**64 - 1, "f_ffree": 2**64 - 1, "f_favail": 2**64 - 1}):
            report = diagnostic.capacity_observation(fixture(**changes), diagnostic.Limits())
            self.assertEqual("unknown", report["state"])
        report = diagnostic.capacity_observation(fixture(f_files=0, f_bavail=0), diagnostic.Limits())
        self.assertEqual("critical", report["state"])

    def test_invalid_thresholds_reject(self):
        for values in ({"warn_percent": True}, {"warn_percent": 95}, {"critical_percent": 101},
                       {"min_free_bytes": -1}, {"min_free_inodes": -1}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                diagnostic.Limits(**values)


class StorageObservationTests(unittest.TestCase):
    def test_existing_directory_contents_are_untouched(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            protected = path / "canonical-fixture.sqlite3"
            protected.write_bytes(b"synthetic do not open or rotate")
            with patch("builtins.open", side_effect=AssertionError("file contents must not be read")), \
                    patch.object(Path, "open", side_effect=AssertionError("file contents must not be read")):
                report = diagnostic.observe(path)
            self.assertIn(report["state"], ("ok", "warning", "critical", "unknown"))
            self.assertEqual("not_assessed", report["enforcement"])
            self.assertEqual("not_performed", report["write_probe"])
            self.assertEqual(b"synthetic do not open or rotate", protected.read_bytes())
            self.assertEqual([protected], list(path.iterdir()))

    def test_missing_directory_and_file_never_fall_back_to_parent_capacity(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "not-mounted"
            report = diagnostic.observe(path)
            self.assertEqual("unknown", report["state"])
            self.assertNotIn("bytes", report)
            self.assertFalse(path.exists())
            path.write_text("existing file")
            self.assertEqual("unknown", diagnostic.observe(path)["state"])
            self.assertEqual("existing file", path.read_text())

    def test_parent_and_leaf_symlinks_reject(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            real = root / "real"
            (real / "child").mkdir(parents=True)
            alias = root / "alias"
            alias.symlink_to(real, target_is_directory=True)
            for path in (alias, alias / "child"):
                with self.subTest(path=path):
                    self.assertEqual("unknown", diagnostic.observe(path)["state"])
            self.assertTrue(alias.is_symlink())

    def test_expected_device_mismatch_does_not_return_fallback_capacity(self):
        with tempfile.TemporaryDirectory() as folder:
            actual = diagnostic.observe(folder)["observed_device"]
            wrong = "0:0" if actual != "0:0" else "1:1"
            report = diagnostic.observe(folder, expected_device=wrong)
            self.assertEqual("unknown", report["state"])
            self.assertIn("unexpected_storage_device", report["reasons"])
            self.assertNotIn("bytes", report)
            device = report["observed_device"]
            self.assertNotIn("unexpected_storage_device", diagnostic.observe(folder, expected_device=device)["reasons"])

    def test_permission_and_stat_failures_are_unknown(self):
        with patch.object(diagnostic.os, "open", side_effect=PermissionError):
            self.assertEqual("unknown", diagnostic.observe(Path("/unreadable"))["state"])
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(diagnostic.os, "fstatvfs", side_effect=OSError(errno.EIO, "fixture")):
            self.assertEqual("unknown", diagnostic.observe(folder)["state"])

    def test_directory_replacement_is_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "target"
            path.mkdir()
            original = diagnostic.os.fstatvfs
            def replaced(descriptor):
                value = original(descriptor)
                path.rename(Path(folder) / "old")
                path.mkdir()
                return value
            with patch.object(diagnostic.os, "fstatvfs", side_effect=replaced):
                report = diagnostic.observe(path)
            self.assertEqual("unknown", report["state"])
            self.assertIn("directory_changed_during_observation", report["reasons"])

    def test_parent_replaced_by_same_target_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            parent = root / "parent"
            path = parent / "target"
            path.mkdir(parents=True)
            original = diagnostic.os.fstatvfs
            def replaced(descriptor):
                value = original(descriptor)
                parent.rename(root / "saved")
                parent.symlink_to(root / "saved", target_is_directory=True)
                return value
            with patch.object(diagnostic.os, "fstatvfs", side_effect=replaced):
                report = diagnostic.observe(path)
            self.assertEqual("unknown", report["state"])
            self.assertNotIn("bytes", report)
            self.assertTrue((root / "saved" / "target").is_dir())

    def test_unsafe_input_rejects_before_observation(self):
        for path in ("relative", "/tmp/../data", "/tmp/bad\nname"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                diagnostic.observe(path)
        with self.assertRaises(ValueError):
            diagnostic.observe(Path("/"), expected_device="not-a-device")

    def test_cli_pressure_exit_and_private_create_only_publication(self):
        with tempfile.TemporaryDirectory() as folder:
            evidence = Path(folder) / "report.json"
            with patch.object(diagnostic.os, "fstatvfs", return_value=fixture(f_bavail=0)), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(1, diagnostic.main(["--path", folder, "--evidence", str(evidence)]))
            self.assertEqual("critical", json.loads(evidence.read_text())["state"])
            self.assertEqual(0o600, evidence.stat().st_mode & 0o777)
            before = evidence.read_bytes()
            with contextlib.redirect_stdout(io.StringIO()) as stdout, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(2, diagnostic.main(["--path", folder, "--evidence", str(evidence)]))
            self.assertEqual("", stdout.getvalue())
            self.assertEqual(before, evidence.read_bytes())

    def test_report_full_disk_error_never_claims_publication(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(diagnostic, "publish_report", side_effect=OSError(errno.ENOSPC, "fixture full")), \
                contextlib.redirect_stdout(io.StringIO()) as stdout, \
                contextlib.redirect_stderr(io.StringIO()) as stderr:
            evidence = Path(folder) / "report.json"
            self.assertEqual(2, diagnostic.main(["--path", folder, "--evidence", str(evidence)]))
            self.assertEqual("", stdout.getvalue())
            self.assertIn("publication failed", stderr.getvalue())
            self.assertFalse(evidence.exists())
