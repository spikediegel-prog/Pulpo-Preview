"""Bounded cached event browser, with an explicit copy of one public hash."""
import time

from .control_center_theme import PALETTE


class EvidenceEvents:
    def __init__(self, page, parent):
        import tkinter as tk
        from tkinter import ttk
        self.page, self.root = page, page.root
        self.signature = None
        self.events = {}
        self.expanded = False
        area = ttk.Frame(parent)
        area.pack(fill="x", pady=(0, 8))
        self.table = ttk.Treeview(area, columns=("time", "event", "outcome"), show="headings", height=5, selectmode="browse")
        for key, title, width in (("time", "Record time", 105), ("event", "Event", 150), ("outcome", "Outcome", 155)):
            self.table.heading(key, text=title)
            self.table.column(key, width=width, minwidth=85)
        self.table.grid(row=0, column=0, sticky="ew")
        scroll = ttk.Scrollbar(area, command=self.table.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(area, orient="horizontal", command=self.table.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.table.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
        area.columnconfigure(0, weight=1)
        self.table.bind("<<TreeviewSelect>>", lambda event: self.select())
        self.table.bind("<Down>", self.keyboard_start)
        self.table.bind("<Up>", self.keyboard_start)
        actions = ttk.Frame(parent)
        actions.pack(fill="x", pady=(0, 8))
        self.detail_button = ttk.Button(actions, text="Show event details", command=self.toggle)
        self.copy_button = ttk.Button(actions, text="Copy record hash", command=self.copy, state="disabled")
        from .system_navigation import reflow
        actions.bind("<Configure>", lambda event: reflow(actions, (self.detail_button, self.copy_button), event.width, maximum=2))
        self.notice = page.center.text(parent, "Select a reference. Record times are source-reported; no action stages are inferred.", "Muted.TLabel")
        self.detail_frame = ttk.Frame(parent)
        # Details are still selectable text for keyboard copy and screen magnification.
        self.details = tk.Text(self.detail_frame, height=5, wrap="word", state="disabled", padx=10, pady=10,
            font=("TkDefaultFont", 10), background=PALETTE["surface"], foreground=PALETTE["text"], relief="flat",
            highlightthickness=1, highlightbackground=PALETTE["border"], highlightcolor=PALETTE["accent"],
            selectbackground=PALETTE["accent"], selectforeground=PALETTE["header_text"])
        self.details.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(self.detail_frame, command=self.details.yview)
        scroll.pack(side="right", fill="y")
        self.details.configure(yscrollcommand=scroll.set)
        # Stable packing slot; expanding does not relocate the setup section.
        self.slot = ttk.Frame(parent)
        self.slot.pack(fill="x")
        self.root.bind("<Destroy>", self.destroy, add="+")

    def selected_event(self):
        selected = self.table.selection()
        return self.events.get(selected[0]) if selected else None

    def render(self):
        events = tuple(reversed(self.page.snapshot.events if self.page.snapshot else ()))
        choice = self.page.filter.get()
        events = tuple(event for event in events if not (
            choice == "Policy decisions" and event.event != "decision" or
            choice == "Permit events" and not event.event.startswith("permit_") or
            choice == "Rejections" and event.outcome != "rejected"))
        identity = (str(self.page.path), self.page.snapshot.source_id if self.page.snapshot else None)
        signature = (identity, events, choice)
        if signature == self.signature:
            return  # Polling must not reset selection, scroll or copied notice.
        old = self.selected_event() if self.signature and self.signature[0] == identity else None
        self.signature = signature
        self.table.delete(*self.table.get_children())
        self.events = {str(index): event for index, event in enumerate(events)}
        for key, event in self.events.items():
            stamp = time.strftime("%H:%M:%S", time.localtime(event.timestamp_ns / 1e9))
            self.table.insert("", "end", iid=key, values=(stamp, event.event.replace("_", " "), event.outcome.replace("_", " ")))
        # Restore only the exact reference; changing/evicting records never leaves a stale copy target.
        match = next((key for key, event in self.events.items() if event == old), None)
        if match is not None:
            self.table.selection_set(match)
            self.table.focus(match)
        self.select()

    def select(self):
        event = self.selected_event()
        self.copy_button.configure(state="normal" if event else "disabled")
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        text = "No matching event selected. This does not prove there were no events."
        if event is not None:
            stamp = time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime(event.timestamp_ns / 1e9))
            text = f"Recorded · {stamp}\n{event.event} · {event.outcome.replace('_', ' ')}\nRecord hash: {event.record_hash}\nProvenance and enforcement: Unknown. No neighboring event is inferred to belong to the same action."
        self.details.insert("end", text)
        self.details.configure(state="disabled")
        self.notice.configure(text=("Selected record · source-reported reference" if event else
            f"{len(self.events)} matching reference(s) · select a row to inspect or copy its hash."))

    def toggle(self):
        self.expanded = not self.expanded
        if self.expanded:
            self.detail_frame.pack(fill="x", pady=(0, 8), before=self.slot)
        else:
            self.detail_frame.pack_forget()
        self.detail_button.configure(text="Hide event details" if self.expanded else "Show event details")

    def copy(self):
        event = self.selected_event()
        if event is not None:
            self.root.clipboard_clear()
            self.root.clipboard_append(event.record_hash)
            self.notice.configure(text="Record hash copied · public reference only; provenance remains Unknown.")

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
            self.events.clear()
            self.signature = None
