import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pulpo import session_preferences as preferences
from pulpo import storage_policy as policy
from pulpo.storage_settings import StorageSettings


def plan():
    return dict(revision=policy.REVISION, choice="local", destination="/archive/public.json", acknowledged=True)


def setup():
    return dict(schema=preferences.SCHEMA, sources={}, ranges=dict(overview=60, system=60, evidence=60),
                page="System", system_tab="Session setup")


class Variable:
    def __init__(self, value): self.value = value
    def get(self): return self.value
    def set(self, value): self.value = value


class StoragePlanTests(unittest.TestCase):
    def test_legacy_setup_and_supported_plans_validate_without_accessing_destination(self):
        self.assertEqual(setup(), preferences.validate(setup()))
        for choice in policy.CHOICES:
            value = setup()
            value["storage"] = dict(plan(), choice=choice)
            with patch("pathlib.Path.open", side_effect=AssertionError("destination must not be opened")):
                self.assertEqual(value, preferences.validate(value))

    def test_planned_integrations_unknown_fields_stale_ack_and_unsafe_paths_are_rejected(self):
        for delta in ({"choice": "s3"}, {"choice": "syslog"}, {"choice": "hybrid"},
                      {"acknowledged": False}, {"acknowledged": 1}, {"revision": "old"},
                      {"retention_days": 30}, {"credential": "TEST ONLY"}, {"choice": []}):
            with self.subTest(delta=delta), self.assertRaises(ValueError):
                preferences.validate(dict(setup(), storage=dict(plan(), **delta)))
        for path in ("/", "relative", "//server/share", "s3://bucket", "/archive/../state", "/a\nsecret", "/" + "x" * 4096):
            with self.subTest(path=path), self.assertRaises(ValueError):
                policy.validate(dict(plan(), destination=path))

    def test_edit_invalidates_ack_and_restore_requires_revision(self):
        editor = StorageSettings.__new__(StorageSettings)
        editor.choice, editor.destination, editor.acknowledged = Variable(""), Variable(""), Variable(False)
        self.assertIsNone(editor.capture())
        editor.restore(plan())
        self.assertEqual(plan(), editor.capture())
        editor.destination.set("/other/export.json")
        editor.changed()
        with self.assertRaises(ValueError): editor.capture()
        with self.assertRaises(ValueError): editor.restore(dict(plan(), revision="old"))

    @unittest.skipUnless(os.name == "posix", "private preference filesystem contract")
    def test_persistence_failure_preserves_old_settings_and_never_touches_archive(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            archive = Path(folder) / "customer-archive.json"
            archive.write_bytes(b"TEST ONLY preserve archive")
            value = dict(setup(), storage=dict(plan(), destination=str(archive)))
            preferences.save(path, value)
            self.assertEqual(value, preferences.load(path))
            self.assertEqual(0o600, path.stat().st_mode & 0o777)
            original = path.read_bytes()
            changed = copy.deepcopy(value)
            changed["storage"]["choice"] = "nas"
            with patch("pulpo.session_preferences.os.replace", side_effect=OSError("TEST ONLY failed save")):
                with self.assertRaises(OSError): preferences.save(path, changed)
            self.assertEqual(original, path.read_bytes())
            preferences.forget(path)
            self.assertEqual(b"TEST ONLY preserve archive", archive.read_bytes())
            self.assertEqual([archive], list(Path(folder).iterdir()))


@unittest.skipUnless(os.name == "posix" and os.environ.get("DISPLAY"), "WSL/Ubuntu graphical Tk session")
class StorageSetupUITests(unittest.TestCase):
    def test_session_save_restore_edit_reacknowledge_and_forget(self):
        import tkinter as tk
        from pulpo.control_center import ControlCenter
        from pulpo import tuning_app
        tuning_app._prepare_tk_libraries()
        with tempfile.TemporaryDirectory() as folder:
            root = tk.Tk()
            try:
                center = ControlCenter(root, Path(folder) / "profile.json")
                session = center.system_view.session
                self.assertIsNotNone(session)
                editor = session.storage
                editor.restore(plan())
                session.remember()
                self.assertEqual(plan(), preferences.load(session.path)["storage"])
                editor.destination.set("/edited/public.json")
                self.assertFalse(editor.acknowledged.get())
                session.remember()
                self.assertEqual(plan(), preferences.load(session.path)["storage"])
                editor.acknowledged.set(True)
                session.remember()
                changed = dict(plan(), destination="/edited/public.json")
                self.assertEqual(changed, preferences.load(session.path)["storage"])
                session.restore()
                self.assertEqual(changed, editor.capture())
                center.show("System")
                center.system_view.select_mode("Session setup")
                root.geometry("480x640")
                root.update()
                editor.choice.set("")
                editor.destination.set("")
                session.remember()
                self.assertNotIn("storage", preferences.load(session.path))
                session.forget()
                self.assertFalse(session.path.exists())
                self.assertEqual([], list(Path(folder).iterdir()))
            finally:
                root.destroy()
                import gc
                center = session = editor = None
                gc.collect()
