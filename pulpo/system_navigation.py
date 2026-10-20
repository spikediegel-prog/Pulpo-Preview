"""Grouped WSL navigation over unchanged System view names and actions."""
GROUPS = {
    "Monitor": ("Diagnostics", "Source health", "Troubleshooting"),
    "Set up": ("Setup readiness", "Session setup"),
    "Tune": ("Configuration", "Tuning & benchmarks"),
}
LABELS = {"Source health": "Sources", "Troubleshooting": "Troubleshoot",
    "Setup readiness": "Guide & checklist", "Session setup": "Remember setup",
    "Configuration": "Compare settings", "Tuning & benchmarks": "Benchmarks"}


def reflow(frame, buttons, width, maximum=3):
    if not buttons: return
    columns = min(maximum, len(buttons))
    while columns > 1 and any(sum(button.winfo_reqwidth() + 6 for button in buttons[start:start + columns]) > width
            for start in range(0, len(buttons), columns)):
        columns -= 1
    for index, button in enumerate(buttons):
        button.grid(row=index // columns, column=index % columns, sticky="ew", padx=(0, 6), pady=3)
    for column in range(7): frame.columnconfigure(column, weight=1 if column < columns else 0)


class SystemNavigation:
    def __init__(self, parent, select_mode, modes, *, grouped):
        from tkinter import ttk
        self.select_mode, self.grouped = select_mode, grouped
        self.group = None
        self.frame = ttk.Frame(parent)
        self.frame.pack(fill="x", pady=(0, 12))
        self.group_buttons = {}
        self.last_modes = {name: values[0] for name, values in GROUPS.items()} if grouped else {}
        if grouped:
            self.primary = ttk.Frame(self.frame)
            self.primary.pack(fill="x", pady=(0, 3))
            for name in GROUPS:
                self.group_buttons[name] = ttk.Button(self.primary, text=name, command=lambda n=name: self.choose_group(n))
            self.primary.bind("<Configure>", lambda event: reflow(self.primary, list(self.group_buttons.values()), event.width))
        self.secondary = ttk.Frame(self.frame)
        self.secondary.pack(fill="x")
        self.tabs = {mode: ttk.Button(self.secondary, text=LABELS.get(mode, mode) if grouped else mode,
            command=lambda m=mode: select_mode(m)) for mode in modes}
        self.secondary.bind("<Configure>", lambda event: self.layout(event.width))
        self.location = ttk.Label(self.frame, text="", style="Muted.TLabel", justify="left", wraplength=700) if grouped else None
        if self.location is not None:
            self.location.pack(fill="x", pady=(4, 0))
        self.show_mode("Diagnostics")

    def choose_group(self, name):
        if name not in self.last_modes: raise ValueError("Unknown System group")
        self.select_mode(self.last_modes[name])

    def show_mode(self, mode):
        if mode not in self.tabs: raise ValueError("Unknown System view")
        if self.grouped:
            self.group = next(name for name, values in GROUPS.items() if mode in values)
            self.last_modes[self.group] = mode
            for name, button in self.group_buttons.items():
                button.configure(style="Active.Range.TButton" if name == self.group else "TButton")
            self.location.configure(text=f"{self.group} · {mode}")
        for name, button in self.tabs.items():
            button.grid_forget()
            button.configure(style="Active.Range.TButton" if name == mode else "TButton")
        self.layout(self.secondary.winfo_width())

    def layout(self, width):
        if self.grouped:
            visible = [self.tabs[name] for name in GROUPS[self.group]]
            reflow(self.secondary, visible, width)
            self.location.configure(wraplength=max(220, width))
        else:
            # Existing non-WSL three-view layout is retained.
            columns = 2 if width < 600 else 3
            for index, button in enumerate(self.tabs.values()):
                button.grid(row=index // columns, column=index % columns, sticky="ew", padx=(0, 6), pady=3)
            for column in range(3): self.secondary.columnconfigure(column, weight=1 if column < columns else 0)
