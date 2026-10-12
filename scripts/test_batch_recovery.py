"""Force-stop a child at disposable batch boundaries, then inspect recovery."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import platform
import sqlite3
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from pulpo import Decision, GovernanceKernel, Intent, Policy, ResourceScope, SQLiteKernelState
from pulpo.orchestrator import OrchestrationError, PulpoOrchestrator
from pulpo.traffic import Lane, Path as Route, TrafficControl

STAGES = ("queued", "before_write", "mid_transaction", "commit_race", "after_commit", "after_receipt")
ROWS = tuple((i, "disposable-derived-value") for i in range(8))
DIGEST = sha256(json.dumps(ROWS).encode()).hexdigest()
INTENT = Intent("fixture", "fixture-batch", "fixture:batch:" + DIGEST)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def kernel_for(state):
    return GovernanceKernel(Policy(frozenset({"fixture-batch"}), 0),
                            secret=b"disposable-recovery-fixture", state=state)


def router():
    return TrafficControl((Lane("sql", "sql", queue_limit=4),),
                          (Route("derived", "sql", INTENT, background=True),))


def checkpoint(stage, requested):
    if stage == requested:
        print("READY:" + stage, flush=True)
        if not sys.stdin.readline():
            raise RuntimeError("parent ended the interruption protocol")


def child(directory, stage):
    with ResourceScope() as cleanup:
        state = cleanup.own(SQLiteKernelState(directory / "governance.sqlite"))
        db = cleanup.own(sqlite3.connect(directory / "effects.sqlite"))
        db.execute("PRAGMA synchronous=FULL")
        kernel = kernel_for(state)
        decision = Decision(**json.loads((directory / "decision.json").read_text()))
        traffic = router()
        traffic.enqueue(INTENT, decision, ("derived",))
        checkpoint("queued", stage)
        with PulpoOrchestrator(kernel).traffic_dispatch(traffic) as dispatch:
            require(dispatch is not None, "batch failed to dispatch")
            checkpoint("before_write", stage)
            db.execute("BEGIN IMMEDIATE")
            db.executemany("INSERT INTO derived VALUES (?, ?)", ROWS[:4])
            checkpoint("mid_transaction", stage)
            db.executemany("INSERT INTO derived VALUES (?, ?)", ROWS[4:])
            if stage == "commit_race":
                print("READY:commit_race", flush=True)
                require(sys.stdin.readline().strip() == "GO", "missing commit signal")
                print("COMMITTING", flush=True)
            db.commit()
            if stage == "commit_race":
                # Keep the child alive if COMMIT wins the race, without recording
                # a receipt. The parent still forcibly terminates this process.
                sys.stdin.readline()
            checkpoint("after_commit", stage)
            # Fixture completion receipt is separate from canonical governance.
            # This deliberate second transaction exposes the post-commit gap.
            with db:
                db.execute("INSERT INTO receipts VALUES (?, ?)", (DIGEST, 8))
            checkpoint("after_receipt", stage)


def run_case(stage):
    require(stage in STAGES, "unknown interruption boundary")
    with tempfile.TemporaryDirectory(prefix="pulpo-batch-recovery-") as scratch:
        directory = Path(scratch)
        with SQLiteKernelState(directory / "governance.sqlite") as state:
            decision = kernel_for(state).evaluate(INTENT)
            require(decision.outcome == "allow", "fixture permit denied")
        (directory / "decision.json").write_text(json.dumps(asdict(decision)))
        with ResourceScope() as cleanup:
            db = cleanup.own(sqlite3.connect(directory / "effects.sqlite"))
            require(db.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal", "WAL unavailable")
            db.execute("PRAGMA synchronous=FULL")
            db.executescript("CREATE TABLE derived(id INTEGER PRIMARY KEY, value TEXT);"
                             "CREATE TABLE receipts(digest TEXT PRIMARY KEY, row_count INTEGER);")
        process = subprocess.Popen([sys.executable, "-W", "error", str(Path(__file__).resolve()),
                                    "--child", str(directory), "--stage", stage],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, cwd=REPO,
                                   creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        output = ""
        try:
            with ThreadPoolExecutor(max_workers=1) as reader:
                try:
                    line = reader.submit(process.stdout.readline).result(timeout=20)
                    require(line.strip() == "READY:" + stage, "child checkpoint failed: " + line)
                    if stage == "commit_race":
                        process.stdin.write("GO\n")
                        process.stdin.flush()
                        line = reader.submit(process.stdout.readline).result(timeout=20)
                        require(line.strip() == "COMMITTING", "commit boundary signal missing")
                    process.kill()  # SIGKILL on Linux, TerminateProcess on Windows.
                finally:
                    if process.poll() is None:
                        process.kill()
            output = process.communicate(timeout=10)[0]
            require(process.returncode != 0, "child was not force-stopped")
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=10)

        # Reopen in the parent after the child is reaped; no retry is scheduled.
        with ResourceScope() as cleanup:
            db = cleanup.own(sqlite3.connect(directory / "effects.sqlite", timeout=2))
            db.execute("PRAGMA synchronous=FULL")
            require(db.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "effect database corrupt")
            rows = db.execute("SELECT id,value FROM derived ORDER BY id").fetchall()
            receipts = db.execute("SELECT digest,row_count FROM receipts").fetchall()
            require(rows in ([], list(ROWS)), "partial batch survived")
            if stage in ("queued", "before_write", "mid_transaction"):
                require(not rows and not receipts, "unfinished batch persisted")
            elif stage == "after_commit":
                require(rows == list(ROWS) and not receipts, "post-commit gap misclassified")
            elif stage == "after_receipt":
                require(rows == list(ROWS) and receipts == [(DIGEST, 8)], "durable receipt missing")
            else:
                require(not receipts, "commit race unexpectedly recorded a receipt")
            require(not receipts or receipts == [(DIGEST, 8)], "receipt not bound to exact batch")
            # A rollback-only lock probe proves no orphan writer lock remains.
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO derived VALUES (99, 'lock-probe')")
            db.rollback()

            state = cleanup.own(SQLiteKernelState(directory / "governance.sqlite"))
            kernel = kernel_for(state)
            require(kernel.verify_audit(), "audit invalid after restart")
            consumed = sum(record["event"] == "permit_consumed" for record in kernel.audit)
            require(consumed == (0 if stage == "queued" else 1), "unexpected permit consumption")
            traffic = router()
            require(traffic.snapshot()["sql"] == {"queued": 0, "active": 0, "dropped": 0},
                    "volatile work unexpectedly recovered")
            # A queued-only interruption leaves the original permit unused.
            # Consumed permits must never execute a second effect after restart.
            traffic.enqueue(INTENT, decision, ("derived",))
            if stage == "queued":
                with PulpoOrchestrator(kernel).traffic_dispatch(traffic) as dispatch:
                    require(dispatch is not None, "unused permit lost before dispatch")
            else:
                try:
                    with PulpoOrchestrator(kernel).traffic_dispatch(traffic):
                        raise AssertionError("spent permit reached an effect")
                except OrchestrationError:
                    pass
            require(not kernel.consume(decision.permit, INTENT), "permit replay accepted")
            require(kernel.verify_audit(), "audit invalid after replay checks")
            require(traffic.snapshot()["sql"]["active"] == 0, "replay leaked active slot")
            require(rows == db.execute("SELECT id,value FROM derived ORDER BY id").fetchall(),
                    "recovery/replay changed effect rows")
            require(receipts == db.execute("SELECT digest,row_count FROM receipts").fetchall(),
                    "recovery invented a receipt")
            status = ("committed_with_receipt" if receipts else
                      "committed_without_receipt_requires_reconciliation" if rows else
                      "not_committed_permit_unused" if stage == "queued" else
                      "not_committed_permit_spent_no_retry")
            return {"stage": stage, "rows": len(rows), "receipts": len(receipts),
                    "recovery_status_before_replay_probe": status,
                    "permit_consumptions_before_probe": consumed,
                    "audit_valid": True, "partial_batch": False,
                    "child_returncode": process.returncode, "child_output": output,
                    "writer_lock_released": True, "permit_replay_rejected": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--child", type=Path)
    parser.add_argument("--stage", choices=STAGES)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    if args.child:
        child(args.child, args.stage)
        return
    if not 1 <= args.repeats <= 10:
        parser.error("repeats must be in [1, 10]")
    results = []
    for stage in STAGES:
        for _ in range(args.repeats):
            results.append(run_case(stage))
        print("PASS " + stage + ": atomic rows, receipt boundary, restart, locks and replay", flush=True)
    report = {"python": platform.python_version(), "platform": platform.platform(),
              "timestamp_utc": datetime.now(timezone.utc).isoformat(),
              "fixture": "disposable local WAL/FULL databases; real forced child termination",
              "limits": "commit_race samples a boundary, not guaranteed execution inside COMMIT; no power-loss claim",
              "source_sha256": {name: sha256((REPO / name).read_bytes()).hexdigest() for name in
                  ("scripts/test_batch_recovery.py", "pulpo/traffic.py", "pulpo/state.py", "pulpo/kernel.py",
                   "pulpo/orchestrator.py", "pulpo/resources.py")}, "results": results}
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print("Results: " + str(args.json.resolve()))


if __name__ == "__main__":
    main()
