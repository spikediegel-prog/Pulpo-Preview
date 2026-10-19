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
        self.history = ActivityHistory()
        self.timer, self.active, self.closed = None, False, False
        self.reviewing = False
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
        self.chart = tk.Canvas(self.graph, height=150, highlightthickness=0, background=PALETTE["chart"])
        self.chart.pack(fill="x", pady=8)
        self.chart.bind("<Configure>", lambda event: self.draw())
        self.scale = tk.Label(self.graph, text="Calls/s · awaiting two owner observations", anchor="w",
                              foreground=PALETTE["header_text"], background=PALETTE["chart"], wraplength=700, justify="left")
        self.scale.pack(fill="x")
        self.graph.bind("<Configure>", lambda event: self.scale.configure(wraplength=max(240, event.width - 24)))
        ranges = ttk.Frame(page)
        ranges.pack(fill="x", pady=(0, 10))
        for index, (label, seconds) in enumerate((("1 min", 60), ("15 min", 900), ("1 hour", 3600))):
            ttk.Button(ranges, text=label, style="Range.TButton", command=lambda n=seconds: self.set_range(n)).grid(row=0, column=index, padx=2)
        self.review_button = ttk.Button(ranges, text="Pause for review", style="Range.TButton", command=self.toggle_review)
        ranges.columnconfigure(3, weight=1)
        def reflow(event):
            self.review_button.grid(row=1 if event.width < 600 else 0, column=0 if event.width < 600 else 3,
                                    columnspan=3 if event.width < 600 else 1, sticky="w" if event.width < 600 else "e", pady=4)
        ranges.bind("<Configure>", reflow)
        center.text(page, "Reads = completed SELECT calls; writes = completed write/batch calls; commits = completed transactions. "
                    "Not rows, disk I/O or durable write counts. Includes owner observation reads. "
                    "Rates need two distinct owner samples. Missing readings stay gaps.", "Muted.TLabel")
        controls = ttk.Frame(page)
        controls.pack(fill="x", pady=(0, 10))
        ttk.Button(controls, text="Select source…", command=self.select).pack(side="left")
        self.refresh_button = ttk.Button(controls, text="Re-read", command=self.refresh, state="disabled")
        self.refresh_button.pack(side="left", padx=6)
        ttk.Button(controls, text="Clear", command=self.clear).pack(side="left")
        self.source = center.text(page, "", "Muted.TLabel")
        self.rows = {}
        for key, title in (("storage", "Storage"), ("health", "Database health"), ("integrity", "Audit integrity")):
            self.rows[key] = StatusRow(page, title, "", None)
            self.rows[key].button.configure(width=17)
        center.text(page, "Authorization and permission counters", "Heading.TLabel")
        self.permissions = center.text(page, "")
        center.text(page, "AI usage • separate from authorization permits", "Heading.TLabel")
        self.ai = center.text(page, "")
        center.text(page, "Warnings and alerts", "Heading.TLabel")
        self.warnings = center.text(page, "")
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
        self.render()

    def set_range(self, seconds):
        self.seconds = seconds
        self.draw()

    def set_active(self, active):
        self.active = active
        self.schedule()

    def toggle_review(self):
        self.reviewing = not self.reviewing
        self.review_button.configure(text="Resume updates" if self.reviewing else "Pause for review")
        if self.reviewing:
            self.render()
            self.schedule()
        else:
            self.refresh()

    def schedule(self):
        if self.timer is not None:
            self.root.after_cancel(self.timer)
            self.timer = None
        if not self.closed and self.active and self.path is not None and not self.reviewing:
            self.timer = self.root.after(2000, self.tick)

    def mapped(self, event):
        if event.widget is self.root:
            self.schedule()

    def destroy(self, event):
        if event.widget is self.root:
            self.closed = True
            self.schedule()
            # Release Tk variables on their owner thread, not a later worker GC.
            self.filter = None
            self.center = None

    def tick(self):
        self.timer = None
        if self.active and not self.reviewing and self.root.winfo_viewable() and self.root.state() != "iconic":
            self.refresh()
        else:
            self.schedule()

    def select(self):
        from tkinter import filedialog
        selected = filedialog.askopenfilename(parent=self.root, title="Select evidence observation",
                                              filetypes=(("JSON observation", "*.json"),))
        if selected:
            self.history.clear()
            self.reviewing = False
            self.review_button.configure(text="Pause for review")
            self.path = Path(selected)
            self.refresh_button.configure(state="normal")
            self.refresh()

    def refresh(self):
        if self.path is None or self.closed:
            return
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
        current = (self.snapshot.source_id if self.snapshot else None, bool(self.error))
        if current != previous and hasattr(self.center, "activity_view"):
            self.center.record_activity("Evidence observation unavailable/invalid; inspect Evidence." if self.error else
                "Evidence observation loaded. Source-reported references are bounded; enforcement remains Unknown.",
                category="Evidence", action="source", outcome="Failed" if self.error else "Completed",
                severity="Warning" if self.error else "Info")
        self.render()
        self.schedule()

    def clear(self):
        self.path, self.snapshot, self.error = None, None, None
        self.reviewing = False
        self.review_button.configure(text="Pause for review")
        self.history.clear()
        self.refresh_button.configure(state="disabled")
        self.render()
        self.schedule()

    def render(self):
        s = self.snapshot
        if s is None:
            self.source.configure(text=self.error or "Unknown · No database observation selected.")
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
        self.render_logs()
        self.draw()

    def render_logs(self):
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
        width, height = max(1, self.chart.winfo_width()), 150
        now = time.time()
        points = [(at, rates) for at, rates in self.history.points if now - self.seconds <= at <= now + 5]
        usable = self.snapshot is not None and not self.reviewing and freshness(self.snapshot) == "recent source timestamp"
        values = [v for _, rates in points for v in rates.values() if v is not None]
        peak = max(1, max(values, default=0))
        for y in (20, 75, 130): self.chart.create_line(0, y, width, y, fill=PALETTE["chart_grid"])
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
        if not values:
            self.chart.create_text(width / 2, height / 2, text="Awaiting two distinct owner observations", fill=PALETTE["header_text"])
        self.scale.configure(text=f"0–{peak:.1f} calls/s · last {self.seconds // 60} min · connection-scoped counters, session-only history")
