"""Local installation diagnostics and explicit disposable system comparisons."""
from importlib import metadata
import platform
import queue
import sys
import shutil
import tempfile
import threading
import time

from . import evidence_tuning as tuning
from .system_benchmark import run_task


class SystemPage:
    def __init__(self, center):
        import tkinter as tk
        from tkinter import ttk
        from .control_center import StatusRow
        from .resource_monitor import ResourceMonitor
        self.center, self.root, self.profile = center, center.root, center.profile
        self.busy, self.closed, self.timer = False, False, None
        self.cleanup_blocked = False
        self.operation, self.report = None, None
        self.configuration = None
        self.troubleshooting = None
        self.session = None
        self.messages, self.stop = queue.Queue(), threading.Event()
        self.active, self.mode = False, "Diagnostics"
        page = center.pages["System"]
        from .setup_readiness import is_wsl
        modes = ("Diagnostics", "Tuning & benchmarks", "Source health")
        if is_wsl():
            modes += ("Setup readiness", "Configuration", "Troubleshooting", "Session setup")
        from .system_navigation import SystemNavigation
        self.navigation = SystemNavigation(page, self.select_mode, modes, grouped=is_wsl())
        self.tabs = self.navigation.tabs
        self.views = {name: ttk.Frame(page) for name in self.tabs}
        from .source_health_page import SourceHealthPage
        self.source_health = SourceHealthPage(center, self.views["Source health"])
        self.readiness = None
        if "Setup readiness" in self.views:
            from .readiness_page import ReadinessPage
            self.readiness = ReadinessPage(center, self.views["Setup readiness"])
        diagnostics = self.views["Diagnostics"]
        self.monitor = ResourceMonitor(diagnostics, self.root, lambda sample: None)
        self.monitor.set_active(False)
        self.rows = {}
        for name in ("Installation", "Runtime", "Workspace", "Configuration", "Time", "Recovery"):
            row = StatusRow(diagnostics, name, "", None)
            self.rows[name] = row
        center.text(diagnostics, "Evidence performance profile", "Heading.TLabel")
        center.text(diagnostics, str(self.profile))
        center.profile_label = center.text(diagnostics, "")
        ttk.Button(diagnostics, text="Refresh local profile status", command=center.refresh_profile).pack(anchor="w", pady=(0, 8))
        ttk.Button(diagnostics, text="Refresh diagnostics", command=self.refresh_diagnostics).pack(anchor="w", pady=(0, 8))
        actions = ttk.Frame(diagnostics)
        actions.pack(fill="x", pady=(0, 10))
        ttk.Button(actions, text="Preview summary", command=self.preview_summary).grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=3)
        ttk.Button(actions, text="Copy summary", command=self.copy_summary).grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Button(actions, text="Export summary…", command=self.export_summary).grid(row=1, column=0, columnspan=2, sticky="ew", pady=3)
        for col in (0, 1): actions.columnconfigure(col, weight=1)
        self.diagnostic_status = center.text(diagnostics, "")
        center.section(diagnostics, "Troubleshooting",
            "Profile invalid or stale: complete serial fallback remains active. Compare supported settings before saving a new hint.\n\n"
            "Resource pressure: inspect the labeled volume and available memory before running benchmarks. "
            "Graphs show this host/WSL environment, not fleet health.\n\n"
            "Collector failure: retain the bounded result and inspect Activity. Do not infer enforcement from a passing local test.\n\n"
            "Clock synchronization, service uptime, updates and verified recovery remain Unknown without real observation sources. "
            "No automatic repair, service restart, update, credential scan or network probe is run.")
        benchmark = self.views["Tuning & benchmarks"]
        center.text(benchmark, "Test supported settings before saving", "Heading.TLabel")
        self.baseline = center.text(benchmark, "")
        center.text(benchmark, "Capture-only workload: 64 files / 4 MiB in disposable temporary storage. "
                    "Five alternating baseline/candidate runs each, isolated child processes, at most one child at a time. "
                    "45-second comparison deadline plus worker shutdown/cleanup. No hard RAM cap is promised.", "Muted.TLabel")
        options = ttk.Frame(benchmark)
        options.pack(fill="x", pady=8)
        ttk.Label(options, text="Candidate workers").pack(side="left", padx=(0, 8))
        self.candidate = tk.StringVar(master=self.root, value=str(min(2, tuning.thread_limit())))
        self.spin = ttk.Spinbox(options, from_=0, to=tuning.thread_limit(), width=5, textvariable=self.candidate,
                                command=self.candidate_changed)
        self.spin.pack(side="left")
        self.spin.bind("<KeyRelease>", lambda event: self.candidate_changed())
        self.spin.bind("<FocusOut>", lambda event: self.candidate_changed())
        center.text(benchmark, "0 or 1 uses serial collection. Only evidence worker count can be saved; "
                    "governance, permissions and OS settings stay fixed.", "Muted.TLabel")
        buttons = ttk.Frame(benchmark)
        buttons.pack(fill="x", pady=(0, 8))
        self.compare_button = ttk.Button(buttons, text="Run comparison", command=self.compare)
        self.compare_button.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=3)
        self.cancel_button = ttk.Button(buttons, text="Cancel benchmark", command=self.cancel, state="disabled")
        self.cancel_button.grid(row=0, column=1, sticky="ew", pady=3)
        self.save_button = ttk.Button(buttons, text="Save tested candidate", command=self.save, state="disabled")
        self.save_button.grid(row=1, column=0, sticky="ew", padx=(0, 6), pady=3)
        self.undo_button = ttk.Button(buttons, text="Restore previous setting", command=lambda: self.start("undo", (self.profile,)))
        self.undo_button.grid(row=1, column=1, sticky="ew", pady=3)
        for col in (0, 1): buttons.columnconfigure(col, weight=1)
        self.status = center.text(benchmark, "Ready · No benchmark run; settings unchanged.")
        self.result_title = center.text(benchmark, "No comparison results", "Heading.TLabel")
        self.table = ttk.Treeview(benchmark, columns=("metric", "baseline", "candidate"), show="headings", height=8)
        for key, title, width in (("metric", "Metric", 160), ("baseline", "Baseline", 90), ("candidate", "Candidate", 90)):
            self.table.heading(key, text=title)
            self.table.column(key, width=width, minwidth=70, stretch=True)
        self.table.pack(fill="x", pady=(0, 10))
        center.text(benchmark, "Faster/Slower requires >5% median difference and non-overlapping observed ranges; "
                    "otherwise Inconclusive. This is a conservative comparison rule, not statistical confidence. "
                    "Process CPU can exceed 100% when using multiple cores. Peak RSS includes child startup and correctness checks. "
                    "Fixture payload excludes filesystem metadata and allocation overhead.", "Muted.TLabel")
        exports = ttk.Frame(benchmark)
        exports.pack(fill="x", pady=6)
        self.export_button = ttk.Button(exports, text="Export comparison…", command=self.export_report, state="disabled")
        self.export_button.pack(side="left")
        center.text(benchmark, "Comparison never saves settings automatically. Saving rechecks correctness through the existing settings path. "
                    "Results expire after 15 minutes or a machine, profile, source or candidate change. "
                    "A passing benchmark does not attest governance or production readiness.", "Muted.TLabel")
        if "Configuration" in self.views:
            from .configuration_page import ConfigurationPage
            self.configuration = ConfigurationPage(self, self.views["Configuration"])
        if "Troubleshooting" in self.views:
            from .troubleshooting_page import TroubleshootingPage
            self.troubleshooting = TroubleshootingPage(self, self.views["Troubleshooting"])
        if "Session setup" in self.views:
            from .session_page import SessionPage
            self.session = SessionPage(self, self.views["Session setup"])
        self.root.bind("<Destroy>", self.destroy, add="+")
        self.refresh_diagnostics()
        self.select_mode("Diagnostics")

    def select_mode(self, mode):
        if mode not in self.views: raise ValueError("Unknown System view")
        self.navigation.show_mode(mode)
        for name, view in self.views.items():
            view.pack_forget()
        self.views[mode].pack(fill="x")
        self.mode = mode
        self.monitor.set_active(self.active and mode == "Diagnostics")
        self.source_health.set_active(self.active and mode == "Source health")
        if self.readiness is not None:
            self.readiness.set_active(self.active and mode == "Setup readiness")
        if self.configuration is not None:
            self.configuration.set_active(self.active and mode == "Configuration")
        if self.troubleshooting is not None:
            self.troubleshooting.set_active(self.active and mode == "Troubleshooting")
        if self.session is not None:
            self.session.set_active(self.active and mode == "Session setup")
        if self.readiness is not None:
            self.readiness.guide.update_banner()
        self.center.canvas.yview_moveto(0)

    def set_active(self, active):
        self.active = active
        self.monitor.set_active(active and self.mode == "Diagnostics")
        self.source_health.set_active(active and self.mode == "Source health")
        if self.readiness is not None:
            self.readiness.set_active(active and self.mode == "Setup readiness")
        if self.configuration is not None:
            self.configuration.set_active(active and self.mode == "Configuration")
        if self.troubleshooting is not None:
            self.troubleshooting.set_active(active and self.mode == "Troubleshooting")
        if self.session is not None:
            self.session.set_active(active and self.mode == "Session setup")

    def refresh_diagnostics(self):
        try:
            version = metadata.version("pulpo")
        except metadata.PackageNotFoundError:
            version = "Unknown (uninstalled source checkout)"
        environment = "WSL Linux VM" if "microsoft" in platform.release().lower() else platform.system()
        install = "Frozen application" if getattr(sys, "frozen", False) else "Python source/runtime"
        self.summary = (f"Recorded local environment: {environment}\nPulpo package version: {version}\n"
                        f"Installation: {install}\nArchitecture: {platform.machine()}\nPython: {platform.python_version()}\n"
                        f"Tcl: {self.root.tk.call('info', 'patchlevel')} · Tk: {self.root.tk.call('package', 'provide', 'Tk')}\n"
                        f"Logical CPUs: {tuning.machine()['logical_cpus']}\n"
                        "Build provenance, deployment enforcement, external service health, clock synchronization, "
                        "update availability and verified recovery: Unknown.")
        self.rows["Installation"].update("Unknown", f"Recorded · {environment} · {install}", self.summary)
        self.rows["Runtime"].update("Unknown", "Recorded · This window is running; kernel/service health Unknown",
                                    "An installed/importable module does not prove a service is running. No canonical process, signer or service client is retained here.")
        self.center.refresh_profile()
        try:
            free = shutil.disk_usage(tempfile.gettempdir()).free
            self.rows["Workspace"].update("Attention" if free < 16 * 1024**2 else "Normal",
                f"Recorded · Temporary volume: {free / 1024**3:.2f} GiB free",
                "Comparison uses 4 MiB fixture payload at a time, plus filesystem overhead. "
                "A 16 MiB free-space floor is required before starting; free space can change during a test. No RAM cap is enforced.")
        except OSError:
            self.rows["Workspace"].update("Unknown", "Unknown · Temporary-volume capacity unavailable", "Inspect local temporary-storage access before benchmarking.")
        self.rows["Configuration"].update("Unknown", f"Recorded · Effective evidence workers: {tuning.load_settings(self.profile).workers}",
                                         self.center.profile_label.cget("text") + "\nThis is a local performance hint, not an authority grant.")
        self.rows["Time"].update("Unknown", "Recorded · " + time.strftime("%Y-%m-%d %H:%M:%S %Z"),
                                "Local wall clock only. Synchronization and independent authority time are Unknown; the UI cannot adjust either.")
        self.rows["Recovery"].update("Unknown", "Unknown · Backup, restore test and update availability not observed",
                                    "A backup file existing is not evidence that recovery works. No backup discovery, update check or repair runs automatically.")
        self.baseline.configure(text=f"Current baseline: {tuning.load_settings(self.profile).workers} workers · {environment}\n"
                                     "Run a new comparison after changing settings or the environment.")
        self.diagnostic_status.configure(text="Recorded · Diagnostics refreshed locally; no settings or canonical state changed.")
        self.summary += "\nLocal performance profile: " + self.center.profile_label.cget("text")
        if self.configuration is not None:
            self.configuration.refresh()

    def copy_summary(self):
        self.refresh_diagnostics()
        self.root.clipboard_clear()
        self.root.clipboard_append(self.summary)
        self.diagnostic_status.configure(text="Redacted summary copied · excludes host name, file paths, credentials and raw logs.")

    def preview_summary(self):
        from tkinter import messagebox
        self.refresh_diagnostics()
        messagebox.showinfo("Redacted system summary", self.summary, parent=self.root)

    def export_summary(self):
        self.refresh_diagnostics()
        self.write_file(self.summary, "pulpo-system-summary.txt", ".txt")

    def write_file(self, text, name, extension):
        from tkinter import filedialog
        from pathlib import Path
        selected = filedialog.asksaveasfilename(parent=self.root, initialfile=name, defaultextension=extension)
        if selected:
            try:
                Path(selected).write_text(text, encoding="utf-8")
                return True
            except OSError:
                self.diagnostic_status.configure(text="Export failed. Check destination access; no diagnostic contents were logged.")
                return False

    def export_report(self):
        import json
        if self.report is not None:
            # Profile fingerprint is useful for validation, not needed in support export.
            public = {key: value for key, value in self.report.items() if key != "profile_token"}
            self.write_file(json.dumps(public, indent=2), "pulpo-system-comparison.json", ".json")

    def candidate_changed(self):
        if self.report and self.candidate.get() != str(self.report["candidate"]["workers"]):
            self.report = None
            self.save_button.configure(state="disabled")
            self.export_button.configure(state="disabled")
            self.result_title.configure(text="Candidate changed · compare again")
        if self.configuration is not None:
            self.configuration.proposal_changed()

    def compare(self):
        try:
            candidate = tuning.EvidenceSettings(int(self.candidate.get())).validate().workers
        except ValueError:
            self.status.configure(text=f"Choose an integer from 0 to {tuning.thread_limit()}.")
            return
        self.start("compare", (self.profile, candidate))

    def save(self):
        self.candidate_changed()
        if self.report is not None:
            self.start("save", (self.report, self.profile))

    def start(self, operation, arguments):
        if self.cleanup_blocked:
            self.status.configure(text="Worker cleanup is unverified. Operator investigation is required before another performance operation.")
            return
        if self.busy or getattr(self.center, "performance_busy", lambda: False)():
            self.status.configure(text="Another performance operation is running. Wait for its cleanup before starting a new one.")
            return
        self.busy, self.operation = True, operation
        self.center.record_activity("System operation requested; awaiting result.", category="System",
            action={"compare": "benchmark", "save": "profile_save", "undo": "profile_restore"}[operation], outcome="Started")
        self.stop.clear()
        self.report = None
        if self.configuration is not None:
            self.configuration.begin(operation)
        if operation == "compare":
            self.table.delete(*self.table.get_children())
            self.result_title.configure(text="Comparison in progress")
        for button in (self.spin, self.compare_button, self.save_button, self.undo_button, self.export_button):
            button.configure(state="disabled")
        self.cancel_button.configure(state="normal" if operation == "compare" else "disabled")
        self.status.configure(text="Working · isolated disposable fixtures" if operation == "compare" else "Rechecking settings correctness…")
        self.worker = threading.Thread(target=run_task, args=(operation, arguments, self.messages, self.stop))
        self.worker.start()
        self.timer = self.root.after(50, self.poll)

    def cancel(self):
        if self.busy and self.operation == "compare":
            self.stop.set()
            self.status.configure(text="Cancellation requested · waiting for worker shutdown and fixture cleanup…")
            self.cancel_button.configure(state="disabled")

    def poll(self):
        self.timer = None
        while not self.messages.empty():
            kind, result = self.messages.get_nowait()
            if kind == "progress" and not self.stop.is_set(): self.status.configure(text=result)
            elif kind == "result":
                operation, value = result
                self.center.record_activity("System operation completed through the existing checked path. " +
                    (f"Capture-only comparison: {value['classification']} · correctness PASS; settings unchanged." if operation == "compare" else "Effective on the next configured collection."),
                    category="System", action={"compare": "benchmark", "save": "profile_save", "undo": "profile_restore"}[operation],
                    outcome={"compare": "Completed", "save": "Saved", "undo": "Restored"}[operation])
                if operation == "compare":
                    self.report = value
                    self.render_report()
                else:
                    self.status.configure(text="Setting saved after fresh correctness checks. Effective on the next configured collection.")
                    self.refresh_diagnostics()
                if self.configuration is not None:
                    self.configuration.completed(operation)
            elif kind in ("cancelled", "error", "blocked"):
                self.center.record_activity(result, category="System",
                    action={"compare": "benchmark", "save": "profile_save", "undo": "profile_restore"}[self.operation],
                    outcome="Cancelled" if kind == "cancelled" else "Failed", severity="Info" if kind == "cancelled" else "Error")
                self.cleanup_blocked = kind == "blocked"
                self.result_title.configure(text="Cancelled" if kind == "cancelled" else "Comparison/operation failed")
                self.status.configure(text=result)
                self.report = None
                self.table.delete(*self.table.get_children())
                if self.configuration is not None:
                    self.configuration.failed(kind)
            elif kind == "done":
                self.busy = False
                for button in (self.spin, self.compare_button, self.undo_button):
                    button.configure(state="disabled" if self.cleanup_blocked else "normal")
                self.cancel_button.configure(state="disabled")
                self.save_button.configure(state="normal" if self.report else "disabled")
                self.export_button.configure(state="normal" if self.report else "disabled")
                if self.configuration is not None:
                    self.configuration.render()
        if self.busy and not self.closed:
            self.timer = self.root.after(50, self.poll)

    def render_report(self):
        self.result_title.configure(text=f"{self.report['classification']} · correctness PASS")
        self.status.configure(text="Comparison complete · recorded for this workload only; no setting saved.")
        self.table.delete(*self.table.get_children())
        a, b = self.report["baseline"], self.report["candidate"]
        for label, key, fmt in (("Workers", "workers", "{:d}"), ("Median ms", "median_ms", "{:.2f}"),
            ("Range ms", "range", None),
            ("Sample spread %", "variation_percent", "{:.1f}"), ("Files / second", "files_per_second", "{:.1f}"),
            ("Process CPU core %", "cpu_core_percent", "{:.1f}"), ("Peak child RSS MiB", "peak_process_rss_bytes", None),
            ("Fixture payload MiB", "fixture_payload_bytes", None)):
            def value(row):
                if key == "range":
                    return f"{row['min_ms']:.1f}–{row['max_ms']:.1f}"
                v = row[key]
                return "Unknown" if v is None else fmt.format(v) if fmt else f"{v / 1024**2:.2f}"
            self.table.insert("", "end", values=(label, value(a), value(b)))

    def destroy(self, event):
        if event.widget is self.root:
            self.closed = True
            self.stop.set()
            if self.timer is not None:
                self.root.after_cancel(self.timer)
                self.timer = None
            self.candidate = None
            self.center = None
