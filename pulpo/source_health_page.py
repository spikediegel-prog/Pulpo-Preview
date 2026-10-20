"""Local source coverage UI; refreshes ages, never files or providers."""
from .decision_explorer import record_time
from .source_health_model import source_age, source_health


class SourceHealthPage:
    def __init__(self, center, page):
        import tkinter as tk
        from tkinter import ttk
        from .control_center_theme import PALETTE
        self.center, self.root = center, center.root
        self.active = self.closed = False
        self.timer = None
        self.rows = ()
        self.presentation_signature = None
        center.text(page, "Source Health & Coverage", "Heading.TLabel")
        center.text(page, "Local file reads, source freshness and reported checks are separate. "
                    "This view uses existing caches; it does not read files or contact providers.", "Muted.TLabel")
        self.summary = center.text(page, "", "Muted.TLabel")
        ttk.Button(page, text="Update display · cached sources", command=self.render).pack(anchor="w", pady=(0, 8))
        area = ttk.Frame(page)
        area.pack(fill="x", pady=(0, 8))
        columns = ("source", "read", "age", "read_age") if center.wsl_clarity else ("source", "read", "age")
        self.table = ttk.Treeview(area, columns=columns, show="headings", height=5, selectmode="browse")
        for key, title, width in (("source", "Source", 150), ("read", "Local read", 110), ("age", "Source age", 115)):
            self.table.heading(key, text=title)
            self.table.column(key, width=width, minwidth=85)
        if center.wsl_clarity:
            self.table.heading("age", text="Data age")
            self.table.heading("read_age", text="Read age")
            self.table.column("read_age", width=150, minwidth=70)
            for key in columns:
                self.table.column(key, minwidth=70)
        self.table.grid(row=0, column=0, sticky="ew")
        scroll = ttk.Scrollbar(area, command=self.table.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.table.configure(yscrollcommand=scroll.set)
        if center.wsl_clarity:
            horizontal = ttk.Scrollbar(area, orient="horizontal", command=self.table.xview)
            horizontal.grid(row=1, column=0, sticky="ew")
            self.table.configure(xscrollcommand=horizontal.set)
            self.table.bind("<Configure>", lambda event: self.fit_age_columns())
        area.columnconfigure(0, weight=1)
        self.table.tag_configure("issue", foreground=PALETTE["error"])
        self.table.tag_configure("stale", foreground=PALETTE["warning"])
        self.table.bind("<<TreeviewSelect>>", lambda event: self.select())
        self.table.bind("<Down>", self.keyboard_start)
        self.table.bind("<Up>", self.keyboard_start)
        center.text(page, "Selected source · checks, coverage and next step", "Heading.TLabel")
        area = ttk.Frame(page)
        area.pack(fill="x", pady=(0, 8))
        self.details = tk.Text(area, height=13, wrap="word", state="disabled", takefocus=True, padx=10, pady=10,
            font=("TkDefaultFont", 10), relief="flat", background=PALETTE["surface"], foreground=PALETTE["text"],
            highlightthickness=1, highlightbackground=PALETTE["border"], highlightcolor=PALETTE["accent"],
            selectbackground=PALETTE["accent"], selectforeground=PALETTE["header_text"])
        self.details.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(area, command=self.details.yview)
        scroll.pack(side="right", fill="y")
        self.details.configure(yscrollcommand=scroll.set)
        self.open_button = ttk.Button(page, text="Open source page", command=self.open_source, state="disabled")
        self.open_button.pack(anchor="w", pady=(0, 8))
        self.replace_button = None
        self.machine_button = None
        if center.wsl_clarity:
            self.replace_button = ttk.Button(page, text="Select / replace source…", command=self.replace_source, state="disabled")
            self.replace_button.pack(anchor="w", pady=(0, 8))
            self.machine_button = ttk.Button(page, text="Describe source…", command=self.edit_machine_description, state="disabled")
            self.machine_button.pack(anchor="w", pady=(0, 8))
            self.machine_notice = center.text(page, "Optional source descriptions are operator labels, not authenticated machine identity. Session only; not saved.", "Muted.TLabel")
        center.text(page, "Red: failed read or reported failure. Amber: stale timestamp or clock mismatch. "
                    "Missing checks remain gaps. Evidence is stale after 15 seconds; connectors after 60 seconds.\n"
                    "A selected file is session configuration, not proof a collector is installed or running. "
                    "Source fingerprints are not authenticated identities. Enforcement remains Unknown.", "Muted.TLabel")
        self.root.bind("<Destroy>", self.destroy, add="+")
        self.render()

    def project(self):
        center = self.center
        evidence, connections = center.evidence_view, center.connections_view
        return source_health(governance_selected=center.governance_path is not None,
            governance=center.governance_observation, evidence_selected=evidence.path is not None,
            evidence=evidence.snapshot, evidence_error=evidence.error,
            connections_selected=connections.paths, connections=connections.observations,
            connection_errors=connections.errors, reads=center.source_reads)

    def fit_age_columns(self):
        from tkinter import font, ttk
        heading_font = font.Font(root=self.root, font=ttk.Style(self.root).lookup("Treeview.Heading", "font") or "TkHeadingFont")
        for key in ("source", "read", "age", "read_age"):
            minimum = max(70, heading_font.measure(self.table.heading(key, "text")) + 20)
            if self.table.column(key, "minwidth") != minimum:
                self.table.column(key, minwidth=minimum)

    def render(self):
        if self.closed:
            return
        old = self.rows
        self.rows = self.project()
        from .observation_clarity import source_paths
        signature = (tuple((key, str(path)) for key, path in source_paths(self.center).items()),
                     tuple(self.center.source_success_reads.items()), tuple(self.center.source_machine_labels.items())) if self.center.wsl_clarity else None
        selected = self.table.selection()
        # Fixed stable keys, one row per existing source, no accumulating history.
        for row in self.rows:
            tags = ("issue",) if row.problem else ("stale",) if row.freshness in {"Stale", "Clock mismatch"} else ()
            values = (row.key, row.read_status, source_age(row))
            if self.center.wsl_clarity:
                values += (self.center.source_read_age(row.key),)
            if self.table.exists(row.key):
                self.table.item(row.key, values=values, tags=tags)
            else:
                self.table.insert("", "end", iid=row.key, values=values, tags=tags)
        self.summary.configure(text=f"{sum(row.selected for row in self.rows)} selected exports · "
            f"{sum(row.cached for row in self.rows)} cached observations · source identity and enforcement Unknown.\n"
            "Ages update while this view is visible. Evidence file polling pauses while hidden; connection and Governance re-reads are explicit.")
        if self.center.wsl_clarity:
            self.summary.configure(text=self.summary.cget("text") + "\nData age uses the source timestamp; read age uses the last successful local read.")
        if selected and (old != self.rows or signature != self.presentation_signature):
            self.select(preserve=True)
        elif not selected:
            self.set_details("Unknown · Select a source for its last local read attempt, reported source timestamp, coverage and troubleshooting.")
            self.open_button.configure(state="disabled")
            if self.replace_button is not None:
                self.replace_button.configure(state="disabled")
                self.machine_button.configure(state="disabled")
        self.presentation_signature = signature

    def selected_row(self):
        selection = self.table.selection()
        return next((row for row in self.rows if selection and row.key == selection[0]), None)

    def set_details(self, value):
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("end", value)
        self.details.configure(state="disabled")

    def select(self, preserve=False):
        if self.closed:
            return
        row = self.selected_row()
        if row is None:
            return
        position = self.details.index("@0,0") if preserve else "1.0"
        local = "Unknown · No local read attempt recorded for this selection."
        if row.read:
            local = f"Recorded · {'succeeded' if row.read.succeeded else 'FAILED'} at {record_time(row.read.recorded_at_ns)}"
        stamp = record_time(row.observed_at_ns) if row.observed_at_ns is not None else "Unknown · Not exported or no usable observation."
        location = ""
        if self.center.wsl_clarity:
            from .observation_clarity import source_paths
            path = source_paths(self.center).get(row.key)
            location = (f"Selected file (local only)\n{path or 'None selected'}\n\n"
                f"Source machine\n{self.center.source_description(row.key)}\n\n"
                f"Last successful local read\n{self.center.source_last_success(row.key)}\n"
                "A previous success does not clear a later failure or establish source freshness.\n\n")
        self.set_details(f"{row.key} · {'Selected in this session' if row.selected else 'Not selected'}\n\n"
            + location + f"Last local read result\n{local}\nThis is UI wall-clock time recorded after the read, not source freshness or continuous file readability.\n\n"
            f"Reported source timestamp\n{stamp}\n{row.freshness} · Source age updates in the table above.\nSource fingerprint: {row.source_id}\n\n"
            f"Reported checks / read issues\n{chr(10).join(row.issues) if row.issues else 'No problem indication in this cached projection; this is not an all-clear.'}\n\n"
            f"Coverage\n{row.coverage}\n\nRemaining Unknown\n{row.unknowns}\n\nNext step\n{row.next_step}")
        self.open_button.configure(state="normal")
        if self.replace_button is not None:
            self.replace_button.configure(state="normal")
            self.machine_button.configure(state="normal" if row.selected else "disabled")
        self.details.yview(position)

    def open_source(self):
        if not self.closed:
            row = self.selected_row()
            if row:
                self.center.show(row.page)

    def replace_source(self):
        row = self.selected_row()
        if self.closed or row is None:
            return
        self.center.show(row.page)
        if row.key == "Governance":
            self.center.select_governance_snapshot()
        elif row.key == "Evidence":
            self.center.evidence_view.select()
        else:
            self.center.connections_view.select(row.key)

    def edit_machine_description(self, key=None):
        if self.closed or not self.center.wsl_clarity:
            return
        from tkinter import simpledialog
        from .observation_clarity import source_paths, machine_description
        row = self.selected_row()
        key = key or (row.key if row else None)
        path = source_paths(self.center).get(key)
        if path is None:
            return
        old = self.center.source_machine_labels.get(key)
        value = simpledialog.askstring("Describe selected source",
            "Optional operator description (48 characters max).\nUnverified; this window only. Leave empty to clear.",
            initialvalue=old[1] if old and old[0] == str(path) else "", parent=self.root)
        if value is None:
            return
        # A modal can allow unrelated UI timers; bind the label to the exact selection.
        if source_paths(self.center).get(key) != path:
            self.machine_notice.configure(text="Selection changed. Description was not applied.")
            return
        try:
            label = machine_description(value)
        except ValueError:
            self.machine_notice.configure(text="Use at most 48 printable characters, without line breaks or control characters.")
            return
        if label:
            self.center.source_machine_labels[key] = (str(path), label)
        else:
            self.center.source_machine_labels.pop(key, None)
        self.machine_notice.configure(text="Source description updated · operator label, unverified; not saved.")
        self.render()
        if self.center.evidence_view.clarity:
            self.center.evidence_view.render_timing()

    def keyboard_start(self, event):
        if not self.table.selection():
            children = self.table.get_children()
            key = children[-1] if event.keysym == "Up" else children[0]
            self.table.selection_set(key)
            self.table.focus(key)
            self.table.see(key)
            return "break"

    def set_active(self, active):
        if self.timer is not None:
            self.root.after_cancel(self.timer)
            self.timer = None
        self.active = active and not self.closed
        if self.active:
            self.render()
            self.timer = self.root.after(1000, self.tick)

    def tick(self):
        self.timer = None
        if self.active and not self.closed:
            if self.root.winfo_viewable() and self.root.state() != "iconic":
                # Render changes ages only; selected detail stays scrolled unless
                # the actual cached source/read result changed.
                self.render()
            self.timer = self.root.after(1000, self.tick)

    def destroy(self, event):
        if event.widget is self.root:
            self.closed = True
            self.set_active(False)
            self.center, self.rows = None, ()
