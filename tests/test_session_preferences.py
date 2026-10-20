import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pulpo import session_preferences as preferences


def setup_value():
    return {"schema": preferences.SCHEMA, "sources": {"Evidence": "/missing/owner-export.json"},
        "ranges": {"overview": 60, "system": 900, "evidence": 3600}, "page": "Evidence", "system_tab": "Diagnostics"}


class PreferenceValidationTests(unittest.TestCase):
    def test_schema_rejects_credentials_results_and_unsupported_settings(self):
        for mutate in (lambda v: v.update(credentials="PRIVATE"), lambda v: v.update(snapshot={}),
                lambda v: v.update(page="https://example.invalid"), lambda v: v.update(system_tab="Repair"),
                lambda v: v["sources"].update(Unknown="/tmp/x"), lambda v: v["ranges"].update(evidence=True),
                lambda v: v["ranges"].update(evidence=5)):
            value = setup_value()
            mutate(value)
            with self.assertRaises(ValueError): preferences.validate(value)
        for path in ("relative.json", "//server/share", "/tmp/../secret", "/tmp/token\nPRIVATE", "/" + "x" * 4097):
            value = setup_value()
            value["sources"]["Evidence"] = path
            with self.assertRaises(ValueError): preferences.validate(value)


@unittest.skipUnless(os.name == "posix", "WSL/POSIX private preference file operations")
class PreferenceFileTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.path = self.directory / "control-center-session.json"

    def test_missing_is_read_only_and_save_roundtrip_is_private_and_bounded(self):
        self.assertIsNone(preferences.load(self.path))
        self.assertEqual([], list(self.directory.iterdir()))
        value = setup_value()
        secret = self.directory / "not-an-export"
        secret.write_text("PRIVATE contents must not be opened")
        value["sources"]["Evidence"] = str(secret)
        original = secret.read_bytes()
        preferences.save(self.path, value)
        self.assertEqual(0o600, self.path.stat().st_mode & 0o777)
        self.assertEqual(value, preferences.load(self.path))
        value["ranges"]["evidence"] = 60
        preferences.save(self.path, value)
        self.assertEqual(value, preferences.load(self.path))
        preferences.forget(self.path)
        self.assertFalse(self.path.exists())
        self.assertEqual(original, secret.read_bytes())
        self.assertEqual([secret], list(self.directory.iterdir()))

    def test_malformed_duplicate_oversize_and_nonprivate_are_rejected_without_changes(self):
        for raw in (b"{", b"x" * 16385, b'{"schema":"a","schema":"b"}', b'{"credential":"PRIVATE"}'):
            self.path.write_bytes(raw)
            self.path.chmod(0o600)
            for action in (lambda: preferences.load(self.path), lambda: preferences.save(self.path, setup_value()), lambda: preferences.forget(self.path)):
                with self.assertRaises((ValueError, OSError)): action()
                self.assertEqual(raw, self.path.read_bytes())
        self.path.write_text(json.dumps(setup_value()))
        self.path.chmod(0o644)
        with self.assertRaises(ValueError): preferences.load(self.path)
        self.assertEqual(0o644, self.path.stat().st_mode & 0o777)

    def test_symlink_hardlink_fifo_and_directory_targets_are_rejected(self):
        other = self.directory / "other"
        other.write_text(json.dumps(setup_value()))
        other.chmod(0o600)
        for create in (lambda: self.path.symlink_to(other), lambda: os.link(other, self.path),
                lambda: os.mkfifo(self.path, 0o600), lambda: self.path.mkdir()):
            create()
            for action in (lambda: preferences.load(self.path), lambda: preferences.save(self.path, setup_value()), lambda: preferences.forget(self.path)):
                with self.assertRaises((ValueError, OSError)): action()
            if self.path.is_dir(): self.path.rmdir()
            else: self.path.unlink()
        self.assertEqual(setup_value(), json.loads(other.read_text()))

    def test_replacement_failure_preserves_previous_document_and_removes_temp(self):
        preferences.save(self.path, setup_value())
        original = self.path.read_bytes()
        value = copy.deepcopy(setup_value())
        value["page"] = "System"
        with patch("pulpo.session_preferences.os.replace", side_effect=OSError("PRIVATE")):
            with self.assertRaises(OSError): preferences.save(self.path, value)
        self.assertEqual(original, self.path.read_bytes())
        self.assertEqual([self.path], list(self.directory.iterdir()))

    def test_unsafe_parent_is_rejected_and_no_preferences_are_created(self):
        parent = self.directory / "unsafe"
        parent.mkdir()
        parent.chmod(0o777)
        with self.assertRaises(ValueError): preferences.save(parent / self.path.name, setup_value())
        self.assertEqual([], list(parent.iterdir()))


if __name__ == "__main__":
    unittest.main()
