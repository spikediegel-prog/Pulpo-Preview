import os
from pathlib import Path
import tempfile
import time
try:
    import tkinter as tk
except ImportError:
    tk = None
import unittest
from unittest.mock import patch

from pulpo.control_center import ControlCenter, PAGES, profile_observation
from pulpo import evidence_tuning as tuning
from pulpo import tuning_app


class ProfileObservationTests(unittest.TestCase):
    def test_missing_malformed_and_stale_profiles_never_become_verified(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "profile.json"
            self.assertEqual("Unknown", profile_observation(path)[0])
            self.assertFalse(path.exists())
            for content in (b"{}", b"null", b"{" , b"x" * 17000):
                path.write_bytes(content)
                self.assertEqual("Unknown", profile_observation(path)[0])
                self.assertEqual(content, path.read_bytes())
            tuning.save_settings(tuning.recommended(), path)
            original = path.read_bytes()
            self.assertEqual("Recorded", profile_observation(path)[0])
            with patch.object(tuning, "source_digest", return_value="changed"):
                self.assertEqual("Unknown", profile_observation(path)[0])
            self.assertEqual(original, path.read_bytes())


@unittest.skipUnless(tk is not None and (os.name == "nt" or os.environ.get("DISPLAY")),
                     "Graphical Tk session required")
class ControlCenterTests(unittest.TestCase):
    def setUp(self):
        tuning_app._prepare_tk_libraries()
        self.root = tk.Tk()
        self.addCleanup(self.root.destroy)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.profile = Path(self.temporary.name) / "missing.json"
        self.center = ControlCenter(self.root, self.profile)
        self.root.update()

    def test_navigation_refresh_and_repeated_visits_do_not_create_state(self):
        self.assertEqual("Overview", self.center.current)
        for _ in range(3):
            for name in PAGES:
                self.center.navigation[name].invoke()
                self.root.update()
                self.assertEqual(name, self.center.current)
            self.center.refresh_profile()
        self.assertEqual([], list(Path(self.temporary.name).iterdir()))
        self.assertIn("Unknown", self.center.profile_label.cget("text"))
        with self.assertRaises(ValueError):
            self.center.show("Injected page")

    def test_small_window_reflows_and_scrolls_and_keyboard_changes_page(self):
        wide = self.center.labels[0].cget("wraplength")
        self.root.geometry("640x600")
        self.root.update()
        self.assertLess(self.center.labels[0].cget("wraplength"), wide)
        self.center.show("System")
        self.root.update()
        self.assertGreater(self.center.canvas.bbox("all")[3], self.center.canvas.winfo_height())
        self.center.navigation["System"].focus_force()
        self.root.event_generate("<Alt-Key-1>")
        self.root.update()
        self.assertEqual("Overview", self.center.current)

    def test_session_activity_is_bounded_and_not_persisted(self):
        for index in range(600):
            self.center.append(f"Recorded: local message {index}")
        self.assertLessEqual(int(self.center.output.index("end-1c").split(".")[0]), 501)
        self.assertEqual("disabled", self.center.output.cget("state"))
        self.assertFalse(self.profile.exists())

    def test_existing_launch_comparison_and_explicit_save(self):
        self.root.withdraw()
        windows = []
        def inspect(root):
            windows.append(root)
            def descendants(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from descendants(child)
            def button(label):
                return next(widget for widget in descendants(root)
                            if widget.winfo_class() == "TButton" and widget.cget("text") == label)
            def finish():
                deadline = time.monotonic() + 10
                while str(button("Apply setting").cget("state")) == "disabled":
                    root.update()
                    if time.monotonic() > deadline:
                        self.fail("Fixture operation did not finish")
                    time.sleep(.01)
            root.update()
            self.assertFalse(self.profile.exists())
            button("Evidence").invoke()
            button("Compare thread settings").invoke()
            finish()
            output = next(widget for widget in descendants(root) if isinstance(widget, tk.Text))
            self.assertIn("canonical equality PASS", output.get("1.0", "end"))
            self.assertFalse(self.profile.exists())
            with patch.object(tuning_app, "benchmark_threads", side_effect=ValueError("fixture failure")):
                button("Evidence").invoke()
                button("Compare thread settings").invoke()
                finish()
            self.assertIn("FAILED: fixture failure", output.get("1.0", "end"))
            self.assertFalse(self.profile.exists())
            button("Evidence").invoke()
            button("Apply setting").invoke()
            finish()
            self.assertEqual(0, tuning.load_settings(self.profile).workers)
            self.assertTrue(self.profile.exists())
        try:
            with patch.object(tk.Tk, "mainloop", inspect):
                tuning_app.launch(self.profile)
        finally:
            for root in windows:
                root.destroy()
                self.assertFalse(root.tk.call("after", "info"), "Window left a scheduled callback after destruction")


if __name__ == "__main__":
    unittest.main()
