"""Needs Attention presentation. Consumes cached values; navigation only."""
from .attention_model import KINDS, age_text
from .control_center_theme import PALETTE, surface


class AttentionPanel:
    def __init__(self, center, parent):
        from tkinter import ttk
        self.center, self.closed = center, False
        self.items, self.selected_key = {}, None
        self.compact = False
        self.frame, border = surface(parent)
        self.frame.pack(fill="x", pady=(0, 16))
        body = ttk.Frame(border, style="Card.TFrame", padding=12)
        body.pack(fill="both", expand=True)
        style = ttk.Style(center.root)
        style.configure("AttentionMuted.Card.TLabel", foreground=PALETTE["muted"])
        ttk.Label(body, text="Needs Attention", style="CardHeading.TLabel").pack(anchor="w")
        self.summary = ttk.Label(body, style="AttentionMuted.Card.TLabel", wraplength=700, justify="left")
        self.summary.pack(fill="x", pady=(4, 8))
        area = ttk.Frame(body, style="Card.TFrame")
        area.pack(fill="x")
        area.columnconfigure(0, weight=1)
        self.table = ttk.Treeview(area, columns=("condition", "age"), show="headings", height=3, selectmode="browse")
        self.table.heading("condition", text="Condition")
        self.table.heading("age", text="Source age")
        self.table.column("condition", width=500, minwidth=180)
        self.table.column("age", width=125, minwidth=95, stretch=False)
        self.table.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(area, orient="vertical", command=self.table.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.table.configure(yscrollcommand=scrollbar.set)
        for kind, color in zip(KINDS, (PALETTE["error"], PALETTE["warning"], PALETTE["muted"])):
            self.table.tag_configure(kind, foreground=color)
        self.table.bind("<<TreeviewSelect>>", self.select)
        self.table.bind("<Return>", lambda event: self.open_selected())
        self.details = ttk.Frame(body, style="Card.TFrame")
        self.detail = ttk.Label(self.details, style="Card.TLabel", wraplength=700, justify="left")
        self.detail.pack(fill="x", pady=(8, 6))
        self.open_button = ttk.Button(self.details, command=self.open_selected, state="disabled")
        self.open_button.pack(anchor="w")
        self.notice = ttk.Label(body, text="Select an item for impact, source and next step. Enforcement is unassessed.\n"
                                "Clearing or removing an item does not confirm resolution.",
                                style="AttentionMuted.Card.TLabel", wraplength=700, justify="left")
        self.notice.pack(fill="x", pady=(8, 0))
        body.bind("<Configure>", self.resize)
        center.root.bind("<Destroy>", self.destroy, add="+")

    def update(self, items):
        if self.closed:
            return
        self.items = {item.key: item for item in items}
        for key in self.table.get_children():
            if key not in self.items:
                self.table.delete(key)
        for index, item in enumerate(items):
            values = (self.caption(item), age_text(item.observed_at_ns))
            if self.table.exists(item.key):
                self.table.item(item.key, values=values, tags=(item.kind,))
                self.table.move(item.key, "", index)
            else:
                self.table.insert("", "end", iid=item.key, values=values, tags=(item.kind,))
        counts = {kind: sum(item.kind == kind for item in items) for kind in KINDS}
        self.summary.configure(text=f"{counts['Problem']} problem indications · {counts['Information gap']} information gaps · "
                                    f"{counts['Resource hint']} resource hints · local readings and selected exports")
        self.render_detail()

    def select(self, event=None):
        if self.closed:
            return
        selection = self.table.selection()
        if selection:
            self.selected_key = selection[0]
        self.render_detail()

    def caption(self, item):
        kind = {"Information gap": "Gap", "Resource hint": "Resource"}.get(item.kind, item.kind) if self.compact else item.kind
        return kind + " · " + item.title

    def render_detail(self):
        if self.closed:
            return
        item = self.selected_item()
        if item is not None:
            self.details.pack(fill="x", before=self.notice)
            self.detail.configure(text=f"{item.kind} · {item.title}\n{item.impact}\n"
                                       f"Source: {item.source}\n{age_text(item.observed_at_ns)} · observation time where available")
            self.open_button.configure(text=item.action, state="normal")
        elif self.selected_key is not None:
            self.details.pack(fill="x", before=self.notice)
            self.detail.configure(text="The previous selection is unavailable. This does not confirm resolution; select a current condition to inspect its source.")
            self.open_button.configure(text="Open selected page", state="disabled")
        else:
            self.details.pack_forget()
            self.open_button.configure(state="disabled")

    def open_selected(self):
        item = self.selected_item()
        if item is None:
            return
        # Destinations are fixed by local rules, never routes from an export.
        self.center.show(item.page)
        if item.udm_setup:
            self.center.connections_view.open_setup()

    def selected_item(self):
        if self.closed:
            return None
        # A removed key returning later must not reactivate an old action without
        # an actual current tree selection, even if its condition key matches.
        return self.items.get(self.selected_key) if self.selected_key in self.table.selection() else None

    def resize(self, event):
        width = max(240, event.width - 24)
        for label in (self.summary, self.detail, self.notice):
            label.configure(wraplength=width)
        compact = width < 550
        self.table.column("age", width=95 if compact else 125)
        self.table.column("condition", width=max(180, width - (110 if compact else 140)))
        if compact != self.compact:
            self.compact = compact
            for key, item in self.items.items():
                self.table.set(key, "condition", self.caption(item))

    def destroy(self, event):
        if self.center is not None and event.widget is self.center.root:
            self.closed = True
            self.items.clear()
            self.center = None
