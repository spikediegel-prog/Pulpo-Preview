"""Bounded presentation of existing source caches and session-local read attempts."""
from dataclasses import dataclass
import time

from .connection_observation import PROVIDERS, REASONS
from .attention_model import age_text


SOURCE_KEYS = ("Governance", "Evidence", *PROVIDERS)


@dataclass(frozen=True)
class SourceRead:
    recorded_at_ns: int
    succeeded: bool


@dataclass(frozen=True)
class SourceHealth:
    key: str
    page: str
    selected: bool
    read: SourceRead | None
    observed_at_ns: int | None
    source_id: str
    cached: bool
    freshness: str
    problem: bool
    issues: tuple[str, ...]
    coverage: str
    unknowns: str
    next_step: str

    @property
    def read_status(self):
        return "Not selected" if not self.selected else "Not read" if self.read is None else "Read OK" if self.read.succeeded else "Read failed"


def source_health(*, governance_selected, governance, evidence_selected, evidence, evidence_error,
                  connections_selected, connections, connection_errors, reads, now_ns=None):
    """No I/O, credentials, canonical state, history accumulation or health score."""
    now_ns = time.time_ns() if now_ns is None else now_ns
    result = []
    for key in SOURCE_KEYS:
        selected = bool(governance_selected if key == "Governance" else evidence_selected if key == "Evidence" else key in connections_selected)
        read = reads.get(key) if selected else None
        read_failed = read is not None and not read.succeeded
        observed = None
        source_id = "Unknown"
        issues = []
        cached = False
        problem = False
        page = key if key in {"Governance", "Evidence"} else "Connections"
        if key == "Governance":
            coverage = "Reported policy fingerprint, audit count, tip and audit-check result. No decision records."
            unknowns = "Export time, exporter identity, current rules/grants, approval bindings and deployed enforcement are Unknown."
            value = governance if selected and not read_failed and governance.policy.startswith("Recorded") else None
            failed = read_failed or selected and governance.state == "Attention" and value is None
            cached = value is not None
            if cached and governance.state == "Attention":
                problem = True
                issues.append("Source reports failed audit integrity; preserve evidence and inspect the canonical owner.")
        elif key == "Evidence":
            coverage = "Source-reported database/audit checks, nullable counters, latest-request AI usage and at most 24 redacted record references."
            unknowns = "Source authenticity, complete history, correlated action stages, verified recovery and external consequences are Unknown. Missing counters are not zero."
            failed = read_failed or selected and bool(evidence_error)
            value = evidence if selected and not failed else None
            cached = value is not None
            if cached:
                observed, source_id = value.observed_at_ns, value.source_id
                if not value.audit_valid:
                    problem = True
                    issues.append("Source reports failed audit integrity; preserve evidence and inspect the canonical owner.")
                if value.health != "ok":
                    problem = problem or value.health == "failed"
                    issues.append(f"Reported database check: {value.health.replace('_', ' ')}. This is separate from audit integrity.")
        else:
            coverage = ("Bounded returned device/client pages, maximum 100 records each; online count covers only the returned device page."
                        if key == "UniFi UDM" else "Bounded returned device page (100) and alert records (200); no fleet totals."
                        if key == "NinjaOne" else "Bounded returned host and alert-ID pages (100 each); no fleet totals.")
            unknowns = "Exporter authenticity, full fleet coverage, credential write privileges, overall service health and governance enforcement are Unknown."
            failed = read_failed or selected and key in connection_errors
            value = connections.get(key) if selected and not failed else None
            cached = value is not None
            if cached:
                observed, source_id = value.observed_at_ns, value.source_id
                coverage = f"Reported collection: {REASONS[value.reason]}\n" + coverage
                if value.reason != "ok":
                    problem = value.reason != "unknown"
                    issues.append(REASONS[value.reason])
        if failed or read is not None and not read.succeeded:
            # A failed current read must override any stale cache in every source.
            cached, observed, source_id = False, None, "Unknown"
            problem = True
            issues = ["Local read failed. Previous observations cannot establish current file readability. Check the existing source page."]
        if not selected:
            fresh = "Unknown"
            step = f"Open {page} and select the appropriate trusted-owner export. No source selected does not mean offline."
        elif not cached:
            fresh = "Unknown"
            step = (f"Open {page}; check the selected file, expected format and owner-only permissions in Ubuntu. "
                    "Have the trusted owner republish if needed, then explicitly re-read. Do not loosen permissions or select a raw database/credential.")
        elif observed is None:
            fresh = "Time unknown"
            step = "This Governance format has no export timestamp. Re-reading cannot establish freshness; ask the trusted owner to assess deployment state."
        else:
            seconds = (now_ns - observed) / 1e9
            fresh = "Clock mismatch" if seconds < -5 else "Stale" if seconds > (15 if key == "Evidence" else 60) else "Recent"
            if fresh == "Clock mismatch":
                issues.append("Source clock is ahead by more than five seconds; independent clock synchronization remains Unknown.")
            step = (f"Ask the trusted owner to publish a new observation, then open {page} to re-read. Re-reading an unchanged file does not refresh its source timestamp."
                    if fresh == "Stale" else f"Inspect the reported check on {page}; a successful file read is separate from that check."
                    if issues else f"Open {page} for the bounded observation. Recent is a timestamp description, not a service-health or enforcement verdict.")
        if key == "UniFi UDM" and cached and value.reason == "tls":
            step = "Open Connections → Guided UDM setup and review independently trusted certificate requirements. Do not bypass TLS validation."
        result.append(SourceHealth(key, page, selected, read, observed, source_id, cached, fresh, problem,
                                   tuple(issues), coverage, unknowns, step))
    return tuple(result)


def source_age(row, now_ns=None):
    return age_text(row.observed_at_ns, now_ns=now_ns)
