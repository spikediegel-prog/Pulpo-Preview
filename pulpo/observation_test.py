"""Explicit standalone TEST ONLY owner; never imported or started by the UI."""
import argparse
import json
import os
from pathlib import Path
import tempfile
import time

from .kernel import GovernanceKernel, Intent, Policy
from .orchestrator import PulpoOrchestrator
from .state import SQLiteKernelState
from .mcp_boundary import export_mcp_snapshot
from .evidence_export import export_evidence_observation


def run(*, cycles=30, interval=2):
    # Validate before creating any files. Finite even if left unattended.
    if type(cycles) is not int or not 1 <= cycles <= 60:
        raise ValueError("cycles must be an integer from 1 to 60")
    if type(interval) is not int or not 1 <= interval <= 10:
        raise ValueError("interval must be an integer from 1 to 10 seconds")
    if os.name != "posix":
        raise ValueError("run this test in Ubuntu")
    folder = Path(tempfile.mkdtemp(prefix="pulpo-TEST-ONLY-"))
    governance = folder / "TEST-ONLY-governance.json"
    evidence = folder / "TEST-ONLY-evidence.json"
    (folder / "TEST-ONLY.txt").write_text(
        "Isolated synthetic workload, not a production deployment.\n"
        "Only the two TEST-ONLY JSON exports may be selected/copied to the observer.\n"
        "No external action, human approval, AI request or provider call was made.\n"
        "Owner-reported passing checks do not prove deployed enforcement.\n"
        "Frozen exports become historical after this process stops.\n", encoding="utf-8")
    print("TEST ONLY — synthetic decisions; no external execution", flush=True)
    print(f"Governance: {governance}", flush=True)
    print(f"Evidence: {evidence}", flush=True)
    # No existing database is accepted. Only this unique disposable owner state
    # is created; the private database is removed after closing its connection.
    with tempfile.TemporaryDirectory(prefix="private-state-", dir=folder) as private:
        backend = SQLiteKernelState(Path(private) / "test.sqlite")
        try:
            kernel = GovernanceKernel(Policy(frozenset({"test.inspect"}), 0), state=backend)
            owner = PulpoOrchestrator(kernel)
            for index in range(cycles):
                intent = Intent("agent:test-only", "test.inspect", "fixture:test-only", 0,
                                f"test-only-{index}")
                decision = kernel.evaluate(intent)
                if decision.outcome != "allow" or not decision.permit:
                    raise RuntimeError("test allow check failed")
                if not kernel.consume(decision.permit, intent):
                    raise RuntimeError("test first-consume check failed")
                if kernel.consume(decision.permit, intent):
                    raise RuntimeError("test replay rejection failed")
                denied = kernel.evaluate(Intent("agent:test-only", "test.forbidden", "fixture:test-only"))
                if denied.outcome != "deny" or denied.permit is not None:
                    raise RuntimeError("test policy denial failed")
                if not kernel.verify_audit():
                    raise RuntimeError("test audit verification failed")
                # The existing boundary exports metadata only; no permit/key/DB.
                export_mcp_snapshot(owner, governance)
                sample = export_evidence_observation(owner, evidence, check_database=True)
                print(json.dumps({"classification": "TEST ONLY", "cycle": index + 1,
                    "allowed": sample.allowed, "denied": sample.denied,
                    "consumed": sample.permit_consumed, "rejected": sample.permit_rejected,
                    "audit_valid": sample.audit_valid}), flush=True)
                if index + 1 < cycles:
                    time.sleep(interval)
        finally:
            backend.close()
    print("TEST COMPLETE — exports are frozen; source freshness will expire.", flush=True)
    return folder


def main():
    parser = argparse.ArgumentParser(description="Isolated TEST ONLY decisions and public observation exports. No external execution.")
    parser.add_argument("--cycles", type=int, choices=range(1, 61), default=30, metavar="1..60")
    parser.add_argument("--interval", type=int, choices=range(1, 11), default=2, metavar="1..10")
    args = parser.parse_args()
    try:
        run(cycles=args.cycles, interval=args.interval)
    except KeyboardInterrupt:
        print("TEST STOPPED — any published exports are historical.")
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
