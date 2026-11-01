"""Explicit trusted-owner status projection; no UI writer or database opener.

Call only in the already-owning thread at an idle boundary. No factory, schema
initialization, migration, convergence, checkpoint or canonical mutation occurs.
"""
from hashlib import sha256
import os
import sqlite3
import time

from .mcp_boundary import _publish_snapshot
from .kernel import GovernanceKernel
from .operational_observation import OperationalObservation
from .orchestrator import PulpoOrchestrator
from .state import SQLiteKernelState


def freeze_operational_observation(orchestrator, *, check_database=False):
    if type(orchestrator) is not PulpoOrchestrator or type(check_database) is not bool or type(orchestrator.kernel) is not GovernanceKernel:
        raise TypeError("existing_canonical_owner_required")
    kernel = orchestrator.kernel
    backend = kernel._state
    source_id = sha256(f"{os.getpid()}:{id(backend)}".encode()).hexdigest()[:32]
    health, pending = "not_checked", None
    if type(backend) is SQLiteKernelState:
        connection = backend._connection
        if connection.in_transaction:
            raise ValueError("operational_observation_requires_idle_owner")
        source_id = connection.activity_id
        # Bypass activity accounting: observing must not inflate operation totals.
        if check_database:
            try:
                rows = sqlite3.Connection.execute(connection, "PRAGMA quick_check(1)").fetchall()
                health = "ok" if rows == [("ok",)] else "failed"
            except sqlite3.Error:
                health = "unavailable"
        try:
            present = sqlite3.Connection.execute(connection,
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='custody_evidence_outbox'").fetchone()
            if present:
                pending = sqlite3.Connection.execute(connection,
                    "SELECT COUNT(*) FROM custody_evidence_outbox WHERE projected = 0").fetchone()[0]
        except sqlite3.Error:
            pending = None
    try:
        audit_valid = kernel.verify_audit()
    except ValueError:
        # Canonical head/chain rejection is a reported failure, never a repair.
        audit_valid = False
    return OperationalObservation(source_id, time.time_ns(), kernel.policy_hash,
                                  audit_valid, health, pending)


def export_operational_observation(orchestrator, destination, *, check_database=False):
    return _publish_snapshot(freeze_operational_observation(orchestrator, check_database=check_database), destination)
