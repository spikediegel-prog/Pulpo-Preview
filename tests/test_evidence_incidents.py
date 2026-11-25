"""Evidence page incidents section: frozen report, filters, details, re-read.

Read-only by construction: the section displays a frozen incident report
and offers no lifecycle transition and no authority action. Tests run only
where a Tk session exists, like the other Control Center widget tests.
"""
import gc
import os
import tempfile
import unittest
from pathlib import Path

try:
    import tkinter as tk
except ImportError:
    tk = None

from pulpo import GovernanceKernel, Policy, PulpoOrchestrator, SQLiteKernelState
from pulpo.incident_channel import export_incident_report, load_incident_report


@unittest.skipUnless(tk is not None and (os.name == "nt" or os.environ.get("DISPLAY")),
                     "Graphical Tk session required")
class EvidenceIncidentsTests(unittest.TestCase):
    def setUp(self):
        from pulpo import tuning_app
        from pulpo.control_center import ControlCenter
        tuning_app._prepare_tk_libraries()
        self.root = tk.Tk()

        def release_window():
            self.root.destroy()
            self.center = None
            self.root = None
            gc.collect()
        self.addCleanup(release_window)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.profile = Path(self.temporary.name) / "missing.json"
        self.center = ControlCenter(self.root, self.profile)
        self.root.update()
        self.view = self.center.evidence_view.incidents_view
        self.db = Path(self.temporary.name) / "state.sqlite"
        self.backend = SQLiteKernelState(self.db)
        self.addCleanup(self.backend.close)
        self.kernel = GovernanceKernel(Policy(frozenset({"read"}), 0), secret=b"test-only", state=self.backend)
        self.owner = PulpoOrchestrator(self.kernel)
        self.backend.append("purchase_consequence_unknown",
                            {"order_hash": "a" * 64, "intent_hash": "b" * 64,
                             "permit_hash": "c" * 64, "reservation_id": "res-1",
                             "reason": "external_consequence_not_yet_verified"}, 1_000_000_000)
        self.backend.append("permit_rejected",
                            {"permit": "d" * 64, "reason": "permit_expired"}, 2_000_000_000)
        self.report_path = Path(self.temporary.name) / "incident_report.json"
        export_incident_report(self.owner, self.report_path)
        report = load_incident_report(self.report_path)
        self.incident_id = next(
            record.record_id for record in report.records if record.kind == "incident")
        self.near_miss_id = next(
            record.record_id for record in report.records if record.kind == "near_miss")

    def _load(self):
        self.view.path = self.report_path
        self.view.refresh()
        self.root.update()

    def _rows(self):
        return self.view.table.get_children()

    def test_no_report_selected(self):
        self.assertEqual((), self._rows())
        self.assertIn("No incident report selected", self.view.summary.cget("text"))

    def test_load_renders_rows_and_summary(self):
        self._load()
        self.assertEqual(2, len(self._rows()))
        summary = self.view.summary.cget("text")
        self.assertIn("1 incident(s)", summary)
        self.assertIn("1 near-miss(es)", summary)
        self.assertIn("1 unresolved", summary)
        self.assertIn("Audit valid: yes", summary)

    def test_filters_narrow_rows(self):
        self._load()
        self.view.kind.set("incident")
        self.view.render()
        rows = self._rows()
        self.assertEqual(1, len(rows))
        self.assertIn(self.incident_id, self.view.table.item(rows[0], "values"))
        self.view.kind.set("All kinds")
        self.view.resolution.set("not_applicable")
        self.view.render()
        rows = self._rows()
        self.assertEqual(1, len(rows))
        self.assertIn(self.near_miss_id, self.view.table.item(rows[0], "values"))
        self.view.resolution.set("All resolutions")
        self.view.lifecycle.set("not_applicable")
        self.view.render()
        self.assertEqual(1, len(self._rows()))

    def test_select_row_shows_details_and_enables_copy(self):
        self._load()
        self.assertEqual("disabled", str(self.view.copy_button.cget("state")))
        first = self._rows()[0]
        self.view.table.selection_set(first)
        self.view.select_record()
        details = self.view.details.get("1.0", "end")
        record_id = self.view.table.item(first, "values")[4]
        self.assertIn(record_id, details)
        self.assertIn("Reason:", details)
        self.assertIn("Anchor hash:", details)
        self.assertEqual("normal", str(self.view.copy_button.cget("state")))

    def test_copy_reports_record_id(self):
        self._load()
        first = self._rows()[0]
        self.view.table.selection_set(first)
        self.view.select_record()
        self.view.copy()
        self.assertIn("copied", self.view.notice.cget("text"))
        self.assertEqual(self.view.table.item(first, "values")[4],
                         self.root.clipboard_get())

    def test_clear_empties_table(self):
        self._load()
        self.assertEqual(2, len(self._rows()))
        self.view.clear()
        self.assertEqual((), self._rows())
        self.assertIsNone(self.view.path)
        self.assertIn("No incident report selected", self.view.summary.cget("text"))

    def test_invalid_report_shows_error_and_no_rows(self):
        bad = Path(self.temporary.name) / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        self.view.path = bad
        self.view.refresh()
        self.assertEqual((), self._rows())
        self.assertIn("unavailable or invalid", self.view.summary.cget("text"))

    def test_reread_picks_up_new_report(self):
        self._load()
        self.assertEqual(2, len(self._rows()))
        self.backend.append("purchase_consequence_unknown",
                            {"order_hash": "e" * 64, "intent_hash": "f" * 64,
                             "permit_hash": "0" * 64, "reservation_id": "res-2",
                             "reason": "external_consequence_not_yet_verified"}, 3_000_000_000)
        export_incident_report(self.owner, self.report_path)
        self.view.refresh()
        self.assertEqual(3, len(self._rows()))

    def test_page_refresh_with_only_incident_source(self):
        # The observation source is unset; refreshing must still load incidents.
        self.view.path = self.report_path
        self.center.evidence_view.refresh()
        self.assertEqual(2, len(self._rows()))

    def test_no_authority_actions_offered(self):
        buttons = (self.view.select_button.cget("text"), self.view.refresh_button.cget("text"),
                   self.view.clear_button.cget("text"), self.view.detail_button.cget("text"),
                   self.view.copy_button.cget("text"))
        self.assertEqual(("Select incident report…", "Re-read", "Clear",
                          "Show incident details", "Copy record id"), buttons)
        for label in buttons:
            lowered = label.lower()
            self.assertNotIn("acknowledge", lowered)
            self.assertNotIn("resolve", lowered)
            self.assertNotIn("close", lowered)
            self.assertNotIn("reopen", lowered)


if __name__ == "__main__":
    unittest.main()
