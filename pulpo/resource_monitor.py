"""Native local resource graphs; session-only, no service or canonical writer."""
from __future__ import annotations

import time

from .local_resources import ResourceHistory, ResourceSampler, level

CHART_COLORS = {"Normal": "#B79ADF", "Elevated": "#F2BD62", "Attention": "#FF929C", "Unknown": "#BBB4C5"}


def capacity_text(metric):
    if metric.used is None or metric.total is None:
        return metric.reason
    return f"{metric.used / 1024**3:.1f} / {metric.total / 1024**3:.1f} GiB used"


class ResourceMonitor:
    def __init__(self, parent, root, on_update):
        import tkinter as tk
        from tkinter import ttk
        self.root, self.on_update = root, on_update
        self.sampler, self.history = ResourceSampler(), ResourceHistory()
        self.seconds = 60
        self.active, self.closed = True, False
        self.timer = None
        self.latest = None
        self.frame = ttk.Frame(parent)
        self.frame.pack(fill="x", pady=(0, 18))
        heading = ttk.Frame(self.frame)
        heading.pack(fill="x", pady=(0, 10))
        heading.columnconfigure(0, weight=1)
        ttk.Label(heading, text="Activity monitor", style="Heading.TLabel").grid(row=0, column=0, sticky="w")
        choices = ttk.Frame(heading)
        choices.grid(row=0, column=1, sticky="e")
        self.choices = choices
        self.range_buttons = {}
        for label, seconds in (("1 min", 60), ("15 min", 900), ("1 hour", 3600)):
            button = ttk.Button(choices, text=label, command=lambda value=seconds: self.set_range(value),
                                style="Range.TButton")
            button.pack(side="left", padx=2)
            self.range_buttons[seconds] = button
        self.area = ttk.Frame(self.frame)
        self.area.pack(fill="x")
        self.panels = {}
        for key, title in (("cpu", "CPU"), ("memory", "Memory"), ("storage", "Storage")):
            panel = tk.Frame(self.area, background="#242329", padx=14, pady=12)
            top = tk.Frame(panel, background="#242329")
            top.pack(fill="x")
            tk.Label(top, text=title, background="#242329", foreground="#E8E5ED",
                     font=("TkDefaultFont", 11)).pack(side="left")
            status = tk.Label(top, text="Unknown", background="#242329", foreground=CHART_COLORS["Unknown"],
                              font=("TkDefaultFont", 10))
            status.pack(side="right")
            value = tk.Label(panel, text="—", background="#242329", foreground="#F5F4F7",
                             font=("TkDefaultFont", 24, "bold"), anchor="w")
            value.pack(fill="x", pady=(8, 0))
            note = tk.Label(panel, text="No observations yet", background="#242329", foreground="#C8C0D2",
                            font=("TkDefaultFont", 10), anchor="w", justify="left", wraplength=220)
            note.pack(fill="x")
            chart = tk.Canvas(panel, height=100, background="#242329", highlightthickness=0)
            chart.pack(fill="x", pady=(8, 0))
            scale = tk.Label(panel, text="0–100%", background="#242329", foreground="#BDB5C9",
                             font=("TkDefaultFont", 9), anchor="w")
            scale.pack(fill="x")
            self.panels[key] = {"frame": panel, "status": status, "value": value, "note": note,
                                "chart": chart, "scale": scale}
            chart.bind("<Configure>", lambda event, name=key: self.draw(name))
        self.caption = ttk.Label(self.frame, text=f"Source: {self.sampler.source} · volume {self.sampler.volume} · collecting observations",
                                 style="Muted.TLabel", wraplength=740, justify="left")
        self.caption.pack(fill="x", pady=(9, 0))
        self.area.bind("<Configure>", self._resize)
        root.bind("<Destroy>", self._destroy, add="+")
        root.bind("<Map>", self._mapped, add="+")
        self.set_range(60)
        self._schedule(0)

    def _schedule(self, delay):
        if self.closed:
            return
        if self.timer is not None:
            self.root.after_cancel(self.timer)
        self.timer = self.root.after(delay, self._tick)

    def _mapped(self, event):
        if event.widget is self.root and self.active:
            self._schedule(0)

    def _destroy(self, event):
        if event.widget is self.root:
            self.closed = True
            if self.timer is not None:
                self.root.after_cancel(self.timer)
                self.timer = None

    def set_active(self, active):
        if self.closed:
            return
        if self.active != active:
            self.sampler.previous_cpu = None
        self.active = active
        self._schedule(0 if active else 10000)

    def _tick(self):
        self.timer = None
        if self.closed:
            return
        if not self.active or not self.root.winfo_viewable() or self.root.state() == "iconic":
            self.sampler.previous_cpu = None
            self.caption.configure(text=f"Source: {self.sampler.source} · monitoring paused while Overview is hidden")
            self._schedule(10000)
            return
        self.latest = self.sampler.sample()
        self.history.append(self.latest)
        for name, panel in self.panels.items():
            metric = getattr(self.latest, name)
            status = level(metric.percent)
            panel["status"].configure(text=("! " if status in ("Elevated", "Attention") else "") + status,
                                      foreground=CHART_COLORS[status])
            panel["value"].configure(text="—" if metric.percent is None else f"{metric.percent:.1f}%")
            note = ("Observed counter interval" if name == "cpu" and metric.percent is not None else
                    capacity_text(metric) if name != "cpu" else metric.reason)
            panel["note"].configure(text=note)
        stamp = time.strftime("%H:%M:%S %Z", time.localtime(self.latest.observed_at))
        collected = int(self.latest.monotonic_time - self.history.samples[0].monotonic_time)
        scope = " · Linux VM view, not the full Windows host" if "WSL" in self.latest.source else ""
        self.caption.configure(text=f"Recorded locally · {self.latest.source} · volume {self.latest.volume} · updated {stamp}{scope}\n"
                               f"{collected}s of session history. Purple: normal · amber: ≥75% · red: ≥90%. Missing readings remain gaps.")
        self.on_update(self.latest)
        self.draw_all()
        self._schedule(2000)

    def set_range(self, seconds):
        if seconds not in (60, 900, 3600):
            raise ValueError("Unsupported resource time range")
        self.seconds = seconds
        for value, button in self.range_buttons.items():
            button.configure(style="Active.Range.TButton" if value == seconds else "Range.TButton")
        self.draw_all()

    def _resize(self, event):
        columns = 3 if event.width >= 720 else 1
        if columns == 1:
            self.choices.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        else:
            self.choices.grid(row=0, column=1, columnspan=1, sticky="e", pady=0)
        for index, panel in enumerate(self.panels.values()):
            panel["frame"].grid(row=index // columns, column=index % columns, sticky="nsew",
                                padx=(0, 10 if index % columns < columns - 1 else 0), pady=(0, 8))
            panel["note"].configure(wraplength=max(200, event.width // columns - 40))
        for column in range(3):
            self.area.columnconfigure(column, weight=1 if column < columns else 0,
                                      uniform="resource" if column < columns else "")
        self.caption.configure(wraplength=max(240, event.width))

    def draw_all(self):
        for name in self.panels:
            self.draw(name)

    def draw(self, name):
        chart = self.panels[name]["chart"]
        width, height = max(1, chart.winfo_width()), 100
        chart.delete("all")
        for value in (25, 50, 75):
            y = height - 6 - value / 100 * (height - 12)
            chart.create_line(2, y, width - 2, y, fill="#3A363F")
        now = time.monotonic()
        points = self.history.points(name, self.seconds, now)
        if not points or not any(value is not None for _, value in points):
            chart.create_text(width / 2, height / 2, text="No observations yet" if not points else "Reading unavailable",
                              fill="#C8C0D2", font=("TkDefaultFont", 10))
        previous = None
        for observed, value in points:
            if value is None:
                previous = None
                continue
            x = 3 + (observed - (now - self.seconds)) / self.seconds * max(1, width - 6)
            y = height - 6 - value / 100 * (height - 12)
            if previous is not None and observed - previous[2] <= 5:
                chart.create_line(previous[0], previous[1], x, y,
                                  fill=CHART_COLORS[level(max(value, previous[3]))], width=2)
            previous = x, y, observed, value
        if previous:
            x, y, _, value = previous
            chart.create_oval(x - 2, y - 2, x + 2, y + 2, fill=CHART_COLORS[level(value)], outline="")
        duration = {60: "1 min", 900: "15 min", 3600: "1 hour"}[self.seconds]
        units = "capacity used" if name == "storage" else "used" if name == "memory" else "utilization"
        self.panels[name]["scale"].configure(text=f"0–100% {units}     {duration} → now")
