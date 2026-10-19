"""Native presentation only: no service, canonical state or credential access."""
from __future__ import annotations

from pathlib import Path
import time

from . import evidence_tuning as tuning


PALETTE = {
    "sidebar": "#242329", "sidebar_text": "#E8E5ED",
    "background": "#F5F4F7", "surface": "#FDFCFD",
    "text": "#29262F", "muted": "#615B6B", "accent": "#674396",
    "selected": "#EAE3F2", "warning": "#865200", "error": "#A32935",
}
PAGES = ("Overview", "Connections", "Governance", "Activity", "Evidence", "System")


def profile_observation(profile):
    """Explain the existing resolver's fallback, without writing or repairing."""
    try:
        document = tuning._read_profile(Path(profile))
        return "Recorded", f"Saved choice: {document['settings']['workers']} evidence workers."
    except FileNotFoundError:
        return "Unknown", "No saved profile. Complete serial collection is the default."
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        return "Unknown", ("Profile unavailable, invalid or stale. Complete serial fallback is active. "
                           "Recheck the path and permissions, then explicitly save a validated setting.")


class StatusRow:
    """Expandable text-first state; gradient positions are discrete, not scores."""
    def __init__(self, parent, name, detail, open_page):
        self.name, self.state, self.expanded = name, "Unknown", False
        self.frame = ttk.Frame(parent, style="Card.TFrame", padding=(12, 10))
        self.frame.pack(fill="x", pady=(0, 2))
        self.header = ttk.Frame(self.frame, style="Card.TFrame")
        self.header.pack(fill="x")
        self.header.columnconfigure(2, weight=1)
        self.button = ttk.Button(self.header, text="▸ " + name, style="Row.TButton", width=13, command=self.toggle)
        self.button.grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.bar = tk.Canvas(self.header, width=140, height=23, highlightthickness=0, background=PALETTE["surface"])
        self.bar.grid(row=0, column=1, padx=(0, 14))
        self.summary = ttk.Label(self.header, text="Unknown · No observations", style="Card.TLabel",
                                 justify="left", wraplength=470)
        self.summary.grid(row=0, column=2, sticky="ew")
        self.body = ttk.Frame(self.frame, style="Card.TFrame", padding=(8, 10))
        self.detail = ttk.Label(self.body, text=detail, style="Card.TLabel", justify="left", wraplength=720)
        self.detail.pack(fill="x")
        if open_page is not None:
            ttk.Button(self.body, text=f"Open {name.lower()}", command=open_page).pack(anchor="w", pady=(10, 0))
        self.bar.bind("<Configure>", lambda event: self.draw())
        self.frame.bind("<Configure>", self._resize)

    def toggle(self):
        self.expanded = not self.expanded
        self.button.configure(text=("▾ " if self.expanded else "▸ ") + self.name)
        if self.expanded:
            self.body.pack(fill="x")
        else:
            self.body.pack_forget()

    def update(self, state, summary, detail=None):
        if state not in ("Unknown", "Normal", "Elevated", "Attention"):
            raise ValueError("Unsupported status state")
        self.state = state
        self.summary.configure(text=summary)
        if detail is not None:
            self.detail.configure(text=detail)
        self.draw()

    def draw(self):
        self.bar.delete("all")
        width = max(1, self.bar.winfo_width())
        if self.state == "Unknown":
            self.bar.create_rectangle(0, 8, width, 15, fill="#DED9E5", outline="")
            return
        stops = ((195, 70, 86), (210, 149, 53), (37, 132, 93))
        for x in range(width):
            position = x / max(1, width - 1) * 2
            left = min(1, int(position))
            mix = position - left
            color = "#" + "".join(f"{int(a + (b - a) * mix):02x}" for a, b in zip(stops[left], stops[left + 1]))
            self.bar.create_line(x, 8, x, 15, fill=color)
        marker = {"Attention": .05, "Elevated": .5, "Normal": .95}[self.state] * width
        self.bar.create_rectangle(marker - 3, 3, marker + 3, 20, fill=PALETTE["text"], outline=PALETTE["surface"], width=2)

    def _resize(self, event):
        narrow = event.width < 650
        if narrow:
            self.summary.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(7, 0))
        else:
            self.summary.grid(row=0, column=2, columnspan=1, sticky="ew", pady=0)
        self.summary.configure(wraplength=max(220, event.width - (35 if narrow else 340)))
        self.detail.configure(wraplength=max(220, event.width - 50))


class ControlCenter:
    """A lightweight shell around the existing local tuning actions."""

    def __init__(self, root, profile):
        # Keep profile diagnostics importable on CLI-only Ubuntu installations.
        global tk, ttk
        import tkinter as tk
        from tkinter import ttk
        self.root, self.profile = root, Path(profile)
        self.labels = []
        self.current = None
        self.root.title("Pulpo Control Center — Preview")
        self.root.geometry("1200x900")
        self.root.minsize(640, 600)
        self.root.configure(background=PALETTE["background"])
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background=PALETTE["background"])
        style.configure("TLabel", background=PALETTE["background"],
                        foreground=PALETTE["text"], font=("TkDefaultFont", 11))
        style.configure("TButton", padding=(10, 8), font=("TkDefaultFont", 10))
        style.configure("TButton", background=PALETTE["surface"], foreground=PALETTE["accent"],
                        bordercolor="#D7D1DF", focuscolor=PALETTE["accent"], borderwidth=1)
        style.map("TButton", foreground=[("disabled", PALETTE["muted"])],
                  background=[("active", PALETTE["selected"])])
        style.configure("Nav.TButton", background=PALETTE["sidebar"],
                        foreground=PALETTE["sidebar_text"], anchor="w", borderwidth=0)
        style.map("Nav.TButton", background=[("pressed", PALETTE["accent"]),
                  ("active", PALETTE["accent"])], foreground=[("active", "#FFFFFF")])
        style.configure("Selected.Nav.TButton", background=PALETTE["accent"], foreground="#FFFFFF")
        style.configure("Title.TLabel", font=("TkDefaultFont", 22, "bold"))
        style.configure("Heading.TLabel", font=("TkDefaultFont", 13, "bold"))
        style.configure("Muted.TLabel", foreground=PALETTE["muted"])
        style.configure("Status.TLabel", foreground=PALETTE["warning"])
        style.configure("TRadiobutton", background=PALETTE["background"], foreground=PALETTE["text"],
                        font=("TkDefaultFont", 10))
        style.configure("Card.TFrame", background=PALETTE["surface"])
        style.configure("Card.TLabel", background=PALETTE["surface"])
        style.configure("CardHeading.TLabel", background=PALETTE["surface"], font=("TkDefaultFont", 13, "bold"))
        style.configure("Range.TButton", padding=(6, 4), font=("TkDefaultFont", 9))
        style.configure("Active.Range.TButton", padding=(6, 4), font=("TkDefaultFont", 9), background=PALETTE["selected"])
        style.configure("Row.TButton", background=PALETTE["surface"], foreground=PALETTE["text"],
                        anchor="w", borderwidth=0, padding=(0, 4), font=("TkDefaultFont", 11, "bold"))

        self.sidebar = tk.Frame(root, background=PALETTE["sidebar"], padx=12, pady=20)
        self.sidebar.pack(side="left", fill="y")
        tk.Label(self.sidebar, text="PULPO", foreground="#FFFFFF", background=PALETTE["sidebar"],
                 font=("TkDefaultFont", 19, "bold"), anchor="w").pack(fill="x", pady=(0, 2))
        tk.Label(self.sidebar, text="CONTROL CENTER\nPreview • Local window", justify="left",
                 foreground=PALETTE["sidebar_text"], background=PALETTE["sidebar"],
                 font=("TkDefaultFont", 9)).pack(anchor="w", pady=(0, 24))
        self.navigation = {}
        for number, name in enumerate(PAGES, 1):
            button = ttk.Button(self.sidebar, text=name, style="Nav.TButton",
                                command=lambda page=name: self.show(page), takefocus=True)
            button.pack(fill="x", pady=3)
            self.navigation[name] = button
            root.bind(f"<Alt-Key-{number}>", lambda event, page=name: self.show(page, focus=True))
        tk.Label(self.sidebar, text="Intelligence proposes.\nGovernance disposes.", justify="left",
                 foreground=PALETTE["sidebar_text"], background=PALETTE["sidebar"],
                 font=("TkDefaultFont", 9)).pack(side="bottom", anchor="w", pady=12)

        self.main = ttk.Frame(root, padding=(24, 20))
        self.main.pack(fill="both", expand=True)
        self.page_title = ttk.Label(self.main, style="Title.TLabel")
        self.page_title.pack(anchor="w")
        self.text(self.main, "Local resource observations • Live enforcement is not observed", "Muted.TLabel")
        viewport = ttk.Frame(self.main)
        viewport.pack(fill="both", expand=True, pady=(16, 0))
        self.canvas = tk.Canvas(viewport, background=PALETTE["background"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(viewport, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(fill="both", expand=True)
        self.container = ttk.Frame(self.canvas)
        item = self.canvas.create_window(0, 0, anchor="nw", window=self.container)
        self.canvas.bind("<Configure>", lambda event: self.canvas.itemconfigure(item, width=event.width))
        self.container.bind("<Configure>", lambda event: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        root.bind("<Next>", lambda event: self.canvas.yview_scroll(1, "pages"))
        root.bind("<Prior>", lambda event: self.canvas.yview_scroll(-1, "pages"))
        self.pages = {name: ttk.Frame(self.container) for name in PAGES}
        self._overview()
        self._connections()
        self._governance()
        from .evidence_page import EvidencePage
        self.evidence_view = EvidencePage(self)
        self._activity()
        self._system()
        self.show("Overview")
        self.main.bind("<Configure>", self._resize, add="+")

    def text(self, parent, value, style="TLabel"):
        label = ttk.Label(parent, text=value, style=style, wraplength=700, justify="left")
        label.pack(fill="x", anchor="w", pady=(0, 10))
        self.labels.append(label)
        return label

    def section(self, parent, heading, body):
        self.text(parent, heading, "Heading.TLabel")
        return self.text(parent, body)

    def show(self, name, focus=False):
        if name not in self.pages:
            raise ValueError("Unknown Control Center page")
        for page in self.pages.values():
            page.pack_forget()
        self.pages[name].pack(fill="both", expand=True)
        self.page_title.configure(text=name)
        for key, button in self.navigation.items():
            button.configure(style="Selected.Nav.TButton" if key == name else "Nav.TButton")
        self.current = name
        self.canvas.yview_moveto(0)
        if hasattr(self, "monitor"):
            self.monitor.set_active(name == "Overview")
        if hasattr(self, "evidence_view"):
            self.evidence_view.set_active(name == "Evidence")
        if hasattr(self, "system_view"):
            self.system_view.set_active(name == "System")
        if focus:
            self.navigation[name].focus_set()

    def _overview(self):
        page = self.pages["Overview"]
        from .resource_monitor import ResourceMonitor
        self.monitor = ResourceMonitor(page, self.root, self._resource_update)
        heading = ttk.Frame(page)
        heading.pack(fill="x", pady=(0, 10))
        self.status_heading = heading
        heading.columnconfigure(0, weight=1)
        ttk.Label(heading, text="Operational status", style="Heading.TLabel").grid(row=0, column=0, sticky="w")
        self.attention = ttk.Label(heading, text="No enforcement assessment", style="Muted.TLabel")
        self.attention.grid(row=0, column=1, sticky="e")
        self.status_rows = {}
        for name, detail in (
            ("Connections", "Unknown. No live connection observer is configured. No reachability or connection count is inferred from resource readings."),
            ("Governance", "Unknown. This UI has no authoritative deployment enforcement evidence. A reachable service, normal CPU or a successful local comparison proves no enforcement."),
            ("Evidence", "Unknown. No canonical audit or deployment-report observer is configured. Activity contains local session messages; comparison results cover disposable fixtures only."),
            ("System", "Unknown. Waiting for local resource observations. Resource thresholds are attention hints, not deployment health or authority verification."),
        ):
            row = StatusRow(page, name, detail, lambda target=name: self.show(target))
            self.status_rows[name] = row
        self.status_rows["Connections"].update("Unknown", "Unknown · No connection observer configured")
        self.status_rows["Governance"].update("Unknown", "Unknown · Enforcement not assessed")
        self.status_rows["Evidence"].update("Unknown", "Unknown · No canonical report observer")
        self.text(page, "Red: action required · amber: review · green: scoped checks passed · gray: unknown.\n"
                  "Discrete states, not a health score. Connected does not mean enforcement verified.", "Muted.TLabel")
        self.onboarding = ttk.Frame(page)
        self.onboarding.pack(fill="x", pady=(8, 0))
        self.text(self.onboarding, "First run: inspect System, compare disposable fixtures in Evidence, then review Activity. "
                  "Saving a performance setting is optional. Preview checks do not establish production readiness.", "Muted.TLabel")

    def _resource_update(self, sample):
        from .local_resources import level
        metrics = [sample.cpu, sample.memory, sample.storage]
        states = [level(metric.percent) for metric in metrics]
        issues = [name for name, state in zip(("CPU", "Memory", "Storage"), states) if state in ("Elevated", "Attention")]
        if "Attention" in states:
            state, summary = "Attention", "! Resource attention required: " + ", ".join(issues)
        elif "Elevated" in states:
            state, summary = "Elevated", "! Elevated resource usage: " + ", ".join(issues)
        elif "Unknown" in states:
            state, summary = "Unknown", "Unknown · Some resource readings are unavailable"
        else:
            state, summary = "Normal", "Recorded · Resource readings within thresholds"
        stamp = time.strftime("%H:%M:%S %Z", time.localtime(sample.observed_at))
        self.status_rows["System"].update(state, summary,
            f"Recorded from {sample.source} at {stamp}. Storage is volume {sample.volume}; capacity used is separate from disk I/O. "
            "Elevated begins at 75%; attention begins at 90%. These are resource hints only. "
            "No diagnostics, connection or deployment-enforcement pass is inferred.\n\n"
            + "\n".join(f"{name}: {metric.reason or f'{metric.percent:.1f}%'}" for name, metric in
                          zip(("CPU", "Memory", "Storage"), metrics)))
        self.attention.configure(text=(f"{len(issues)} resource item(s) need attention" if issues else
                                      "Resource readings incomplete · enforcement unknown" if "Unknown" in states else
                                      "No resource alerts · enforcement unknown"))

    def _connections(self):
        page = self.pages["Connections"]
        self.section(page, "Unknown • No live observer",
                     "This release provides local tuning, not provider discovery or connection management. "
                     "No endpoint, account or credential is read by this page.")
        self.section(page, "When a connection fails",
                     "Check the intended deployment's service status and endpoint, then its network and "
                     "authentication configuration using that deployment's tools. Keep private keys and "
                     "tokens out of screenshots and shared logs.")
        self.section(page, "A successful connection is only reachability",
                     "Verify the action's policy, permit binding, expiry, replay rejection and evidence "
                     "through the canonical deployment before claiming governed execution.")
        ttk.Button(page, text="Review governance boundary", command=lambda: self.show("Governance")).pack(anchor="w")

    def _governance(self):
        page = self.pages["Governance"]
        from .governance_observer import GovernanceObservation
        self.governance_path = None
        self.governance_status = self.text(page, "", "Heading.TLabel")
        self.text(page, "Read-only observation • Connected does not mean governed. "
                  "This window cannot approve, grant, revoke or execute.", "Muted.TLabel")
        controls = ttk.Frame(page)
        controls.pack(fill="x", pady=(0, 12))
        ttk.Button(controls, text="Select snapshot…", command=self.select_governance_snapshot).pack(side="left")
        self.governance_refresh = ttk.Button(controls, text="Re-read", state="disabled",
                                             command=self.refresh_governance)
        self.governance_refresh.pack(side="left", padx=6)
        ttk.Button(controls, text="Clear", command=self.clear_governance).pack(side="left")
        self.governance_source = self.text(page, "", "Muted.TLabel")
        self.governance_fields = {}
        self.governance_rows = {}
        for name, title in (("policy", "Policy"), ("decisions", "Decisions"), ("integrity", "Audit integrity")):
            row = StatusRow(page, title, "", None)
            self.governance_rows[name] = row
            self.governance_fields[name] = row.detail
        self.text(page, "Expand a row for its evidence and limitations. Gray means Unknown; "
                  "red means a reported problem needs attention.", "Muted.TLabel")
        self.section(page, "Connect an observation source",
                     "Select a frozen read snapshot exported by your trusted Pulpo process "
                     "(pulpo.mcp-read-snapshot.v0 JSON). Do not select a state database, credential or raw audit file. "
                     "Selection stays in this session. On Ubuntu the export must be readable only by its owner.")
        self.section(page, "What needs further evidence",
                     "Deployment identity, current rules and grants, human authority, individual decisions, "
                     "permits, execution evidence and unresolved consequences remain Unknown. "
                     "Unknown consequences never authorize retry.")
        self._render_governance(GovernanceObservation())

    def select_governance_snapshot(self):
        from tkinter import filedialog
        selected = filedialog.askopenfilename(parent=self.root, title="Select frozen Pulpo read snapshot",
                                              filetypes=(("JSON snapshot", "*.json"),))
        if selected:
            self.governance_path = Path(selected)
            self.governance_refresh.configure(state="normal")
            self.refresh_governance()

    def refresh_governance(self):
        from .governance_observer import observe_snapshot
        if self.governance_path is not None:
            self._render_governance(observe_snapshot(self.governance_path))

    def clear_governance(self):
        from .governance_observer import GovernanceObservation
        self.governance_path = None
        self.governance_refresh.configure(state="disabled")
        self._render_governance(GovernanceObservation())

    def _render_governance(self, observation):
        self.governance_status.configure(text=observation.summary,
                                         foreground=PALETTE["error"] if observation.state == "Attention" else PALETTE["muted"])
        location = f"Selected file: {self.governance_path}\n" if self.governance_path else ""
        self.governance_source.configure(text=location + observation.source)
        summaries = {"policy": "Unknown · No policy observation", "decisions": "Unknown · Decision records unavailable",
                     "integrity": "Unknown · No audit observation"}
        if observation.policy.startswith("Recorded"):
            summaries["policy"] = "Recorded · Source-reported fingerprint"
            summaries["integrity"] = ("Attention · Source reports audit check FAILED" if observation.state == "Attention"
                                       else "Recorded · Source reports audit check passed")
        for name, row in self.governance_rows.items():
            state = "Attention" if name == "integrity" and observation.state == "Attention" else "Unknown"
            row.update(state, summaries[name], getattr(observation, name))
        self.status_rows["Governance"].update(observation.state, observation.summary,
                                               "Enforcement remains unassessed. " + observation.source)

    def _activity(self):
        page = self.pages["Activity"]
        self.text(page, "Session activity", "Heading.TLabel")
        self.text(page, "Messages from this window only. Not the canonical audit journal; cleared on exit.", "Muted.TLabel")
        area = ttk.Frame(page)
        area.pack(fill="both", expand=True)
        self.output = tk.Text(area, height=8, wrap="word", state="disabled", padx=12, pady=12,
                              font=("TkDefaultFont", 11), background=PALETTE["surface"],
                              foreground=PALETTE["text"], takefocus=True)
        scroll = ttk.Scrollbar(area, command=self.output.yview)
        self.output.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.output.pack(fill="both", expand=True)
        self.append("Recorded: Control Center opened. No fixture checks run and no settings saved. Resource observations stay in this session.")

    def append(self, message):
        self.output.configure(state="normal")
        self.output.insert("end", message + "\n\n")
        # Keep the UI bounded; the canonical evidence source is never this buffer.
        lines = int(self.output.index("end-1c").split(".")[0])
        if lines > 500:
            self.output.delete("1.0", f"{lines - 500}.0")
        self.output.see("end")
        self.output.configure(state="disabled")

    def _system(self):
        from .system_page import SystemPage
        self.system_view = SystemPage(self)

    def refresh_profile(self):
        classification, explanation = profile_observation(self.profile)
        self.profile_label.configure(text=f"{classification} • {explanation}")

    def _resize(self, event):
        if event.widget is not self.main:
            return
        width = max(260, event.width - 72)
        for label in self.labels:
            label.configure(wraplength=width)
        if width < 650:
            self.attention.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        else:
            self.attention.grid(row=0, column=1, columnspan=1, sticky="e", pady=0)
