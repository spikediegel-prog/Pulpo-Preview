"""Bounded cached incident browser over a frozen incident report.

Read-only, in the EvidenceEvents pattern: the component loads one frozen
`pulpo.incident-report.v2` JSON export produced by the trusted owner and
renders its records. It never opens a database, never appends to the audit,
and offers no lifecycle transition -- acknowledging, resolving or closing
an incident stays a library-level operator action, not a button here.
"""
import stat
import time
from pathlib import Path

from .control_center_theme import PALETTE

KINDS = ("All kinds", "incident", "near_miss")
RESOLUTIONS = ("All resolutions", "unresolved", "resolved_cleanly", "confirmed_wrong", "not_applicable")
LIFECYCLES = ("All lifecycles", "open", "acknowledged", "resolved", "closed", "not_applicable")


def _format_time(timestamp_ns):
    return time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime(timestamp_ns / 1e9))


def _describe_record(record):
    """Full read-only detail for one record, as selectable text."""
    lines = [
        record.record_id,
        f"{record.kind} · {record.resolution} · {record.lifecycle} "
        f"(since {_format_time(record.lifecycle_at_ns)}"
        f"{' by ' + record.lifecycle_actor if record.lifecycle_actor else ''})",
        f"Source: {record.source} · {record.source_detail}",
        f"Reason: {record.reason}",
        f"First seen: {_format_time(record.first_seen_ns)} · "
        f"Last seen: {_format_time(record.last_seen_ns)}",
        f"Anchor hash: {record.anchor_hash}",
    ]
    for name, value in record.anchors:
        lines.append(f"Anchor {name}: {value}")
    return "\n".join(lines)


class EvidenceIncidents:
    def __init__(self, page, parent):
        import tkinter as tk
        from tkinter import ttk
        from .system_navigation import reflow
        self.page, self.center, self.root = page, page.center, page.root
        self.path, self.report, self.error = None, None, None
        self.records = {}
        self.signature = None
        self.expanded = False
        controls = ttk.Frame(parent)
        controls.pack(fill="x", pady=(0, 8))
        self.select_button = ttk.Button(controls, text="Select incident report…", command=self.select)
        self.select_button.pack(side="left")
        self.refresh_button = ttk.Button(controls, text="Re-read", command=self.refresh, state="disabled")
        self.refresh_button.pack(side="left", padx=6)
        self.clear_button = ttk.Button(controls, text="Clear", command=self.clear)
        self.clear_button.pack(side="left")
        controls.bind("<Configure>", lambda event: reflow(
            controls, (self.select_button, self.refresh_button, self.clear_button),
            event.width, maximum=3))
        filters = ttk.Frame(parent)
        filters.pack(fill="x", pady=(0, 8))
        self.kind = tk.StringVar(master=self.root, value="All kinds")
        self.resolution = tk.StringVar(master=self.root, value="All resolutions")
        self.lifecycle = tk.StringVar(master=self.root, value="All lifecycles")
        for variable, values in ((self.kind, KINDS), (self.resolution, RESOLUTIONS),
                                 (self.lifecycle, LIFECYCLES)):
            selector = ttk.Combobox(filters, textvariable=variable, state="readonly",
                                    width=18, values=values)
            selector.pack(side="left", padx=(0, 8))
            selector.bind("<<ComboboxSelected>>", lambda event: self.render())
        self.summary = page.center.text(parent, "No incident report selected.", "Muted.TLabel")
        area = ttk.Frame(parent)
        area.pack(fill="x", pady=(0, 8))
        self.table = ttk.Treeview(area, columns=("seen", "kind", "resolution", "lifecycle", "record"),
                                  show="headings", height=5, selectmode="browse")
        for key, title, width in (("seen", "First seen", 140), ("kind", "Kind", 90),
                                  ("resolution", "Resolution", 120), ("lifecycle", "Lifecycle", 110),
                                  ("record", "Record", 260)):
            self.table.heading(key, text=title)
            self.table.column(key, width=width, minwidth=80)
        self.table.grid(row=0, column=0, sticky="ew")
        scroll = ttk.Scrollbar(area, command=self.table.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(area, orient="horizontal", command=self.table.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.table.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
        area.columnconfigure(0, weight=1)
        self.table.bind("<<TreeviewSelect>>", lambda event: self.select_record())
        self.table.bind("<Down>", self.keyboard_start)
        self.table.bind("<Up>", self.keyboard_start)
        actions = ttk.Frame(parent)
        actions.pack(fill="x", pady=(0, 8))
        self.detail_button = ttk.Button(actions, text="Show incident details", command=self.toggle)
        self.copy_button = ttk.Button(actions, text="Copy record id", command=self.copy, state="disabled")
        actions.bind("<Configure>", lambda event: reflow(
            actions, (self.detail_button, self.copy_button), event.width, maximum=2))
        self.notice = page.center.text(
            parent, "Select a frozen incident report. Times are source-reported; no action is staged.",
            "Muted.TLabel")
        self.detail_frame = ttk.Frame(parent)
        # Details are still selectable text for keyboard copy and screen magnification.
        self.details = tk.Text(self.detail_frame, height=6, wrap="word", state="disabled", padx=10, pady=10,
                               font=("TkDefaultFont", 10), background=PALETTE["surface"],
                               foreground=PALETTE["text"], relief="flat",
                               highlightthickness=1, highlightbackground=PALETTE["border"],
                               highlightcolor=PALETTE["accent"], selectbackground=PALETTE["accent"],
                               selectforeground=PALETTE["header_text"])
        self.details.pack(side="left", fill="both", expand=True)
        detail_scroll = ttk.Scrollbar(self.detail_frame, command=self.details.yview)
        detail_scroll.pack(side="right", fill="y")
        self.details.configure(yscrollcommand=detail_scroll.set)
        # Stable packing slot; expanding does not relocate the setup section.
        self.slot = ttk.Frame(parent)
        self.slot.pack(fill="x")
        self.root.bind("<Destroy>", self.destroy, add="+")
        self.render()

    def selected_record(self):
        selected = self.table.selection()
        return self.records.get(selected[0]) if selected else None

    def _matching_records(self):
        if self.report is None:
            return ()
        kind, resolution, lifecycle = self.kind.get(), self.resolution.get(), self.lifecycle.get()
        return tuple(
            record for record in self.report.records
            if (kind == "All kinds" or record.kind == kind)
            and (resolution == "All resolutions" or record.resolution == resolution)
            and (lifecycle == "All lifecycles" or record.lifecycle == lifecycle)
        )

    def render(self):
        records = self._matching_records()
        identity = (str(self.path), self.report.source_id if self.report else None)
        signature = (identity, records, self.kind.get(), self.resolution.get(), self.lifecycle.get())
        if signature == self.signature:
            return  # Polling must not reset selection, scroll or copied notice.
        old = self.selected_record() if self.signature and self.signature[0] == identity else None
        self.signature = signature
        self.table.delete(*self.table.get_children())
        self.records = {str(index): record for index, record in enumerate(records)}
        for key, record in self.records.items():
            self.table.insert("", "end", iid=key, values=(
                _format_time(record.first_seen_ns), record.kind.replace("_", " "),
                record.resolution.replace("_", " "), record.lifecycle.replace("_", " "),
                record.record_id))
        # Restore only the exact reference; changing/evicting records never leaves a stale copy target.
        match = next((key for key, record in self.records.items() if record == old), None)
        if match is not None:
            self.table.selection_set(match)
            self.table.focus(match)
        if self.report is None:
            self.summary.configure(text=self.error or "No incident report selected.")
        else:
            self.summary.configure(
                text=f"Recorded · {self.report.incidents} incident(s) · {self.report.near_misses} "
                     f"near-miss(es) · {self.report.unresolved} unresolved · "
                     f"{len(records)} matching · Audit valid: "
                     f"{'yes' if self.report.audit_valid else 'no'}")
        self.select_record()

    def select(self):
        from tkinter import filedialog
        selected = filedialog.askopenfilename(parent=self.root, title="Select incident report",
                                              filetypes=(("JSON report", "*.json"),))
        if selected:
            self.path = Path(selected)
            self.refresh_button.configure(state="normal")
            self.refresh()

    def refresh(self):
        if self.path is None or self.page.closed:
            return
        try:
            if not self.path.is_absolute() or not stat.S_ISREG(self.path.lstat().st_mode):
                raise ValueError("not_regular_file")
            from .incident_channel import load_incident_report
            self.report = load_incident_report(self.path)
            self.error = None
        except (OSError, ValueError, TypeError, RecursionError):
            self.report = None
            self.records = {}
            self.error = ("Incident report unavailable or invalid. Check the path, private-file "
                          "permissions and format.")
        self.render()

    def clear(self):
        self.path, self.report, self.error = None, None, None
        self.records = {}
        self.refresh_button.configure(state="disabled")
        self.render()

    def select_record(self):
        record = self.selected_record()
        self.copy_button.configure(state="normal" if record else "disabled")
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        text = "No matching record selected. This does not prove there were no incidents."
        if record is not None:
            text = _describe_record(record)
        self.details.insert("end", text)
        self.details.configure(state="disabled")
        self.notice.configure(text=("Selected record · frozen report reference" if record else
            f"{len(self.records)} matching record(s) · select a row to inspect or copy its id."))

    def toggle(self):
        self.expanded = not self.expanded
        if self.expanded:
            self.detail_frame.pack(fill="x", pady=(0, 8), before=self.slot)
        else:
            self.detail_frame.pack_forget()
        self.detail_button.configure(text="Hide incident details" if self.expanded else "Show incident details")

    def copy(self):
        record = self.selected_record()
        if record is not None:
            self.root.clipboard_clear()
            self.root.clipboard_append(record.record_id)
            self.notice.configure(text="Record id copied · public reference only.")

    def keyboard_start(self, event):
        keys = self.table.get_children()
        if keys and not self.table.selection():
            key = keys[-1] if event.keysym == "Up" else keys[0]
            self.table.selection_set(key)
            self.table.focus(key)
            self.table.see(key)
            return "break"

    def destroy(self, event):
        if event.widget is self.root:
            self.page = None
            self.records.clear()
            self.signature = None
            self.kind = None
            self.resolution = None
            self.lifecycle = None
