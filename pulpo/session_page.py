"""Explicit WSL setup persistence, restoring locations without reading them."""
from pathlib import Path

from . import session_preferences as preferences


class SessionPage:
    def __init__(self, system, page):
        import tkinter as tk
        from tkinter import ttk
        self.system, self.center, self.root = system, system.center, system.root
        self.closed = False
        self.path = preferences.preference_path(system.profile)
        self.preferred_page = tk.StringVar(master=self.root, value="Overview")
        self.preferred_tab = tk.StringVar(master=self.root, value="Diagnostics")
        center = self.center
        center.text(page, "Remember this setup · WSL", "Heading.TLabel")
        center.text(page, "Optional: save the currently selected owner-export locations, three graph ranges and preferred startup view. "
            "Changes are saved only when you press Remember this setup. No save on close.", "Muted.TLabel")
        options = ttk.Frame(page)
        options.pack(fill="x", pady=(0, 12))
        for row, (label, variable, values) in enumerate((("Startup page", self.preferred_page, preferences.PAGES),
                ("System tab", self.preferred_tab, preferences.TABS))):
            ttk.Label(options, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
            ttk.Combobox(options, textvariable=variable, values=values, state="readonly", width=24).grid(row=row, column=1, sticky="ew", pady=4)
        options.columnconfigure(1, weight=1)
        from .storage_settings import StorageSettings
        self.storage = StorageSettings(center, page)
        self.summary = center.text(page, "", "Muted.TLabel")
        ttk.Button(page, text="Review current setup", command=self.render).pack(anchor="w", pady=(0, 8))
        ttk.Button(page, text="Remember this setup", command=self.remember).pack(anchor="w", pady=(0, 8))
        ttk.Button(page, text="Forget saved setup", command=self.forget).pack(anchor="w", pady=(0, 8))
        self.status = center.text(page, "Not saved by default. No source locations are read by this page.", "Muted.TLabel")
        center.section(page, "Restored does not mean checked",
            "Remembered sources start Not checked this session. Re-read explicitly from their source page or Troubleshooting. "
            "Evidence polling waits for that first explicit re-read. Missing locations, failed reads and stale exports keep their normal Unknown/attention behavior.\n\n"
            "The private preferences file stores paths, which can contain personal names. It contains no credentials, file contents, "
            "cached metrics, health results, activity, approvals, benchmark reports or authority. Do not share it as a support report.\n\n"
            "Forget removes only the saved preferences. Current source selections and graph ranges stay available in this window; "
            "no source export or performance profile is deleted.")
        self.root.bind("<Destroy>", self.destroy, add="+")

    def capture(self):
        center = self.center
        sources = {key: str(path) for key, path in center.connections_view.paths.items()}
        if center.governance_path is not None: sources["Governance"] = str(center.governance_path)
        if center.evidence_view.path is not None: sources["Evidence"] = str(center.evidence_view.path)
        storage = self.storage.capture()
        return preferences.validate({**({"storage": storage} if storage is not None else {}), "schema": preferences.SCHEMA, "sources": sources,
            "ranges": {"overview": center.monitor.seconds, "system": self.system.monitor.seconds, "evidence": center.evidence_view.seconds},
            "page": self.preferred_page.get(), "system_tab": self.preferred_tab.get()})

    def render(self):
        if self.closed: return
        try:
            value = self.capture()
            locations = "\n".join(f"{key}: {path}" for key, path in value["sources"].items()) or "None selected."
            self.summary.configure(text="Current locations to remember · paths only\n" + locations +
                "\n\nGraph ranges (seconds): " + ", ".join(f"{key} {n}" for key, n in value["ranges"].items()))
        except (ValueError, TypeError):
            self.summary.configure(text="Current setup is not supported for saving. Choose supported pages, ranges and absolute paths; acknowledge the storage plan after any edit.")

    def set_active(self, active):
        if active and not self.closed: self.render()

    def restore(self):
        try:
            value = preferences.load(self.path)
            if value is None: return
            self.storage.restore(value.get("storage"))
            self.preferred_page.set(value["page"])
            self.preferred_tab.set(value["system_tab"])
            center = self.center
            for key, location in value["sources"].items():
                path = Path(location)  # No expanduser, resolve, stat or source read.
                if key == "Evidence":
                    evidence = center.evidence_view
                    evidence.path, evidence.awaiting_reread = path, True
                    evidence.refresh_button.configure(state="normal")
                    evidence.render()
                elif key == "Governance":
                    from .governance_observer import GovernanceObservation
                    center.governance_path = path
                    center.governance_refresh.configure(state="normal")
                    center._render_governance(GovernanceObservation(source="Restored selection · Not checked this session. Press Re-read to inspect the owner export."))
                else:
                    center.connections_view.paths[key] = path
                    center.connections_view.refresh_buttons[key].configure(state="normal")
            center.connections_view.render()
            center.monitor.set_range(value["ranges"]["overview"])
            self.system.monitor.set_range(value["ranges"]["system"])
            center.evidence_view.set_range(value["ranges"]["evidence"])
            self.system.select_mode(value["system_tab"])
            center.show(value["page"])
            self.status.configure(text="Saved setup restored · source locations are Not checked this session. No source file was opened.")
            self.render()
        except (OSError, ValueError, TypeError, RecursionError):
            self.status.configure(text="Saved setup unavailable or rejected. Defaults retained; no source location was read. Inspect the private preferences file manually.")

    def remember(self):
        if self.closed: return
        try:
            preferences.save(self.path, self.capture())
            self.status.configure(text="Setup saved privately. Next launch restores locations only; sources require explicit re-read. Any storage plan acknowledgment is recorded locally; delivery, durability and retention remain unverified. Changes after this save are not remembered automatically.")
            self.render()
        except (OSError, ValueError, TypeError, RecursionError):
            self.status.configure(text="Could not save setup. Check private directory/file access and supported values. Check the storage plan path and acknowledgment after edits. No diagnostic contents were logged.")

    def forget(self):
        if self.closed: return
        try:
            preferences.forget(self.path)
            self.status.configure(text="Saved setup forgotten. Current window selections/ranges remain; source files and performance settings were untouched.")
        except (OSError, ValueError):
            self.status.configure(text="Could not forget saved setup. Inspect private preferences access manually; no other file was removed.")

    def destroy(self, event):
        if event.widget is self.root:
            self.closed = True
            self.storage.close()
            self.storage = None
            self.preferred_page = self.preferred_tab = None
            self.center = self.system = None
