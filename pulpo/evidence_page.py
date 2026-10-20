"""Native, read-only consumer of frozen owner-side evidence observations."""
from pathlib import Path
import time

from .evidence_observation import ActivityHistory, freshness, load_observation
from .control_center_theme import PALETTE, surface


SERIES = {"reads": ("Reads", "#B79ADF"), "writes": ("Writes", "#78C8DD"), "commits": ("Commits", "#F2BD62")}


def count(value):
    return "Unknown" if value is None else f"{value:,}"


def size(value):
    return "Unknown" if value is None else f"{value / 1024**2:,.2f} MiB"


class EvidencePage:
    def __init__(self, center):
        import tkinter as tk
        from tkinter import ttk
        from .control_center import StatusRow
        self.center, self.root = center, center.root
        self.path, self.snapshot, self.error = None, None, None
        self.awaiting_reread = False
        self.history = ActivityHistory()
        self.timer, self.active, self.closed = None, False, False
        self.age_timer = None
        self.reviewing = False
        self.clarity = center.wsl_clarity
        self.test_label = tk.BooleanVar(master=self.root, value=False) if self.clarity else None
        self.source_details_visible = False
        self.warnings_visible = False
        self.seconds = 60
        page = center.pages["Evidence"]
        center.text(page, "Database activity", "Heading.TLabel")
        shadow, border = surface(page, dark=True)
        shadow.pack(fill="x", pady=(0, 10))
        self.graph = tk.Frame(border, background=PALETTE["chart"], padx=12, pady=12)
        self.graph.pack(fill="x")
        self.values = {}
        legend = tk.Frame(self.graph, background=PALETTE["chart"])
        legend.pack(fill="x")
        for index, (key, (title, color)) in enumerate(SERIES.items()):
            label = tk.Label(legend, text=f"{title}\nUnknown", foreground=color, background=PALETTE["chart"],
                             font=("TkDefaultFont", 11, "bold"), anchor="w", justify="left")
            label.grid(row=0, column=index, sticky="ew", padx=4)
            legend.columnconfigure(index, weight=1)
            self.values[key] = label
        if self.clarity:
            from .system_navigation import reflow as fit_legend
            legend.bind("<Configure>", lambda event: fit_legend(legend, tuple(self.values.values()), event.width, maximum=3))
        self.chart = tk.Canvas(self.graph, height=150, highlightthickness=0, background=PALETTE["chart"])
        self.chart.pack(fill="x", pady=8)
        self.chart.bind("<Configure>", lambda event: self.draw())
        self.scale = tk.Label(self.graph, text="Calls/s · awaiting two owner observations", anchor="w",
                              foreground=PALETTE["header_text"], background=PALETTE["chart"], wraplength=700, justify="left")
        self.scale.pack(fill="x")
        self.graph_notice = None
        if self.clarity:
            self.graph_notice = tk.Label(self.graph, text="", anchor="w", justify="left",
                foreground=PALETTE["chart_muted"], background=PALETTE["chart"], wraplength=700)
            self.graph_notice.pack(fill="x", pady=(6, 0))
            self.graph.bind("<Configure>", lambda event: self.graph_notice.configure(wraplength=max(220, event.width - 24)), add="+")
        self.graph.bind("<Configure>", lambda event: self.scale.configure(wraplength=max(220, event.width - 24)), add="+")
        ranges = ttk.Frame(page)
        ranges.pack(fill="x", pady=(0, 10))
        range_buttons = []
        for index, (label, seconds) in enumerate((("1 min", 60), ("15 min", 900), ("1 hour", 3600))):
            button = ttk.Button(ranges, text=label, style="Range.TButton", command=lambda n=seconds: self.set_range(n))
            button.grid(row=0, column=index, padx=2)
            range_buttons.append(button)
        self.review_button = ttk.Button(ranges, text="Pause for review", style="Range.TButton", command=self.toggle_review)
        ranges.columnconfigure(3, weight=1)
        def reflow(event):
            self.review_button.grid(row=1 if event.width < 600 else 0, column=0 if event.width < 600 else 3,
                                    columnspan=3 if event.width < 600 else 1, sticky="w" if event.width < 600 else "e", pady=4)
        if self.clarity:
            from .system_navigation import reflow as fit_controls
            ranges.bind("<Configure>", lambda event: fit_controls(ranges, (*range_buttons, self.review_button), event.width, maximum=4))
        else:
            ranges.bind("<Configure>", reflow)
        center.text(page, "Completed calls and transactions · not rows or disk I/O. Definitions are under Source details." if self.clarity else "Reads = completed SELECT calls; writes = completed write/batch calls; commits = completed transactions. "
                    "Not rows, disk I/O or durable write counts. Includes owner observation reads. "
                    "Rates need two distinct owner samples. Missing readings stay gaps.", "Muted.TLabel")
        controls = ttk.Frame(page)
        controls.pack(fill="x", pady=(0, 10))
        self.select_button = ttk.Button(controls, text="Select source…", command=self.select)
        self.select_button.pack(side="left")
        self.refresh_button = ttk.Button(controls, text="Re-read", command=self.refresh, state="disabled")
        self.refresh_button.pack(side="left", padx=6)
        self.clear_button = ttk.Button(controls, text="Clear selection" if self.clarity else "Clear", command=self.clear)
        self.clear_button.pack(side="left")
        if self.clarity:
            from .system_navigation import reflow as fit_controls
            for button in (self.select_button, self.refresh_button, self.clear_button):
                button.pack_forget()
            controls.bind("<Configure>", lambda event: fit_controls(controls,
                (self.select_button, self.refresh_button, self.clear_button, self.source_toggle), event.width, maximum=4))
            self.test_check = ttk.Checkbutton(page, text="Test observations",
                variable=self.test_label, command=self.set_test_label)
            self.source_brief = center.text(page, "", "Muted.TLabel")
            self.source_toggle = ttk.Button(controls, text="Source details", command=self.toggle_source_details)
            self.describe_button = ttk.Button(page, text="Describe source…", command=self.describe_source)
        self.source = center.text(page, "", "Muted.TLabel")
        if self.clarity:
            self.source.pack_forget()
            self.source_slot = ttk.Frame(page)
            self.source_slot.pack(fill="x")
            self.snapshot_summary = center.text(page, "", "Heading.TLabel")
        self.rows = {}
        for key, title in (("storage", "Storage"), ("health", "Database health"), ("integrity", "Audit integrity")):
            self.rows[key] = StatusRow(page, title, "", None)
            self.rows[key].button.configure(width=17)
        self.warnings_parent = page
        if self.clarity:
            self.warnings_parent = ttk.Frame(page)
            self.warnings_parent.pack(fill="x", pady=(0, 8))
        center.text(page, "Authorization and permission counters", "Heading.TLabel")
        self.permissions = center.text(page, "")
        center.text(page, "AI usage • separate from authorization permits", "Heading.TLabel")
        self.ai = center.text(page, "")
        if self.clarity:
            self.warning_button = ttk.Button(self.warnings_parent, text="Observation notes", command=self.toggle_warnings)
            self.warning_button.pack(anchor="w", pady=(0, 6))
        else:
            center.text(page, "Warnings and alerts", "Heading.TLabel")
        self.warnings = center.text(self.warnings_parent, "")
        if self.clarity:
            self.warnings.pack_forget()
        self.warnings.configure(foreground=PALETTE["warning"])
        center.text(page, "Evidence event index", "Heading.TLabel")
        center.text(page, "Latest 24 redacted canonical event references, not a second audit log. "
                    "Select and copy a record hash to locate full evidence through the existing trusted audit path. "
                    "Raw payloads, prompts, bearer permits and credentials are never loaded here.", "Muted.TLabel")
        self.filter = tk.StringVar(master=self.root, value="All events")
        selector = ttk.Combobox(page, textvariable=self.filter, state="readonly", width=24,
                                values=("All events", "Policy decisions", "Permit events", "Rejections"))
        selector.pack(anchor="w", pady=(0, 8))
        selector.bind("<<ComboboxSelected>>", lambda event: self.render_logs())
        self.events_view = None
        if self.clarity:
            from .evidence_events import EvidenceEvents
            self.events_view = EvidenceEvents(self, page)
            self.logs = self.events_view.details
        else:
            log_frame = ttk.Frame(page)
            log_frame.pack(fill="x", pady=(0, 12))
            self.logs = tk.Text(log_frame, height=10, wrap="word", state="disabled", padx=10, pady=10,
                                background=PALETTE["surface"], foreground=PALETTE["text"], font=("TkDefaultFont", 10),
                                relief="flat", highlightthickness=1, highlightbackground=PALETTE["border"],
                                highlightcolor=PALETTE["accent"], selectbackground=PALETTE["accent"], selectforeground=PALETTE["header_text"])
            log_scroll = ttk.Scrollbar(log_frame, command=self.logs.yview)
            log_scroll.pack(side="right", fill="y")
            self.logs.configure(yscrollcommand=log_scroll.set)
            self.logs.pack(side="left", fill="both", expand=True)
        center.section(page, "Observation setup",
                       "Choose an existing pulpo.evidence-observation.v1 JSON export produced by the trusted database owner. "
                       "The page re-reads it every 2 seconds while visible. The owner must publish new observations for activity to update. "
                       "No database is opened here. Source identity and timestamps are reported metadata, not authenticated deployment proof. "
                       "No purge, repair, checkpoint, permission change or retry is offered.")
        self.root.bind("<Destroy>", self.destroy, add="+")
        self.root.bind("<Map>", self.mapped, add="+")
        self.root.bind("<Unmap>", self.unmapped, add="+")
        self.render()

    def set_range(self, seconds):
        self.seconds = seconds
        self.draw()

    def set_active(self, active):
        self.active = active
        self.schedule()
        self.schedule_ages()
        if self.clarity and active:
            self.render_timing()
            self.draw()

    def toggle_review(self):
        self.reviewing = not self.reviewing
        self.review_button.configure(text="Resume updates" if self.reviewing else "Pause for review")
        if self.reviewing:
            self.render()
            self.schedule()
        elif not self.awaiting_reread:
            self.refresh()
        else:
            self.render()
            self.schedule()

    def schedule(self):
        if self.timer is not None:
            self.root.after_cancel(self.timer)
            self.timer = None
        if not self.closed and self.active and self.path is not None and not self.reviewing and not self.awaiting_reread:
            self.timer = self.root.after(2000, self.tick)

    def mapped(self, event):
        if event.widget is self.root:
            self.schedule()
            self.schedule_ages()

    def unmapped(self, event):
        if event.widget is self.root:
            self.schedule_ages()

    def schedule_ages(self):
        if self.age_timer is not None:
            self.root.after_cancel(self.age_timer)
            self.age_timer = None
        if self.clarity and not self.closed and self.active and self.root.winfo_viewable() and self.root.state() != "iconic":
            self.age_timer = self.root.after(1000, self.tick_ages)

    def tick_ages(self):
        self.age_timer = None
        if self.clarity and not self.closed and self.active and self.root.winfo_viewable() and self.root.state() != "iconic":
            # Display clocks only: even paused/restored sources are never read here.
            self.render_timing()
            self.draw()
        self.schedule_ages()

    def destroy(self, event):
        if event.widget is self.root:
            self.closed = True
            self.schedule()
            self.schedule_ages()
            # Release Tk variables on their owner thread, not a later worker GC.
            self.filter = None
            self.test_label = None
            self.center = None

    def tick(self):
        self.timer = None
        if self.active and not self.reviewing and not self.awaiting_reread and self.root.winfo_viewable() and self.root.state() != "iconic":
            self.refresh()
        else:
            self.schedule()

    def select(self):
        from tkinter import filedialog
        selected = filedialog.askopenfilename(parent=self.root, title="Select evidence observation",
                                              filetypes=(("JSON observation", "*.json"),))
        if selected:
            self.center.reset_source_read("Evidence")
            if self.test_label is not None:
                self.test_label.set(False)
            self.history.clear()
            self.reviewing = False
            self.review_button.configure(text="Pause for review")
            self.path = Path(selected)
            self.refresh_button.configure(state="normal")
            self.refresh()

    def refresh(self):
        if self.path is None or self.closed:
            return
        self.awaiting_reread = False  # Explicit re-read unlocks normal visible polling.
        previous = (self.snapshot.source_id if self.snapshot else None, bool(self.error))
        try:
            import stat
            if not self.path.is_absolute() or not stat.S_ISREG(self.path.lstat().st_mode):
                raise ValueError("not_regular_file")
            snapshot = load_observation(self.path)
            if freshness(snapshot) == "clock mismatch":
                raise ValueError("source_clock_mismatch")
            self.history.add(snapshot)
            self.snapshot, self.error = snapshot, None
        except (OSError, ValueError, TypeError, RecursionError):
            self.snapshot = None
            self.history.clear()
            self.error = "Observation unavailable or invalid. Previous values cleared. Check the path, private-file permissions, format and owner clock."
        self.center.record_source_read("Evidence", self.error is None)
        current = (self.snapshot.source_id if self.snapshot else None, bool(self.error))
        if current != previous and hasattr(self.center, "activity_view"):
            self.center.record_activity("Evidence observation unavailable/invalid; inspect Evidence." if self.error else
                "Evidence observation loaded. Source-reported references are bounded; enforcement remains Unknown.",
                category="Evidence", action="source", outcome="Failed" if self.error else "Completed",
                severity="Warning" if self.error else "Info")
        self.render()
        self.schedule()

    def clear(self):
        self.center.reset_source_read("Evidence")
        if self.test_label is not None:
            self.test_label.set(False)
        self.path, self.snapshot, self.error = None, None, None
        self.awaiting_reread = False
        self.reviewing = False
        self.review_button.configure(text="Pause for review")
        self.history.clear()
        self.refresh_button.configure(state="disabled")
        self.render()
        self.schedule()

    def render(self):
        s = self.snapshot
        if s is None:
            self.source.configure(text=("Restored selection · Not checked this session. Press Re-read to inspect the owner export."
                if self.awaiting_reread else self.error or "Unknown · No database observation selected."))
            for row in self.rows.values():
                row.update("Unknown", "Unknown · No observation", "Select a trusted-owner export. A missing value is not zero.")
            self.permissions.configure(text="Allowed decisions: Unknown · Denied decisions: Unknown · Approval requests: Unknown\n"
                                       "Permits consumed: Unknown · Permit rejections: Unknown · Approval rejections: Unknown\n"
                                       "Expired approvals: Unknown · Replayed approvals: Unknown")
            self.ai.configure(text="Input tokens: Unknown · Output tokens: Unknown · Cost: Unknown")
            self.warnings.configure(text=self.error or "No source connected. Database, permissions and AI telemetry are Unknown.")
            self.center.status_rows["Evidence"].update("Attention" if self.error else "Unknown",
                "Attention · Observation read failed" if self.error else "Unknown · No evidence observation",
                self.error or "No frozen owner observation selected. Comparison results concern disposable fixtures only; enforcement is not assessed.")
        else:
            stamp = time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime(s.observed_at_ns / 1e9))
            age = freshness(s)
            review = "Paused for review · historical values\n" if self.reviewing else ""
            self.source.configure(text=review + f"Recorded · Source time {stamp} · {age}\nSelected file: {self.path}\n"
                                  "Provenance and deployment enforcement remain Unknown. Hidden-page polling pauses.")
            used = (1 - s.volume_free / s.volume_total) * 100 if s.volume_total else None
            storage_state = "Unknown" if used is None else "Attention" if used >= 95 else "Elevated" if used >= 85 else "Normal"
            if (age == "stale" or self.reviewing) and storage_state == "Normal":
                storage_state = "Unknown"
            self.rows["storage"].update(storage_state,
                "Unknown · Capacity unavailable" if used is None else f"Recorded · Volume {used:.1f}% used · {size(s.volume_free)} free",
                f"Database file: {size(s.database_bytes)} · WAL file: {size(s.wal_bytes)}\n"
                f"Database volume capacity: {size(s.volume_total)}. Shared volume use is not all Pulpo evidence. "
                "Amber ≥85% used; red ≥95%. These are capacity hints, not retention recommendations.")
            self.rows["health"].update("Normal" if s.health == "ok" and age != "stale" and not self.reviewing else "Attention" if s.health == "failed" else "Unknown",
                f"Recorded · Source database check: {s.health.replace('_', ' ')}" + (" · stale" if age == "stale" else ""),
                "Source-reported SQLite quick_check(1), only when requested by the trusted owner. "
                "A passing physical database check does not verify audit integrity, backups, recovery or enforcement. "
                f"Connection totals: errors {count(s.errors)} · rollbacks {count(s.rollbacks)}. Past errors are not a current outage.")
            self.rows["integrity"].update("Unknown" if s.audit_valid else "Attention",
                "Recorded · Source audit check passed" if s.audit_valid else "Attention · Source reports failed audit check",
                f"Source audit records: {s.audit_records:,}. This redacted projection cannot independently verify the chain or completeness. "
                "Health and audit validity are separate. No enforcement attestation is made.")
            self.permissions.configure(text=f"Source audit totals · not current outstanding permits or pending approvals\n"
                f"Allowed decisions: {count(s.allowed)} · Denied decisions: {count(s.denied)} · Approval requests: {count(s.approval_required)}\n"
                f"Permits consumed: {count(s.permit_consumed)} · Permit rejections: {count(s.permit_rejected)} · Approval rejections: {count(s.approval_rejected)}\n"
                f"Expired approvals: {count(s.approval_expired)} · Replayed approvals: {count(s.approval_replayed)}\n"
                "Permit expiry/replay breakdown: Unknown (not recorded separately). Policy denials and approval requests are workflow outcomes, not incidents by themselves.")
            cost = "Unknown" if s.ai.cost_microusd is None else f"USD {s.ai.cost_microusd / 1e6:.6f} (reported)"
            self.ai.configure(text=f"Provider: {s.ai.provider} · Scope: {s.ai.scope.replace('_', ' ')}\n"
                              f"Input tokens: {count(s.ai.input_tokens)} · Output tokens: {count(s.ai.output_tokens)} · Cost: {cost}\n"
                              "Provider-reported usage. This is not a lifetime total or permission budget. Missing usage/prices are never estimated. "
                              "AI quota/limit alerts: Unknown — no configured usage-limit source.")
            warnings = []
            if age == "stale": warnings.append("Stale observation: owner timestamp is over 15 seconds old; activity rates unavailable.")
            if storage_state in {"Attention", "Elevated"}: warnings.append("Database volume capacity needs attention. Review retention through the governed operator path.")
            if s.health != "ok": warnings.append(f"Database check {s.health.replace('_', ' ')}; inspect through the trusted owner.")
            if not s.audit_valid: warnings.append("Source reports failed audit integrity. Preserve evidence and investigate through the canonical path.")
            if s.permit_rejected or s.approval_rejected: warnings.append("Recorded permit/approval rejections exist. Use Rejections below; historical counts are not active incidents.")
            if s.errors: warnings.append("Connection has recorded SQL errors; inspect owner diagnostics. No SQL text is exported.")
            if s.database_bytes is not None and s.wal_bytes is not None and s.wal_bytes > max(64 * 1024**2, s.database_bytes):
                warnings.append("WAL file is large relative to the database. Inspect checkpoint/backups on the trusted side; no automatic cleanup.")
            if s.ai.input_tokens is None or s.ai.output_tokens is None: warnings.append("AI usage incomplete or unavailable; no token-limit conclusion can be drawn.")
            self.warnings.configure(text="\n".join("• " + item for item in warnings) or "No warning conditions found in this snapshot. This is not an all-clear for deployment.")
            self.center.status_rows["Evidence"].update("Attention" if not s.audit_valid or s.health == "failed" else "Unknown",
                "Recorded · Evidence observation loaded; enforcement unassessed",
                "Frozen owner observation loaded. Metrics and audit results are source-reported, not independently authenticated. "
                "Open Evidence to inspect timestamps, database health, warnings and redacted record references. No enforcement attestation is made.")
        if self.clarity:
            self.render_clarity()
            definitions = ("\n\nActivity definitions · Reads: completed SELECT calls. Writes: completed write/batch calls. "
                "Commits: completed transactions. Not rows, disk I/O or durable write counts. Includes owner observation reads. "
                "Rates require distinct comparable owner timestamps; missing readings stay gaps. "
                "The Test observations checkbox and source description are session-only operator labels, not authenticated provenance. They are not saved. "
                "Resource graphs elsewhere describe this WSL Linux VM, not the machine that produced this export.")
            self.source.configure(text=self.source.cget("text") + definitions)
        self.render_logs()
        if hasattr(self.center, "decision_explorer"):
            self.center.decision_explorer.render()
        self.center.refresh_attention()
        self.draw()

    def render_logs(self):
        if self.events_view is not None:
            self.events_view.render()
            return
        lines = []
        for event in reversed(self.snapshot.events if self.snapshot else ()):
            choice = self.filter.get()
            if choice == "Policy decisions" and event.event != "decision": continue
            if choice == "Permit events" and not event.event.startswith("permit_"): continue
            if choice == "Rejections" and event.outcome != "rejected": continue
            stamp = time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime(event.timestamp_ns / 1e9))
            lines.append(f"{stamp} · {event.event} · {event.outcome.replace('_', ' ')}\n{event.record_hash}")
        self.logs.configure(state="normal")
        self.logs.delete("1.0", "end")
        self.logs.insert("end", "\n\n".join(lines) or "No matching event references available. This does not prove there were no events.")
        self.logs.configure(state="disabled")

    def draw(self):
        self.chart.delete("all")
        width = max(1, self.chart.winfo_width())
        now = time.time()
        points = [(at, rates) for at, rates in self.history.points if now - self.seconds <= at <= now + 5]
        usable = self.snapshot is not None and not self.reviewing and freshness(self.snapshot) == "recent source timestamp"
        values = [v for _, rates in points for v in rates.values() if v is not None]
        height = 90 if self.clarity and not values else 150
        if int(self.chart.cget("height")) != height:
            self.chart.configure(height=height)
        peak = max(1, max(values, default=0))
        for y in (20, height / 2, height - 20): self.chart.create_line(0, y, width, y, fill=PALETTE["chart_grid"])
        for key, (title, color) in SERIES.items():
            latest = self.history.points[-1][1][key] if self.history.points and usable else None
            self.values[key].configure(text=f"{title}\n" + ("Unknown" if latest is None else f"{latest:.1f}/s"))
            previous = None
            for at, rates in points:
                value = rates[key]
                if value is None:
                    previous = None
                    continue
                x = 8 + (at - (now - self.seconds)) / self.seconds * max(1, width - 16)
                y = height - 12 - value / peak * (height - 24)
                if previous and 0 < at - previous[2] <= 15:
                    self.chart.create_line(previous[0], previous[1], x, y, fill=color, width=2)
                self.chart.create_oval(x-2, y-2, x+2, y+2, fill=color, outline="")
                previous = x, y, at
        if self.clarity:
            from .observation_clarity import graph_state
            title, detail = graph_state(self.snapshot, self.history, selected=self.path is not None,
                error=bool(self.error), pending=self.awaiting_reread, paused=self.reviewing)
            self.graph_notice.configure(text=f"{title} · {detail}")
            if not values:
                self.chart.create_text(width / 2, height / 2, text=title, width=max(150, width - 28),
                    justify="center", fill=PALETTE["header_text"])
        elif not values:
            self.chart.create_text(width / 2, height / 2, text="Awaiting two distinct owner observations", fill=PALETTE["header_text"])
        self.scale.configure(text=f"0–{peak:.1f} calls/s · last {self.seconds // 60} min · connection-scoped counters, session-only history")

    def set_test_label(self):
        if self.path is not None and self.test_label.get():
            self.center.source_test_labels["Evidence"] = str(self.path)
        else:
            self.center.source_test_labels.pop("Evidence", None)
        self.center.refresh_observation_context()

    def toggle_source_details(self):
        self.source_details_visible = not self.source_details_visible
        if self.source_details_visible:
            self.source.pack(fill="x", pady=(0, 10), before=self.source_slot)
            self.test_check.pack(anchor="w", pady=(0, 8), before=self.source)
            self.describe_button.pack(anchor="w", pady=(0, 8), before=self.source)
        else:
            self.source.pack_forget()
            self.test_check.pack_forget()
            self.describe_button.pack_forget()
        self.source_toggle.configure(text="Hide source details" if self.source_details_visible else "Source details")
        self.layout_source_controls()

    def layout_source_controls(self):
        from .system_navigation import reflow
        frame = self.source_toggle.master
        reflow(frame, (self.select_button, self.refresh_button, self.clear_button, self.source_toggle), frame.winfo_width(), maximum=4)

    def toggle_warnings(self):
        self.warnings_visible = not self.warnings_visible
        if self.warnings_visible:
            self.warnings.pack(fill="x", pady=(0, 10))
        else:
            self.warnings.pack_forget()
        self.render_clarity()

    def render_clarity(self):
        self.select_button.configure(text="Replace source…" if self.path is not None else "Select source…")
        self.test_check.configure(state="normal" if self.path is not None else "disabled")
        self.describe_button.configure(state="normal" if self.path is not None else "disabled")
        # Operator label is scoped to the current selection, not persisted or provenance.
        if self.path is None:
            self.test_label.set(False)
        self.render_timing()
        lines = self.warnings.cget("text").splitlines()
        notes = sum(line.startswith("• ") for line in lines)
        label = f"Notes ({notes})" if self.snapshot is not None else "Notes · unavailable"
        self.warning_button.configure(text=f"{label} · {'hide' if self.warnings_visible else 'show'}")
        self.layout_source_controls()
        self.center.refresh_observation_context()

    def render_timing(self):
        if not self.clarity or self.closed:
            return
        from .observation_clarity import elapsed_age
        name = self.path.name if self.path is not None else "None selected"
        age = elapsed_age(self.snapshot.observed_at_ns) if self.snapshot is not None else "Unknown · no usable source timestamp"
        state = "read failed" if self.error else "not checked" if self.awaiting_reread else "Unknown" if self.snapshot is None else "Paused" if self.reviewing else freshness(self.snapshot)
        self.source_brief.configure(text=f"Selected export · {name}\nSource machine · {self.center.source_description('Evidence')}\n"
            f"Source-data age · {age}\nLast successful read · {self.center.source_read_age('Evidence')} (local UI time)")
        self.snapshot_summary.configure(text=f"Snapshot summary · {state}")

    def describe_source(self):
        if self.path is not None and not self.closed:
            self.center.system_view.source_health.edit_machine_description("Evidence")
