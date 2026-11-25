import os
from types import SimpleNamespace
from unittest.mock import patch
try:
    import tkinter as tk
except ImportError:
    tk = None
import unittest

from pulpo.tuning_app import _confirm_close


@unittest.skipUnless(tk is not None and (os.name == "nt" or os.environ.get("DISPLAY")),
                     "Graphical Tk session required")
class CloseDialogTests(unittest.TestCase):
    """The Control Center close dialog, tested without the full launch loop.

    A separate Toplevel is the window under test, so "Keep closed" can
    destroy it without killing the test root.
    """

    def setUp(self):
        self.root = tk.Tk()
        self.addCleanup(self.root.destroy)
        self.window = tk.Toplevel(self.root)
        self.root.update()
        self.refresh_calls = []
        self.center = SimpleNamespace(
            refresh_profile=lambda: self.refresh_calls.append("refresh")
        )

    def buttons(self, dialog):
        found = {}

        def walk(widget):
            for child in widget.winfo_children():
                if child.winfo_class() == "TButton":
                    found[child.cget("text")] = child
                walk(child)

        walk(dialog)
        return found

    def test_busy_close_shows_info_and_creates_no_dialog(self):
        before = set(self.window.winfo_children())
        with patch("tkinter.messagebox.showinfo") as shown:
            result = _confirm_close(self.window, self.center, lambda: True)
        self.assertIsNone(result)
        shown.assert_called_once_with(
            "Operation in progress", "Wait for the operation to finish before closing.")
        self.assertEqual(before, set(self.window.winfo_children()))

    def test_idle_close_shows_dialog_with_three_actions(self):
        dialog = _confirm_close(self.window, self.center, lambda: False)
        try:
            self.assertEqual("Close Pulpo Control Center", dialog.title())
            self.assertEqual(
                {"Keep open", "Keep closed", "Open again later…"},
                set(self.buttons(dialog)),
            )
        finally:
            if dialog.winfo_exists():
                dialog.destroy()

    def test_keep_open_destroys_only_the_dialog(self):
        dialog = _confirm_close(self.window, self.center, lambda: False)
        self.buttons(dialog)["Keep open"].invoke()
        self.root.update()
        self.assertFalse(dialog.winfo_exists())
        self.assertTrue(self.window.winfo_exists())

    def test_keep_closed_destroys_the_window(self):
        dialog = _confirm_close(self.window, self.center, lambda: False)
        self.buttons(dialog)["Keep closed"].invoke()
        self.root.update()
        self.assertFalse(dialog.winfo_exists())
        self.assertFalse(self.window.winfo_exists())

    def test_reopen_later_withdraws_window_and_restores_it_on_schedule(self):
        scheduled = {}

        def capture_after(delay, callback, *args):
            scheduled["delay"] = delay
            scheduled["callback"] = callback
            return "after-id"

        dialog = _confirm_close(self.window, self.center, lambda: False)
        with patch("tkinter.simpledialog.askinteger", return_value=15), \
             patch.object(self.window, "after", side_effect=capture_after):
            self.buttons(dialog)["Open again later…"].invoke()
        self.root.update()
        self.assertFalse(dialog.winfo_exists())
        self.assertFalse(self.window.winfo_viewable())
        self.assertEqual(15 * 60 * 1000, scheduled["delay"])
        scheduled["callback"]()
        self.root.update()
        self.assertTrue(self.window.winfo_viewable())
        self.assertEqual(["refresh"], self.refresh_calls)

    def test_reopen_later_cancel_keeps_dialog_and_window(self):
        dialog = _confirm_close(self.window, self.center, lambda: False)
        try:
            with patch("tkinter.simpledialog.askinteger", return_value=None):
                self.buttons(dialog)["Open again later…"].invoke()
            self.root.update()
            self.assertTrue(dialog.winfo_exists())
            self.assertTrue(self.window.winfo_exists())
            self.assertTrue(self.window.winfo_viewable())
        finally:
            if dialog.winfo_exists():
                dialog.destroy()


if __name__ == "__main__":
    unittest.main()
