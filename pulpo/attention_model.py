"""Bounded presentation of cached observations; no reads, writes or execution."""
from dataclasses import dataclass
import time

from .connection_observation import PROVIDERS, REASONS
from .evidence_observation import freshness
from .local_resources import level


KINDS = ("Problem", "Resource hint", "Information gap")


@dataclass(frozen=True, slots=True)
class AttentionItem:
    key: str
    kind: str
    title: str
    impact: str
    source: str
    observed_at_ns: int | None
    page: str
    action: str
    udm_setup: bool = False


def age_text(observed_at_ns, now_ns=None):
    if observed_at_ns is None:
        return "Age unknown"
    seconds = ((time.time_ns() if now_ns is None else now_ns) - observed_at_ns) / 1e9
    if seconds < 0:
        return f"Source time {abs(seconds):.0f}s ahead"
    if seconds < 60:
        return f"{int(seconds)}s old"
    if seconds < 3600:
        return f"{int(seconds // 60)}m old"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h old"
    return f"{int(seconds // 86400)}d old"


def attention_items(*, connections, connection_errors, evidence, evidence_error,
                    governance, governance_selected, resources, now_ns=None):
    """Derive fixed-rule items from already validated in-memory projections.

    Fixed providers/rules bound output. Error flags override old cached values.
    No event totals are promoted to incidents, and no resolved state is inferred.
    """
    now = time.time_ns() if now_ns is None else now_ns
    items = []

    def add(key, kind, title, impact, source, at, page, action=None, udm_setup=False):
        items.append(AttentionItem(key, kind, title, impact, source, at, page,
                                   action or "Open " + page, udm_setup))

    missing = []
    for provider in PROVIDERS:
        if provider in connection_errors:
            add("connection:" + provider + ":invalid", "Problem", provider + " observation unavailable",
                "The selected report could not be used. Provider status is unknown; inspect the export and its permissions.",
                provider + " · local observation read · source identity unverified", None, "Connections")
            continue
        report = connections.get(provider)
        if report is None:
            missing.append(provider)
            continue
        source = provider + " · source report " + report.source_id + " · identity unverified"
        age = report.freshness(now)
        if report.reason not in ("ok", "unknown"):
            title = "certificate validation failed" if report.reason == "tls" else "collection reported " + report.reason.replace("_", " ")
            setup = provider == "UniFi UDM" and report.reason in ("tls", "configuration")
            add("connection:" + provider + ":failure", "Problem", provider + ": " + title,
                REASONS[report.reason] + " This describes the reported collection, not overall provider health.",
                source, report.observed_at_ns, "Connections", "Open UDM setup guide" if setup else None, setup)
        elif report.reason == "unknown":
            add("connection:" + provider + ":unknown", "Information gap", provider + " collection not assessed",
                "The selected report has no completed collection result. Reachability and authentication remain unknown.",
                source, report.observed_at_ns, "Connections")
        if age != "Recent source timestamp":
            add("connection:" + provider + ":age", "Information gap", provider + ": " + age.lower() + " observation",
                "The source timestamp is stale or inconsistent. Collect a new sample through the trusted owner and re-read explicitly.",
                source, report.observed_at_ns, "Connections")
    if missing:
        add("connections:missing", "Information gap", "Connection observations not selected",
            "No selected report for: " + ", ".join(missing) + ". Unselected does not mean offline.",
            "Connections · local source selection", None, "Connections")

    if evidence_error:
        add("evidence:invalid", "Problem", "Evidence observation unavailable",
            "The selected export could not be used. Inspect its format, permissions and owner clock; previous values are not reused.",
            "Evidence · local observation read · source identity unverified", None, "Evidence")
    elif evidence is None:
        add("evidence:missing", "Information gap", "Evidence observation not selected",
            "Database activity, capacity and audit results cannot be assessed without a selected trusted-owner export.",
            "Evidence · local source selection", None, "Evidence")
    else:
        s = evidence
        source = "Evidence · source report " + s.source_id + " · identity unverified"
        at = s.observed_at_ns
        age = freshness(s, now)
        if age != "recent source timestamp":
            add("evidence:age", "Information gap", "Evidence: " + age + " observation",
                "The last source sample is historical or has a clock mismatch. Live rates and current database condition are unknown; inspect the owner export.",
                source, at, "Evidence")
        if not s.audit_valid:
            add("evidence:audit", "Problem", "Evidence source reports failed audit check",
                "Preserve evidence and investigate through the canonical owner path. This redacted view cannot independently verify the audit chain.",
                source, at, "Evidence")
        if s.health == "failed":
            add("evidence:health", "Problem", "Evidence source reports failed database check",
                "The reported physical database check failed. Inspect owner diagnostics before relying on the sample; no repair is run here.",
                source, at, "Evidence")
        elif s.health != "ok":
            add("evidence:health", "Information gap", "Database health not assessed",
                "The owner check is " + s.health.replace("_", " ") + ". A fresh timestamp alone does not establish database health.",
                source, at, "Evidence")
        if s.volume_total is None:
            add("evidence:capacity", "Information gap", "Evidence volume capacity unavailable",
                "Available space cannot be assessed from this sample. Inspect the trusted owner's volume observation.",
                source, at, "Evidence")
        else:
            used = (1 - s.volume_free / s.volume_total) * 100
            if used >= 85:
                add("evidence:capacity", "Resource hint", f"Evidence volume sample: {used:.1f}% used",
                    "Shared volume capacity crossed the existing 85% review threshold (95% attention). Not all use is Pulpo evidence; inspect retention through the governed owner path.",
                    source, at, "Evidence")
        if s.database_bytes is not None and s.wal_bytes is not None and s.wal_bytes > max(64 * 1024**2, s.database_bytes):
            add("evidence:wal", "Resource hint", "Evidence WAL sample is large relative to database",
                "Inspect checkpoint and backup conditions through the trusted owner. File size alone does not prove a fault or authorize cleanup.",
                source, at, "Evidence")
        # Cumulative errors, denials and permit/approval totals are not active incidents.

    if governance_selected and governance is not None and governance.state == "Attention":
        failed_audit = governance.policy.startswith("Recorded")
        add("governance:problem", "Problem",
            "Governance source reports failed audit check" if failed_audit else "Governance snapshot unavailable",
            "Preserve the reported evidence and inspect Governance. Export time, authenticity and enforcement remain unassessed." if failed_audit else
            "The selected snapshot could not be used. Inspect its path, format and permissions; no previous good value is reused.",
            "Governance · selected export · source time and identity unverified", None, "Governance")
    add("governance:coverage", "Information gap", "Governance enforcement coverage incomplete",
        "No snapshot is selected. Deployment enforcement and unresolved consequences remain unknown." if not governance_selected else
        "This metadata export cannot establish current deployment enforcement or unresolved consequences. Inspect its stated coverage and limitations.",
        "Governance · local source selection" if not governance_selected else "Governance · selected metadata export · source age unknown",
        None, "Governance")

    if resources is not None:
        at = int(resources.observed_at * 1e9)
        environment = {"Windows": "Windows", "Linux": "Linux", "Linux / WSL": "Linux / WSL VM"}.get(resources.source, "environment unknown")
        source = "Local OS resources · " + environment + " · volume shown in System"
        if now - at > 10_000_000_000 or at - now > 5_000_000_000:
            add("resources:age", "Information gap", "Local resource sample is historical or clock-inconsistent",
                "Resource hints describe the last local sample, not a current system-health assessment.", source, at, "System")
        unknown = []
        for key, label in (("cpu", "CPU"), ("memory", "Memory"), ("storage", "Storage")):
            metric = getattr(resources, key)
            state = level(metric.percent)
            if state == "Unknown":
                unknown.append(label)
            elif state in ("Elevated", "Attention"):
                add("resource:" + key, "Resource hint", f"{label} sample: {metric.percent:.1f}% used",
                    "The local sample crossed the existing 75% review threshold (90% attention). This is a resource hint, not deployment or governance health.",
                    source, at, "System")
        if unknown:
            add("resources:missing", "Information gap", "Some local resource readings unavailable",
                "Not assessed in the last sample: " + ", ".join(unknown) + ". Missing data is not zero.", source, at, "System")
    return tuple(sorted(items, key=lambda item: (KINDS.index(item.kind), item.key)))
