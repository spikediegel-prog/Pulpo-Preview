"""WSL setup checklist over cached source observations and non-secret UI state."""
from .setup_readiness import readiness_items, reviewed_udm_setup
from .source_health_page import SourceHealthPage


class ReadinessPage(SourceHealthPage):
    # Reuse the bounded view's keyboard, visible-only timer and teardown. No new
    # source reader, persistence, provider client or execution control is added.
    def __init__(self, center, page):
        import tkinter as tk
        from tkinter import ttk
        from .control_center_theme import PALETTE
        self.center, self.root = center, center.root
        self.active = self.closed = False
        self.timer = None
        self.rows = ()
        self.guide_visible = False
        modes = ttk.Frame(page)
        modes.pack(fill="x", pady=(0, 10))
        ttk.Button(modes, text="Guided walkthrough", command=self.show_guide).pack(side="left", padx=(0, 6))
        ttk.Button(modes, text="Checklist", command=self.show_checklist).pack(side="left")
        self.checklist = ttk.Frame(page)
        self.checklist.pack(fill="x")
        self.guide_frame = ttk.Frame(page)
        from .setup_walkthrough import SetupWalkthrough
        self.guide = SetupWalkthrough(self, self.guide_frame)
        page = self.checklist
        center.text(page, "Setup Readiness · WSL", "Heading.TLabel")
        center.text(page, "Follow the next step for each observation gap. Recorded means this local setup fact was observed; "
                    "it does not mean enforcement verified. Connector setup is optional.", "Muted.TLabel")
        self.summary = center.text(page, "", "Muted.TLabel")
        ttk.Button(page, text="Update checklist · cached observations", command=self.render).pack(anchor="w", pady=(0, 8))
        area = ttk.Frame(page)
        area.pack(fill="x", pady=(0, 8))
        self.table = ttk.Treeview(area, columns=("step", "state"), show="headings", height=6, selectmode="browse")
        for key, title, width in (("step", "Setup step", 235), ("state", "Observation", 130)):
            self.table.heading(key, text=title)
            self.table.column(key, width=width, minwidth=115)
        self.table.grid(row=0, column=0, sticky="ew")
        scroll = ttk.Scrollbar(area, command=self.table.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.table.configure(yscrollcommand=scroll.set)
        area.columnconfigure(0, weight=1)
        self.table.tag_configure("Needs attention", foreground=PALETTE["error"])
        self.table.tag_configure("Needs setup", foreground=PALETTE["warning"])
        self.table.bind("<<TreeviewSelect>>", lambda event: self.select())
        self.table.bind("<Down>", self.keyboard_start)
        self.table.bind("<Up>", self.keyboard_start)
        center.text(page, "Selected step · evidence, limits and next action", "Heading.TLabel")
        area = ttk.Frame(page)
        area.pack(fill="x", pady=(0, 8))
        self.details = tk.Text(area, height=12, wrap="word", state="disabled", takefocus=True, padx=10, pady=10,
            font=("TkDefaultFont", 10), relief="flat", background=PALETTE["surface"], foreground=PALETTE["text"],
            highlightthickness=1, highlightbackground=PALETTE["border"], highlightcolor=PALETTE["accent"],
            selectbackground=PALETTE["accent"], selectforeground=PALETTE["header_text"])
        self.details.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(area, command=self.details.yview)
        scroll.pack(side="right", fill="y")
        self.details.configure(yscrollcommand=scroll.set)
        self.open_button = ttk.Button(page, text="Open related setup", command=self.open_source, state="disabled")
        self.open_button.pack(anchor="w", pady=(0, 8))
        center.text(page, "No overall Ready verdict or completion score is calculated. Source authenticity, Governance freshness "
                    "and deployed enforcement remain Unknown. No auto-configuration or credential entry is introduced.", "Muted.TLabel")
        self.root.bind("<Destroy>", self.destroy, add="+")
        # SystemPage is still being constructed here. First render happens when
        # the WSL-only view becomes active, after center.system_view is assigned.

    def project(self):
        sources = self.center.system_view.source_health.project()
        return readiness_items(sources, udm_reviewed=reviewed_udm_setup(self.center.connections_view.setup_guide))

    def render(self):
        if self.closed:
            return
        if self.guide_visible:
            self.guide.render()
        old = self.rows
        self.rows = self.project()
        for row in self.rows:
            values = (row.title, row.state)
            if self.table.exists(row.key):
                self.table.item(row.key, values=values, tags=(row.state,))
            else:
                self.table.insert("", "end", iid=row.key, values=values, tags=(row.state,))
        self.summary.configure(text="Core observation setup: Governance metadata + Evidence telemetry. "
            "UDM, NinjaOne and CrowdStrike are optional.\nWSL-local checklist · existing caches only · source files are not re-read here.")
        if self.table.selection() and old != self.rows:
            self.select(preserve=True)
        elif not self.table.selection():
            self.set_details("Select a step to see what is known, what is missing and where to continue. Unknown does not mean offline or denied.")
            self.open_button.configure(state="disabled")

    def select(self, preserve=False):
        if self.closed:
            return
        row = self.selected_row()
        if row:
            position = self.details.index("@0,0") if preserve else "1.0"
            self.set_details(f"{row.title}\n{row.state}\n\n{row.detail}")
            self.details.yview(position)
            self.open_button.configure(state="normal")

    def show_guide(self):
        if self.closed: return
        self.guide.start()
        self.guide_visible = True
        self.checklist.pack_forget()
        self.guide_frame.pack(fill="x")
        self.center.show("System")
        self.center.system_view.select_mode("Setup readiness")
        self.guide.render()

    def show_checklist(self):
        if self.closed: return
        self.guide_visible = False
        self.guide_frame.pack_forget()
        self.checklist.pack(fill="x")
        self.render()
        self.guide.update_banner()

    def open_source(self):
        if self.closed:
            return
        # Reproject before navigation, so an old selection never carries a saved
        # setup result across changed fields. Actions are fixed navigation only.
        self.render()
        row = self.selected_row()
        if not row:
            return
        center = self.center
        if row.action == "diagnostics":
            center.system_view.select_mode("Diagnostics")
        elif row.action in {"governance", "evidence", "connections"}:
            center.show(row.action.capitalize())
        elif row.action == "decisions":
            center.show("Governance")
            center.governance_tabs.select(center.decision_page)
        elif row.action == "udm":
            center.show("Connections")
            center.connections_view.open_setup()
