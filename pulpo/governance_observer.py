"""Presentation of the existing frozen export; never opens canonical state."""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import stat


@dataclass(frozen=True)
class GovernanceObservation:
    state: str = "Unknown"
    summary: str = "Unknown · Enforcement not assessed"
    source: str = "No snapshot selected. Deployment identity and freshness are unknown."
    policy: str = "Unknown · No policy observation."
    integrity: str = "Unknown · No audit observation."
    decisions: str = ("Unknown · This export contains no decision records. Approval, permit, "
                      "execution and reconciliation stages are unavailable; no counts are inferred.")


def observe_snapshot(path):
    """Read bounded public metadata using the existing private-file loader.

    File selection, schema validity and re-reading do not authenticate provenance,
    establish export freshness or verify deployed enforcement.
    """
    from .mcp_plugin import load_mcp_snapshot
    from .mcp_boundary import MCPBoundaryError
    try:
        target = Path(path).expanduser()
        # Avoid opening an accidentally selected directory/device/FIFO.
        if not target.is_absolute() or not stat.S_ISREG(target.lstat().st_mode):
            raise ValueError("not_regular_absolute_file")
        snapshot = load_mcp_snapshot(target)
        if (snapshot.audit_records == 0) != (snapshot.audit_tip is None):
            raise ValueError("inconsistent_audit_summary")
    except (OSError, ValueError, TypeError, MCPBoundaryError, RecursionError):
        # Do not echo arbitrary JSON, tokens, exception strings or a prior good value.
        return GovernanceObservation(
            state="Attention", summary="Attention · Snapshot unavailable or invalid",
            source="Read failed. Previous observations cleared. Check the export path, schema and file permissions.")
    read_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    result = "passed" if snapshot.audit_valid else "FAILED"
    return GovernanceObservation(
        state="Unknown" if snapshot.audit_valid else "Attention",
        summary=("Unknown · Snapshot read; enforcement not assessed" if snapshot.audit_valid else
                 "Attention · Source reports failed audit check"),
        source=(f"Read locally: {read_at}\nFormat: {snapshot.schema}\n"
                "Deployment, export time and source authenticity: Unknown. Refresh re-reads the file; it does not refresh the deployment."),
        policy=(f"Recorded · Source-reported policy fingerprint\n{snapshot.policy_hash}\n"
                "Rules, grants and human authority configuration are not included."),
        integrity=(f"Recorded · Source reports audit check {result}\n"
                   f"Audit records: {snapshot.audit_records} · these are not decision counts.\n"
                   f"Audit tip: {snapshot.audit_tip or 'None (empty audit)'}\n"
                   "This window has no audit records to independently verify the chain. A passing report does not establish enforcement."))
