"""WSL-only troubleshooting; explicit existing reads, previewed safe report."""
import time

from .source_health_page import SourceHealthPage
from .troubleshooting import findings, stamp, support_report


class TroubleshootingPage(SourceHealthPage):
    def __init__(self, system, page):
        import tkinter as tk
        from tkinter import ttk
        from .control_center_theme import PALETTE
        self.system, self.center, self.root = system, system.center, system.root
        self.active = self.closed = False
        self.timer = None
        self.rows = ()
        self.local_checked_at_ns = None
        self.preview = None
        center = self.center
        center.text(page, "Troubleshooting · WSL", "Heading.TLabel")
        center.text(page, "Select an observation for its cause, impact and next step. Checks re-read only already selected owner exports. "
            "No network probes, service discovery, restarts or repairs. Unknown is an evidence gap, not an outage.", "Muted.TLabel")
        self.summary = center.text(page, "", "Muted.TLabel")
        self.table = ttk.Treeview(page, columns=("check", "state"), show="headings", height=9, selectmode="browse")
        for key, title, width in (("check", "Check", 225), ("state", "Observation", 140)):
            self.table.heading(key, text=title)
            self.table.column(key, width=width, minwidth=110)
        self.table.pack(fill="x", pady=(0, 10))
        self.table.tag_configure("Needs attention", foreground=PALETTE["error"])
        self.table.bind("<<TreeviewSelect>>", lambda event: self.select())
        self.table.bind("<Down>", self.keyboard_start)
        self.table.bind("<Up>", self.keyboard_start)
        detail_area = ttk.Frame(page)
        detail_area.pack(fill="x", pady=(0, 8))
        self.details = tk.Text(detail_area, height=10, wrap="word", state="disabled", takefocus=True,
            background=PALETTE["surface"], foreground=PALETTE["text"], padx=10, pady=10,
            highlightcolor=PALETTE["accent"], selectbackground=PALETTE["accent"], selectforeground=PALETTE["header_text"])
        self.details.pack(side="left", fill="both", expand=True)
        detail_scroll = ttk.Scrollbar(detail_area, command=self.details.yview)
        detail_scroll.pack(side="right", fill="y")
        self.details.configure(yscrollcommand=detail_scroll.set)
        controls = ttk.Frame(page)
        controls.pack(fill="x", pady=(0, 8))
        self.check_button = ttk.Button(controls, text="Check selected source", command=self.check, state="disabled")
        self.check_button.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=3)
        self.open_button = ttk.Button(controls, text="Open related page", command=self.open_source, state="disabled")
        self.open_button.grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Button(controls, text="Preview diagnostic report", command=self.preview_report).grid(row=1, column=0, sticky="ew", padx=(0, 6), pady=3)
        self.export_button = ttk.Button(controls, text="Export preview…", command=self.export_preview, state="disabled")
        self.export_button.grid(row=1, column=1, sticky="ew", pady=3)
        for col in (0, 1): controls.columnconfigure(col, weight=1)
        self.notice = center.text(page, "Select a row. Unconfigured checks stay unavailable; repairs remain manual.", "Muted.TLabel")
        center.text(page, "Report preview · frozen until Preview is pressed again", "Heading.TLabel")
        report_area = ttk.Frame(page)
        report_area.pack(fill="x")
        self.report_text = tk.Text(report_area, height=10, wrap="word", state="disabled", takefocus=True,
            background=PALETTE["surface"], foreground=PALETTE["text"], padx=10, pady=10,
            highlightcolor=PALETTE["accent"], selectbackground=PALETTE["accent"], selectforeground=PALETTE["header_text"])
        self.report_text.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(report_area, command=self.report_text.yview)
        scroll.pack(side="right", fill="y")
        self.report_text.configure(yscrollcommand=scroll.set)
        self.root.bind("<Destroy>", self.destroy, add="+")

    def project(self):
        return findings(self.system.source_health.project(), self.center.evidence_view.snapshot,
            local_checked_at_ns=self.local_checked_at_ns, cleanup_blocked=self.system.cleanup_blocked)

    def render(self):
        if self.closed: return
        old = self.rows
        self.rows = self.project()
        for row in self.rows:
            if self.table.exists(row.key):
                self.table.item(row.key, values=(row.title, row.state), tags=(row.state,))
            else:
                self.table.insert("", "end", iid=row.key, values=(row.title, row.state), tags=(row.state,))
        self.summary.configure(text=f"{sum(row.state == 'Needs attention' for row in self.rows)} attention indications · "
            f"{sum(row.state == 'Unknown' for row in self.rows)} information gaps · cached observations, no overall health score.")
        if self.table.selection():
            self.select(preserve=old == self.rows)
        else:
            self.set_details("Select a check. Check times and source timestamps are separate; missing measurements remain Unknown.")
            self.check_button.configure(state="disabled")
            self.open_button.configure(state="disabled")

    def can_check(self, row):
        if row.key == "runtime": return True
        if row.key == "Governance": return self.center.governance_path is not None
        if row.key in {"Evidence", "storage"}: return self.center.evidence_view.path is not None
        from .connection_observation import PROVIDERS
        return row.key in PROVIDERS and row.key in self.center.connections_view.paths

    def select(self, preserve=False):
        row = self.selected_row()
        if row is None or self.closed: return
        position = self.details.index("@0,0") if preserve else "1.0"
        self.set_details(f"{row.title} · {row.state}\nLocal check completed: {stamp(row.checked_at_ns)}\n"
            f"Source timestamp: {stamp(row.source_at_ns)}\n\nCause / observation\n{row.cause}\n\n"
            f"Impact\n{row.impact}\n\nNext step\n{row.next_step}")
        self.details.yview(position)
        self.check_button.configure(state="normal" if self.can_check(row) else "disabled")
        self.open_button.configure(state="normal")

    def check(self):
        if self.closed: return
        row = self.selected_row()
        if row is None: return
        if not self.can_check(row):
            self.notice.configure(text="Check unavailable. Select an owner export on its source page; service discovery is not configured.")
            self.render()
            return
        if row.key == "runtime":
            self.system.refresh_diagnostics()
            self.local_checked_at_ns = time.time_ns()
        elif row.key == "Governance": self.center.refresh_governance()
        elif row.key in {"Evidence", "storage"}: self.center.evidence_view.refresh()
        else: self.center.connections_view.refresh(row.key)
        self.notice.configure(text="Check completed through the existing local reader. Inspect the observation below; completion is not a health or enforcement verdict. Earlier report preview stays frozen.")
        self.render()

    def open_source(self):
        row = self.selected_row()
        if row is None or self.closed: return
        if row.page in self.system.tabs: self.system.select_mode(row.page)
        else: self.center.show(row.page)

    def preview_report(self):
        if self.closed: return
        self.render()
        self.preview = support_report(self.rows, time.time_ns())
        self.report_text.configure(state="normal")
        self.report_text.delete("1.0", "end")
        self.report_text.insert("end", self.preview)
        self.report_text.configure(state="disabled")
        self.export_button.configure(state="normal")
        self.notice.configure(text="Review the frozen report below before exporting. It excludes paths, raw logs, identifiers, credentials and raw errors. Later checks do not change this preview.")

    def export_preview(self):
        if self.closed or self.preview is None: return
        result = self.system.write_file(self.preview, "pulpo-wsl-diagnostics.json", ".json")
        self.notice.configure(text="Frozen preview exported locally; no automatic upload." if result else
            "Export failed; check destination access. Report preview retained." if result is False else
            "Export cancelled; report preview retained.")

    def destroy(self, event):
        if event.widget is self.root:
            super().destroy(event)
            self.system = self.preview = self.local_checked_at_ns = None
