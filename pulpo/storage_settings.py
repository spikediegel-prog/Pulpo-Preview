"""Local storage plan editor. Never opens, mounts, tests or exports to its path."""
from . import storage_policy as policy


class StorageSettings:
    def __init__(self, center, page):
        import tkinter as tk
        from tkinter import ttk
        self.choice = tk.StringVar(master=center.root, value="")
        self.destination = tk.StringVar(master=center.root, value="")
        self.acknowledged = tk.BooleanVar(master=center.root, value=False)
        center.text(page, "Customer evidence storage plan", "Heading.TLabel")
        center.text(page, policy.RESPONSIBILITY, "Muted.TLabel")
        center.text(page, "Optional planning record only. Save with Remember this setup. "
            "The destination is not checked or activated; it must already be mounted and meet the owner's export permissions. "
            "No credentials, network discovery, transfer schedule or retention/deletion setting is configured here.", "Muted.TLabel")
        ttk.Combobox(page, textvariable=self.choice, values=("", *policy.CHOICES.values()), state="readonly").pack(fill="x", pady=4)
        center.text(page, "Planned public-export destination (absolute path on the owner's Linux filesystem)", "Muted.TLabel")
        ttk.Entry(page, textvariable=self.destination).pack(fill="x", pady=4)
        self.traces = [(variable, variable.trace_add("write", self.changed))
                       for variable in (self.choice, self.destination)]
        center.text(page, policy.ACKNOWLEDGMENT, "Muted.TLabel")
        box = ttk.Checkbutton(page, text="I acknowledge these storage responsibilities", variable=self.acknowledged)
        box.pack(anchor="w", pady=4)
        center.text(page, "Changing the choice or path clears acknowledgment. Clear both fields to remove the saved plan on the next setup save. "
            "Acknowledgment is a local preference, not a signed approval, compliance verdict or verified storage connection.", "Muted.TLabel")
        center.text(page, policy.PLANNED, "Muted.TLabel")
        center.text(page, "Keep enforcement-critical state, replay guards, unresolved consequences and tamper evidence in their existing governed path. "
            "Export failure never authorizes deletion. Full audit archival, verified delivery and safe pruning are not implemented by this screen.", "Muted.TLabel")

    def changed(self, *args):
        self.acknowledged.set(False)

    def close(self):
        for variable, trace in self.traces:
            variable.trace_remove("write", trace)
        self.traces.clear()
        self.choice = self.destination = self.acknowledged = None

    def capture(self):
        if not self.choice.get() and not self.destination.get() and not self.acknowledged.get():
            return None
        key = next((key for key, label in policy.CHOICES.items() if label == self.choice.get()), None)
        return policy.validate({"revision": policy.REVISION, "choice": key,
            "destination": self.destination.get(), "acknowledged": self.acknowledged.get()})

    def restore(self, value):
        if value is None:
            return
        policy.validate(value)
        self.choice.set(policy.CHOICES[value["choice"]])
        self.destination.set(value["destination"])
        self.acknowledged.set(True)
