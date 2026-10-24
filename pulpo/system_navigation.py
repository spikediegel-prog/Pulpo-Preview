"""Visible, task-named System destinations over the existing view/action keys."""
GROUPS = {
    "System health": ("Diagnostics", "Source health", "Troubleshooting"),
    "Setup & storage": ("Setup readiness", "Session setup"),
    "Appearance": ("Display preferences",),
    "Performance": ("Configuration", "Tuning & benchmarks"),
}
LABELS = {
    "Diagnostics": "System status", "Source health": "Export sources",
    "Troubleshooting": "Troubleshooting", "Setup readiness": "Setup guide",
    "Session setup": "Storage & saved setup", "Display preferences": "Appearance",
    "Configuration": "Performance settings", "Tuning & benchmarks": "Benchmark tools",
}
DESCRIPTIONS = {
    "Diagnostics": "View this machine's resources, installation details and diagnostics.",
    "Source health": "Review selected owner exports, their freshness and missing observations.",
    "Troubleshooting": "Investigate a selected problem and explicitly run an available check.",
    "Setup readiness": "Follow the setup guide or review the observation checklist.",
    "Session setup": "Plan customer evidence storage, acknowledge responsibilities and save startup preferences.",
    "Display preferences": "Choose the theme, text size and spacing.",
    "Configuration": "Compare the current evidence-worker setting with a proposal.",
    "Tuning & benchmarks": "Run a disposable performance comparison before explicitly saving a tested setting.",
}


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
        self.primary = ttk.Frame(self.frame)
        self.primary.pack(fill="x")
        self.sections = {}
        self.tabs = {}
        if grouped:
            for title, members in GROUPS.items():
                visible = [mode for mode in members if mode in modes]
                if not visible: continue
                ttk.Label(self.primary, text=title, style="Muted.TLabel").pack(anchor="w", pady=(6, 0))
                row = ttk.Frame(self.primary)
                row.pack(fill="x")
                self.sections[title] = row
                for mode in visible:
                    self.tabs[mode] = ttk.Button(row, text=LABELS[mode], command=lambda m=mode: select_mode(m))
                row.bind("<Configure>", lambda event: self.layout(event.width))
        else:
            self.sections["System"] = self.primary
            self.tabs = {mode: ttk.Button(self.primary, text=LABELS.get(mode, mode),
                command=lambda m=mode: select_mode(m)) for mode in modes}
            self.primary.bind("<Configure>", lambda event: self.layout(event.width))
        self.location = ttk.Label(self.frame, text="", style="Muted.TLabel", justify="left", wraplength=700)
        self.location.pack(fill="x", pady=(8, 0))
        self.show_mode("Diagnostics")

    def show_mode(self, mode):
        if mode not in self.tabs: raise ValueError("Unknown System view")
        self.group = next((title for title, members in GROUPS.items() if mode in members), "System")
        for name, button in self.tabs.items():
            button.configure(style="Active.Range.TButton" if name == mode else "Overview.TButton")
        self.location.configure(text=f"{LABELS.get(mode, mode)} · {DESCRIPTIONS.get(mode, '')}")
        self.layout(self.primary.winfo_width())

    def layout(self, width):
        for title, row in self.sections.items():
            members = GROUPS[title] if self.grouped else self.tabs
            buttons = [self.tabs[name] for name in members if name in self.tabs]
            reflow(row, buttons, width)
        self.location.configure(wraplength=max(220, width))
