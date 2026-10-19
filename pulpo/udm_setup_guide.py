"""Guided non-secret handoff. No network calls, credentials or command execution."""
from pathlib import Path
import os

from .udm_setup import UdmSetup, collector_command, discovery_source, load_sites


class UdmSetupGuide:
    def __init__(self, page):
        import tkinter as tk
        from tkinter import ttk
        self.page, self.root = page, page.root
        self.window = tk.Toplevel(self.root)
        self.window.title("Pulpo · UDM connection setup")
        self.window.geometry("720x660")
        self.window.minsize(600, 580)
        self.window.transient(self.root)
        self.saved = {}
        self.discovery_origin = None
        self.fields = {key: tk.StringVar(master=self.root) for key in ("origin", "ca", "sites_output", "site", "inventory_output")}
        self.fields["origin"].set("https://192.168.1.1")
        self.labels = []
        container = ttk.Frame(self.window, padding=16)
        container.pack(fill="both", expand=True)
        self.text(container, "Set up a read-only UDM connection", "Heading.TLabel")
        self.text(container, "Keep API keys with the collector. This guide checks setup details locally; it cannot establish certificate trust or test a connection.")
        self.tabs = ttk.Notebook(container)
        self.tabs.pack(fill="both", expand=True, pady=8)
        self.steps = []
        self.scrollers = []
        for name in ("1 · Trust", "2 · Find site", "3 · Collect", "4 · Review"):
            viewport = ttk.Frame(self.tabs)
            self.tabs.add(viewport, text=name)
            canvas = tk.Canvas(viewport, highlightthickness=0, takefocus=True,
                               background=ttk.Style(self.root).lookup("TFrame", "background"))
            scrollbar = ttk.Scrollbar(viewport, orient="vertical", command=canvas.yview)
            canvas.configure(yscrollcommand=scrollbar.set)
            scrollbar.pack(side="right", fill="y")
            canvas.pack(side="left", fill="both", expand=True)
            frame = ttk.Frame(canvas, padding=12)
            item = canvas.create_window((0, 0), window=frame, anchor="nw")
            frame.bind("<Configure>", lambda event, c=canvas: c.configure(scrollregion=c.bbox("all")))
            canvas.bind("<Configure>", lambda event, c=canvas, i=item: c.itemconfigure(i, width=event.width))
            for key, amount in (("<Next>", 1), ("<Prior>", -1)):
                canvas.bind(key, lambda event, c=canvas, n=amount: c.yview_scroll(n, "pages"))
            self.scrollers.append(canvas)
            self.steps.append(frame)
            frame.bind("<Configure>", self.wrap, add="+")
        trust, sites, inventory, review = self.steps
        self.text(trust, "Confirm the address and certificate", "Heading.TLabel")
        self.entry(trust, "UDM HTTPS address · example shown, not discovered", "origin")
        self.entry(trust, "Trusted public CA certificate file · optional if system trust works", "ca", self.pick_ca)
        self.text(trust, "If certificate validation fails, obtain the public CA certificate through your known, trusted UDM management setup, or configure a certificate trusted by this computer. "
            "For this version the certificate must match the private IP address. A certificate obtained only from an unverified network connection is not an identity check.")
        self.text(trust, "Do not select a private key. Certificate verification stays enabled. The guide does not install certificates, change your UDM or bypass browser warnings.")
        ttk.Button(trust, text="Continue to site discovery", command=lambda: self.tabs.select(sites)).pack(anchor="w", pady=6)
        self.text(sites, "Find the site UUID", "Heading.TLabel")
        self.text(sites, "After certificate trust is established, the trusted collector can request the site list using its existing least-privilege API key. It exports UUIDs only, without site names. "
            "No API key is entered here. The key belongs in PULPO_UNIFI_API_KEY on the collector side.")
        self.entry(sites, "Site-list output file", "sites_output", lambda: self.pick_output("sites_output", "udm-sites.json"))
        self.handoff_buttons(sites, "sites")
        ttk.Button(sites, text="Load collected site list…", command=self.import_sites).pack(fill="x", pady=6)
        ttk.Label(sites, text="Choose a returned site UUID explicitly").pack(anchor="w")
        self.site_choices = ttk.Combobox(sites, textvariable=self.fields["site"], state="readonly", values=())
        self.site_choices.pack(fill="x", pady=4)
        self.text(inventory, "Collect a bounded inventory sample", "Heading.TLabel")
        self.text(inventory, "Use the site chosen in step 2, or enter a site UUID already known from your trusted management setup. "
            "The collector reads devices and connected clients. It does not change network settings.")
        self.entry(inventory, "Selected site UUID", "site")
        self.entry(inventory, "Inventory observation output file", "inventory_output", lambda: self.pick_output("inventory_output", "udm-observation.json"))
        self.handoff_buttons(inventory, "collect")
        self.text(inventory, "Saving a setup file or copying a command does not connect the UDM. Run the copied command in the same environment where you saved the setup; configure the key separately there.")
        self.text(review, "Review what actually happened", "Heading.TLabel")
        self.text(review, "After the collector finishes, load its inventory observation in Connections. Check the timestamp, authentication, coverage and any reported error. "
            "A successful read is not governance enforcement verification.")
        ttk.Button(review, text="Select UDM observation…", command=self.review).pack(fill="x", pady=8)
        self.text(review, "Certificate failure: fix trust or address matching first.\nAuthentication rejected: check the collector's key.\nAccess denied: check the provider's read permissions.\n"
            "Site list missing: complete step 2.\nStale sample: collect again explicitly.\nNo records: inspect returned coverage; do not infer a fleet total.")
        self.status = self.text(container, "Setup not yet validated · no network request or settings change has occurred.")
        ttk.Button(container, text="Close guide", command=self.window.destroy).pack(anchor="e", pady=6)
        self.window.bind("<Destroy>", self.destroy, add="+")
        self.window.bind("<FocusIn>", self.reveal, add="+")
        self.window.bind("<MouseWheel>", self.wheel, add="+")
        self.window.bind("<Button-4>", self.wheel, add="+")
        self.window.bind("<Button-5>", self.wheel, add="+")
        container.bind("<Configure>", self.wrap)

    def text(self, parent, value, style="TLabel"):
        from tkinter import ttk
        label = ttk.Label(parent, text=value, style=style, wraplength=620, justify="left")
        label.pack(fill="x", pady=(0, 10))
        self.labels.append(label)
        return label

    def entry(self, parent, label, key, browse=None):
        from tkinter import ttk
        caption = ttk.Label(parent, text=label, wraplength=510)
        caption.pack(anchor="w")
        self.labels.append(caption)
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(4, 10))
        ttk.Entry(row, textvariable=self.fields[key]).pack(side="left", fill="x", expand=True)
        if browse: ttk.Button(row, text="Browse…", command=browse).pack(side="left", padx=(6, 0))

    def wrap(self, event):
        width = max(250, self.window.winfo_width()-90)
        for label in self.labels: label.configure(wraplength=width)

    def reveal(self, event):
        # Toplevel bindings see descendant focus without global bindings.
        for frame, canvas in zip(self.steps, self.scrollers):
            if str(event.widget).startswith(str(frame) + "."):
                y = event.widget.winfo_rooty() - frame.winfo_rooty()
                top = canvas.canvasy(0)
                if y < top or y + event.widget.winfo_height() > top + canvas.winfo_height():
                    canvas.yview_moveto(max(0, y - 12) / max(1, frame.winfo_height()))
                break

    def wheel(self, event):
        for frame, canvas in zip(self.steps, self.scrollers):
            if str(event.widget).startswith(str(canvas)):
                direction = -1 if getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0 else 1
                canvas.yview_scroll(direction * 3, "units")
                return "break"

    def pick_ca(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(parent=self.window, title="Choose a trusted PUBLIC CA certificate, not a private key")
        if path: self.fields["ca"].set(path)

    def pick_output(self, key, name):
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(parent=self.window, initialfile=name, defaultextension=".json")
        if path: self.fields[key].set(path)

    def config(self, mode):
        setup = UdmSetup(self.fields["origin"].get().strip(), mode,
            self.fields["sites_output" if mode == "sites" else "inventory_output"].get(),
            self.fields["ca"].get() or None, self.fields["site"].get().strip() if mode == "collect" else None)
        if not Path(setup.output).parent.is_dir(): raise ValueError("Choose an output folder that already exists.")
        if setup.ca_file and not Path(setup.ca_file).is_file(): raise ValueError("Choose an existing public CA certificate file.")
        if mode == "collect" and self.discovery_origin and setup.origin != self.discovery_origin:
            raise ValueError("UDM address changed; discover its sites again.")
        return setup

    def handoff_buttons(self, parent, mode):
        from tkinter import ttk
        ttk.Button(parent, text="Review and save non-secret setup…", command=lambda: self.save(mode)).pack(fill="x", pady=4)
        ttk.Button(parent, text="Copy collector command", command=lambda: self.copy_command(mode)).pack(fill="x", pady=4)

    def save(self, mode):
        from dataclasses import asdict
        import json
        import tkinter as tk
        from tkinter import ttk, filedialog
        from .mcp_boundary import _publish_snapshot
        try:
            setup = self.config(mode)
        except (ValueError, TypeError, OSError):
            self.status.configure(text="Check the HTTPS address, absolute output path, CA file and selected site UUID. No setup saved.")
            return
        preview = tk.Toplevel(self.window)
        preview.title("Review non-secret UDM setup")
        preview.geometry("650x480")
        area = tk.Text(preview, wrap="word")
        area.pack(fill="both", expand=True, padx=12, pady=12)
        area.insert("end", json.dumps(asdict(setup), indent=2))
        area.configure(state="disabled")
        def publish():
            selected = filedialog.asksaveasfilename(parent=preview, initialfile=f"udm-{mode}-setup.json", defaultextension=".json")
            if not selected: return
            try:
                if Path(selected).resolve() in {Path(setup.output).resolve(), *(set() if not setup.ca_file else {Path(setup.ca_file).resolve()})}:
                    raise ValueError("Setup must be separate from certificate and output")
                _publish_snapshot(setup, selected)
                self.saved[mode] = (setup, selected)
                self.status.configure(text="Non-secret setup saved · no credential read, connection test or network change occurred.")
                preview.destroy()
            except (OSError, ValueError, RuntimeError):
                self.status.configure(text="Setup save failed. Choose a separate writable private file; no contents logged.")
        actions = ttk.Frame(preview, padding=12)
        actions.pack(fill="x")
        ttk.Button(actions, text="Save setup…", command=publish).pack(side="left")
        ttk.Button(actions, text="Cancel", command=preview.destroy).pack(side="right")
        return preview

    def copy_command(self, mode):
        try:
            setup = self.config(mode)
            old, selected = self.saved[mode]
            if old != setup: raise ValueError("Changed setup")
        except (ValueError, TypeError, OSError, KeyError):
            self.status.configure(text="Review and save this setup first. Changed details require a new saved handoff.")
            return
        try:
            command = collector_command(selected, windows=os.name == "nt")
        except ValueError:
            self.status.configure(text="Use a setup filename without control characters or typographic quotes before copying a command.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(command)
        self.status.configure(text="Collector command copied for this environment; run it yourself after configuring the key. Nothing executed here.")

    def import_sites(self):
        from tkinter import filedialog
        selected = filedialog.askopenfilename(parent=self.window, title="Choose the collected UDM site report", filetypes=(("JSON site report", "*.json"),))
        if not selected: return
        self.site_choices.configure(values=())
        self.fields["site"].set("")
        self.discovery_origin = None
        try:
            sites = load_sites(selected)
            if sites.source_id != discovery_source(self.fields["origin"].get().strip()): raise ValueError("Different origin")
            self.discovery_origin = self.fields["origin"].get().strip()
            self.site_choices.configure(values=sites.site_ids)
            self.status.configure(text=f"{len(sites.site_ids)} returned site UUIDs · choose one explicitly. " + ("More sites exist beyond this page." if sites.more_available else "No additional page reported.") + " Source identity remains unverified.")
        except (OSError, ValueError, TypeError, RecursionError):
            self.status.configure(text="Site report unavailable, invalid, stale or for another address. Check the collector result and discover again.")

    def review(self):
        self.page.select("UniFi UDM")
        self.status.configure(text="Review the UDM row in Connections. File selection does not establish source identity or enforcement.")

    def destroy(self, event):
        if event.widget is self.window:
            self.fields.clear()
            self.saved.clear()
            self.page = None
            self.window = None
