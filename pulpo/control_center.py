"""Native presentation only: no service, canonical state or credential access."""
from __future__ import annotations

from pathlib import Path

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
        self.root.geometry("1120x780")
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
        self.text(self.main, "Local performance tools • Live enforcement is not observed", "Muted.TLabel")
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
        if focus:
            self.navigation[name].focus_set()

    def _overview(self):
        page = self.pages["Overview"]
        self.section(page, "Welcome to your local Control Center",
                     "Start with evidence settings and a bounded local check. This window does not connect "
                     "providers, enroll agents or establish deployment authority.")
        self.cards_area = ttk.Frame(page)
        self.cards_area.pack(fill="x", pady=(4, 16))
        self.status_cards = []
        for title, description in (
            ("Connection / Unknown", "No live connection observer. No connection count is measured."),
            ("Enforcement / Unknown", "No deployment enforcement evidence is available to this window."),
        ):
            card = ttk.Frame(self.cards_area, style="Card.TFrame", padding=16)
            labels = [self.text(card, title, "CardHeading.TLabel"),
                      self.text(card, description, "Card.TLabel")]
            self.status_cards.append((card, labels))
        self.text(page, "Connected means reachable. Governed means the exact action follows the canonical "
                  "policy, permit and evidence path. Reachability alone proves no enforcement.")
        self.text(page, "First run: three steps", "Heading.TLabel")
        self.text(page, "1. Open System to inspect this machine and the local profile.\n"
                  "2. Open Evidence to compare settings on disposable fixtures; saving is optional.\n"
                  "3. Review Activity for this session's result and save measurements from Evidence.")
        ttk.Button(page, text="Inspect system", command=lambda: self.show("System")).pack(anchor="w", pady=6)
        ttk.Button(page, text="Open evidence settings", command=lambda: self.show("Evidence")).pack(anchor="w", pady=6)
        self.text(page, "Preview checks do not establish production readiness.", "Status.TLabel")

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
        self.section(page, "Unknown • Enforcement not verified here",
                     "This window has no canonical kernel, state writer, signer or authority-service client. "
                     "It cannot grant, revoke or attest authority.")
        self.section(page, "Evidence required for a governed claim",
                     "Use the deployment's existing authority and evidence path to establish identity, "
                     "policy, exact intent, valid one-use permit and consequence reconciliation. "
                     "A passing local benchmark is not that evidence.")
        self.section(page, "Keep uncertainty visible",
                     "An unknown consequence is not permission to retry. Local tuning success does not "
                     "prove provider containment, credential revocation or host integrity.")

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
        self.append("Recorded: Control Center opened. No checks run and no settings saved.")

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
        page = self.pages["System"]
        self.section(page, "Recorded • Local machine", "\n".join(
            f"{label}: {tuning.machine()[key]}" for label, key in
            (("Platform", "platform"), ("Python", "python"), ("Logical CPUs", "logical_cpus"))))
        self.section(page, "Evidence performance profile", str(self.profile))
        self.profile_label = self.text(page, "")
        ttk.Button(page, text="Refresh local profile status", command=self.refresh_profile).pack(anchor="w", pady=(0, 16))
        self.section(page, "Troubleshooting",
                     "Invalid or stale profile: complete serial collection remains the fallback. "
                     "Check the profile path and access permissions, then use Evidence to save a checked setting.\n\n"
                     "A failed comparison: open Activity, retain the error and verify available disk space "
                     "and temporary-directory access before retrying.\n\n"
                     "Ubuntu window unavailable: install python3-tk for your Python interpreter and use a "
                     "graphical desktop session. Source experiments also require psutil.")
        self.text(page, "Keyboard: Tab / Shift+Tab between controls; Space to activate; Alt+1…6 to change pages; "
                  "Page Up / Page Down to scroll.", "Muted.TLabel")
        self.refresh_profile()

    def refresh_profile(self):
        classification, explanation = profile_observation(self.profile)
        self.profile_label.configure(text=f"{classification} • {explanation}")

    def _resize(self, event):
        if event.widget is not self.main:
            return
        width = max(260, event.width - 72)
        for label in self.labels:
            label.configure(wraplength=width)
        columns = 2 if width >= 650 else 1
        for index, (card, labels) in enumerate(self.status_cards):
            card.grid(row=index // columns, column=index % columns, sticky="nsew", padx=(0, 10), pady=4)
            for label in labels:
                label.configure(wraplength=max(210, width // columns - 42))
        for column in (0, 1):
            self.cards_area.columnconfigure(column, weight=1 if column < columns else 0,
                                            uniform="cards" if column < columns else "")
