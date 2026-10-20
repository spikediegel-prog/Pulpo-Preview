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
from pulpo.local_resources import Metric, ResourceHistory, ResourceSample


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
        def release_window():
            import gc
            self.root.destroy()
            self.center = None
            self.root = None
            # Test suites create many interpreters, unlike the one-window app.
            # Finalize closed Tcl cycles here, before unrelated worker GC.
            gc.collect()
        self.addCleanup(release_window)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.profile = Path(self.temporary.name) / "missing.json"
        self.center = ControlCenter(self.root, self.profile)
        self.root.update()

    def test_decision_explorer_uses_cached_records_without_linking_neighbors(self):
        from pulpo.evidence_observation import EvidenceEvent, EvidenceObservation
        center = self.center
        view = center.decision_explorer
        events = tuple(EvidenceEvent(index, name, outcome, str(index) * 64) for index, name, outcome in (
            (1, "decision", "allowed"), (2, "approval_verified", "recorded"), (3, "permit_consumed", "recorded")))
        center.evidence_view.snapshot = EvidenceObservation("a" * 32, time.time_ns(), True, 3, events=events)
        with patch("pulpo.evidence_page.load_observation", side_effect=AssertionError("No reads")), \
             patch("pulpo.governance_observer.observe_snapshot", side_effect=AssertionError("No reads")):
            for _ in range(3):
                center.show("Governance")
                view.render()
                self.root.update()
                self.assertEqual(3, len(view.table.get_children()))
            view.table.selection_set("2")  # newest first: select the decision
            view.select()
            detail = view.details.get("1.0", "end")
            self.assertIn("Source-reported outcome: allowed", detail)
            self.assertIn("Approval\nUnknown", detail)
            self.assertIn("Permit\nUnknown", detail)
            self.assertIn("Execution and consequence\nUnknown", detail)
            self.assertIn(".000000001 UTC", detail)
            with patch.object(self.root, "clipboard_clear"), patch.object(self.root, "clipboard_append") as copied:
                view.copy()
                safe = copied.call_args.args[0]
                self.assertIn("record=" + "1" * 64, safe)
                self.assertIn("enforcement=Unknown", safe)
                self.assertNotIn("permit=", safe)
            self.assertIn("Enforcement not assessed", center.governance_status.cget("text"))
        self.assertEqual([], list(Path(self.temporary.name).iterdir()))

    def test_decision_explorer_invalidates_replaced_failed_and_returning_sources(self):
        from pulpo.evidence_observation import EvidenceEvent, EvidenceObservation
        from dataclasses import replace
        view, source = self.center.decision_explorer, self.center.evidence_view
        original = EvidenceObservation("a" * 32, 1, True, 1,
            events=(EvidenceEvent(1, "decision", "denied", "f" * 64),))
        source.snapshot = original
        view.render()
        view.table.selection_set("0")
        view.select()
        view.filter.set("Decisions")  # same single row still requires re-selection
        view.render()
        self.assertEqual((), view.table.selection())
        self.assertTrue(view.copy_button.instate(("disabled",)))
        view.table.selection_set("0")
        view.select()
        source.snapshot = replace(original, source_id="b" * 32, audit_valid=False)
        with patch.object(self.root, "clipboard_clear") as cleared:
            view.copy()  # source changed before an explicit UI refresh
            cleared.assert_not_called()
        self.assertEqual((), view.table.selection())
        self.assertTrue(view.copy_button.instate(("disabled",)))
        self.assertIn("FAILED", view.coverage.cget("text"))
        source.error = "PRIVATE /path/token-secret"
        view.render()
        self.assertEqual(0, len(view.table.get_children()))
        self.assertNotIn("PRIVATE", view.coverage.cget("text"))
        source.error = None
        source.snapshot = original
        view.render()
        self.assertEqual((), view.table.selection())
        self.assertTrue(view.copy_button.instate(("disabled",)))
        view.table.selection_set("0")
        view.select()
        source.clear()
        self.assertIsNone(view.snapshot)
        self.assertEqual(0, len(view.table.get_children()))
        self.assertTrue(view.copy_button.instate(("disabled",)))

    def test_decision_explorer_filters_and_narrow_keyboard_selection(self):
        from pulpo.evidence_observation import EvidenceEvent, EvidenceObservation
        view = self.center.decision_explorer
        events = (EvidenceEvent(1, "decision", "allowed", "a" * 64),
                  EvidenceEvent(2, "permit_consumed", "recorded", "b" * 64))
        self.center.evidence_view.snapshot = EvidenceObservation("c" * 32, time.time_ns(), True, 100, events=events)
        self.root.geometry("640x600")
        self.center.show("Governance")
        self.center.governance_tabs.select(self.center.decision_page)
        view.filter.set("Decisions")
        view.render()
        self.root.update()
        self.assertEqual(1, len(view.events))
        self.assertIn("not full history", view.coverage.cget("text"))
        self.assertLessEqual(sum(view.table.column(c, "width") for c in ("event", "outcome")), view.table.winfo_width())
        view.table.focus_force()
        self.root.update()
        view.table.event_generate("<Down>")
        self.root.update()
        self.assertIsNotNone(view.selected_event())
        self.assertFalse(view.copy_button.instate(("disabled",)))
        view.filter.set("Approvals")
        view.render()
        self.root.update()
        self.assertEqual(0, len(view.events))
        self.assertTrue(view.copy_button.instate(("disabled",)))

    def test_source_health_navigation_reads_only_cache_and_stops_age_timer(self):
        center = self.center
        view = center.system_view.source_health
        with patch("pulpo.evidence_page.load_observation", side_effect=AssertionError("No file reads")), \
             patch("pulpo.connections_page.load_connection_observation", side_effect=AssertionError("No file reads")), \
             patch("pulpo.governance_observer.observe_snapshot", side_effect=AssertionError("No file reads")):
            for _ in range(3):
                center.show("System")
                center.system_view.select_mode("Source health")
                view.render()
                self.root.update()
                self.assertEqual(5, len(view.table.get_children()))
                self.assertTrue(view.active)
                self.assertIsNotNone(view.timer)
                view.table.selection_set("Evidence")
                view.select()
                self.assertIn("No local read attempt", view.details.get("1.0", "end"))
                view.open_button.invoke()
                self.assertEqual("Evidence", center.current)
                self.assertFalse(view.active)
                self.assertIsNone(view.timer)
        self.assertFalse(center.source_reads)
        self.assertEqual([], list(Path(self.temporary.name).iterdir()))

    def test_source_health_records_real_reads_rereads_failures_and_clear(self):
        from dataclasses import asdict
        import json
        from pulpo.evidence_observation import EvidenceObservation
        from pulpo.connection_observation import ConnectionObservation
        from pulpo.mcp_boundary import MCPReadSnapshot
        center = self.center
        folder = Path(self.temporary.name)
        def write(name, value):
            path = folder / name
            path.write_text(json.dumps(asdict(value)), encoding="utf-8")
            path.chmod(0o600)
            return path
        source_time = time.time_ns() - 20_000_000_000
        evidence = EvidenceObservation("a" * 32, source_time, True, 0)
        path = write("evidence.json", evidence)
        center.evidence_view.path = path
        center.evidence_view.refresh()
        first = center.source_reads["Evidence"]
        center.evidence_view.refresh()
        self.assertTrue(center.source_reads["Evidence"].succeeded)
        self.assertGreaterEqual(center.source_reads["Evidence"].recorded_at_ns, first.recorded_at_ns)
        view = center.system_view.source_health
        view.render()
        row = next(row for row in view.rows if row.key == "Evidence")
        self.assertEqual(source_time, row.observed_at_ns)
        self.assertEqual("Stale", row.freshness)
        self.assertEqual("Read OK", row.read_status)
        self.assertEqual(evidence, center.evidence_view.snapshot)
        self.assertEqual(json.dumps(asdict(evidence)), path.read_text())
        path.write_text('{"PRIVATE":"secret"}', encoding="utf-8")
        center.evidence_view.refresh()
        view.render()
        row = next(row for row in view.rows if row.key == "Evidence")
        self.assertEqual("Read failed", row.read_status)
        self.assertIsNone(row.observed_at_ns)
        view.table.selection_set("Evidence")
        view.select()
        self.assertNotIn("PRIVATE", view.details.get("1.0", "end"))
        center.evidence_view.clear()
        self.assertNotIn("Evidence", center.source_reads)
        center.governance_path = write("governance.json", MCPReadSnapshot("b" * 64, False, 1, "c" * 64))
        center.refresh_governance()
        self.assertTrue(center.source_reads["Governance"].succeeded)  # reported audit failure is a readable file
        view.render()
        row = next(row for row in view.rows if row.key == "Governance")
        self.assertIsNone(row.observed_at_ns)
        self.assertTrue(row.issues)
        center.clear_governance()
        self.assertNotIn("Governance", center.source_reads)
        connection = ConnectionObservation("UniFi UDM", time.time_ns(), reason="tls")
        center.connections_view.paths["UniFi UDM"] = write("udm.json", connection)
        center.connections_view.refresh("UniFi UDM")
        self.assertTrue(center.source_reads["UniFi UDM"].succeeded)
        view.render()
        row = next(row for row in view.rows if row.key == "UniFi UDM")
        self.assertEqual("Read OK", row.read_status)
        self.assertIn("TLS", row.issues[0])
        center.connections_view.clear("UniFi UDM")
        self.assertNotIn("UniFi UDM", center.source_reads)
        with self.assertRaises(ValueError):
            center.record_source_read("PRIVATE arbitrary key", True)
        self.assertEqual({}, center.source_reads)

    def test_source_health_narrow_tabs_table_keyboard_and_age_selection(self):
        from dataclasses import replace
        from pulpo.evidence_observation import EvidenceObservation
        center = self.center
        self.root.geometry("640x600")
        center.show("System")
        center.system_view.select_mode("Source health")
        view = center.system_view.source_health
        self.root.update()
        self.assertEqual(1, int(center.system_view.tabs["Source health"].grid_info()["row"]))
        self.assertLessEqual(sum(view.table.column(c, "width") for c in ("source", "read", "age")), view.table.winfo_width())
        view.table.focus_force()
        self.root.update()
        view.table.event_generate("<Down>")
        self.root.update()
        self.assertEqual("Governance", view.selected_row().key)
        self.assertFalse(view.open_button.instate(("disabled",)))
        center.evidence_view.path = Path(self.temporary.name) / "not-read.json"
        center.evidence_view.snapshot = EvidenceObservation("d" * 32, time.time_ns(), True, 0)
        view.render()
        view.table.selection_set("Evidence")
        view.select()
        self.root.update()
        view.details.yview_moveto(1)
        position = view.details.index("@0,0").split(".")[0]
        center.evidence_view.snapshot = replace(center.evidence_view.snapshot, observed_at_ns=time.time_ns() - 30_000_000_000)
        view.render()
        self.root.update()
        self.assertEqual("Evidence", view.selected_row().key)
        self.assertEqual(position, view.details.index("@0,0").split(".")[0])
        self.assertIn("Stale", view.details.get("1.0", "end"))
        self.assertEqual(5, len(view.table.get_children()))

    def test_readiness_is_absent_outside_wsl(self):
        root = tk.Tk()
        try:
            with patch("pulpo.setup_readiness.is_wsl", return_value=False):
                center = ControlCenter(root, self.profile)
            self.assertIsNone(center.system_view.readiness)
            self.assertIsNone(center.system_view.configuration)
            self.assertIsNone(center.system_view.troubleshooting)
            self.assertNotIn("Troubleshooting", center.system_view.tabs)
            self.assertNotIn("Configuration", center.system_view.tabs)
            self.assertNotIn("Setup readiness", center.system_view.tabs)
            self.assertEqual(3, len(center.system_view.tabs))
        finally:
            root.destroy()

    def test_wsl_readiness_cache_only_navigation_optional_scope_and_lifecycle(self):
        from pulpo.setup_readiness import is_wsl
        if not is_wsl():
            self.skipTest("WSL-only checklist")
        center = self.center
        view = center.system_view.readiness
        with patch("pulpo.evidence_page.load_observation", side_effect=AssertionError("No reads")), \
             patch("pulpo.connections_page.load_connection_observation", side_effect=AssertionError("No reads")), \
             patch("pulpo.governance_observer.observe_snapshot", side_effect=AssertionError("No reads")):
            for _ in range(3):
                center.show("System")
                center.system_view.select_mode("Setup readiness")
                self.root.update()
                self.assertEqual(9, len(view.table.get_children()))
                self.assertTrue(view.active)
                self.assertIsNotNone(view.timer)
                view.table.selection_set("assurance")
                view.select()
                self.assertIn("Unknown", view.details.get("1.0", "end"))
                view.open_button.invoke()
                self.assertEqual("Governance", center.current)
                self.assertEqual(str(center.decision_page), center.governance_tabs.select())
                self.assertFalse(view.active)
                self.assertIsNone(view.timer)
        self.assertEqual([], list(Path(self.temporary.name).iterdir()))

    def test_wsl_readiness_narrow_keyboard_and_udm_guide_navigation(self):
        from pulpo.setup_readiness import is_wsl
        if not is_wsl():
            self.skipTest("WSL-only checklist")
        center = self.center
        view = center.system_view.readiness
        self.root.geometry("640x600")
        center.show("System")
        center.system_view.select_mode("Setup readiness")
        self.root.update()
        self.assertEqual(1, int(center.system_view.tabs["Setup readiness"].grid_info()["row"]))
        self.assertLessEqual(sum(view.table.column(c, "width") for c in ("step", "state")), view.table.winfo_width())
        view.table.focus_force()
        self.root.update()
        view.table.event_generate("<Down>")
        self.root.update()
        self.assertEqual("runtime", view.selected_row().key)
        view.table.selection_set("udm_site")
        view.select()
        self.assertIn("No matching reviewed", view.details.get("1.0", "end"))
        view.open_button.invoke()
        self.assertEqual("Connections", center.current)
        guide = center.connections_view.setup_guide
        self.assertIsNotNone(guide.window)
        guide.window.destroy()
        center.show("System")
        center.system_view.select_mode("Setup readiness")
        view.render()
        self.assertEqual("Unknown", next(row for row in view.rows if row.key == "udm_site").state)

    def test_wsl_configuration_shares_proposal_and_idle_updates_do_not_read_files(self):
        from pulpo.setup_readiness import is_wsl
        if not is_wsl(): self.skipTest("WSL-only configuration view")
        system = self.center.system_view
        self.center.show("System")
        system.select_mode("Configuration")
        view = system.configuration
        self.assertEqual(0, view.current.workers)
        self.assertIsNone(view.proposal_at)
        self.assertIn("initial suggestion", view.proposal.cget("text"))
        system.candidate.set("1")
        system.candidate_changed()
        self.assertIsNotNone(view.proposal_at)
        self.assertEqual("1", str(view.table.item("workers", "values")[2]))
        self.assertIn("Both values use serial", view.proposal.cget("text"))
        with patch("pulpo.configuration_page.inspect_configuration", side_effect=AssertionError("Idle updates are cache-only")):
            for _ in range(3): view.render()
            self.center.show("Overview")
            self.assertFalse(view.active)
            self.assertIsNone(view.timer)
        self.assertFalse(self.profile.exists())
        self.assertEqual([], list(Path(self.temporary.name).iterdir()))

    def test_wsl_configuration_expiry_external_profile_edit_and_minimum_layout(self):
        from pulpo.setup_readiness import is_wsl
        if not is_wsl(): self.skipTest("WSL-only configuration view")
        from pulpo import system_benchmark as benchmark
        from tests.test_system_benchmark import SystemBenchmarkTests
        import threading
        system = self.center.system_view
        view = system.configuration
        system.candidate.set("1")
        helper = SystemBenchmarkTests()
        with patch.object(benchmark, "measure_case", side_effect=lambda workers, *_: helper.row(workers)):
            system.report = benchmark.compare_settings(self.profile, 1, threading.Event(), lambda text: None)
        self.root.geometry("640x600")
        self.center.show("System")
        system.select_mode("Configuration")
        self.root.update()
        self.assertIn("Applicable", view.validity.cget("text"))
        self.assertIn("Exact benchmark pair: 0 → 1", view.measurements.cget("text"))
        self.assertLessEqual(sum(view.table.column(c, "width") for c in ("setting", "current", "proposed")), view.table.winfo_width())
        self.assertEqual(2, int(system.tabs["Configuration"].grid_info()["row"]))
        completed = system.report["completed_at"]
        with patch("pulpo.configuration_comparison.time.time", return_value=completed + 901):
            view.render()
            self.assertIn("expired", view.validity.cget("text"))
            self.assertNotIn("Median:", view.measurements.cget("text"))
        tuning.save_settings(tuning.EvidenceSettings(0), self.profile)
        before = self.profile.read_bytes()
        view.refresh()
        self.assertIn("Current profile changed", view.validity.cget("text"))
        self.assertEqual(before, self.profile.read_bytes())
        self.assertIsNone(view.last_change)  # external change time/reason not inferred

    def test_wsl_troubleshooting_navigation_does_not_read_or_create_state(self):
        from pulpo.setup_readiness import is_wsl
        if not is_wsl(): self.skipTest("WSL-only troubleshooting")
        system = self.center.system_view
        view = system.troubleshooting
        self.root.geometry("640x600")
        with patch("pulpo.evidence_page.load_observation", side_effect=AssertionError("No implicit reads")), \
             patch("pulpo.connections_page.load_connection_observation", side_effect=AssertionError("No implicit reads")), \
             patch("pulpo.governance_observer.observe_snapshot", side_effect=AssertionError("No implicit reads")):
            for _ in range(3):
                self.center.show("System")
                system.select_mode("Troubleshooting")
                self.root.update()
                view.render()
                self.assertEqual(9, len(view.table.get_children()))
                self.assertTrue(view.export_button.instate(("disabled",)))
            self.assertEqual(2, int(system.tabs["Troubleshooting"].grid_info()["row"]))
            self.assertLessEqual(sum(view.table.column(c, "width") for c in ("check", "state")), view.table.winfo_width())
            view.table.focus_force()
            self.root.update()
            view.table.event_generate("<Down>")
            self.root.update()
            self.assertEqual("runtime", view.selected_row().key)
            view.table.selection_set("services")
            view.select()
            self.assertTrue(view.check_button.instate(("disabled",)))
            view.check()
            self.assertIn("unavailable", view.notice.cget("text"))
            self.center.show("Overview")
            self.assertFalse(view.active)
            self.assertIsNone(view.timer)
        self.assertEqual([], list(Path(self.temporary.name).iterdir()))

    def test_wsl_troubleshooting_explicit_reader_failure_and_frozen_export(self):
        from pulpo.setup_readiness import is_wsl
        if not is_wsl(): self.skipTest("WSL-only troubleshooting")
        import json
        from dataclasses import asdict
        from pulpo.evidence_observation import EvidenceObservation
        view = self.center.system_view.troubleshooting
        self.center.show("System")
        self.center.system_view.select_mode("Troubleshooting")
        path = Path(self.temporary.name) / "evidence.json"
        source = EvidenceObservation("a" * 32, time.time_ns(), True, 0, volume_total=1000, volume_free=50)
        path.write_text(json.dumps(asdict(source)))
        path.chmod(0o600)
        self.center.evidence_view.path = path
        view.render()
        view.table.selection_set("storage")
        view.select()
        self.assertFalse(view.check_button.instate(("disabled",)))
        before = path.read_bytes()
        view.check_button.invoke()
        self.assertEqual(before, path.read_bytes())
        self.assertEqual(source, self.center.evidence_view.snapshot)
        self.assertIn("50 of 1000", view.details.get("1.0", "end"))
        self.assertIn("Local check completed: 20", view.details.get("1.0", "end"))
        view.preview_report()
        preview = view.preview
        self.assertEqual(preview, view.report_text.get("1.0", "end-1c"))
        path.write_text("PRIVATE token /secret/file")
        view.check_button.invoke()
        self.assertIsNone(self.center.evidence_view.snapshot)
        self.assertNotIn("50 of 1000", view.details.get("1.0", "end"))
        self.assertEqual(preview, view.preview)
        with patch.object(self.center.system_view, "write_file") as export:
            view.export_button.invoke()
            self.assertEqual(preview, export.call_args.args[0])
        output = Path(self.temporary.name) / "report.json"
        with patch("tkinter.filedialog.asksaveasfilename", return_value=str(output)):
            view.export_button.invoke()
        self.assertEqual(preview, output.read_text())
        with patch("tkinter.filedialog.asksaveasfilename", return_value=""):
            view.export_button.invoke()
        self.assertIn("cancelled", view.notice.cget("text"))
        with patch("tkinter.filedialog.asksaveasfilename", return_value=str(output / "unwritable.json")):
            view.export_button.invoke()
        self.assertIn("failed", view.notice.cget("text"))
        self.assertEqual(preview, view.preview)
        view.preview_report()
        self.assertNotIn("50 of 1000", view.preview)
        self.assertNotIn("PRIVATE", view.preview)
        self.assertNotIn(str(path), view.preview)
        view.table.selection_set("runtime")
        view.check()
        self.assertIsNotNone(view.local_checked_at_ns)
        view.table.selection_set("cleanup")
        view.open_button.invoke()
        self.assertEqual("Tuning & benchmarks", self.center.system_view.mode)

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
        self.assertEqual(1, int(self.center.monitor.choices.grid_info()["row"]))
        choices = self.center.monitor.choices
        self.assertLessEqual(choices.winfo_x() + choices.winfo_width(), choices.master.winfo_width())
        self.assertEqual(1, int(self.center.attention.grid_info()["row"]))
        self.center.show("System")
        self.root.update()
        self.assertGreater(self.center.canvas.bbox("all")[3], self.center.canvas.winfo_height())
        self.center.navigation["System"].focus_force()
        self.root.event_generate("<Alt-Key-1>")
        self.root.update()
        self.assertEqual("Overview", self.center.current)

    def test_session_activity_is_bounded_and_not_persisted(self):
        for index in range(600):
            self.assertIsNone(self.center.append(f"Recorded: local message {index}"))
        self.assertLessEqual(int(self.center.output.index("end-1c").split(".")[0]), 501)
        self.assertEqual("disabled", self.center.output.cget("state"))
        self.assertFalse(self.profile.exists())

    def test_attention_navigation_uses_only_cached_reports(self):
        from pulpo.connection_observation import ConnectionObservation
        center = self.center
        center.connections_view.observations["UniFi UDM"] = ConnectionObservation("UniFi UDM", time.time_ns(), reason="tls")
        with patch("pulpo.connections_page.load_connection_observation", side_effect=AssertionError("No file reads")), \
             patch("pulpo.evidence_page.load_observation", side_effect=AssertionError("No file reads")), \
             patch("pulpo.governance_observer.observe_snapshot", side_effect=AssertionError("No file reads")):
            center.refresh_attention()
            panel = center.needs_attention
            panel.table.selection_set("connection:UniFi UDM:failure")
            panel.select()
            self.assertIn("identity unverified", panel.detail.cget("text"))
            self.assertEqual("Open UDM setup guide", panel.open_button.cget("text"))
            panel.open_button.invoke()
        self.assertEqual("Connections", center.current)
        self.assertIsNotNone(center.connections_view.setup_guide.window)
        self.assertEqual("Unknown", center.status_rows["Governance"].state)
        center.connections_view.setup_guide.window.destroy()
        self.assertEqual([], list(Path(self.temporary.name).iterdir()))

    def test_attention_age_selection_and_clearing_do_not_resolve_conditions(self):
        from pulpo.connection_observation import ConnectionObservation
        center, now = self.center, time.time_ns()
        page, panel = center.connections_view, center.needs_attention
        page.observations["UniFi UDM"] = ConnectionObservation("UniFi UDM", now, reason="tls")
        center.refresh_attention()
        key = "connection:UniFi UDM:failure"
        panel.table.selection_set(key)
        panel.select()
        with patch("pulpo.attention_model.time.time_ns", return_value=now+61_000_000_000):
            center.refresh_attention()
            center.refresh_attention()
        self.assertEqual((key,), panel.table.selection())
        self.assertIn("connection:UniFi UDM:age", panel.items)
        self.assertEqual(len(panel.items), len(panel.table.get_children()))
        page.clear("UniFi UDM")
        self.assertIn("does not confirm resolution", panel.detail.cget("text"))
        self.assertTrue(panel.open_button.instate(("disabled",)))
        page.observations["UniFi UDM"] = ConnectionObservation("UniFi UDM", time.time_ns(), reason="tls")
        center.refresh_attention()
        self.assertTrue(panel.open_button.instate(("disabled",)))
        self.assertFalse(panel.table.selection())
        panel.open_selected()
        self.assertEqual("Overview", center.current)
        self.root.geometry("640x600")
        self.root.update()
        self.assertLessEqual(panel.table.winfo_width(), panel.table.master.winfo_width())
        self.assertTrue(panel.table.set("evidence:missing", "condition").startswith("Gap ·"))
        panel.table.selection_set("evidence:missing")
        panel.select()
        self.assertIn("Information gap", panel.detail.cget("text"))

    def test_udm_guide_requires_review_and_explicit_site_choice(self):
        from pulpo.udm_setup import UdmSites, discovery_source, load_setup
        from pulpo.mcp_boundary import _publish_snapshot
        from tests.test_connections import SITE
        page = self.center.connections_view
        page.open_setup()
        guide = page.setup_guide
        guide.window.geometry("600x580")
        self.root.update()
        self.assertIsNone(guide.save("sites"))
        directory = Path(self.temporary.name)
        guide.fields["sites_output"].set(str(directory / "sites.json"))
        guide.fields["inventory_output"].set(str(directory / "inventory.json"))
        preview = guide.save("sites")
        self.assertEqual({}, guide.saved)
        def buttons(widget):
            for child in widget.winfo_children():
                if child.winfo_class() == "TButton": yield child
                yield from buttons(child)
        saved = directory / "setup.json"
        with patch("tkinter.filedialog.asksaveasfilename", return_value=str(saved)):
            next(button for button in buttons(preview) if button.cget("text") == "Save setup…").invoke()
        self.assertEqual("sites", load_setup(saved).mode)
        guide.copy_command("sites")
        copied = self.root.clipboard_get()
        self.assertIn("--setup-profile", copied)
        guide.fields["origin"].set("https://192.168.1.2")
        guide.copy_command("sites")
        self.assertEqual(copied, self.root.clipboard_get())
        self.assertIn("save this setup first", guide.status.cget("text"))
        guide.fields["origin"].set("https://192.168.1.1")
        report = directory / "sites.json"
        _publish_snapshot(UdmSites(time.time_ns(), discovery_source("https://192.168.1.1"), (SITE,), False), report)
        with patch("tkinter.filedialog.askopenfilename", return_value=str(report)):
            guide.import_sites()
        self.assertEqual("", guide.fields["site"].get())
        self.assertEqual((SITE,), guide.site_choices.cget("values"))
        guide.fields["site"].set(SITE)
        self.assertEqual(SITE, guide.config("collect").site_id)
        guide.fields["origin"].set("https://192.168.1.2")
        with self.assertRaises(ValueError): guide.config("collect")
        with patch("tkinter.filedialog.askopenfilename", return_value=str(report)):
            guide.import_sites()
        self.assertEqual("", guide.fields["site"].get())
        self.assertFalse(guide.site_choices.cget("values"))
        self.assertEqual("Unknown", self.center.status_rows["Governance"].state)
        guide.window.destroy()
        self.assertEqual({}, guide.fields)

    def test_connection_reports_separate_auth_freshness_failures_and_governance(self):
        from dataclasses import asdict, replace
        import json
        from pulpo.connection_observation import ConnectionObservation
        page = self.center.connections_view
        self.center.show("Connections")
        self.assertIsNotNone(page.timer)
        self.assertEqual(3, len(page.rows))
        self.assertTrue(all(row.state == "Unknown" for row in page.rows.values()))
        path = Path(self.temporary.name) / "connection.json"
        sample = ConnectionObservation("UniFi UDM", time.time_ns(), "Responded", "Accepted", "ok",
                                       source_id="a" * 32, devices_seen=2, online_seen=1, clients_seen=3)
        def write(value):
            path.write_text(json.dumps(asdict(value)))
            path.chmod(0o600)
        write(sample)
        original = path.read_bytes()
        with patch("tkinter.filedialog.askopenfilename", return_value=str(path)):
            page.select("UniFi UDM")
        self.assertEqual("Unknown", page.rows["UniFi UDM"].state)
        self.assertIn("HTTP Responded", page.rows["UniFi UDM"].summary.cget("text"))
        self.assertIn("enforcement unassessed", page.rows["UniFi UDM"].summary.cget("text"))
        self.assertEqual("Unknown", self.center.status_rows["Governance"].state)
        events = len(self.center.activity_view.model.events)
        page.refresh("UniFi UDM")
        self.assertEqual(events, len(self.center.activity_view.model.events))
        self.root.after_cancel(page.timer)
        page.timer = None
        with patch("pulpo.connections_page.load_connection_observation", side_effect=AssertionError("Timer cannot read files")):
            page.tick()
        page.copy()
        self.assertNotIn(str(path), self.root.clipboard_get())
        self.assertEqual(original, path.read_bytes())
        write(replace(sample, observed_at_ns=time.time_ns()-61_000_000_000))
        page.observations.clear()  # Select a historical export without an in-session ordering conflict.
        page.refresh("UniFi UDM")
        self.assertEqual("Attention", page.rows["UniFi UDM"].state)
        self.assertIn("Stale", page.rows["UniFi UDM"].summary.cget("text"))
        path.write_text('{"api_key":"PRIVATE"}')
        page.refresh("UniFi UDM")
        self.assertNotIn("UniFi UDM", page.observations)
        self.assertNotIn("PRIVATE", page.rows["UniFi UDM"].detail.cget("text"))
        write(ConnectionObservation("NinjaOne", time.time_ns()))
        page.refresh("UniFi UDM")
        self.assertNotIn("UniFi UDM", page.observations)
        page.clear("UniFi UDM")
        self.assertEqual("Unknown", page.rows["UniFi UDM"].state)
        page.open_activity()
        self.assertEqual("Connections", self.center.activity_view.variables["Category"].get())
        self.assertIsNone(page.timer)
        self.assertFalse(self.profile.exists())

    def test_activity_filters_pause_review_export_and_lifecycle(self):
        import json
        page = self.center.activity_view
        self.center.record_activity("fixture PRIVATE /private/path", action="benchmark", outcome="Failed", severity="Error")
        self.assertIn("(2)", self.center.navigation["Activity"].cget("text"))
        self.center.show("Activity")
        self.root.update()
        self.assertEqual("Activity", self.center.navigation["Activity"].cget("text"))
        page.only_attention.set(True)
        page.render()
        self.assertEqual(1, len(page.displayed))
        page.copy()
        self.assertNotIn("PRIVATE", self.root.clipboard_get())
        page.toggle_pause()
        frozen = page.public_rows()
        self.center.record_activity("cancelled", action="benchmark", outcome="Cancelled")
        self.root.update()
        self.assertEqual(frozen, page.public_rows())
        self.assertEqual(1, page.unread)
        destination = Path(self.temporary.name) / "safe.json"
        with patch("tkinter.filedialog.asksaveasfilename") as dialog:
            preview = page.preview_export()
            preview.destroy()
            dialog.assert_not_called()
        preview = page.preview_export()
        self.center.record_activity("arrived after preview; exclude from frozen export")
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        save = next(w for w in descendants(preview) if w.winfo_class() == "TButton" and w.cget("text") == "Save as…")
        with patch("tkinter.filedialog.asksaveasfilename", return_value=str(destination)):
            save.invoke()
        exported = json.loads(destination.read_text())
        self.assertEqual(frozen, exported["rows"])
        self.assertNotIn("PRIVATE", destination.read_text())
        page.review()
        self.assertEqual("Failed", page.displayed[0].outcome)
        page.toggle_pause()
        self.assertFalse(page.displayed)
        self.assertIn("0 unreviewed", page.attention.cget("text"))
        page.only_attention.set(False)
        page.variables["Category"].set("AI")
        page.render()
        self.assertFalse(page.displayed)
        self.assertIn("does not prove", page.empty.cget("text"))
        self.center.show("Overview")
        self.assertIsNone(page.timer)
        self.assertFalse(self.profile.exists())

    def test_activity_reference_scope_no_duplicates_no_authority_or_source_reads(self):
        from pulpo.evidence_observation import EvidenceObservation, EvidenceEvent
        page = self.center.activity_view
        snapshot = EvidenceObservation("a" * 32, time.time_ns() - 30_000_000_000, True, 2,
            events=(EvidenceEvent(time.time_ns(), "decision", "blocked_by_policy", "b" * 64),
                    EvidenceEvent(time.time_ns(), "permit_rejected", "rejected", "c" * 64)))
        self.center.evidence_view.snapshot = snapshot
        page.variables["View"].set("Evidence references")
        self.center.show("Activity")
        with patch("pulpo.evidence_page.load_observation", side_effect=AssertionError("Activity must not read files")):
            for _ in range(3): page.render()
        self.assertEqual(2, len(page.references))
        self.assertIn("maximum 24", page.coverage.cget("text"))
        self.assertIn("stale", page.coverage.cget("text"))
        self.assertEqual("disabled", str(page.review_button.cget("state")))
        page.variables["Outcome"].set("blocked_by_policy")
        page.render()
        self.assertEqual(1, len(page.references))
        page.copy()
        self.assertEqual("b" * 64, self.root.clipboard_get())
        self.assertIn("do not attest", page.output.get("1.0", "end"))
        self.assertEqual("Unknown", self.center.status_rows["Governance"].state)
        page.toggle_pause()
        self.center.evidence_view.snapshot = None
        self.center.evidence_view.error = "invalid"
        self.assertEqual(1, len(page.references))
        page.toggle_pause()
        self.assertFalse(page.references)
        self.assertIn("read failed", page.coverage.cget("text"))
        self.assertFalse(self.profile.exists())

    def test_status_expansion_and_resource_alerts_never_attest_enforcement(self):
        now = time.monotonic()
        for value, expected in ((20, "Normal"), (78, "Elevated"), (95, "Attention"), (None, "Unknown")):
            self.center._resource_update(ResourceSample(time.time(), now, "fixture", "/fixture",
                                                       Metric(value), Metric(20), Metric(20)))
            self.assertEqual(expected, self.center.status_rows["System"].state)
            for name in ("Connections", "Governance", "Evidence"):
                self.assertEqual("Unknown", self.center.status_rows[name].state)
        row = self.center.status_rows["Governance"]
        row.button.invoke()
        self.root.update()
        self.assertTrue(row.expanded)
        self.assertTrue(row.body.winfo_ismapped())
        row.button.invoke()
        self.assertFalse(row.expanded)
        self.assertFalse(self.profile.exists())

    def test_graph_history_gaps_ranges_and_pause(self):
        monitor = self.center.monitor
        monitor.history = ResourceHistory()
        now = time.monotonic()
        for at, value in ((now - 40, 20), (now - 38, None), (now - 20, 30), (now - 18, 40)):
            monitor.history.append(ResourceSample(time.time(), at, "fixture", "/fixture",
                                                  Metric(value), Metric(20), Metric(20)))
        with patch("pulpo.resource_monitor.time.monotonic", return_value=now):
            monitor.draw("cpu")
        chart = monitor.panels["cpu"]["chart"]
        # Three grid lines and only one contiguous observed segment; never bridge missing time.
        self.assertEqual(4, sum(chart.type(item) == "line" for item in chart.find_all()))
        before = list(monitor.history.samples)
        for seconds in (60, 900, 3600):
            monitor.range_buttons[seconds].invoke()
            self.assertEqual(seconds, monitor.seconds)
        self.assertEqual(before, list(monitor.history.samples))
        with patch.object(monitor.sampler, "sample", side_effect=AssertionError("Hidden page sampled")):
            self.center.show("Connections")
            self.root.update()
        self.assertFalse(monitor.active)
        self.assertIsNone(monitor.sampler.previous_cpu)
        self.assertFalse(self.profile.exists())

    def test_governance_selection_refresh_failure_cancel_and_clear(self):
        from dataclasses import asdict
        import json
        from pulpo.mcp_boundary import MCPReadSnapshot
        path = Path(self.temporary.name) / "snapshot.json"
        path.write_text(json.dumps(asdict(MCPReadSnapshot("a" * 64, True, 0, None))))
        path.chmod(0o600)
        original = path.read_bytes()
        self.center.show("Governance")
        with patch("tkinter.filedialog.askopenfilename", return_value=str(path)):
            self.center.select_governance_snapshot()
        self.assertIn("a" * 64, self.center.governance_fields["policy"].cget("text"))
        self.assertEqual("Unknown", self.center.status_rows["Governance"].state)
        self.assertEqual(original, path.read_bytes())
        with patch("tkinter.filedialog.askopenfilename", return_value=""):
            self.center.select_governance_snapshot()
        self.assertEqual(path, self.center.governance_path)
        path.write_text("{}")
        self.center.governance_refresh.invoke()
        self.assertNotIn("a" * 64, self.center.governance_fields["policy"].cget("text"))
        self.assertEqual("Attention", self.center.status_rows["Governance"].state)
        self.center.clear_governance()
        self.assertIsNone(self.center.governance_path)
        self.assertEqual("disabled", str(self.center.governance_refresh.cget("state")))
        self.assertEqual("Unknown", self.center.status_rows["Governance"].state)
        self.assertEqual("{}", path.read_text())
        self.assertFalse(self.profile.exists())

    def test_evidence_source_rates_filters_alerts_pause_and_failure_clears_values(self):
        from dataclasses import asdict, replace
        import json
        from pulpo.evidence_observation import EvidenceObservation, EvidenceEvent
        page = self.center.evidence_view
        self.center.show("Evidence")
        path = Path(self.temporary.name) / "observation.json"
        now = time.time_ns()
        snapshot = EvidenceObservation("a" * 32, now - 4_000_000_000, False, 2, health="ok",
            reads=10, writes=3, commits=1, volume_total=1000, volume_free=30, permit_rejected=1,
            events=(EvidenceEvent(now, "decision", "blocked_by_policy", "b" * 64),
                    EvidenceEvent(now, "permit_rejected", "rejected", "c" * 64)))
        def write(value):
            path.write_text(json.dumps(asdict(value)))
            path.chmod(0o600)
        write(snapshot)
        with patch("tkinter.filedialog.askopenfilename", return_value=str(path)):
            page.select()
        self.assertEqual("Normal", page.rows["health"].state)
        self.assertEqual("Attention", page.rows["integrity"].state)
        self.assertEqual("Attention", page.rows["storage"].state)
        self.assertIn("Frozen owner observation loaded", self.center.status_rows["Evidence"].detail.cget("text"))
        self.assertIn("AI usage incomplete", page.warnings.cget("text"))
        self.assertIsNone(page.history.points[-1][1]["reads"])
        snapshot = replace(snapshot, observed_at_ns=now - 2_000_000_000, reads=16, commits=3)
        write(snapshot)
        original = path.read_bytes()
        page.refresh_button.invoke()
        self.assertEqual(3, page.history.points[-1][1]["reads"])
        page.filter.set("Permit events")
        page.render_logs()
        self.assertIn("c" * 64, page.logs.get("1.0", "end"))
        self.assertNotIn("b" * 64, page.logs.get("1.0", "end"))
        self.assertEqual("disabled", str(page.logs.cget("state")))
        page.review_button.invoke()
        self.assertTrue(page.reviewing)
        self.assertIsNone(page.timer)
        self.assertIn("Paused for review", page.source.cget("text"))
        self.assertEqual("Unknown", page.rows["health"].state)
        with patch("pulpo.evidence_page.load_observation", side_effect=AssertionError("Paused page read")):
            page.tick()
        page.review_button.invoke()
        self.assertFalse(page.reviewing)
        self.center.show("Overview")
        self.assertIsNone(page.timer)
        with patch("pulpo.evidence_page.load_observation", side_effect=AssertionError("Hidden page read")):
            page.tick()
        self.assertEqual(original, path.read_bytes())
        path.write_text('{"permit":"PRIVATE"}')
        page.refresh()
        self.assertIsNone(page.snapshot)
        self.assertFalse(page.history.points)
        self.assertNotIn("PRIVATE", page.logs.get("1.0", "end"))
        self.assertNotIn("3.0/s", page.values["reads"].cget("text"))
        page.clear()
        self.assertIsNone(page.path)
        self.assertIsNone(page.timer)

    def test_existing_launch_comparison_and_explicit_save(self):
        import weakref
        self.root.withdraw()
        windows = []
        variables = []
        original_variable = tk.StringVar
        def owned_variable(*args, **kwargs):
            variable = original_variable(*args, **kwargs)
            self.assertIs(kwargs["master"], variable._root)
            variables.append(weakref.ref(variable))
            return variable
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
            # More than one read-only text pane now exists; find the Activity
            # comparison output by its actual result, not widget creation order.
            output = next(widget for widget in descendants(root) if isinstance(widget, tk.Text)
                          and "canonical equality PASS" in widget.get("1.0", "end"))
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
            # A MagicMock call history would retain Tk masters in mock cycles,
            # allowing a later benchmark worker to collect Tcl on the wrong thread.
            with patch.object(tk.Tk, "mainloop", inspect), patch.object(tk, "StringVar", owned_variable):
                tuning_app.launch(self.profile)
        finally:
            for root in windows:
                root.destroy()
                self.assertFalse(root.tk.call("after", "info"), "Window left a scheduled callback after destruction")
            self.assertTrue(variables)
            self.assertTrue(all(reference() is None for reference in variables), "Closed window retained a Tk variable")

    def test_system_diagnostics_benchmark_failure_cancel_and_explicit_save(self):
        from pulpo import system_benchmark as benchmark
        from tests.test_system_benchmark import SystemBenchmarkTests
        page = self.center.system_view
        self.center.show("System")
        self.assertTrue(page.monitor.active)
        self.assertIn("Unknown", page.summary)
        self.assertNotIn(str(self.profile), page.summary)
        page.tabs["Tuning & benchmarks"].invoke()
        self.assertFalse(page.monitor.active)
        page.candidate.set("1")
        def finish():
            deadline = time.monotonic() + 15
            while page.busy:
                self.root.update()
                if time.monotonic() > deadline: self.fail("System operation did not finish")
                time.sleep(.01)
        helper = SystemBenchmarkTests()
        with patch.object(benchmark, "measure_case", side_effect=lambda workers, *_: helper.row(workers)):
            page.compare_button.invoke()
            finish()
        self.assertIsNotNone(page.report)
        if page.configuration is not None:
            self.assertIn("Applicable", page.configuration.validity.cget("text"))
            self.assertIsNone(page.configuration.last_change)
        self.assertFalse(self.profile.exists())
        page.save_button.invoke()
        finish()
        self.assertEqual(1, tuning.load_settings(self.profile).workers)
        if page.configuration is not None:
            change = page.configuration.last_change
            self.assertEqual(("save", 0, 1), (change.operation, change.before_workers, change.after_workers))
            self.assertIn("Historical profile change time and reason: Unknown", page.configuration.history.cget("text"))
        page.undo_button.invoke()
        finish()
        self.assertEqual(0, tuning.load_settings(self.profile).workers)
        if page.configuration is not None:
            change = page.configuration.last_change
            self.assertEqual(("undo", 1, 0), (change.operation, change.before_workers, change.after_workers))
        page.candidate.set("1")
        with patch.object(benchmark, "measure_case", side_effect=ValueError("Correctness failed")):
            page.compare_button.invoke()
            finish()
        self.assertIsNone(page.report)
        self.assertEqual("disabled", str(page.save_button.cget("state")))
        before = self.profile.read_bytes()
        with patch.object(benchmark, "measure_case", side_effect=benchmark.BenchmarkCancelled("Cancelled")):
            page.compare_button.invoke()
            finish()
        self.assertIsNone(page.report)
        self.assertEqual(before, self.profile.read_bytes())

    def test_destroy_releases_tk_variables_and_callback_cycles_on_owner_thread(self):
        import gc
        import threading
        import weakref
        root = tk.Tk()
        destroyed = False
        try:
            center = ControlCenter(root, self.profile)
            root.update()
            page = center.evidence_view
            self.assertIs(root, page.filter._root)
            variable = weakref.ref(page.filter)
            logo = weakref.ref(center.sidebar_logo_images[128])
            page.set_active(True)
            root.destroy()
            destroyed = True
            self.assertIsNone(page.filter)
            self.assertIsNone(page.center)
            self.assertIsNone(variable())
            self.assertFalse(center.sidebar_logo_images)
            self.assertIsNone(logo())
            self.assertIsNone(center.monitor.on_update)
            self.assertTrue(center.needs_attention.closed)
            self.assertIsNone(center.needs_attention.center)
            self.assertTrue(center.decision_explorer.closed)
            self.assertIsNone(center.decision_explorer.center)
            self.assertIsNone(center.decision_explorer.snapshot)
            self.assertTrue(center.system_view.source_health.closed)
            self.assertIsNone(center.system_view.source_health.center)
            self.assertIsNone(center.system_view.source_health.timer)
            if center.system_view.readiness is not None:
                self.assertTrue(center.system_view.readiness.closed)
                self.assertIsNone(center.system_view.readiness.center)
                self.assertIsNone(center.system_view.readiness.timer)
            if center.system_view.configuration is not None:
                self.assertTrue(center.system_view.configuration.closed)
                self.assertIsNone(center.system_view.configuration.system)
                self.assertIsNone(center.system_view.configuration.timer)
                self.assertIsNone(center.system_view.configuration.last_change)
            if center.system_view.troubleshooting is not None:
                self.assertTrue(center.system_view.troubleshooting.closed)
                self.assertIsNone(center.system_view.troubleshooting.system)
                self.assertIsNone(center.system_view.troubleshooting.timer)
                self.assertIsNone(center.system_view.troubleshooting.preview)
            self.assertIsNone(page.timer)
            # Later worker collection must have no Tk variable left to finalize.
            worker = threading.Thread(target=gc.collect)
            worker.start()
            worker.join(timeout=5)
            self.assertFalse(worker.is_alive())
        finally:
            if not destroyed:
                root.destroy()


if __name__ == "__main__":
    unittest.main()
