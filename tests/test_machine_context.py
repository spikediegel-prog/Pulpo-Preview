from dataclasses import asdict
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from pulpo.evidence_observation import EvidenceObservation
from pulpo.observation_clarity import elapsed_age, machine_description


class MachineContextModelTests(unittest.TestCase):
    def test_elapsed_age_keeps_missing_and_future_unknown(self):
        now = 200_000_000_000
        self.assertIn("Unknown", elapsed_age(None, now))
        self.assertIn("Unknown", elapsed_age(True, now))
        self.assertIn("ahead", elapsed_age(now + 1, now))
        self.assertEqual("under 1s ago", elapsed_age(now, now))
        self.assertEqual("12s ago", elapsed_age(now - 12_000_000_000, now))
        self.assertEqual("2m 0s ago", elapsed_age(now - 120_000_000_000, now))
        self.assertEqual("1d 1h ago", elapsed_age(1_000_000_000, 90_001_000_000_000))

    def test_operator_description_is_bounded_plain_text_not_a_destination(self):
        self.assertEqual("Pulpo-OS-Dev", machine_description(" Pulpo-OS-Dev "))
        self.assertEqual("", machine_description("   "))
        for value in (None, "x" * 49, "vm\n", "\tvm", "vm\x00", "\u202evm"):
            with self.assertRaises(ValueError):
                machine_description(value)


@unittest.skipUnless(os.environ.get("DISPLAY"), "Native Tk display required")
class MachineContextUITests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from pulpo.control_center import ControlCenter
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = tk.Tk()
        self.scaling = self.root.tk.call("tk", "scaling")
        self.profile = Path(self.temp.name) / "profile.json"
        with patch("pulpo.setup_readiness.is_wsl", return_value=True):
            self.center = ControlCenter(self.root, self.profile)
        def close():
            import gc
            if self.root is not None:
                self.root.tk.call("tk", "scaling", self.scaling)
                self.root.destroy()
            self.center = None
            gc.collect()
        self.addCleanup(close)
        self.page = self.center.evidence_view
        self.path = Path(self.temp.name) / "TEST-ONLY-evidence.json"
        self.now = time.time_ns()
        self.sample = EvidenceObservation("a" * 32, self.now - 120_000_000_000, True, 0)
        self.path.write_text(json.dumps(asdict(self.sample)))
        self.path.chmod(0o600)
        self.page.path = self.path
        self.page.refresh()
        self.center.show("Evidence")
        self.root.update()

    def tick_display(self):
        if self.page.age_timer is not None:
            self.root.after_cancel(self.page.age_timer)
            self.page.age_timer = None
        self.page.tick_ages()

    def test_old_export_and_new_local_read_are_distinct_even_after_reread(self):
        self.assertIn("This window: WSL", self.center.page_caption.cget("text"))
        self.assertIn("local Linux VM", self.center.page_caption.cget("text"))
        self.assertIn("Unknown", self.center.source_description("Evidence"))
        for _ in range(2):
            self.page.refresh()
            text = self.page.source_brief.cget("text")
            self.assertIn("Source-data age · 2m", text)
            self.assertIn("Last successful read · under 1s ago", text)
            self.assertEqual(self.sample.observed_at_ns, self.page.snapshot.observed_at_ns)

    def test_pause_display_age_advances_without_source_reads(self):
        self.center.source_success_reads["Evidence"] = (str(self.path), self.now)
        self.page.toggle_review()
        self.assertIsNone(self.page.timer)
        original = self.path.read_bytes()
        with patch("pulpo.evidence_page.load_observation", side_effect=AssertionError("Display must not read")), \
                patch("pulpo.evidence_page.time.time_ns", return_value=self.now + 10_000_000_000):
            self.tick_display()
        text = self.page.source_brief.cget("text")
        self.assertIn("Source-data age · 2m 10s ago", text)
        self.assertIn("Last successful read · 10s ago", text)
        self.assertEqual(original, self.path.read_bytes())
        self.assertIsNone(self.page.timer)
        self.assertEqual("Paused", self.page.snapshot_summary.cget("text").split(" · ")[-1])

    def test_restored_selection_age_tick_never_reads_or_claims_a_read(self):
        self.page.snapshot = None
        self.page.awaiting_reread = True
        self.center.reset_source_read("Evidence")
        with patch("pulpo.evidence_page.load_observation", side_effect=AssertionError("No restored source read")):
            self.tick_display()
        self.assertIsNone(self.page.snapshot)
        self.assertIn("Last successful read · Unknown", self.page.source_brief.cget("text"))
        self.assertTrue(self.page.awaiting_reread)

    def test_operator_description_is_unverified_cancelable_not_saved_and_cleared_on_replace(self):
        view = self.center.system_view.source_health
        with patch("tkinter.simpledialog.askstring", return_value="Pulpo-OS-Dev"), \
                patch("pulpo.evidence_page.load_observation", side_effect=AssertionError("Label must not read")):
            self.page.describe_source()
        self.assertIn("Pulpo-OS-Dev (operator description; unverified)", self.page.source_brief.cget("text"))
        self.assertIn("This window: WSL", self.center.page_caption.cget("text"))
        with patch("tkinter.simpledialog.askstring", return_value="bad\nlabel"):
            view.edit_machine_description("Evidence")
        self.assertIn("Pulpo-OS-Dev", self.center.source_description("Evidence"))
        with patch("tkinter.simpledialog.askstring", return_value=None):
            view.edit_machine_description("Evidence")
        self.assertIn("Pulpo-OS-Dev", self.center.source_description("Evidence"))
        self.assertFalse(self.profile.exists())
        self.assertFalse(self.profile.with_name("control-center-session.json").exists())
        with patch("tkinter.filedialog.askopenfilename", return_value=str(self.path)):
            self.page.select()
        self.assertIn("Unknown", self.center.source_description("Evidence"))

    def test_failed_read_retains_only_historical_read_age_and_clears_data_age(self):
        self.path.write_text("{}")
        self.page.refresh()
        self.assertIsNone(self.page.snapshot)
        self.assertIn("Source-data age · Unknown", self.page.source_brief.cget("text"))
        self.assertNotIn("Last successful read · Unknown", self.page.source_brief.cget("text"))
        self.assertIn("read failed", self.page.snapshot_summary.cget("text"))
        self.page.clear()
        self.assertIn("Last successful read · Unknown", self.page.source_brief.cget("text"))

    def test_display_timer_stops_hidden_unmapped_and_destroyed(self):
        self.assertIsNotNone(self.page.age_timer)
        self.center.show("Overview")
        self.assertIsNone(self.page.age_timer)
        self.center.show("Evidence")
        self.root.update()
        self.assertIsNotNone(self.page.age_timer)
        self.root.withdraw()
        self.root.update()
        self.assertIsNone(self.page.age_timer)
        self.root.deiconify()
        self.root.update()
        self.assertIsNotNone(self.page.age_timer)
        self.root.tk.call("tk", "scaling", self.scaling)
        self.root.destroy()
        self.root = None
        self.assertTrue(self.page.closed)
        self.assertIsNone(self.page.age_timer)

    def test_age_headers_remain_readable_with_narrow_large_text(self):
        from tkinter import font, ttk
        self.root.tk.call("tk", "scaling", 2.0)
        self.root.geometry("640x600")
        self.center.show("System")
        self.center.system_view.select_mode("Source health")
        self.root.update()
        table = self.center.system_view.source_health.table
        heading_font = font.Font(root=self.root, font=ttk.Style(self.root).lookup("Treeview.Heading", "font") or "TkHeadingFont")
        for column in ("source", "read", "age", "read_age"):
            self.assertGreaterEqual(table.column(column, "width"), heading_font.measure(table.heading(column, "text")))
        if sum(table.column(column, "width") for column in ("source", "read", "age", "read_age")) > table.winfo_width():
            table.xview_moveto(1)
            self.root.update()
            self.assertEqual(1, table.xview()[1])
