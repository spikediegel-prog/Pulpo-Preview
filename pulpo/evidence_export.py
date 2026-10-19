"""Trusted-owner projection of existing canonical evidence, never a UI service.

Call in the owning process/thread. No database, writer, prompt, credential,
permit, payload or authority object crosses the frozen file boundary.
"""
from collections import Counter, deque
from pathlib import Path
import hashlib
import os
import shutil
import sqlite3
import time

from .evidence_observation import AIUsage, EvidenceEvent, EvidenceObservation, EVENT_NAMES
from .mcp_boundary import _publish_snapshot
from .orchestrator import PulpoOrchestrator
from .state import SQLiteKernelState


def freeze_evidence_observation(orchestrator, *, check_database=False, ai=None):
    if type(orchestrator) is not PulpoOrchestrator:
        raise TypeError("canonical PulpoOrchestrator required")
    if type(check_database) is not bool or (ai is not None and type(ai) is not AIUsage):
        raise TypeError("invalid observation options")
    kernel = orchestrator.kernel
    backend = kernel._state
    database = {}
    source_id = hashlib.sha256(f"{os.getpid()}:{id(backend)}".encode()).hexdigest()[:32]
    if type(backend) is SQLiteKernelState:
        connection = backend._connection
        source_id = connection.activity_id
        database.update(connection.activity)
        # Diagnostic PRAGMAs use the same connection but bypass activity counting.
        # No checkpoint, vacuum, recovery, migration or separate database open.
        if connection.in_transaction:
            raise ValueError("observation_requires_idle_owner_transaction")
        database["health"] = "not_checked"
        if check_database:
            try:
                rows = sqlite3.Connection.execute(connection, "PRAGMA quick_check(1)").fetchall()
                database["health"] = "ok" if rows == [("ok",)] else "failed"
            except sqlite3.Error:
                database["health"] = "unavailable"
        try:
            paths = sqlite3.Connection.execute(connection, "PRAGMA database_list").fetchall()
            filename = next(row[2] for row in paths if row[1] == "main")
            if filename:
                path = Path(filename)
                database["database_bytes"] = path.stat().st_size
                wal = Path(str(path) + "-wal")
                database["wal_bytes"] = wal.stat().st_size if wal.exists() else 0
                volume = shutil.disk_usage(path.parent)
                database.update(volume_total=volume.total, volume_free=volume.free)
        except (OSError, StopIteration):
            # Partial readings remain absent, never a zero-capacity guess.
            database.pop("volume_total", None)
            database.pop("volume_free", None)
    audit = kernel.audit
    valid = kernel.verify_audit()
    counts = Counter()
    events = deque(maxlen=24)
    for record in audit:
        event, payload = record["event"], record["payload"]
        outcome = "recorded"
        if event == "decision":
            result = payload.get("outcome")
            if result in {"allow", "deny", "require_approval"}:
                counter, outcome = {"allow": ("allowed", "allowed"), "deny": ("denied", "denied"),
                                    "require_approval": ("approval_required", "approval_required")}[result]
                counts[counter] += 1
                if result == "deny" and payload.get("reason") in {"incomplete_intent", "invalid_cost", "budget_exceeded",
                    "action_not_allowed", "unknown_principal", "agent_action_not_allowed", "agent_resource_not_allowed", "agent_budget_exceeded"}:
                    outcome = "blocked_by_policy"
        if event in {"permit_consumed", "permit_rejected", "approval_rejected"}:
            counts[event] += 1
            if event.endswith("rejected"):
                outcome = "rejected"
        if event == "approval_rejected":
            if payload.get("reason") in {"approval_expired", "approval_expired_during_verification"}:
                counts["approval_expired"] += 1
            if payload.get("reason") in {"approval_id_replayed", "approval_nonce_replayed"}:
                counts["approval_replayed"] += 1
        # Only fixed event/outcome enums and existing hashes leave the owner.
        events.append(EvidenceEvent(record["timestamp_ns"], event if event in EVENT_NAMES else "other",
                                    outcome, record["hash"]))
    counters = {key: counts[key] for key in ("allowed", "denied", "approval_required", "permit_consumed",
                                            "permit_rejected", "approval_rejected", "approval_expired", "approval_replayed")}
    return EvidenceObservation(source_id, time.time_ns(), valid, len(audit), **database, **counters,
                               ai=ai or AIUsage(), events=tuple(events))


def export_evidence_observation(orchestrator, destination, *, check_database=False, ai=None):
    """Explicit owner-side export; does not install a timer or alter authority."""
    snapshot = freeze_evidence_observation(orchestrator, check_database=check_database, ai=ai)
    return _publish_snapshot(snapshot, destination)
