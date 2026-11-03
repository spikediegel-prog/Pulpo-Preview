"""Read-only Sextant workload status presentation."""
import time

from .control_center_theme import PALETTE, surface


REFRESH_INTERVALS = {
    "Off": None,
    "30 seconds": 30,
    "1 minute": 60,
    "5 minutes": 300,
}
PERIODS = ("24 hours", "Week", "Month")


class SextantPage:
    def __init__(self, center):
        import tkinter as tk
        from tkinter import ttk

        self.center, self.root = center, center.root
        self.active = False
        self.paused = False
        self.closed = False
        self.timer = None
        self.interval_seconds = 30
        self.period = PERIODS[0]
        self.last_display_refresh_ns = time.time_ns()
        page = center.pages["Sextant"]

        center.text(page, "Sextant", "Heading.TLabel")
        center.text(
            page,
            "Read-only workload signals. Drift and correlations are investigation signals, not proof of cause. "
            "Statistical change is not cryptographic verification or correctness.",
            "Muted.TLabel",
        )

        shadow, border = surface(page, dark=True)
        shadow.pack(fill="x", pady=(0, 10))
        summary = ttk.Frame(border, style="Header.TFrame", padding=(14, 12))
        summary.pack(fill="both", expand=True)
        self.summary = ttk.Label(
            summary,
            text="Unknown · No workload-specific observation source is available",
            style="HeaderTitle.TLabel",
            wraplength=760,
        )
        self.summary.pack(anchor="w", fill="x")
        ttk.Label(
            summary,
            text="No reviewed, known-correct workload outcomes or comparable workload baseline are present.",
            style="HeaderMuted.TLabel",
            wraplength=760,
        ).pack(anchor="w", fill="x", pady=(5, 0))

        metrics = ttk.Frame(page)
        metrics.pack(fill="x", pady=(0, 10))
        self.metric_labels = {}
        self.metric_details = {}
        for column, (key, title, explanation) in enumerate((
            ("accuracy", "Accuracy", "Unknown · No reviewed, known-correct outcomes or eligible sample count."),
            ("drift", "Calibrated drift", "Unknown · No workload/model series, comparable baseline or calibrated threshold."),
        )):
            card_shadow, card_border = surface(metrics)
            card_shadow.grid(row=0, column=column, sticky="nsew", padx=(0, 8) if column == 0 else (0, 0))
            card = ttk.Frame(card_border, style="Card.TFrame", padding=(12, 10))
            card.pack(fill="both", expand=True)
            self.metric_labels[key] = ttk.Label(card, text=f"{title} · Unknown", style="CardHeading.TLabel")
            self.metric_labels[key].pack(anchor="w", fill="x")
            self.metric_details[key] = ttk.Label(card, text=explanation, style="Card.TLabel",
                                                  justify="left", wraplength=380)
            self.metric_details[key].pack(anchor="w", fill="x", pady=(6, 0))
        metrics.columnconfigure(0, weight=1)
        metrics.columnconfigure(1, weight=1)

        source_shadow, source_border = surface(page)
        source_shadow.pack(fill="x", pady=(0, 10))
        source = ttk.Frame(source_border, style="Card.TFrame", padding=(12, 10))
        source.pack(fill="both", expand=True)
        ttk.Label(source, text="Available evidence source · separate from workload outcomes",
                  style="CardHeading.TLabel").pack(anchor="w")
        self.source_summary = ttk.Label(source, text="", style="Card.TLabel", justify="left", wraplength=760)
        self.source_summary.pack(anchor="w", fill="x", pady=(5, 0))

        controls = ttk.Frame(page)
        controls.pack(fill="x", pady=(0, 10))
        self.pause_button = ttk.Button(controls, text="Pause auto-refresh", command=self.toggle_pause)
        self.pause_button.grid(row=0, column=0, sticky="w", padx=(0, 8), pady=3)
        self.refresh_button = ttk.Button(controls, text="Refresh available evidence", command=self.refresh)
        self.refresh_button.grid(row=0, column=1, sticky="w", padx=(0, 8), pady=3)
        self.cadence_label = ttk.Label(controls, text="Cadence")
        self.cadence_label.grid(row=0, column=2, sticky="e", padx=(8, 4))
        self.cadence = tk.StringVar(master=self.root, value="30 seconds")
        self.cadence_box = ttk.Combobox(
            controls, textvariable=self.cadence, values=tuple(REFRESH_INTERVALS),
            state="readonly", width=13,
        )
        self.cadence_box.grid(row=0, column=3, sticky="w", pady=3)
        self.cadence_box.bind("<<ComboboxSelected>>", self.set_cadence)
        controls.columnconfigure(4, weight=1)
        controls.bind("<Configure>", self.reflow_controls)
        self.updated = center.text(page, "", "Muted.TLabel")

        center.text(page, "Workload observations", "Heading.TLabel")
        center.text(
            page,
            "The existing Pulpo evidence snapshot is not workload-scoped, so its governance events are not shown here as workload events.",
            "Muted.TLabel",
        )
        list_frame = ttk.Frame(page)
        list_frame.pack(fill="x", pady=(0, 8))
        self.events = ttk.Treeview(
            list_frame,
            columns=("time", "workload", "model", "observation", "outcome"),
            show="headings",
            height=5,
            selectmode="browse",
        )
        for key, title, width in (
            ("time", "Time", 145),
            ("workload", "Workload version", 150),
            ("model", "Model version", 150),
            ("observation", "Observation", 190),
            ("outcome", "Outcome", 120),
        ):
            self.events.heading(key, text=title)
            self.events.column(key, width=width, minwidth=70, stretch=True)
        self.events.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.events.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.events.configure(yscrollcommand=scrollbar.set)
        list_frame.columnconfigure(0, weight=1)
        self.empty = center.text(page, "", "Muted.TLabel")

        center.text(page, "Selected observation details", "Heading.TLabel")
        details_frame = ttk.Frame(page)
        details_frame.pack(fill="x", pady=(0, 10))
        self.details = tk.Text(
            details_frame, height=6, wrap="word", state="disabled", padx=10, pady=10,
            background=PALETTE["surface"], foreground=PALETTE["text"],
            relief="flat", highlightthickness=1, highlightbackground=PALETTE["border"],
            highlightcolor=PALETTE["accent"],
        )
        self.details.pack(side="left", fill="both", expand=True)
        details_scroll = ttk.Scrollbar(details_frame, command=self.details.yview)
        details_scroll.pack(side="right", fill="y")
        self.details.configure(yscrollcommand=details_scroll.set)

        center.text(page, "Workload evidence counts · separate from metric trends", "Heading.TLabel")
        period_controls = ttk.Frame(page)
        period_controls.pack(fill="x", pady=(0, 4))
        self.period_buttons = {}
        for index, period in enumerate(PERIODS):
            button = ttk.Button(
                period_controls, text=period, style="Range.TButton",
                command=lambda selected=period: self.select_period(selected),
            )
            button.grid(row=0, column=index, padx=(0, 5))
            self.period_buttons[period] = button
        chart_shadow, chart_border = surface(page, dark=True)
        chart_shadow.pack(fill="x", pady=(0, 8))
        self.histogram = tk.Canvas(
            chart_border, height=105, highlightthickness=0, background=PALETTE["chart"],
        )
        self.histogram.pack(fill="x", padx=10, pady=8)
        self.histogram.bind("<Configure>", lambda event: self.draw_histogram())
        self.draw_histogram()

        center.text(
            page,
            "No workload event counts are available for any period. Bars, when a workload-scoped source exists, represent evidence counts only—not accuracy or drift values.",
            "Muted.TLabel",
        )
        self.root.bind("<Destroy>", self.destroy, add="+")
        self.render()

    def set_active(self, active):
        self.active = active
        self.schedule()
        self.render()

    def reflow_controls(self, event):
        if event.width < 600:
            self.pause_button.grid(row=0, column=0, columnspan=2, sticky="w", padx=0)
            self.refresh_button.grid(row=1, column=0, columnspan=2, sticky="w", padx=0)
            self.cadence_label.grid(row=2, column=0, sticky="w", padx=0)
            self.cadence_box.grid(row=2, column=1, sticky="w", pady=3)
        else:
            self.pause_button.grid(row=0, column=0, columnspan=1, sticky="w", padx=(0, 8))
            self.refresh_button.grid(row=0, column=1, columnspan=1, sticky="w", padx=(0, 8))
            self.cadence_label.grid(row=0, column=2, sticky="e", padx=(8, 4))
            self.cadence_box.grid(row=0, column=3, sticky="w", pady=3)

    def set_cadence(self, _event=None):
        selected = self.cadence.get()
        if selected not in REFRESH_INTERVALS:
            raise ValueError("Unsupported Sextant refresh cadence")
        self.interval_seconds = REFRESH_INTERVALS[selected]
        self.schedule()

    def toggle_pause(self):
        self.paused = not self.paused
        self.pause_button.configure(text="Resume auto-refresh" if self.paused else "Pause auto-refresh")
        self.schedule()

    def refresh(self):
        if self.closed:
            return
        evidence = self.center.evidence_view
        if evidence.path is not None:
            evidence.refresh()
        self.last_display_refresh_ns = time.time_ns()
        self.render()
        self.schedule()

    def schedule(self):
        if self.timer is not None:
            self.root.after_cancel(self.timer)
            self.timer = None
        if self.active and not self.paused and not self.closed and self.interval_seconds is not None:
            self.timer = self.root.after(self.interval_seconds * 1000, self.tick)

    def tick(self):
        self.timer = None
        if self.active and not self.paused and not self.closed:
            self.refresh()

    def select_period(self, period):
        if period not in PERIODS:
            raise ValueError("Unsupported Sextant period")
        self.period = period
        for name, button in self.period_buttons.items():
            button.configure(style="Active.Range.TButton" if name == period else "Range.TButton")
        self.draw_histogram()

    def draw_histogram(self):
        canvas = self.histogram
        canvas.delete("all")
        width, height = max(1, canvas.winfo_width()), max(1, canvas.winfo_height())
        axis_y = height - 23
        canvas.create_line(12, axis_y, width - 12, axis_y, fill=PALETTE["chart_muted"])
        for fraction in (0, .25, .5, .75, 1):
            x = 12 + fraction * max(1, width - 24)
            canvas.create_line(x, axis_y - 4, x, axis_y + 4, fill=PALETTE["chart_muted"])
        canvas.create_text(
            width / 2, max(24, axis_y / 2),
            text=f"No workload evidence counts · {self.period}",
            fill=PALETTE["header_text"], font=("TkDefaultFont", 10),
        )

    def render(self):
        if self.closed:
            return
        evidence = self.center.evidence_view
        snapshot = evidence.snapshot
        if evidence.error:
            source = (
                "Attention · The selected general evidence observation could not be read. "
                "Workload accuracy, drift, versions, baselines and sample counts remain Unknown."
            )
        elif snapshot is None:
            source = (
                "Unknown · No general evidence observation selected. No workload-specific source or "
                "workload outcome observations are integrated."
            )
        else:
            from .evidence_observation import freshness
            age = freshness(snapshot)
            stamp = time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime(snapshot.observed_at_ns / 1e9))
            source = (
                f"Recorded · General Pulpo evidence snapshot: {age}; source timestamp {stamp}; "
                f"{snapshot.audit_records:,} source-reported audit records and {len(snapshot.events)} "
                "redacted event references (maximum 24). This schema has no workload/model identity, "
                "known-correct outcomes or workload baseline; these counts do not populate the monitor."
            )
        self.source_summary.configure(text=source)
        self.empty.configure(text="No workload events in the available observations.")
        detail = (
            "No workload observation is selected. Workload/model versions, evaluated sample count, "
            "reviewed correctness labels, baseline, calibrated threshold, checkpoint and evidence detail are Unknown.\n\n"
            "Accuracy is not computed without known-correct reviewed outcomes. Drift is not computed without "
            "a comparable workload baseline and calibrated threshold. Source events and statistical signals "
            "do not establish cause, correctness or cryptographic verification."
        )
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", detail)
        self.details.configure(state="disabled")
        updated = time.strftime(
            "%Y-%m-%d %H:%M:%S %Z", time.localtime(self.last_display_refresh_ns / 1e9),
        )
        freshness_label = " · display refresh paused" if self.paused else ""
        self.updated.configure(text=f"Display last refreshed locally: {updated}{freshness_label}")
        self.draw_histogram()

    def destroy(self, event):
        if event.widget is self.root:
            self.closed = True
            self.schedule()
            self.cadence = None
            self.center = None
