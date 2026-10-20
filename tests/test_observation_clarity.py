from dataclasses import replace
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from pulpo.evidence_observation import ActivityHistory, EvidenceObservation, EvidenceEvent
from pulpo.observation_clarity import context_text, graph_state


class ClarityModelTests(unittest.TestCase):
    def setUp(self):
        self.now = time.time_ns()
        self.snapshot = EvidenceObservation("a" * 32, self.now, True, 0, reads=0, writes=0, commits=0)
        self.history = ActivityHistory()

    def state(self, snapshot=None, **options):
        return graph_state(snapshot, self.history, now_ns=self.now, **options)[0]

    def test_selection_error_pending_and_pause_have_distinct_explanations(self):
        self.assertEqual("No observation source selected", self.state())
        self.assertEqual("Source read failed", self.state(error=True, selected=True))
        self.assertEqual("Selection restored · not read", self.state(pending=True, selected=True))
        self.assertEqual("Paused for review", self.state(self.snapshot, selected=True, paused=True))

    def test_frozen_stale_and_clock_mismatch_never_claim_owner_stopped(self):
        stale = replace(self.snapshot, observed_at_ns=self.now - 20_000_000_000)
        title, detail = graph_state(stale, self.history, selected=True, now_ns=self.now)
        self.assertEqual("Source observation is stale", title)
        self.assertIn("may have stopped", detail)
        future = replace(self.snapshot, observed_at_ns=self.now + 10_000_000_000)
        self.assertEqual("Source clock mismatch", self.state(future, selected=True))

    def test_distinct_samples_zero_activity_missing_counters_and_gaps(self):
        self.history.add(replace(self.snapshot, observed_at_ns=self.now - 2_000_000_000))
        self.assertEqual("Waiting for a second sample", self.state(self.snapshot, selected=True))
        self.history.add(self.snapshot)
        self.assertEqual("Recent exported samples", self.state(self.snapshot, selected=True))
        self.assertEqual(0, self.history.points[-1][1]["reads"])
        self.assertEqual("Activity counters unavailable", self.state(replace(self.snapshot, reads=None, writes=None, commits=None), selected=True))
        self.history.points[-1][1]["writes"] = None
        self.assertEqual("Partial activity readings", self.state(self.snapshot, selected=True))
        for key in self.history.points[-1][1]:
            self.history.points[-1][1][key] = None
        self.assertEqual("Waiting for comparable counters", self.state(self.snapshot, selected=True))

    def test_name_hint_and_operator_label_are_unverified_and_never_production(self):
        paths = {"Evidence": Path("/tmp/TEST-ONLY/evidence.json")}
        self.assertIn("unverified filename hint", context_text(paths, {}))
        self.assertIn("enforcement remain Unknown", context_text(paths, {}))
        paths["Evidence"] = Path("/tmp/export.json")
        self.assertEqual("", context_text(paths, {}))
        self.assertIn("Operator-labeled", context_text(paths, {"Evidence": "/tmp/export.json"}))
        self.assertEqual("", context_text(paths, {"Evidence": "/different/export.json"}))


@unittest.skipUnless(os.environ.get("DISPLAY"), "Native Tk display required")
class ClarityUITests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from pulpo.control_center import ControlCenter
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = tk.Tk()
        self.original_scaling = self.root.tk.call("tk", "scaling")
        with patch("pulpo.setup_readiness.is_wsl", return_value=True):
            self.center = ControlCenter(self.root, Path(self.temporary.name) / "profile.json")
        def close():
            import gc
            self.root.tk.call("tk", "scaling", self.original_scaling)
            self.root.destroy()
            self.center = None
            gc.collect()
        self.addCleanup(close)
        self.center.show("Evidence")
        self.page = self.center.evidence_view
        self.root.update()

    def sample(self, path="/tmp/TEST-ONLY/observation.json"):
        now = time.time_ns()
        self.page.path = Path(path)
        self.page.snapshot = EvidenceObservation("a" * 32, now, True, 1,
            events=(EvidenceEvent(now, "decision", "allowed", "b" * 64),))
        self.page.render()
        self.root.update()

    def test_persistent_test_context_no_reads_and_clears_with_selection(self):
        self.sample()
        with patch("pulpo.evidence_page.load_observation", side_effect=AssertionError("no read")):
            self.center.show("Activity")
            self.assertIn("Test-named", self.center.observation_context.cget("text"))
            self.center.show("Governance")
            self.assertTrue(self.center.observation_context.winfo_ismapped())
        self.page.clear()
        self.root.update()
        self.assertFalse(self.center.observation_context.winfo_ismapped())
        self.sample("/tmp/export.json")
        self.page.test_label.set(True)
        self.page.set_test_label()
        self.assertIn("Operator-labeled", self.center.observation_context.cget("text"))
        self.page.clear()
        self.assertEqual({}, self.center.source_test_labels)

    def test_event_copy_exact_hash_and_selection_invalidated_on_source_change_or_failure(self):
        self.sample()
        events = self.page.events_view
        self.assertEqual("disabled", str(events.copy_button.cget("state")))
        events.table.selection_set("0")
        events.select()
        events.toggle()
        self.assertIn("b" * 64, self.page.logs.get("1.0", "end"))
        events.copy()
        self.assertEqual("b" * 64, self.root.clipboard_get())
        self.page.render_logs()
        self.assertEqual(("0",), events.table.selection())
        self.page.path = Path("/different/export.json")
        self.page.render_logs()
        self.assertFalse(events.table.selection())
        self.assertEqual("disabled", str(events.copy_button.cget("state")))
        self.page.snapshot, self.page.error = None, "Read failed"
        self.page.render()
        self.assertFalse(events.events)
        self.assertNotIn("b" * 64, self.page.logs.get("1.0", "end"))

    def test_source_success_is_historical_and_replacement_uses_existing_dialog(self):
        self.sample()
        self.center.record_source_read("Evidence", True)
        successful = self.center.source_last_success("Evidence")
        self.center.record_source_read("Evidence", False)
        self.assertEqual(successful, self.center.source_last_success("Evidence"))
        page = self.center.system_view.source_health
        page.render()
        page.table.selection_set("Evidence")
        page.select()
        self.assertIn(str(self.page.path), page.details.get("1.0", "end"))
        self.assertIn("Last successful local read", page.details.get("1.0", "end"))
        with patch.object(self.page, "select") as select:
            page.replace_button.invoke()
            select.assert_called_once()
        self.page.clear()
        self.assertIn("Unknown", self.center.source_last_success("Evidence"))

    def test_narrow_large_text_context_and_controls_fit(self):
        from tkinter import ttk
        self.sample()
        self.root.tk.call("tk", "scaling", 2.0)
        ttk.Style(self.root).configure("TButton", font=("TkDefaultFont", 14))
        self.root.geometry("640x600")
        self.root.update()
        self.page.toggle_source_details()
        self.root.update()
        for button in (self.page.select_button, self.page.refresh_button, self.page.clear_button, self.page.review_button, self.page.source_toggle):
            parent = button.master
            self.assertLessEqual(button.winfo_x() + button.winfo_width(), parent.winfo_width() + 1)
        for label in self.page.values.values():
            self.assertLessEqual(label.winfo_x() + label.winfo_width(), label.master.winfo_width())
            self.assertGreaterEqual(label.winfo_width(), label.winfo_reqwidth())
        for control in (self.page.test_check, self.page.warning_button):
            self.assertGreaterEqual(control.winfo_width(), control.winfo_reqwidth())
        self.assertLessEqual(self.center.observation_context.winfo_x() + self.center.observation_context.winfo_width(),
                             self.center.observation_context.master.winfo_width())

    def test_non_wsl_retains_original_event_text_and_has_no_test_label(self):
        import tkinter as tk
        from pulpo.control_center import ControlCenter
        root = tk.Toplevel(self.root)
        try:
            with patch("pulpo.setup_readiness.is_wsl", return_value=False):
                center = ControlCenter(root, Path(self.temporary.name) / "other-profile.json")
            self.assertIsNone(center.evidence_view.events_view)
            self.assertIsNone(center.evidence_view.test_label)
            self.assertFalse(center.observation_context.winfo_manager())
        finally:
            root.destroy()
