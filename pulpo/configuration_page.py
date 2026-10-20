"""WSL-only comparison display sharing the existing candidate and checked actions."""
import time

from .configuration_comparison import (LocalConfigurationChange, applicability,
    candidate_workers, collector_mode, inspect_configuration)


def stamp(value):
    return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(value))


def count(value):
    return "Unknown" if value is None else str(value)


class ConfigurationPage:
    def __init__(self, system, page):
        from tkinter import ttk
        self.system, self.center, self.root = system, system.center, system.root
        self.closed = self.active = False
        self.timer = None
        self.current = self.last_change = None
        self.before_workers = None
        self.proposal_at = None
        self.candidate_text = system.candidate.get()
        self.operation_status = "No System configuration operation observed in this session."
        center = self.center
        center.text(page, "Configuration Comparison · WSL", "Heading.TLabel")
        center.text(page, "Compare the effective local performance hint with a proposal. Only evidence worker count is tunable here; "
                    "governance permissions and OS settings stay outside tuning controls.", "Muted.TLabel")
        self.context = center.text(page, "", "Muted.TLabel")
        options = ttk.Frame(page)
        options.pack(fill="x", pady=(0, 8))
        ttk.Label(options, text="Proposed workers").grid(row=0, column=0, sticky="w", padx=(0, 8))
        from . import evidence_tuning as tuning
        self.spin = ttk.Spinbox(options, from_=0, to=tuning.thread_limit(), width=6,
            textvariable=system.candidate, command=system.candidate_changed)
        self.spin.grid(row=0, column=1, sticky="ew")
        self.spin.bind("<KeyRelease>", lambda event: system.candidate_changed())
        self.spin.bind("<FocusOut>", lambda event: system.candidate_changed())
        options.columnconfigure(1, weight=1)
        self.table = ttk.Treeview(page, columns=("setting", "current", "proposed"), show="headings", height=2)
        for key, title, width in (("setting", "Setting", 145), ("current", "Current", 95), ("proposed", "Proposed", 95)):
            self.table.heading(key, text=title)
            self.table.column(key, width=width, minwidth=75)
        self.table.pack(fill="x", pady=(0, 10))
        for key in ("workers", "mode"):
            self.table.insert("", "end", iid=key)
        self.proposal = center.text(page, "", "Muted.TLabel")
        self.validity = center.text(page, "", "Heading.TLabel")
        self.measurements = center.text(page, "", "Muted.TLabel")
        self.history = center.text(page, "", "Muted.TLabel")
        self.operation = center.text(page, "", "Muted.TLabel")
        controls = ttk.Frame(page)
        controls.pack(fill="x", pady=(0, 8))
        ttk.Button(controls, text="Re-check current settings", command=self.refresh).grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=3)
        ttk.Button(controls, text="Open benchmark controls", command=lambda: system.select_mode("Tuning & benchmarks")).grid(
            row=0, column=1, sticky="ew", pady=3)
        for col in (0, 1): controls.columnconfigure(col, weight=1)
        center.text(page, "Saving and restoring stay in the existing benchmark controls. Save rechecks the profile, report age, "
                    "code and machine context, then runs fresh correctness checks. No automatic save or restore.\n"
                    "Idle display updates only expire evidence; changes outside this window require Re-check current settings. "
                    "Benchmark results cover disposable capture fixtures, not enforcement or production performance.", "Muted.TLabel")
        self.root.bind("<Destroy>", self.destroy, add="+")

    def refresh(self):
        if not self.closed:
            self.current = inspect_configuration(self.system.profile)
            self.render()

    def proposal_changed(self):
        self.render()

    def begin(self, operation):
        if operation in {"save", "undo"}:
            self.refresh()
            self.before_workers = self.current.workers
        self.operation_status = {"compare": "Benchmark running · no setting saved.",
            "save": "Save requested · awaiting checked result.", "undo": "Restore requested · awaiting checked result."}[operation]
        self.render()

    def completed(self, operation):
        self.refresh()
        if operation in {"save", "undo"}:
            self.last_change = LocalConfigurationChange(operation, self.before_workers, self.current.workers, time.time())
        self.operation_status = "Recorded · " + {"compare": "Benchmark completed; settings unchanged.",
            "save": "Explicit Save tested candidate completed.", "undo": "Explicit Restore previous setting completed."}[operation]
        self.render()

    def failed(self, kind):
        self.operation_status = {"cancelled": "Cancelled · no successful configuration change recorded.",
            "error": "Operation failed · inspect benchmark controls; no successful change recorded.",
            "blocked": "Worker cleanup unverified · operator investigation required."}[kind]
        self.render()

    def render(self):
        if self.closed:
            return
        self.proposal_changed_without_render()
        current = self.current
        proposed = candidate_workers(self.system.candidate.get())
        workers = current.workers if current else None
        self.context.configure(text=(f"Recorded local check: {stamp(current.checked_at)}\n{current.status}" if current else
            "Unknown · Current settings have not been checked in this view."))
        self.table.item("workers", values=("Evidence workers", count(workers), count(proposed)))
        self.table.item("mode", values=("Collector mode", collector_mode(workers), collector_mode(proposed)))
        edited = stamp(self.proposal_at) if self.proposal_at is not None else "Unknown · initial suggestion, not a recorded edit"
        self.proposal.configure(text=f"Proposed change: {count(workers)} → {count(proposed)} workers. "
            f"{'Both values use serial collection.' if workers is not None and proposed is not None and workers <= 1 and proposed <= 1 else ''}\n"
            f"Proposal edit observed locally: {edited}.")
        state = applicability(current, proposed, self.system.report)
        self.validity.configure(text=state)
        if state == "Applicable to last checked context":
            report = self.system.report
            first, second = report["baseline"], report["candidate"]
            self.measurements.configure(text=f"Recorded · {report['classification']} · correctness PASS · completed {stamp(report['completed_at'])}\n"
                f"Exact benchmark pair: {first['workers']} → {second['workers']} workers. Median: {first['median_ms']:.2f} → {second['median_ms']:.2f} ms.\n"
                "Five alternating runs per setting; 64 files / 4 MiB capture-only fixtures. Applicable means matching the last explicit check; saving validates again.")
        else:
            self.measurements.configure(text="No applicable measurements displayed for this proposal. Run/re-run through benchmark controls; "
                "old measurements are never relabeled as results for new settings.")
        previous = count(current.previous_workers) if current else "Unknown"
        history = f"Recorded rollback worker count: {previous}. Historical profile change time and reason: Unknown (not recorded in the profile)."
        if self.last_change:
            change = self.last_change
            action = "Save tested candidate" if change.operation == "save" else "Restore previous setting"
            history += (f"\nLast observed System configuration action: {action}; observed workers {count(change.before_workers)} → {count(change.after_workers)}. "
                f"Completion received by UI: {stamp(change.received_at)}. Reason known: explicit {action} action; operator motivation is not recorded.")
        self.history.configure(text=history)
        self.operation.configure(text=self.operation_status)
        self.spin.configure(state="disabled" if self.system.busy or self.system.cleanup_blocked else "normal")

    def proposal_changed_without_render(self):
        text = self.system.candidate.get()
        if text != self.candidate_text:
            self.candidate_text, self.proposal_at = text, time.time()

    def set_active(self, active):
        if self.timer is not None:
            self.root.after_cancel(self.timer)
            self.timer = None
        self.active = active and not self.closed
        if self.active:
            self.refresh()
            self.timer = self.root.after(1000, self.tick)

    def tick(self):
        self.timer = None
        if self.active and not self.closed:
            if self.root.winfo_viewable() and self.root.state() != "iconic":
                self.render()  # Age/applicability only; no profile or code reads.
            self.timer = self.root.after(1000, self.tick)

    def destroy(self, event):
        if event.widget is self.root:
            self.closed = True
            self.set_active(False)
            self.center = self.system = self.current = self.last_change = None
