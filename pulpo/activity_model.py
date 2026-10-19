"""Bounded session presentation data. Never a canonical audit journal."""
from collections import deque
from dataclasses import dataclass
import time


ACTIONS = {
    "opened": "Control Center opened", "message": "Local diagnostic message",
    "benchmark": "Benchmark comparison", "profile_save": "Performance setting save",
    "profile_restore": "Previous setting restore", "check": "Evidence fixture operation",
    "export": "Local report export", "source": "Observation read",
}
CATEGORIES = ("System", "Evidence", "Governance", "Connections", "AI")
OUTCOMES = ("Recorded", "Started", "Completed", "Failed", "Cancelled", "Saved", "Restored")
LEVELS = ("Info", "Warning", "Error")


@dataclass(frozen=True, slots=True)
class SessionEvent:
    sequence: int
    timestamp_ns: int
    category: str
    action: str
    outcome: str
    severity: str
    detail: str

    def public(self):
        # Strict allowlist: no free-form message, path, command, prompt or error.
        return {"sequence": self.sequence, "timestamp_ns": self.timestamp_ns,
                "category": self.category, "action": ACTIONS[self.action],
                "outcome": self.outcome, "severity": self.severity, "claim": "Recorded local session event"}


class SessionActivity:
    def __init__(self):
        self.events = deque(maxlen=500)
        self.sequence = self.dropped = 0
        self.reviewed = set()
        self.started_at_ns = time.time_ns()

    def add(self, detail, *, category="System", action="message", outcome="Recorded", severity="Info"):
        if category not in CATEGORIES or action not in ACTIONS or outcome not in OUTCOMES or severity not in LEVELS:
            raise ValueError("Invalid local activity metadata")
        if type(detail) is not str:
            raise ValueError("Activity detail must be text")
        # Bounded local display; raw text is never included in public exports.
        detail = "".join(c for c in detail[:8192] if c in "\n\t" or c.isprintable())
        self.sequence += 1
        if len(self.events) == self.events.maxlen:
            old = self.events[0]
            self.reviewed.discard(old.sequence)
            self.dropped += 1
        event = SessionEvent(self.sequence, time.time_ns(), category, action, outcome, severity, detail)
        self.events.append(event)
        return event

    def needs_attention(self, event):
        return event.severity != "Info" and event.sequence not in self.reviewed

    def select(self, *, category="All", outcome="All", severity="All", search="", since_ns=0, attention=False):
        search = search[:200].casefold()
        return tuple(e for e in reversed(self.events)
                     if (category == "All" or e.category == category)
                     and (outcome == "All" or e.outcome == outcome)
                     and (severity == "All" or e.severity == severity)
                     and e.timestamp_ns >= since_ns
                     and (not attention or self.needs_attention(e))
                     and (not search or search in (ACTIONS[e.action] + " " + e.detail + " " + e.outcome).casefold()))

    def review(self, sequence):
        if any(e.sequence == sequence for e in self.events):
            self.reviewed.add(sequence)

    def histogram(self, now_ns=None):
        """Last ten wall-clock minutes, retained local events only; no rates."""
        minute = (time.time_ns() if now_ns is None else now_ns) // 60_000_000_000
        bins = [{level: 0 for level in LEVELS} for _ in range(10)]
        for event in self.events:
            index = event.timestamp_ns // 60_000_000_000 - minute + 9
            if 0 <= index < 10:
                bins[index][event.severity] += 1
        return bins
