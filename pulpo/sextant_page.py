"""Read-only Sextant workload status presentation."""
import time

from .control_center_theme import PALETTE, surface
from .sextant_observation import replay


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
        self.demo_observation = None
        page = center.pages["Sextant"]

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
            text="Unknown · Workload source unavailable",
            style="HeaderTitle.TLabel",
            wraplength=760,
        )
        self.summary.pack(anchor="w", fill="x")
        self.summary_detail = ttk.Label(
            summary,
            text="No reviewed, known-correct workload outcomes or comparable workload baseline are present.",
            style="HeaderMuted.TLabel",
            wraplength=760,
        )
        self.summary_detail.pack(anchor="w", fill="x", pady=(5, 0))

        demo_controls = ttk.Frame(page)
        demo_controls.pack(fill="x", pady=(0, 10))
        self.demo_button = ttk.Button(
            demo_controls, text="Run synthetic demo", command=self.run_synthetic_demo,
        )
        self.demo_button.pack(side="left", padx=(0, 8))
        self.clear_demo_button = ttk.Button(
            demo_controls, text="Clear demo", command=self.clear_synthetic_demo, state="disabled",
        )
        self.clear_demo_button.pack(side="left")

        metric_shadow, metric_border = surface(page)
        metric_shadow.pack(fill="x", pady=(0, 10))
        metrics = ttk.Frame(metric_border, style="Card.TFrame", padding=(14, 12))
        metrics.pack(fill="both", expand=True)
        self.metrics = metrics
        self.metric_columns = []
        self.metric_labels = {}
        self.metric_values = {}
        self.metric_details = {}
        for column, (key, title, explanation) in enumerate((
            ("drift", "Calibrated drift", "Unknown · No workload/model series, comparable baseline or calibrated threshold."),
            ("accuracy", "Accuracy", "Unknown · No reviewed, known-correct outcomes or eligible sample count."),
        )):
            metric = ttk.Frame(metrics, style="Card.TFrame")
            metric.grid(row=0, column=column * 2, sticky="nsew",
                        padx=(0, 14) if column == 0 else (14, 0))
            self.metric_columns.append(metric)
            self.metric_labels[key] = ttk.Label(
                metric, text=f"{title} · Unknown", style="CardHeading.TLabel", anchor="center",
            )
            self.metric_labels[key].pack(fill="x")
            self.metric_values[key] = ttk.Label(
                metric,
                text="Unknown",
                style="CardValue.TLabel",
                anchor="center",
            )
            self.metric_values[key].pack(fill="x", pady=(4, 0))
            self.metric_details[key] = ttk.Label(
                metric, text=explanation, style="Card.TLabel",
                justify="center", anchor="center", wraplength=380,
            )
            self.metric_details[key].pack(fill="x", pady=(2, 0))
        self.metric_separator = ttk.Separator(metrics, orient="vertical")
        self.metric_separator.grid(row=0, column=1, sticky="ns")
        metrics.columnconfigure(0, weight=1, uniform="metric")
        metrics.columnconfigure(1, weight=0)
        metrics.columnconfigure(2, weight=1, uniform="metric")
        metrics.bind("<Configure>", self.reflow_metric_cards)

        center.text(page, "Deviation from reference", "Heading.TLabel")
        center.text(
            page,
            "The outer rails move symmetrically with deviation; the signed value shows direction. Synthetic scenario only.",
            "Muted.TLabel",
        )
        self.graphs = ttk.Frame(page)
        self.graphs.pack(fill="x", pady=(6, 10))
        self.graph_cards = []
        self.graph_canvases = {}
        self.graph_titles = {}
        for key, title in (
            ("latency", "Latency drift from calibrated zero"),
            ("accuracy", "Accuracy deviation from target"),
        ):
            graph_shadow, graph_border = surface(self.graphs)
            graph_shadow.grid(row=0, column=len(self.graph_cards), sticky="nsew",
                              padx=(0, 8) if not self.graph_cards else (0, 0))
            graph_card = ttk.Frame(graph_border, style="Card.TFrame", padding=(10, 8))
            graph_card.pack(fill="both", expand=True)
            self.graph_titles[key] = ttk.Label(
                graph_card, text=title, style="CardHeading.TLabel", anchor="center",
            )
            self.graph_titles[key].pack(fill="x")
            canvas = tk.Canvas(
                graph_card, height=160, highlightthickness=0,
                background=PALETTE["surface"],
            )
            canvas.pack(fill="both", expand=True, pady=(4, 0))
            canvas.bind("<Configure>", lambda _event: self.draw_synthetic_graphs())
            self.graph_cards.append(graph_shadow)
            self.graph_canvases[key] = canvas
        self.graphs.columnconfigure(0, weight=1)
        self.graphs.columnconfigure(1, weight=1)
        self.graphs.bind("<Configure>", self.reflow_synthetic_graphs)

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
            ("time", "Time (UTC)", 145),
            ("workload", "Workload version", 150),
            ("model", "Model version", 150),
            ("observation", "Metric / value", 190),
            ("outcome", "Generated label", 120),
        ):
            self.events.heading(key, text=title)
            self.events.column(key, width=width, minwidth=70, stretch=True)
        self.events.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.events.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.events.configure(yscrollcommand=scrollbar.set)
        self.events.bind("<<TreeviewSelect>>", self.show_selected_event)
        list_frame.columnconfigure(0, weight=1)
        self.empty = center.text(page, "", "Muted.TLabel")

        center.text(page, "Selected observation details", "Heading.TLabel")
        details_frame = ttk.Frame(page)
        details_frame.pack(fill="x", pady=(0, 10))
        self.details = tk.Text(
            details_frame, height=6, wrap="word", state="disabled", padx=10, pady=10,
            background=PALETTE["surface"], foreground=PALETTE["text"],
            font=("TkDefaultFont", 10),
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
            "Without the synthetic scenario, no workload event counts are available. Demo bars count generated events only—not production evidence, accuracy or drift.",
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

    def run_synthetic_demo(self):
        from .sextant_demo import build_synthetic_observation

        self.demo_observation = build_synthetic_observation()
        self.clear_demo_button.configure(state="normal")
        self.last_display_refresh_ns = time.time_ns()
        self.render()

    def clear_synthetic_demo(self):
        self.demo_observation = None
        self.clear_demo_button.configure(state="disabled")
        self.render()

    def reflow_synthetic_graphs(self, event):
        stacked = event.width < 700
        for index, card in enumerate(self.graph_cards):
            card.grid(
                row=index if stacked else 0,
                column=0 if stacked else index,
                sticky="nsew",
                padx=(0, 0 if stacked or index else 8),
                pady=(0, 8) if stacked and index == 0 else (0, 0),
            )

    def reflow_metric_cards(self, event):
        stacked = event.width < 700
        for index, metric in enumerate(self.metric_columns):
            metric.grid_configure(
                row=index * 2 if stacked else 0,
                column=0 if stacked else index * 2,
                padx=(0, 0) if stacked else ((0, 14) if index == 0 else (14, 0)),
                pady=(0, 10) if stacked and index == 0 else (0, 0),
            )
        self.metric_separator.configure(orient="horizontal" if stacked else "vertical")
        self.metric_separator.grid_configure(
            row=1 if stacked else 0,
            column=0 if stacked else 1,
            sticky="ew" if stacked else "ns",
            pady=(0, 10) if stacked else (0, 0),
        )

    def draw_synthetic_graphs(self):
        latency_canvas = self.graph_canvases["latency"]
        latency_canvas.delete("all")
        accuracy_canvas = self.graph_canvases["accuracy"]
        accuracy_canvas.delete("all")
        if self.demo_observation is None:
            for canvas in (latency_canvas, accuracy_canvas):
                canvas.create_text(
                    max(1, canvas.winfo_width()) / 2,
                    max(1, canvas.winfo_height()) / 2,
                    text="Run synthetic demo to display generated data",
                    fill=PALETTE["muted"],
                    font=("TkDefaultFont", 9),
                )
            return

        result = replay(self.demo_observation)
        drift = result.drift
        drift_percent = (
            0.0 if drift.observed_mean is None or drift.baseline_mean == 0
            else (drift.observed_mean - drift.baseline_mean) / abs(drift.baseline_mean) * 100
        )
        self._draw_deviation_gauge(
            latency_canvas,
            drift_percent,
            scale=50,
            unit="%",
            zero_label="CALIBRATED ZERO",
            annotation=f"Synthetic latency is {drift_percent:+.1f}% vs calibrated baseline",
        )

        accuracy = result.accuracy
        accuracy_target_percent = 95.0
        accuracy_delta = (
            accuracy.accuracy * 100 - accuracy_target_percent
            if accuracy.accuracy is not None
            else 0.0
        )
        self._draw_deviation_gauge(
            accuracy_canvas,
            accuracy_delta,
            scale=50,
            unit=" pp",
            zero_label=f"{accuracy_target_percent:.0f}% TARGET",
            annotation=(
                f"Synthetic accuracy is {accuracy_delta:+.0f} pp vs "
                f"{accuracy_target_percent:.0f}% target"
                if accuracy.accuracy is not None
                else "Synthetic accuracy unavailable · no reviewed labels"
            ),
        )

    @staticmethod
    def _draw_deviation_gauge(canvas, deviation, *, scale, unit, zero_label, annotation):
        width, height = max(1, canvas.winfo_width()), max(1, canvas.winfo_height())
        left, right = 42, max(43, width - 42)
        center = (left + right) / 2
        center_y, top, bottom = height / 2 + 5, 42, height - 28
        canvas.create_text(
            width / 2, 13, text=annotation, fill=PALETTE["text"],
            font=("TkDefaultFont", 9, "bold"),
        )
        canvas.create_line(left, center_y, right, center_y, fill=PALETTE["border"], width=2)
        canvas.create_line(center, top, center, bottom, fill=PALETTE["text"], width=2)
        canvas.create_text(
            center, bottom + 11, text=zero_label,
            fill=PALETTE["text"], font=("TkDefaultFont", 8, "bold"),
        )
        canvas.create_text(
            left, bottom + 11, anchor="w", text=f"−{scale:g}{unit}",
            fill=PALETTE["muted"], font=("TkDefaultFont", 8),
        )
        canvas.create_text(
            right, bottom + 11, anchor="e", text=f"+{scale:g}{unit}",
            fill=PALETTE["muted"], font=("TkDefaultFont", 8),
        )

        extent = min(abs(deviation), scale) / scale * (right - center)
        for x, label in (
            (center - extent, f"−{abs(deviation):.1f}{unit}"),
            (center + extent, f"+{abs(deviation):.1f}{unit}"),
        ):
            canvas.create_line(x, top, x, bottom, fill=PALETTE["accent"], width=3)
            canvas.create_text(
                x, top - 8, text=label, fill=PALETTE["accent"],
                font=("TkDefaultFont", 8, "bold"),
            )

    def draw_histogram(self):
        canvas = self.histogram
        canvas.delete("all")
        width, height = max(1, canvas.winfo_width()), max(1, canvas.winfo_height())
        axis_y = height - 23
        canvas.create_line(12, axis_y, width - 12, axis_y, fill=PALETTE["chart_muted"])
        if self.demo_observation is None:
            for fraction in (0, .25, .5, .75, 1):
                x = 12 + fraction * max(1, width - 24)
                canvas.create_line(x, axis_y - 4, x, axis_y + 4, fill=PALETTE["chart_muted"])
            canvas.create_text(
                width / 2, max(24, axis_y / 2),
                text=f"No workload evidence counts · {self.period}",
                fill=PALETTE["header_text"], font=("TkDefaultFont", 10),
            )
            canvas.create_text(
                12, height - 7, anchor="w", text="Earlier",
                fill=PALETTE["chart_muted"], font=("TkDefaultFont", 8),
            )
            canvas.create_text(
                width - 12, height - 7, anchor="e", text="Most recent",
                fill=PALETTE["chart_muted"], font=("TkDefaultFont", 8),
            )
            return

        day_ns = 24 * 60 * 60 * 1_000_000_000
        window_ns, bucket_count = {
            "24 hours": (day_ns, 12),
            "Week": (7 * day_ns, 7),
            "Month": (30 * day_ns, 6),
        }[self.period]
        bucket_ns = window_ns // bucket_count
        counts = [0] * bucket_count
        observed_at = self.demo_observation.observed_at_ns
        for event in self.demo_observation.events:
            age = observed_at - event.timestamp_ns
            if 0 <= age < window_ns:
                index = bucket_count - 1 - age // bucket_ns
                counts[index] += 1
        left, right = 18, max(19, width - 18)
        slot = max(1, (right - left) / bucket_count)
        maximum = max(counts, default=0)
        for index, count in enumerate(counts):
            x = left + index * slot + slot * .18
            bar_width = max(1, slot * .64)
            bar_height = (count / maximum) * max(1, axis_y - 34) if maximum else 0
            if count:
                canvas.create_rectangle(
                    x, axis_y - bar_height, x + bar_width, axis_y,
                    fill=PALETTE["accent"], outline="",
                )
                canvas.create_text(
                    x + bar_width / 2, axis_y - bar_height - 7,
                    text=str(count), fill=PALETTE["chart_muted"],
                    font=("TkDefaultFont", 8),
                )
        canvas.create_text(
            left, height - 7, anchor="w", text="Earlier",
            fill=PALETTE["chart_muted"], font=("TkDefaultFont", 8),
        )
        canvas.create_text(
            right, height - 7, anchor="e", text="Most recent",
            fill=PALETTE["chart_muted"], font=("TkDefaultFont", 8),
        )
        canvas.create_text(
            width / 2, 14,
            text=f"Synthetic event counts · {self.period} · {sum(counts)} events",
            fill=PALETTE["header_text"], font=("TkDefaultFont", 10),
        )

    def render(self):
        if self.closed:
            return
        if self.demo_observation is None:
            self.render_empty()
        else:
            self.render_synthetic_demo()
        self.draw_synthetic_graphs()
        updated = time.strftime(
            "%Y-%m-%d %H:%M:%S %Z", time.localtime(self.last_display_refresh_ns / 1e9),
        )
        freshness_label = " · display refresh paused" if self.paused else ""
        self.updated.configure(text=f"Display last refreshed locally: {updated}{freshness_label}")
        self.draw_histogram()

    def render_empty(self):
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
        self.summary.configure(text="Unknown · Workload source unavailable")
        self.summary_detail.configure(
            text="No reviewed, known-correct workload outcomes or comparable workload baseline are present."
        )
        self.source_summary.configure(text=source)
        self.metric_labels["accuracy"].configure(text="Accuracy · Unknown")
        self.metric_values["accuracy"].configure(text="Unknown")
        self.metric_details["accuracy"].configure(
            text="Unknown · No reviewed, known-correct outcomes or eligible sample count."
        )
        self.metric_labels["drift"].configure(text="Calibrated drift · Unknown")
        self.metric_values["drift"].configure(text="Unknown", foreground=PALETTE["accent"])
        self.metric_details["drift"].configure(
            text="Unknown · No workload/model series, comparable baseline or calibrated threshold."
        )
        for details in self.metric_details.values():
            if not details.winfo_manager():
                details.pack(anchor="w", fill="x", pady=(2, 0))
        for item in self.events.get_children():
            self.events.delete(item)
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

    def render_synthetic_demo(self):
        observation = self.demo_observation
        result = replay(observation)
        self.summary.configure(
            text=f"SIMULATION ONLY · Synthetic · {result.drift.status}"
        )
        self.summary_detail.configure(
            text="All values below are generated for demonstration; no real workload or correctness review occurred."
        )
        self.source_summary.configure(
            text=(
                "Proposed · Deterministic synthetic values held in memory. No real workload, model, "
                "service, or inference ran; generated labels and references are not evidence. "
                "No canonical Pulpo state was read or changed by this demo."
            )
        )
        accuracy = result.accuracy
        self.metric_labels["accuracy"].configure(text="Accuracy")
        if accuracy.accuracy is None:
            self.metric_values["accuracy"].configure(text="Unknown")
            accuracy_detail = "Synthetic scenario contains no reviewed outcomes."
        else:
            self.metric_values["accuracy"].configure(text=f"{accuracy.accuracy:.0%}")
            accuracy_detail = (
                f"{accuracy.correct_count} / {accuracy.reviewed_sample_count} generated labels · "
                f"Wilson 95% CI {accuracy.wilson_95_low:.0%}–{accuracy.wilson_95_high:.0%}"
            )
        self.metric_details["accuracy"].configure(text=accuracy_detail)
        for details in self.metric_details.values():
            details.pack_forget()
        drift = result.drift
        self.metric_labels["drift"].configure(text=f"Latency drift · {drift.status}")
        self.metric_values["drift"].configure(
            foreground=PALETTE["warning"] if drift.status == "Investigate" else PALETTE["accent"]
        )
        score = (
            "unavailable"
            if drift.standardized_delta is None
            else f"{drift.standardized_delta:.2f}"
        )
        drift_percent = (
            0.0 if drift.observed_mean is None or drift.baseline_mean == 0
            else (drift.observed_mean - drift.baseline_mean) / abs(drift.baseline_mean) * 100
        )
        self.metric_values["drift"].configure(text=f"{drift_percent:+.1f}%")
        self.metric_details["drift"].configure(
            text=(
                f"{drift.observed_mean:.1f} ms mean vs {drift.baseline_mean:.1f} ms baseline · "
                f"z = {score} ({drift.investigate_z_threshold:.1f} threshold) · "
                f"{drift.sample_count} samples"
            )
        )
        for item in self.events.get_children():
            self.events.delete(item)
        for event in observation.events:
            timestamp = time.strftime(
                "%Y-%m-%d %H:%M:%S UTC", time.gmtime(event.timestamp_ns / 1e9),
            )
            if event.reviewed_correct is None:
                outcome = "Synthetic: unreviewed"
            else:
                outcome = f"Synthetic: {'correct' if event.reviewed_correct else 'incorrect'}"
            self.events.insert(
                "", "end", iid=str(event.sequence),
                values=(
                    timestamp,
                    event.workload_version,
                    event.model_version,
                    f"{event.metric_id}: {event.metric_value:.1f}",
                    outcome,
                ),
            )
        self.empty.configure(text="SIMULATION ONLY · Generated scenario events; no real workload ran.")
        detail = (
            "SIMULATION ONLY · Select a row to inspect one generated sample.\n\n"
            f"Synthetic scenario: {observation.calibration.workload_id}; "
            f"{len(observation.events)} generated samples. Freshness is not measured: "
            "timestamps belong to the generated demo, not a workload source. "
            "Synthetic checkpoint/evidence references are placeholders, not evidence or attestations."
        )
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", detail)
        self.details.configure(state="disabled")

    def show_selected_event(self, _event=None):
        if self.demo_observation is None:
            return
        selected = self.events.selection()
        if not selected:
            return
        sequence = int(selected[0])
        event = self.demo_observation.events[sequence - self.demo_observation.first_sequence]
        outcome = (
            "unreviewed"
            if event.reviewed_correct is None
            else "synthetically labeled correct"
            if event.reviewed_correct
            else "synthetically labeled incorrect"
        )
        detail = (
            f"SIMULATION ONLY · Generated sample {event.sequence}\n"
            f"Workload: {event.workload_id} ({event.workload_version})\n"
            f"Model: {event.model_version}\n"
            f"Synthetic metric: {event.metric_id} = {event.metric_value:.1f}\n"
            f"Generated outcome label: {outcome}\n"
            f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(event.timestamp_ns / 1e9))}\n\n"
            "No real workload ran; these generated values, labels, and references are not evidence."
        )
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", detail)
        self.details.configure(state="disabled")

    def destroy(self, event):
        if event.widget is self.root:
            self.closed = True
            self.schedule()
            self.cadence = None
            self.center = None
