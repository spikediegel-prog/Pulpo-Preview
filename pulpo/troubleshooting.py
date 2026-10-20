"""Fixed, non-authoritative findings from existing local observation caches."""
from dataclasses import dataclass
import json

from .decision_explorer import record_time
from .connection_observation import PROVIDERS


@dataclass(frozen=True)
class Finding:
    key: str
    title: str
    state: str
    checked_at_ns: int | None
    source_at_ns: int | None
    cause: str
    impact: str
    next_step: str
    page: str


def findings(sources, evidence=None, *, local_checked_at_ns=None, cleanup_blocked=False):
    """No I/O. No raw source/error text, identities, paths or arbitrary report fields."""
    rows = [Finding("runtime", "Local UI runtime", "Recorded" if local_checked_at_ns else "Unknown",
        local_checked_at_ns, None,
        "Explicit local diagnostic refresh completed." if local_checked_at_ns else "No troubleshooting runtime check has completed in this session.",
        "This window running does not prove kernel, collector or service health.",
        "Check this row to refresh existing local diagnostics; open Diagnostics for environment details.", "Diagnostics"),
        Finding("services", "Pulpo service health", "Unknown", None, None,
        "No live service-health observation contract is configured in Control Center.",
        "Service uptime, collector liveness and deployment availability cannot be established here.",
        "Ask the trusted deployment owner to inspect the intended Ubuntu service and its status. Do not infer a service name or restart from missing evidence.", "Diagnostics")]
    for source in sources:
        if source.key not in {"Governance", "Evidence", *PROVIDERS}:
            continue
        checked = source.read.recorded_at_ns if source.read else None
        if not source.selected:
            state, cause = "Unknown", "No owner export selected."
        elif source.read and not source.read.succeeded:
            state, cause = "Needs attention", "The latest local file read failed. Previous cached values cannot establish current readability."
        elif source.problem:
            state, cause = "Needs attention", "The cached source reports a failed check. A successful local file read is separate from that check."
        elif not source.cached or source.read is None:
            state, cause = "Unknown", "No usable locally read observation is available."
        elif source.freshness in {"Stale", "Clock mismatch"}:
            state, cause = "Needs attention", "Source timestamp is stale or ahead of the local clock. Re-reading does not renew that timestamp."
        elif source.issues:
            state, cause = "Unknown", "The cached source reports an unavailable, unchecked or incomplete observation."
        else:
            state, cause = "Recorded", "A local file read and bounded source observation are recorded. Source authenticity remains Unknown."
        rows.append(Finding(source.key, source.key + " export", state, checked, source.observed_at_ns,
            cause, "This observation does not establish current service availability, full coverage or enforcement.",
            "Select or re-read the trusted-owner export on its source page. Inspect Source health for reported checks and freshness. Never loosen permissions or provide credentials.", source.page))
    source = next((row for row in sources if row.key == "Evidence"), None)
    usable = source is not None and source.cached and source.read is not None and source.read.succeeded and not source.problem
    value = evidence if usable else None
    state, cause = "Unknown", "No usable evidence capacity observation is available."
    if value is not None and value.volume_total is not None:
        free, total = value.volume_free, value.volume_total
        state = "Needs attention" if free / total < .1 else "Recorded"
        cause = f"Source-reported evidence volume: {free} of {total} bytes free."
        if source.freshness in {"Stale", "Clock mismatch"}:
            state = "Needs attention"
            cause += " Source timestamp is stale or ahead of the local clock."
    rows.append(Finding("storage", "Evidence storage capacity", state,
        source.read.recorded_at_ns if source and source.read else None,
        value.observed_at_ns if value else None, cause,
        "Below 10% free is an attention hint. Exported capacity may be historical; it is not local WSL disk capacity or a write/recovery test.",
        "Ask the evidence owner to inspect the reported volume and publish a current export; re-read Evidence. Do not delete evidence to clear a warning.", "Evidence"))
    rows.append(Finding("cleanup", "Benchmark worker cleanup", "Needs attention" if cleanup_blocked else "Unknown", None, None,
        "The existing benchmark controls report unverified cleanup." if cleanup_blocked else "No cleanup failure is currently flagged by this window; no independent service/process scan was performed.",
        "Unverified cleanup blocks further performance operations; this display cannot clear that block.",
        "Open Tuning & benchmarks and retain the bounded result for operator investigation. No automatic retry or repair.", "Tuning & benchmarks"))
    return tuple(rows)


def stamp(value):
    return "Unknown" if value is None else record_time(value)


def support_report(rows, generated_at_ns):
    """Export only our fixed projections; never serialize source objects or UI state."""
    return json.dumps({
        "schema": "pulpo.wsl-troubleshooting.v1", "claim": "Recorded local diagnostic projection",
        "generated_at": stamp(generated_at_ns),
        "scope": "Frozen preview. Check times are local UI receipt times, not source freshness or authenticated timestamps.",
        "authority_effect": "none", "enforcement": "Unknown",
        "excluded": "Paths, host/device identifiers, source fingerprints, raw logs, credentials and raw errors are excluded by construction.",
        "findings": [{"check": row.title, "state": row.state, "local_check_at": stamp(row.checked_at_ns),
            "source_timestamp": stamp(row.source_at_ns), "cause": row.cause, "impact": row.impact,
            "next_step": row.next_step} for row in rows],
    }, indent=2) + "\n"
