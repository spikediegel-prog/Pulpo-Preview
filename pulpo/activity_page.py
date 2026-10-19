"""Session timeline and separate bounded evidence-reference inspection."""
import json
import time

from .activity_model import ACTIONS, CATEGORIES, LEVELS, OUTCOMES, SessionActivity
from .evidence_observation import freshness
from .control_center_theme import surface


class ActivityPage:
    def __init__(self, center):
        import tkinter as tk
        from tkinter import ttk
        from .control_center import PALETTE
        self.palette = PALETTE
        self.center, self.root = center, center.root
        self.model = SessionActivity()
        self.active = self.paused = self.closed = False
        self.timer = None
        self.unread = 0
        self.displayed, self.references, self.source_snapshot = (), (), None
        self.chart_bins = self.model.histogram()
        self.chart_minute = time.time_ns() // 60_000_000_000
        self.chart_local = True
        page = center.pages["Activity"]
        center.text(page, "Observed activity", "Heading.TLabel")
        center.text(page, "Local session events and evidence references have separate coverage. "
                    "This view cannot approve, retry, revoke or execute actions.", "Muted.TLabel")
        shadow, border = surface(page, dark=True)
        shadow.pack(fill="x", pady=(0, 8))
        self.chart = tk.Canvas(border, height=105, highlightthickness=0, background=PALETTE["chart"])
        self.chart.pack(fill="x", padx=10, pady=8)
        self.chart.bind("<Configure>", lambda event: self.draw())
        self.coverage = center.text(page, "", "Muted.TLabel")
        self.attention = center.text(page, "", "Status.TLabel")
        tools = ttk.Frame(page)
        tools.pack(fill="x", pady=(0, 8))
        self.pause_button = ttk.Button(tools, text="Pause display", command=self.toggle_pause)
        self.pause_button.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=3)
        self.refresh_button = ttk.Button(tools, text="Refresh display", command=self.render)
        self.refresh_button.grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Button(tools, text="Open Evidence source", command=lambda: center.show("Evidence")).grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=3)
        for col in (0, 1): tools.columnconfigure(col, weight=1)
        self.variables = {}
        filters = ttk.Frame(page)
        filters.pack(fill="x", pady=(0, 8))
        specs = (("View", ("Local session", "Evidence references")), ("Time", ("Available coverage", "Last 5 minutes", "Last hour")),
                 ("Category", ("All", *CATEGORIES)), ("Outcome", ("All", *OUTCOMES, "allowed", "denied", "blocked_by_policy", "approval_required", "rejected", "recorded")),
                 ("Severity", ("All", *LEVELS)))
        self.filter_frames = []
        for key, values in specs:
            box = ttk.Frame(filters)
            ttk.Label(box, text=key).pack(anchor="w")
            variable = tk.StringVar(master=self.root, value=values[0])
            self.variables[key] = variable
            combo = ttk.Combobox(box, textvariable=variable, values=values, state="readonly", width=18)
            combo.pack(fill="x")
            combo.bind("<<ComboboxSelected>>", lambda event: self.render())
            self.filter_frames.append(box)
        box = ttk.Frame(filters)
        ttk.Label(box, text="Search local text / record hash").pack(anchor="w")
        self.search = tk.StringVar(master=self.root)
        entry = ttk.Entry(box, textvariable=self.search, width=18)
        entry.pack(fill="x")
        entry.bind("<KeyRelease>", lambda event: self.render())
        self.filter_frames.append(box)
        self.only_attention = tk.BooleanVar(master=self.root, value=False)
        self.attention_filter = ttk.Checkbutton(page, text="Needs attention · local warnings/errors",
                        variable=self.only_attention, command=self.render)
        self.attention_filter.pack(anchor="w", pady=(0, 8))
        def reflow(event):
            cols = 2 if event.width < 650 else 3
            for i, box in enumerate(self.filter_frames):
                box.grid(row=i // cols, column=i % cols, sticky="ew", padx=(0, 8), pady=3)
            for col in range(3): filters.columnconfigure(col, weight=1 if col < cols else 0)
            self.table.configure(displaycolumns=("time", "action", "outcome") if cols == 2 else ("time", "category", "action", "outcome", "severity"))
        filters.bind("<Configure>", reflow)
        area = ttk.Frame(page)
        area.pack(fill="x", pady=(0, 8))
        style = ttk.Style(self.root)
        style.configure("Activity.Treeview", background=PALETTE["surface"], fieldbackground=PALETTE["surface"],
                        foreground=PALETTE["text"], rowheight=26, font=("TkDefaultFont", 10))
        style.map("Activity.Treeview", background=[("selected", PALETTE["accent"])], foreground=[("selected", "#FFFFFF")])
        self.table = ttk.Treeview(area, columns=("time", "category", "action", "outcome", "severity"), show="headings", height=7, selectmode="browse", style="Activity.Treeview")
        for name, title, width in (("time", "Local time", 105), ("category", "Category", 95), ("action", "Event", 250), ("outcome", "Outcome", 110), ("severity", "Level", 65)):
            self.table.heading(name, text=title)
            self.table.column(name, width=width, minwidth=60 if name != "action" else 130, stretch=True)
        self.table.grid(row=0, column=0, sticky="nsew")
        ttk.Scrollbar(area, orient="vertical", command=self.table.yview).grid(row=0, column=1, sticky="ns")
        self.table.configure(yscrollcommand=lambda *args: area.winfo_children()[1].set(*args))
        horizontal = ttk.Scrollbar(area, orient="horizontal", command=self.table.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.table.configure(xscrollcommand=horizontal.set)
        area.columnconfigure(0, weight=1)
        for level, color in (("Warning", PALETTE["warning"]), ("Error", PALETTE["error"]), ("Info", PALETTE["text"])):
            self.table.tag_configure(level, foreground=color)
        self.table.bind("<<TreeviewSelect>>", lambda event: self.show_details())
        self.empty = center.text(page, "", "Muted.TLabel")
        center.text(page, "Selected event details", "Heading.TLabel")
        details = ttk.Frame(page)
        details.pack(fill="x", pady=(0, 8))
        self.output = tk.Text(details, height=8, wrap="word", state="disabled", padx=10, pady=10,
                              background=PALETTE["surface"], foreground=PALETTE["text"], takefocus=True, font=("TkDefaultFont", 10),
                              relief="flat", highlightthickness=1, highlightbackground=PALETTE["border"],
                              highlightcolor=PALETTE["accent"], selectbackground=PALETTE["accent"], selectforeground=PALETTE["header_text"])
        self.output.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(details, command=self.output.yview)
        scroll.pack(side="right", fill="y")
        self.output.configure(yscrollcommand=scroll.set)
        actions = ttk.Frame(page)
        actions.pack(fill="x")
        self.review_button = ttk.Button(actions, text="Mark reviewed locally", command=self.review)
        self.review_button.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=3)
        self.copy_button = ttk.Button(actions, text="Copy safe reference", command=self.copy)
        self.copy_button.grid(row=0, column=1, sticky="ew", pady=3)
        self.open_button = ttk.Button(actions, text="Open related page", command=self.open_related)
        self.open_button.grid(row=1, column=0, sticky="ew", padx=(0, 6), pady=3)
        self.export_button = ttk.Button(actions, text="Preview safe export…", command=self.preview_export)
        self.export_button.grid(row=1, column=1, sticky="ew", pady=3)
        for col in (0, 1): actions.columnconfigure(col, weight=1)
        self.notice = center.text(page, "Local diagnostic text can contain paths or sensitive details. "
                                  "Copy/export omits all free-form text. Local review does not resolve a canonical incident.", "Muted.TLabel")
        def wrap(event):
            for label in (self.coverage, self.attention, self.empty, self.notice):
                label.configure(wraplength=max(220, event.width - 16))
            self.chart.configure(height=140 if event.width < 650 else 105)
        page.bind("<Configure>", wrap)
        self.root.bind("<Destroy>", self.destroy, add="+")
        self.add("Recorded: Control Center opened. No fixture checks run and no settings saved. Resource observations stay in this session.", action="opened")

    def add(self, detail, **metadata):
        event = self.model.add(detail, **metadata)
        if not self.active or self.paused:
            self.unread += 1
            self.update_badge()
        if not self.paused and (self.active or event.sequence == 1):
            self.render()
        elif self.paused:
            self.coverage.configure(text=f"Display paused · {self.unread} new local events; collection continues within the 500-event limit.")
        return event.sequence

    def update_badge(self):
        self.center.navigation["Activity"].configure(text="Activity" + (f" ({self.unread})" if self.unread else ""))

    def set_active(self, active):
        self.active = active
        if self.timer is not None:
            self.root.after_cancel(self.timer)
            self.timer = None
        if active:
            self.render()
            self.timer = self.root.after(1000, self.tick)

    def tick(self):
        self.timer = None
        if self.active and not self.closed:
            if not self.paused and self.root.winfo_viewable() and self.root.state() != "iconic":
                self.render(preserve=True)
            self.timer = self.root.after(1000, self.tick)

    def toggle_pause(self):
        self.paused = not self.paused
        self.pause_button.configure(text="Resume display" if self.paused else "Pause display")
        self.refresh_button.configure(state="disabled" if self.paused else "normal")
        for frame in self.filter_frames:
            control = frame.winfo_children()[1]
            control.configure(state="disabled" if self.paused else "readonly" if control.winfo_class() == "TCombobox" else "normal")
        self.attention_filter.configure(state="disabled" if self.paused else "normal")
        if self.paused:
            self.coverage.configure(text="Display paused · collection continues within the 500-event limit; exports use the frozen visible rows.")
        else:
            self.render()

    def render(self, preserve=False):
        if self.paused or self.closed:
            return
        if self.active:
            self.unread = 0
            self.update_badge()
        selected = self.table.selection() if preserve else ()
        position = self.table.yview()
        self.table.delete(*self.table.get_children())
        choice = {key: value.get() for key, value in self.variables.items()}
        self.chart_local = choice["View"] == "Local session"
        self.chart_bins = self.model.histogram()
        self.chart_minute = time.time_ns() // 60_000_000_000
        seconds = {"Available coverage": None, "Last 5 minutes": 300, "Last hour": 3600}[choice["Time"]]
        since = 0 if seconds is None else time.time_ns() - seconds * 1_000_000_000
        self.source_snapshot = self.center.evidence_view.snapshot
        self.references = ()
        if choice["View"] == "Local session":
            self.displayed = self.model.select(category=choice["Category"], outcome=choice["Outcome"], severity=choice["Severity"],
                search=self.search.get(), since_ns=since, attention=self.only_attention.get())
            for event in self.displayed:
                self.table.insert("", "end", iid=str(event.sequence), values=(self.stamp(event.timestamp_ns), event.category,
                    ACTIONS[event.action], event.outcome, event.severity), tags=(event.severity,))
            self.coverage.configure(text=f"Recorded local session · {len(self.model.events)} retained · {self.model.dropped} older events dropped · "
                                    "chart: retained events/minute, last 10 minutes; no fleet totals. Cleared on exit.")
        else:
            self.displayed = ()
            snapshot = self.source_snapshot
            events = snapshot.events if snapshot else ()
            category = lambda event: "Governance" if event.event != "other" else "Evidence"
            self.references = tuple(e for e in reversed(events) if e.timestamp_ns >= since
                and (choice["Category"] in ("All", category(e))) and (choice["Outcome"] in ("All", e.outcome))
                and choice["Severity"] in ("All", "Info") and not self.only_attention.get()
                and self.search.get()[:200].casefold() in (e.event + " " + e.record_hash + " " + e.outcome).casefold())
            for index, event in enumerate(self.references):
                self.table.insert("", "end", iid=f"ref{index}", values=(self.stamp(event.timestamp_ns), category(event), event.event.replace("_", " "), event.outcome.replace("_", " "), "Info"))
            error = self.center.evidence_view.error
            scope = f"{len(events)} supplied references (maximum 24) · {freshness(snapshot)}" if snapshot else "No valid observation available"
            if error: scope += " · Evidence source read failed"
            self.coverage.configure(text="Recorded source-reported index · " + scope + ". No complete history, activity rate or enforcement conclusion. Source refresh is controlled in Evidence.")
        self.attention.configure(text=f"{sum(self.model.needs_attention(e) for e in self.model.events)} unreviewed local warnings/errors · "
            + ("Evidence observation unavailable/invalid; inspect Evidence." if self.center.evidence_view.error else
               "Evidence observation stale; inspect Evidence." if self.source_snapshot and freshness(self.source_snapshot) != "recent source timestamp" else
               "Historical policy blocks/rejections are outcomes, not active incident counts."))
        has_attention = any(self.model.needs_attention(e) for e in self.model.events) or self.center.evidence_view.error or (
            self.source_snapshot and freshness(self.source_snapshot) != "recent source timestamp")
        self.attention.configure(foreground=self.palette["warning"] if has_attention else self.palette["muted"])
        ids = self.table.get_children()
        self.empty.configure(text=f"{len(ids)} matching entries · newest first" if ids else "No matching entries in available coverage. This does not prove there were no events.")
        if ids:
            self.table.selection_set(selected[0] if selected and selected[0] in ids else ids[0])
            if preserve and position: self.table.yview_moveto(position[0])
        self.show_details()
        self.draw()

    @staticmethod
    def stamp(ns):
        return time.strftime("%H:%M:%S", time.localtime(ns / 1e9))

    def selected(self):
        selection = self.table.selection()
        if not selection:
            return None
        key = selection[0]
        if key.startswith("ref"):
            return self.references[int(key[3:])]
        return next((e for e in self.displayed if str(e.sequence) == key), None)

    def show_details(self):
        from .activity_model import SessionEvent
        event = self.selected()
        local = isinstance(event, SessionEvent)
        self.review_button.configure(state="normal" if local and self.model.needs_attention(event) else "disabled")
        self.copy_button.configure(state="normal" if event else "disabled")
        self.open_button.configure(state="normal" if event else "disabled")
        text = "Select an event to inspect its details."
        if local:
            text = (f"Recorded local session · {time.strftime('%Y-%m-%d %H:%M:%S %Z', time.localtime(event.timestamp_ns / 1e9))}\n"
                    f"{event.category} · {ACTIONS[event.action]} · {event.outcome} · {event.severity}\n"
                    + ("Reviewed locally; underlying outcome unchanged.\n" if event.sequence in self.model.reviewed else "")
                    + event.detail + "\n\nNext: inspect the related page. This event is not canonical audit evidence.")
        elif event:
            text = (f"Source-reported reference · {time.strftime('%Y-%m-%d %H:%M:%S %Z', time.localtime(event.timestamp_ns / 1e9))}\n"
                    f"{event.event} · {event.outcome}\nRecord hash: {event.record_hash}\n"
                    f"Source: {self.source_snapshot.source_id}\n"
                    "Next: copy the record hash and locate full evidence through the existing trusted audit path. "
                    "Reference presence, allowed decisions and consumed permits do not attest execution or enforcement.")
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("end", text)
        self.output.configure(state="disabled")

    def review(self):
        from .activity_model import SessionEvent
        event = self.selected()
        if isinstance(event, SessionEvent):
            self.model.review(event.sequence)
            if self.paused:
                self.show_details()
            else:
                self.render(preserve=True)

    def public_rows(self):
        return [e.public() for e in self.displayed] + [{"timestamp_ns": e.timestamp_ns, "event": e.event,
            "outcome": e.outcome, "record_hash": e.record_hash, "source_id": self.source_snapshot.source_id,
            "claim": "Recorded source-reported reference; enforcement Unknown"} for e in self.references]

    def copy(self):
        from .activity_model import SessionEvent
        event = self.selected()
        if event:
            text = json.dumps(event.public(), indent=2) if isinstance(event, SessionEvent) else event.record_hash
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.notice.configure(text="Copied safe metadata/reference only; free-form diagnostic text omitted.")

    def open_related(self):
        from .activity_model import SessionEvent
        event = self.selected()
        if event:
            self.center.show(event.category if isinstance(event, SessionEvent) else "Evidence")

    def preview_export(self):
        import tkinter as tk
        from tkinter import ttk, filedialog
        from pathlib import Path
        # Freeze exactly what was previewed, even if new events arrive later.
        document = {"schema": "pulpo.activity-display.v1", "claim": "Recorded bounded UI selection; not canonical audit",
                    "exported_at_ns": time.time_ns(), "display_paused": self.paused,
                    "omitted": "All free-form diagnostic text, paths, credentials, commands and prompts",
                    "coverage": self.coverage.cget("text"), "rows": self.public_rows()}
        text = json.dumps(document, indent=2)
        preview = tk.Toplevel(self.root)
        preview.title("Activity — safe export preview")
        preview.geometry("720x520")
        preview.transient(self.root)
        ttk.Label(preview, text="Review the exact export below. Free-form diagnostic text is omitted.",
                  wraplength=650, padding=12).pack(fill="x")
        area = ttk.Frame(preview)
        area.pack(fill="both", expand=True, padx=12)
        content = tk.Text(area, wrap="word", takefocus=True)
        content.pack(side="left", fill="both", expand=True)
        content.insert("end", text)
        content.configure(state="disabled")
        scroll = ttk.Scrollbar(area, command=content.yview)
        scroll.pack(side="right", fill="y")
        content.configure(yscrollcommand=scroll.set)
        def save():
            selected = filedialog.asksaveasfilename(parent=preview, initialfile="pulpo-activity.json", defaultextension=".json")
            if selected:
                try:
                    Path(selected).write_text(text, encoding="utf-8")
                    self.add("Selected safe Activity export written.", category="System", action="export", outcome="Completed")
                    preview.destroy()
                except OSError:
                    self.add("Activity export failed. Check destination access.", action="export", outcome="Failed", severity="Error")
        actions = ttk.Frame(preview, padding=12)
        actions.pack(fill="x")
        ttk.Button(actions, text="Save as…", command=save).pack(side="left")
        ttk.Button(actions, text="Cancel", command=preview.destroy).pack(side="right")
        return preview

    def draw(self):
        self.chart.delete("all")
        if not self.chart_local:
            self.chart.create_text(16, 38, anchor="w", text="Evidence index · complete event volume and rates Unknown", fill=self.palette["header_text"], width=max(150, self.chart.winfo_width() - 32))
            return
        bins = self.chart_bins
        width = max(240, self.chart.winfo_width())
        peak = max(1, *(sum(row.values()) for row in bins))
        minute = self.chart_minute
        self.chart.create_text(12, 14, anchor="w", text=f"Retained local events / minute · scale 0–{peak} · purple Info / amber Warning / red Error", fill=self.palette["header_text"], width=width - 24)
        for i, row in enumerate(bins):
            if minute - 9 + i < self.model.started_at_ns // 60_000_000_000:
                continue
            x, bottom = 12 + i * (width - 24) / 10, 82
            for level, color in (("Info", "#B79ADF"), ("Warning", "#F2BD62"), ("Error", "#F07882")):
                height = row[level] / peak * 43
                if height:
                    self.chart.create_rectangle(x, bottom - height, x + (width - 24) / 10 - 4, bottom, fill=color, outline="")
                bottom -= height
        self.chart.create_text(12, 96, anchor="w", text="−9 min → now · gaps before session start; counts may be truncated by retention", fill=self.palette["header_text"], width=width - 24)

    def destroy(self, event):
        if event.widget is self.root:
            self.closed = True
            if self.timer is not None:
                self.root.after_cancel(self.timer)
                self.timer = None
            self.variables.clear()
            self.search = self.only_attention = None
            self.center = None
