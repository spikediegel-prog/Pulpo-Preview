"""Compact WSL resource presentation; age refreshes use cached samples only."""
import math
import time

from .control_center_theme import PALETTE


def duration(seconds):
    if not math.isfinite(seconds) or seconds < 0: return "Unknown"
    hours, remainder = divmod(int(seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return (f"{hours}h {minutes}m {seconds}s" if hours else f"{minutes}m {seconds}s" if minutes else f"{seconds}s")


def status_text(sample, first_at, *, now=None, paused=False):
    if sample is None: return "WSL resources · Awaiting readings · History unknown"
    age = (time.monotonic() if now is None else now) - sample.monotonic_time
    updated = "Update time unknown" if not math.isfinite(age) or age < 0 else "Updated just now" if age < 1 else f"Updated {duration(age)} ago"
    history = duration(sample.monotonic_time - first_at) if first_at is not None else "Unknown"
    return f"WSL resources · {'Paused · ' if paused else ''}{updated} · {history} history"


class ResourceStatus:
    def __init__(self, parent, root):
        from tkinter import ttk
        self.root = root
        self.sample = self.first_at = self.timer = None
        self.active = self.closed = self.expanded = False
        self.frame = ttk.Frame(parent)
        self.frame.pack(fill="x", pady=(9, 0))
        self.summary = ttk.Label(self.frame, text=status_text(None, None), style="Muted.TLabel", justify="left", wraplength=700)
        self.button = ttk.Button(self.frame, text="Details", style="Range.TButton", command=self.toggle)
        self.legend = ttk.Frame(self.frame)
        self.labels = []
        for text, color in (("● Normal", "accent"), ("● Elevated", "warning"), ("● High", "error"), ("● Unknown", "muted")):
            self.labels.append(ttk.Label(self.legend, text=text, foreground=PALETTE[color], font=("TkDefaultFont", 10)))
        self.details = ttk.Label(self.frame, text="Awaiting a local resource sample. Missing readings remain Unknown.",
            style="Muted.TLabel", wraplength=700, justify="left")
        self.frame.bind("<Configure>", lambda event: self.layout(event.width))
        root.bind("<Destroy>", self.destroy, add="+")
        root.bind("<Unmap>", self.unmap, add="+")

    def layout(self, width):
        narrow = width < 600
        legend_columns = 2 if narrow else 4
        legend_width = sum(max(label.winfo_reqwidth() for label in self.labels[column::legend_columns]) + 12
            for column in range(legend_columns))
        stacked_button = narrow and legend_width + self.button.winfo_reqwidth() + 8 > width
        self.summary.grid(row=0, column=0, columnspan=2 if narrow else 1, sticky="ew", pady=(0, 4))
        self.summary.configure(wraplength=max(220, width - (0 if narrow else self.button.winfo_reqwidth() + 12)))
        self.button.grid(row=2 if stacked_button else 1 if narrow else 0, column=0 if stacked_button else 1,
            columnspan=2 if stacked_button else 1, sticky="w" if stacked_button else "ne", padx=(0 if stacked_button else 8, 0), pady=(4 if stacked_button else 0, 0))
        self.legend.grid(row=1, column=0, columnspan=1 if narrow and not stacked_button else 2, sticky="w")
        for index, label in enumerate(self.labels):
            label.grid(row=index // legend_columns, column=index % legend_columns, sticky="w", padx=(0, 12), pady=2)
        self.frame.columnconfigure(0, weight=1)
        self.details.configure(wraplength=max(220, width))
        if self.expanded: self.details.grid(row=3 if stacked_button else 2, column=0, columnspan=2, sticky="ew", pady=(8, 0))

    def update(self, sample, first_at):
        self.sample, self.first_at = sample, first_at
        self.render()

    def render(self):
        if self.closed: return
        self.summary.configure(text=status_text(self.sample, self.first_at, paused=not self.active))
        if self.sample is not None:
            sample = self.sample
            stamp = time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime(sample.observed_at))
            self.details.configure(text=f"Recorded locally at {stamp}. Source: {sample.source} · volume {sample.volume}.\n"
                "Linux VM readings; the full Windows host, fleet and deployed enforcement are not assessed.\n"
                "Normal: below 75% · Elevated: 75% to below 90% · High: 90% or more (Attention in status rows). "
                "Color always accompanies a text label. Missing/invalid readings stay Unknown and appear as graph gaps.\n"
                "History is the retained session sample span, including possible gaps; it is not service uptime or proof of continuous coverage. "
                "These are resource hints, not health or governance verification.")

    def toggle(self):
        if self.closed: return
        self.expanded = not self.expanded
        self.button.configure(text="Hide details" if self.expanded else "Details")
        if not self.expanded: self.details.grid_forget()
        self.layout(self.frame.winfo_width())

    def set_active(self, active):
        if self.closed: return
        if self.timer is not None:
            self.root.after_cancel(self.timer)
            self.timer = None
        self.active = active
        self.render()
        if active and self.root.winfo_viewable() and self.root.state() != "iconic":
            self.timer = self.root.after(1000, self.tick)

    def tick(self):
        self.timer = None
        if not self.closed:
            self.set_active(self.active and self.root.winfo_viewable() and self.root.state() != "iconic")

    def unmap(self, event):
        if event.widget is self.root: self.set_active(False)

    def destroy(self, event):
        if event.widget is self.root:
            if self.timer is not None:
                self.root.after_cancel(self.timer)
                self.timer = None
            self.active = False
            self.closed = True
            self.sample = self.first_at = None
