"""Inspect one existing redacted reference; never infer a correlated action chain."""
from datetime import datetime, timezone

from .evidence_observation import freshness


GROUPS = {
    "All references": None,
    "Decisions": {"decision"},
    "Approvals": {"approval_verified", "approval_rejected"},
    "Permits": {"permit_consumed", "permit_rejected"},
}


def record_time(timestamp_ns):
    # Integer seconds avoid float rounding at the public contract's upper bound.
    seconds, nanos = divmod(timestamp_ns, 1_000_000_000)
    return datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%d %H:%M:%S") + f".{nanos:09d} UTC"


def record_details(event):
    """Only the selected event supports a stage; neighboring events support none."""
    stages = {
        "Request and target": "Unknown · Intent, principal, target and correlation ID are not exported.",
        "Policy decision": "Unknown · No decision can be linked to this reference.",
        "Approval": "Unknown · No approval can be linked to this reference.",
        "Permit": "Unknown · No permit can be linked to this reference.",
        "Execution and consequence": "Unknown · Attempt, transmission, completion and reconciliation are not exported.",
    }
    if event.event == "decision":
        stages["Policy decision"] = (f"Recorded · Source-reported outcome: {event.outcome.replace('_', ' ')}. "
                                     "Decision reason and policy binding are not exported. This does not prove execution.")
    elif event.event in GROUPS["Approvals"]:
        stages["Approval"] = (f"Recorded · Source event: {event.event.replace('_', ' ')}. "
                              "Exact approval binding, validity now and related decision are Unknown.")
    elif event.event in GROUPS["Permits"]:
        stages["Permit"] = (f"Recorded · Source event: {event.event.replace('_', ' ')}. "
                            "Permit consumption does not prove a provider request or completed effect; rejection does not prove no other effect.")
    return "\n\n".join(f"{name}\n{detail}" for name, detail in stages.items())


class DecisionExplorer:
    def __init__(self, center, page):
        import tkinter as tk
        from tkinter import ttk
        from .control_center_theme import PALETTE, surface
        self.center, self.root = center, center.root
        self.closed = False
        self.snapshot = None
        self.events = ()
        self.group = None
        center.text(page, "Decision Explorer · record view", "Heading.TLabel")
        center.text(page, "Inspect a reference from the Evidence source. Authorization, attempted execution and completed "
                    "consequences are separate facts. These exports cannot link stages into one action.", "Muted.TLabel")
        tools = ttk.Frame(page)
        tools.pack(fill="x", pady=(0, 8))
        ttk.Button(tools, text="Open Evidence source", command=lambda: center.show("Evidence")).grid(
            row=0, column=0, sticky="ew", padx=(0, 6), pady=3)
        ttk.Button(tools, text="Update display", command=self.render).grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Label(tools, text="Reference type").grid(row=1, column=0, sticky="w", pady=3)
        self.filter = ttk.Combobox(tools, values=tuple(GROUPS), state="readonly", width=18)
        self.filter.set("All references")
        self.filter.grid(row=1, column=1, sticky="ew", pady=3)
        self.filter.bind("<<ComboboxSelected>>", lambda event: self.render())
        for col in (0, 1): tools.columnconfigure(col, weight=1)
        self.coverage = center.text(page, "", "Muted.TLabel")
        shadow, body = surface(page)
        shadow.pack(fill="x", pady=(0, 8))
        area = ttk.Frame(body, style="Card.TFrame")
        area.pack(fill="x")
        self.table = ttk.Treeview(area, columns=("event", "outcome"), show="headings", height=4,
                                  selectmode="browse")
        for key, title in (("event", "Source event"), ("outcome", "Reported outcome")):
            self.table.heading(key, text=title)
            self.table.column(key, width=160, minwidth=95)
        self.table.grid(row=0, column=0, sticky="ew", padx=(8, 0), pady=8)
        scroll = ttk.Scrollbar(area, command=self.table.yview)
        scroll.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=8)
        self.table.configure(yscrollcommand=scroll.set)
        area.columnconfigure(0, weight=1)
        self.table.bind("<<TreeviewSelect>>", lambda event: self.select())
        self.table.bind("<Down>", self.keyboard_start)
        self.table.bind("<Up>", self.keyboard_start)
        center.text(page, "Selected reference · stages and gaps", "Heading.TLabel")
        details = ttk.Frame(page)
        details.pack(fill="x", pady=(0, 8))
        self.details = tk.Text(details, height=12, wrap="word", state="disabled", takefocus=True,
                               padx=10, pady=10, font=("TkDefaultFont", 10), relief="flat",
                               background=PALETTE["surface"], foreground=PALETTE["text"],
                               highlightthickness=1, highlightbackground=PALETTE["border"],
                               highlightcolor=PALETTE["accent"], selectbackground=PALETTE["accent"],
                               selectforeground=PALETTE["header_text"])
        self.details.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(details, command=self.details.yview)
        scroll.pack(side="right", fill="y")
        self.details.configure(yscrollcommand=scroll.set)
        self.copy_button = ttk.Button(page, text="Copy safe record reference", command=self.copy, state="disabled")
        self.copy_button.pack(anchor="w", pady=(0, 8))
        center.text(page, "Source-reported records are not independently authenticated here. A hash is a reference, "
                    "not chain verification. Missing stages never authorize retry. No approval or execution controls are available.", "Muted.TLabel")
        self.root.bind("<Destroy>", self.destroy, add="+")
        self.render()

    def current_snapshot(self):
        view = getattr(self.center, "evidence_view", None)
        return view.snapshot if view is not None and not view.error else None

    def render(self):
        if self.closed:
            return
        snapshot = self.current_snapshot()
        group = self.filter.get()
        changed = snapshot != self.snapshot or group != self.group
        self.snapshot = snapshot
        self.group = group
        allowed = GROUPS[group]
        events = tuple(event for event in reversed(snapshot.events) if allowed is None or event.event in allowed) if snapshot else ()
        if changed or events != self.events:
            self.table.delete(*self.table.get_children())
            self.events = events
            for index, event in enumerate(events):
                self.table.insert("", "end", iid=str(index), values=(event.event.replace("_", " "), event.outcome.replace("_", " ")))
            self.set_details("Unknown · Select a current reference. Changing or clearing the source clears the selection; it does not resolve any consequence.")
        if snapshot:
            self.coverage.configure(text=f"Recorded · {len(events)} matching references in the latest {len(snapshot.events)} exported records "
                f"(maximum 24; not full history).\nSource {snapshot.source_id} · {freshness(snapshot)} · "
                f"audit check {'passed' if snapshot.audit_valid else 'FAILED'} (reported).\n"
                "Cached Evidence source. Update display reads this cache only; open Evidence to re-read the file.")
        else:
            self.coverage.configure(text="Unknown · No usable Evidence observation. Open Evidence to select a trusted-owner export. "
                "The separate Governance metadata snapshot contains no decision records.")
            self.set_details("Unknown · No current record selected. Request, decision, approval, permit, execution and consequence are unavailable.")

    def selected_event(self):
        if (self.closed or self.snapshot is None or self.current_snapshot() != self.snapshot
                or self.filter.get() != self.group):
            return None
        selection = self.table.selection()
        if not selection or not selection[0].isdigit():
            return None
        index = int(selection[0])
        return self.events[index] if index < len(self.events) else None

    def keyboard_start(self, event):
        # Tk leaves a freshly populated Treeview without a focused row. Let an
        # explicit arrow key begin review without auto-selecting new source data.
        children = self.table.get_children()
        if not self.table.selection() and children:
            key = children[-1] if event.keysym == "Up" else children[0]
            self.table.selection_set(key)
            self.table.focus(key)
            self.table.see(key)
            return "break"

    def set_details(self, value):
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("end", value)
        self.details.configure(state="disabled")
        self.details.yview_moveto(0)
        self.copy_button.configure(state="disabled")

    def select(self):
        if self.closed:
            return
        event = self.selected_event()
        if event is None:
            self.set_details("Unknown · Select a current reference; previous source selection is unavailable.")
            return
        self.set_details(f"Recorded · {event.event.replace('_', ' ')} / {event.outcome.replace('_', ' ')}\n"
            f"Source record time: {record_time(event.timestamp_ns)}\n"
            f"Export observation time: {record_time(self.snapshot.observed_at_ns)}\n"
            f"Record hash: {event.record_hash}\n\n" + record_details(event))
        self.copy_button.configure(state="normal")

    def copy(self):
        event = self.selected_event()
        if event is None:
            if not self.closed:
                self.render()
            return
        # Only strict public enums, numeric times and hashes; no raw text or paths.
        value = (f"Recorded | source={self.snapshot.source_id} | record={event.record_hash} | "
                 f"event={event.event} | outcome={event.outcome} | record_time_ns={event.timestamp_ns} | "
                 f"observation_time_ns={self.snapshot.observed_at_ns} | provenance=Unknown | enforcement=Unknown")
        self.root.clipboard_clear()
        self.root.clipboard_append(value)

    def destroy(self, event):
        if event.widget is self.root:
            self.closed = True
            self.snapshot, self.events, self.center = None, (), None
