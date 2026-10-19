"""Capability-free connection display over manually selected frozen observations."""
from pathlib import Path
import time

from .connection_observation import PROVIDERS, REASONS, load_connection_observation


class ConnectionsPage:
    def __init__(self, center):
        from tkinter import ttk
        from .control_center import StatusRow
        self.center, self.root = center, center.root
        self.paths, self.observations, self.errors, self.rows, self.refresh_buttons = {}, {}, {}, {}, {}
        self.active, self.closed, self.timer = False, False, None
        page = center.pages["Connections"]
        center.text(page, "Connection inventory", "Heading.TLabel")
        center.text(page, "Reachability, authentication and governance are separate observations. "
                    "Connected never means enforcement verified. No account or network scan runs on startup.", "Muted.TLabel")
        self.summary = center.text(page, "", "Heading.TLabel")
        self.scope = center.text(page, "Only explicitly selected owner exports are shown. No source selected means Unknown, not offline.", "Muted.TLabel")
        self.setup_guide = None
        ttk.Button(page, text="Guided UDM setup…", command=self.open_setup).pack(anchor="w", pady=(0, 12))
        for provider in PROVIDERS:
            row = StatusRow(page, provider, "", None)
            self.rows[provider] = row
            controls = ttk.Frame(row.body)
            controls.pack(fill="x", pady=(8, 0))
            ttk.Button(controls, text="Select observation…", command=lambda p=provider: self.select(p)).grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=3)
            self.refresh_buttons[provider] = ttk.Button(controls, text="Re-read file", command=lambda p=provider: self.refresh(p), state="disabled")
            self.refresh_buttons[provider].grid(row=0, column=1, sticky="ew", pady=3)
            ttk.Button(controls, text="Clear selection", command=lambda p=provider: self.clear(p)).grid(row=1, column=0, columnspan=2, sticky="ew", pady=3)
            for column in (0, 1): controls.columnconfigure(column, weight=1)
        center.section(page, "First connection",
            "1. Configure an existing, least-privilege provider credential with the trusted owner collector. "
            "This window never receives API keys, client secrets or provider clients.\n\n"
            "2. Run the explicit read collector outside this window and publish its sanitized private observation. "
            "No automatic login, polling, model inference or provider action is introduced.\n\n"
            "3. Expand the provider row and select its observation file. Re-read explicitly after collecting a new sample. "
            "An observation older than 60 seconds is historical; provenance remains unverified.")
        center.section(page, "UniFi UDM · reference target, not an observed version",
            "Reference compatibility target: UniFi OS 5.1.33 / Network 10.6.106. "
            "The collector uses the official local Network Integration API with a selected site UUID and trusted HTTPS. "
            "Version compatibility is fixture-tested, not yet verified against your UDM. "
            "No private legacy API, TLS bypass, device adoption, reboot or firewall change is provided.")
        center.section(page, "What these collectors cover",
            "UniFi: returned adopted devices, online devices within that page and connected clients. "
            "NinjaOne: returned device and active-alert records. CrowdStrike: returned host and alert IDs. "
            "Device/client/host pages are capped at 100; NinjaOne alert responses at 200. "
            "Counts are returned records, not fleet totals. Oversized or partial failures clear all metrics. "
            "WAN rates, patch posture, sensor health and per-device details remain Unknown in this increment.")
        actions = ttk.Frame(page)
        actions.pack(fill="x", pady=(0, 10))
        ttk.Button(actions, text="Review governance", command=lambda: center.show("Governance")).grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=3)
        ttk.Button(actions, text="Connection activity", command=self.open_activity).grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Button(actions, text="Copy safe connection summary", command=self.copy).grid(row=1, column=0, columnspan=2, sticky="ew", pady=3)
        for col in (0, 1): actions.columnconfigure(col, weight=1)
        self.notice = center.text(page, "This page holds only sanitized values. Source selection does not authenticate the exporter or establish provider enforcement.", "Muted.TLabel")
        self.root.bind("<Destroy>", self.destroy, add="+")
        self.render()

    def select(self, provider):
        from tkinter import filedialog
        selected = filedialog.askopenfilename(parent=self.root, title=f"Select {provider} owner observation", filetypes=(("JSON observation", "*.json"),))
        if selected:
            self.paths[provider] = Path(selected)
            self.refresh_buttons[provider].configure(state="normal")
            self.refresh(provider)

    def open_setup(self):
        if self.setup_guide is not None and self.setup_guide.window is not None:
            self.setup_guide.window.lift()
            return self.setup_guide
        from .udm_setup_guide import UdmSetupGuide
        self.setup_guide = UdmSetupGuide(self)
        return self.setup_guide

    def refresh(self, provider):
        if provider not in self.paths: return
        old = (self.observations.get(provider), self.errors.get(provider))
        try:
            value = load_connection_observation(self.paths[provider])
            if value.provider != provider: raise ValueError("provider_mismatch")
            previous = self.observations.get(provider)
            if previous and previous.source_id == value.source_id and value.observed_at_ns <= previous.observed_at_ns and value != previous:
                raise ValueError("replayed_or_substituted_observation")
            self.observations[provider] = value
            self.errors.pop(provider, None)
        except (OSError, ValueError, TypeError, RecursionError):
            self.observations.pop(provider, None)
            self.errors[provider] = "Observation unavailable, invalid, wrong provider or replayed. Previous values cleared; inspect owner export and permissions."
        if old != (self.observations.get(provider), self.errors.get(provider)):
            self.record(provider, "Connection observation rejected; inspect the selected owner export." if provider in self.errors else "Connection observation loaded; source-reported values, enforcement Unknown.", provider in self.errors)
        self.render()

    def record(self, provider, detail, error=False):
        if hasattr(self.center, "activity_view"):
            self.center.record_activity(provider + ": " + detail, category="Connections", action="source",
                                        outcome="Failed" if error else "Recorded", severity="Warning" if error else "Info")

    def clear(self, provider):
        self.paths.pop(provider, None)
        self.observations.pop(provider, None)
        self.errors.pop(provider, None)
        self.refresh_buttons[provider].configure(state="disabled")
        self.record(provider, "Observation selection cleared locally; provider connection unchanged.")
        self.render()

    def render(self):
        recent, issues = 0, len(self.errors)
        for provider, row in self.rows.items():
            value = self.observations.get(provider)
            if value is None:
                row.update("Attention" if provider in self.errors else "Unknown", "Unknown · no valid observation · enforcement unassessed",
                    self.errors.get(provider, "Expand this row to select a sanitized owner observation. No connection test has run in this window."))
                continue
            age = value.freshness()
            good = age == "Recent source timestamp" and value.reason == "ok"
            recent += int(good)
            issue = age != "Recent source timestamp" or value.reason != "ok"
            issues += int(issue)
            stamp = time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime(value.observed_at_ns / 1e9))
            count = lambda v: "Unknown" if v is None else str(v)
            detail = (f"Recorded source report · {stamp} · {age}\nSource fingerprint: {value.source_id}\n"
                f"HTTP reachability: {value.reachability}\nAuthentication: {value.authentication}\nGovernance: enforcement unassessed\n"
                f"Read permissions: only completed requests observed; credential write privileges Unknown.\n{REASONS[value.reason]}\n\n"
                f"Devices/hosts returned: {count(value.devices_seen)} · Online in returned device page: {count(value.online_seen)}\n"
                f"Connected clients returned: {count(value.clients_seen)} · Alert records/IDs returned: {count(value.alerts_seen)}\n"
                "Bounded pages only; no fleet totals or historical rates. Stale counts describe the older sample. "
                "A successful request does not attest overall service health, data completeness, source identity or enforcement.")
            row.update("Attention" if issue else "Unknown", f"{age} · HTTP {value.reachability} · Auth {value.authentication} · enforcement unassessed", detail)
        self.summary.configure(text=f"{len(self.observations)} selected reports · {recent} recent successful collections · {issues} need review · enforcement Unknown")
        if hasattr(self.center, "status_rows"):
            self.center.status_rows["Connections"].update("Attention" if issues else "Unknown", self.summary.cget("text"),
                "Only selected frozen provider reports; no direct UI network access. Reachability and authentication never imply verified enforcement.")

    def set_active(self, active):
        self.active = active
        if self.timer is not None:
            self.root.after_cancel(self.timer)
            self.timer = None
        if active:
            self.render()
            self.timer = self.root.after(1000, self.tick)

    def tick(self):
        self.timer = None
        if self.active and not self.closed:
            if self.root.winfo_viewable() and self.root.state() != "iconic": self.render()
            self.timer = self.root.after(1000, self.tick)

    def open_activity(self):
        self.center.activity_view.variables["View"].set("Local session")
        self.center.activity_view.variables["Category"].set("Connections")
        self.center.show("Activity")

    def copy(self):
        import json
        from dataclasses import asdict
        text = json.dumps({"claim": "Recorded source reports; provenance/enforcement Unknown", "reports": [asdict(v) for v in self.observations.values()]}, indent=2)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.notice.configure(text="Copied sanitized observation metadata; selected file paths and credentials omitted.")

    def destroy(self, event):
        if event.widget is self.root:
            self.closed = True
            if self.timer is not None:
                self.root.after_cancel(self.timer)
                self.timer = None
            self.center = None
