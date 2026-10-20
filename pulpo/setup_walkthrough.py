"""Session-local WSL guide: fixed navigation over existing observation controls."""
from .decision_explorer import record_time


STEPS = (
    ("Understand the observations",
     "Control Center shows local WSL resource readings and selected owner exports. Recorded describes a local read or source-reported fact. "
     "Unknown means the required evidence is missing. Connected, a passing benchmark and a completed guide do not mean governed or enforcement verified. "
     "This walkthrough never approves, executes, repairs or changes permissions.", ()),
    ("Select Governance and Evidence exports",
     "Open each source page and use its existing Select control for a sanitized export from your trusted Pulpo owner. "
     "Do not select a state database, raw audit log or credential. Selection uses the existing validated reader; remembered locations require explicit Re-read. "
     "Return here to review the observed result. You can continue with gaps; they remain Unknown.",
     (("Open Governance", "Governance"), ("Open Evidence", "Evidence"))),
    ("Choose optional connections",
     "UniFi UDM, NinjaOne and CrowdStrike are optional. Open Connections to select an existing trusted-owner observation or review Guided UDM setup. "
     "API keys, private certificates and provider logins stay outside Control Center. Skipping this step does not disconnect a provider or remove a selection.",
     (("Open Connections", "Connections"),)),
    ("Check observations and investigate gaps",
     "Open Troubleshooting, select a row and explicitly run an available check. Its existing reader re-reads only the selected owner export. "
     "Review cause, impact, local check time, source timestamp and next step. Re-reading an old export does not make it fresh. "
     "Live service health remains Unknown without an observation contract; there is no automatic repair or bulk check.",
     (("Open Troubleshooting", "Troubleshooting"),)),
    ("Optionally remember your setup",
     "Review Session setup if you want to remember export locations, graph ranges and startup choices. Press Remember this setup there to save explicitly. "
     "The guide does not save anything. Restored sources start Not checked this session; credentials, results and authority are not remembered. "
     "You can return to Overview with remaining gaps; reaching this step is not an overall Ready or governed verdict.",
     (("Review Session setup", "Session setup"),)),
)


class SetupWalkthrough:
    def __init__(self, readiness, page):
        from tkinter import ttk
        self.readiness, self.center, self.root = readiness, readiness.center, readiness.root
        self.index = 0
        self.active = self.closed = self.skipped_connectors = False
        center = self.center
        center.text(page, "Guided setup · WSL", "Heading.TLabel")
        self.progress = center.text(page, "", "Muted.TLabel")
        self.title = center.text(page, "", "Heading.TLabel")
        self.explanation = center.text(page, "")
        self.observed = center.text(page, "", "Muted.TLabel")
        self.actions = ttk.Frame(page)
        self.actions.pack(fill="x", pady=(0, 10))
        self.action_buttons = []
        self.skip_button = ttk.Button(page, text="Skip optional connections", command=self.skip_connections)
        navigation = ttk.Frame(page)
        navigation.pack(fill="x", pady=(0, 10))
        self.previous_button = ttk.Button(navigation, text="Previous step", command=lambda: self.go_to(self.index - 1))
        self.previous_button.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=3)
        self.next_button = ttk.Button(navigation, text="Next step", command=self.advance)
        self.next_button.grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Button(navigation, text="Close guide", command=self.close).grid(row=1, column=0, columnspan=2, sticky="ew", pady=3)
        for col in (0, 1): navigation.columnconfigure(col, weight=1)
        center.text(page, "Step numbers show your place in the guide, not a readiness score. "
            "Use Return to guide while visiting source pages. Guide position is session-only; no completion record is saved.", "Muted.TLabel")
        self.banner = ttk.Frame(center.main)
        self.banner_label = ttk.Label(self.banner, text="", style="Muted.TLabel", wraplength=700, justify="left")
        self.banner_label.pack(fill="x")
        center.labels.append(self.banner_label)
        buttons = ttk.Frame(self.banner)
        buttons.pack(fill="x", pady=(4, 0))
        self.return_button = ttk.Button(buttons, text="Return to guide", command=readiness.show_guide)
        self.return_button.pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="Close guide", command=self.close).pack(side="left")
        self.root.bind("<Destroy>", self.destroy, add="+")

    def start(self):
        if self.closed: return
        if not self.active:
            self.index, self.skipped_connectors = 0, False
        self.active = True

    def go_to(self, index):
        if self.closed: return
        if type(index) is not int or not 0 <= index < len(STEPS):
            raise ValueError("unsupported_guide_step")
        self.index = index
        self.render()
        self.center.canvas.yview_moveto(0)

    def advance(self):
        if self.closed: return
        if self.index == len(STEPS) - 1:
            self.close()
            self.center.show("Overview")
        else: self.go_to(self.index + 1)

    def skip_connections(self):
        if not self.closed and self.index == 2:
            self.skipped_connectors = True
            self.go_to(3)

    def observations(self):
        if self.index == 0:
            return "No source is required to explore this window. Missing exports are setup gaps, not proof of an outage or denial."
        if self.index == 4:
            return "Optional persistence is separate from current observations. This guide does not inspect whether a saved preferences file exists."
        if self.index == 3:
            rows = self.center.system_view.troubleshooting.project()
            return "Current cached checks · no check runs when this guide renders\n" + "\n".join(f"{row.title}: {row.state}" for row in rows)
        sources = self.center.system_view.source_health.project()
        keys = {"Governance", "Evidence"} if self.index == 1 else {"UniFi UDM", "NinjaOne", "CrowdStrike"}
        lines = []
        if self.index == 2 and self.skipped_connectors:
            lines.append("You skipped optional connection setup earlier in this guide. Existing selections were preserved.")
        for row in sources:
            if row.key in keys:
                checked = record_time(row.read.recorded_at_ns) if row.read else "Unknown"
                lines.append(f"{row.key}\nLocal read: {row.read_status} · completion time: {checked}\nSource freshness: {row.freshness}")
        return "\n\n".join(lines) + "\n\nThese are existing cached observations, not source authenticity or enforcement checks."

    def render(self):
        if self.closed: return
        title, explanation, actions = STEPS[self.index]
        self.progress.configure(text=f"Step {self.index + 1} of {len(STEPS)} · navigation position only")
        self.title.configure(text=title)
        self.explanation.configure(text=explanation)
        self.observed.configure(text=self.observations())
        # Rebuild only on a step change, preserving keyboard focus during cache updates.
        if getattr(self, "rendered_index", None) != self.index:
            for button in self.action_buttons: button.destroy()
            self.action_buttons = []
            from tkinter import ttk
            for label, target in actions:
                button = ttk.Button(self.actions, text=label, command=lambda t=target: self.open_action(t))
                button.pack(fill="x", pady=3)
                self.action_buttons.append(button)
            self.rendered_index = self.index
        if self.index == 2:
            self.skip_button.pack(fill="x", before=self.actions, pady=(0, 8))
        else: self.skip_button.pack_forget()
        self.previous_button.configure(state="disabled" if self.index == 0 else "normal")
        self.next_button.configure(text="Return to overview" if self.index == 4 else "Next step")
        self.update_banner()

    def open_action(self, target):
        if self.closed: return
        if target not in {action[1] for action in STEPS[self.index][2]}:
            raise ValueError("unsupported_guide_navigation")
        if target in {"Troubleshooting", "Session setup"}:
            self.center.system_view.select_mode(target)
        else: self.center.show(target)

    def update_banner(self):
        if self.closed: return
        button = getattr(self.center, "setup_guide_button", None)
        if button is not None:
            button.configure(text="Resume guided setup" if self.active else "Start guided setup")
        if not self.active:
            self.banner.pack_forget()
            return
        system = self.center.system_view
        inside = self.center.current == "System" and system.mode == "Setup readiness" and self.readiness.guide_visible
        if inside: self.banner.pack_forget()
        else:
            self.banner_label.configure(text=f"Setup guide · Step {self.index + 1} of {len(STEPS)} · {STEPS[self.index][0]}")
            self.banner.pack(fill="x", before=self.center.canvas.master, pady=(8, 0))

    def close(self):
        if self.closed: return
        self.active = False
        self.readiness.show_checklist()
        self.update_banner()

    def destroy(self, event):
        if event.widget is self.root:
            self.closed = True
            self.active = False
            self.center = self.readiness = None
