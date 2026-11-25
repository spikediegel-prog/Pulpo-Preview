"""Cache-only presentation helpers; names and labels never authenticate sources."""
from .evidence_observation import freshness
from pathlib import Path
import time


def source_paths(center):
    result = {}
    if getattr(center, "governance_path", None) is not None:
        result["Governance"] = center.governance_path
    evidence = getattr(center, "evidence_view", None)
    if evidence is not None and evidence.path is not None:
        result["Evidence"] = evidence.path
    connections = getattr(center, "connections_view", None)
    if connections is not None:
        result.update(connections.paths)
    return result


def test_named(path):
    return path is not None and "test-only" in str(path).casefold()


def _same_path(left, right):
    """Compare path labels using the current platform's lexical path rules."""
    try:
        return Path(left) == Path(right)
    except (TypeError, ValueError):
        return False


def elapsed_age(timestamp_ns, now_ns=None):
    """Wall-clock age of a recorded timestamp, never a liveness assessment."""
    if type(timestamp_ns) is not int or timestamp_ns <= 0:
        return "Unknown · timestamp unavailable"
    now_ns = time.time_ns() if now_ns is None else now_ns
    delta = now_ns - timestamp_ns
    if delta < 0:
        return "Unknown · timestamp ahead of this clock"
    seconds = delta // 1_000_000_000
    if seconds < 1:
        return "under 1s ago"
    if seconds < 60:
        return f"{seconds}s ago"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds}s ago"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {minutes}m ago"
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h ago"


def machine_description(value):
    """Short operator text only; never parse it as a host, URL or credential."""
    if type(value) is not str:
        raise ValueError("invalid_description")
    if any(not character.isprintable() for character in value):
        raise ValueError("invalid_description")
    value = value.strip()
    if len(value) > 48:
        raise ValueError("invalid_description")
    return value


def context_text(paths, labels, compact=False):
    hints = [name for name, path in paths.items() if test_named(path)]
    marked = [name for name, path in paths.items()
              if name in labels and _same_path(path, labels[name])]
    if compact and (hints or marked):
        basis = "filename hint + operator label" if hints and marked else "filename hint" if hints else "operator label"
        return f"Test context · {basis}, not authenticated."
    parts = []
    if hints:
        parts.append("Test-named source: " + ", ".join(hints) + " (unverified filename hint)")
    if marked:
        parts.append("Operator-labeled test observations: " + ", ".join(marked))
    return " · ".join(parts) + ". Source authenticity and enforcement remain Unknown." if parts else ""


def graph_state(snapshot, history, *, selected=False, error=False, pending=False, paused=False, now_ns=None):
    if pending:
        return "Selection restored · not read", "Press Re-read to inspect this export. Navigation does not read a restored selection."
    if error:
        return "Source read failed", "Previous readings cleared. Check the selected export, format and owner-only permissions."
    if not selected:
        return "No observation source selected", "Select an owner export to inspect database activity. Missing readings are not zero."
    if paused:
        return "Paused for review", "Displayed values are historical. Resume updates to re-read the export; the owner may continue running."
    if snapshot is None:
        return "No usable observation", "Re-read the selected owner export. No database is opened by this window."
    if freshness(snapshot, now_ns=now_ns) == "clock mismatch":
        return "Source clock mismatch", "The source timestamp is in the future. Check the owner clock; current rates are Unknown."
    if freshness(snapshot, now_ns=now_ns) == "stale":
        return "Source observation is stale", "Current rates are Unknown. The owner may have stopped or the file may be a frozen copy; service status is unassessed."
    counters = (snapshot.reads, snapshot.writes, snapshot.commits)
    if all(value is None for value in counters):
        return "Activity counters unavailable", "This export contains no read, write or commit counters. Do not infer zero activity."
    latest = history.points[-1][1] if history.points else {}
    rates = [latest.get(key) for key in ("reads", "writes", "commits")]
    if all(value is None for value in rates):
        if len(history.points) <= 1:
            return "Waiting for a second sample", "Rates require two distinct, comparable owner timestamps. Re-reading an unchanged file adds no sample."
        return "Waiting for comparable counters", "A time gap, missing or reset counter prevents a current rate. Missing history stays a gap."
    if any(value is None for value in rates):
        return "Partial activity readings", "Some current rates are unavailable. Shown rates use source-reported counter differences."
    return "Recent exported samples", "Measured counter differences; a recent timestamp is not proof of service liveness or enforcement."
