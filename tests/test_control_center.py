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
            self.center.append(f"Recorded: local message {index}")
        self.assertLessEqual(int(self.center.output.index("end-1c").split(".")[0]), 501)
        self.assertEqual("disabled", self.center.output.cget("state"))
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
        self.assertFalse(self.profile.exists())
        page.save_button.invoke()
        finish()
        self.assertEqual(1, tuning.load_settings(self.profile).workers)
        page.undo_button.invoke()
        finish()
        self.assertEqual(0, tuning.load_settings(self.profile).workers)
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
            page.set_active(True)
            root.destroy()
            destroyed = True
            self.assertIsNone(page.filter)
            self.assertIsNone(page.center)
            self.assertIsNone(variable())
            self.assertIsNone(center.monitor.on_update)
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
