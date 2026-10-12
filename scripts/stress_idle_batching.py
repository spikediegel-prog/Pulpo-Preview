"""Bounded disposable idle-batch stress fixtures with concurrent read-only SQLite readers."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import platform
import sqlite3
import statistics
import subprocess
import sys
import tempfile
from threading import Event
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from pulpo import GovernanceKernel, Intent, Policy, ResourceScope, SQLiteKernelState
from pulpo.orchestrator import PulpoOrchestrator
from pulpo.traffic import Backpressure, Lane, Path as Route, TrafficControl


@dataclass(frozen=True)
class Scenario:
    name: str
    foreground: int = 64
    batches: int = 8
    batch_rows: int = 128
    readers: int = 2
    interval: float = .003
    burst: int = 1
    prefill: bool = False
    hold_ms: int = 0
    foreground_offset: float = 0


SCENARIOS = {
    item.name: item for item in (
        Scenario("small_batch", batch_rows=32),
        Scenario("medium_batch", batch_rows=512),
        Scenario("large_batch", batch_rows=4096),
        Scenario("bursts", foreground=96, burst=24, interval=.015, prefill=True),
        Scenario("sustained_foreground", foreground=160, interval=0, prefill=True),
        Scenario("read_pressure", foreground=96, batch_rows=512, readers=8),
        Scenario("slow_active_batch", batch_rows=512, readers=4, hold_ms=40,
                 foreground_offset=.005),
    )}
QUEUE_LIMIT, RESERVE = 8, 2
PAYLOAD = "disposable-derived-value:" + "x" * 232


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def percentile(values, fraction=.95):
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)] if values else 0


def peak_memory_mib():
    if sys.platform.startswith("linux"):
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    if os.name == "nt":
        import ctypes
        class Counters(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_ulong), ("faults", ctypes.c_ulong)] + [
                (name, ctypes.c_size_t) for name in ("peak", "working", "quota_peak_paged",
                 "quota_paged", "quota_peak_nonpaged", "quota_nonpaged", "pagefile", "peak_pagefile")]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        function = ctypes.windll.psapi.GetProcessMemoryInfo
        function.argtypes = (ctypes.c_void_p, ctypes.POINTER(Counters), ctypes.c_ulong)
        require(function(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(counters),
                         counters.cb), "memory measurement failed")
        return counters.peak / 2**20
    return None


class Pool:
    def __init__(self, workers):
        self.executor = ThreadPoolExecutor(max_workers=workers)
    def close(self):
        self.executor.shutdown(wait=True, cancel_futures=True)


def observe(path, stop, ready, transaction_active):
    with ResourceScope() as cleanup:
        db = cleanup.own(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5))
        db.execute("PRAGMA query_only=ON")
        try:
            db.execute("INSERT INTO foreground VALUES (-1)")
        except sqlite3.OperationalError:
            pass
        else:
            raise AssertionError("observer connection accepted a write")
        ready.set()
        count, maximum, total, during_write = 0, 0.0, 0.0, 0
        while not stop.is_set():
            started = time.perf_counter()
            writing = transaction_active.is_set()
            db.execute("SELECT COUNT(*) FROM derived").fetchone()
            during_write += writing and transaction_active.is_set()
            elapsed = time.perf_counter() - started
            count += 1
            total += elapsed
            maximum = max(maximum, elapsed)
            stop.wait(.001)
        return {"reads": count, "read_max_ms": maximum * 1000,
                "read_total_seconds": total, "read_only_verified": True,
                "reads_during_write_transaction": during_write}


def write_job(path, job, hold_ms, transaction_active):
    started = time.perf_counter()
    with ResourceScope() as cleanup:
        db = cleanup.own(sqlite3.connect(path, timeout=5))
        db.execute("PRAGMA synchronous=FULL")
        try:
            with db:
                db.execute("BEGIN IMMEDIATE")
                transaction_active.set()
                if job["background"]:
                    db.executemany("INSERT INTO derived VALUES (?,?,?)", job["rows"])
                    if hold_ms:
                        time.sleep(hold_ms / 1000)
                else:
                    db.execute("INSERT INTO foreground VALUES (?)", (job["index"],))
        finally:
            transaction_active.clear()
        committed = time.perf_counter()
    return {"write_ms": (committed - started) * 1000, "committed_at": committed}


def run_case(scenario):
    with tempfile.TemporaryDirectory(prefix="pulpo-idle-stress-") as scratch, ResourceScope() as cleanup:
        directory = Path(scratch).resolve()
        effect_path = directory / "effects.sqlite"
        db = cleanup.own(sqlite3.connect(effect_path))
        require(db.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal", "WAL unavailable")
        db.execute("PRAGMA synchronous=FULL")
        db.executescript("CREATE TABLE foreground(id INTEGER PRIMARY KEY);"
                         "CREATE TABLE derived(batch INTEGER, row_id INTEGER, value TEXT,"
                         "PRIMARY KEY(batch,row_id));")
        state = cleanup.own(SQLiteKernelState(directory / "governance.sqlite"))
        kernel = GovernanceKernel(Policy(frozenset({"fixture-write"}), 0),
                                  secret=b"disposable-stress-fixture", state=state)
        owner = PulpoOrchestrator(kernel)
        jobs = []
        for index in range(scenario.foreground):
            jobs.append({"id": "fg-" + str(index), "background": False, "index": index,
                         "arrival": scenario.foreground_offset + (index // scenario.burst) * scenario.interval,
                         "intent": Intent("fixture", "fixture-write", f"fixture:foreground:{index}")})
        for index in range(scenario.batches):
            rows = tuple((index, row, PAYLOAD) for row in range(scenario.batch_rows))
            digest = sha256(json.dumps(rows).encode()).hexdigest()
            jobs.append({"id": "bg-" + str(index), "background": True, "rows": rows,
                         "arrival": 0, "intent": Intent("fixture", "fixture-write", "fixture:batch:" + digest)})
        traffic = TrafficControl((Lane("sql", "sql", queue_limit=QUEUE_LIMIT,
                                       foreground_reserve=RESERVE),),
                                 tuple(Route(j["id"], "sql", j["intent"], j["background"]) for j in jobs))
        decisions = {j["id"]: kernel.evaluate(j["intent"]) for j in jobs}
        require(all(d.outcome == "allow" for d in decisions.values()), "fixture permit denied")
        by_id = {j["id"]: j for j in jobs}
        pending = list(jobs)
        completed, admitted = set(), set()
        backpressure = {"foreground": 0, "background": 0}
        maximum_queue, maximum_background, reserve_observed = 0, 0, False
        foreground_latency, background_wait, writes, starts = [], [], [], []
        active = None
        last_foreground_commit = 0.0
        arrivals_during_background = 0
        if scenario.prefill:
            for job in jobs:
                if job["background"] and len(admitted) < QUEUE_LIMIT - RESERVE:
                    traffic.enqueue(job["intent"], decisions[job["id"]], (job["id"],))
                    admitted.add(job["id"])
                    pending.remove(job)
        writer = cleanup.own(Pool(1)).executor
        readers = cleanup.own(Pool(scenario.readers)).executor
        stop = Event()
        transaction_active = Event()
        readiness = [Event() for _ in range(scenario.readers)]
        observations = [readers.submit(observe, effect_path, stop, event, transaction_active) for event in readiness]
        try:
            require(all(event.wait(10) for event in readiness), "reader startup failed")
            started, cpu_started = time.perf_counter(), time.process_time()
            while len(completed) != len(jobs):
                now = time.perf_counter()
                require(now - started < 45, "stress fixture exceeded bounded deadline")
                if active is not None and active[0].done():
                    future, context, job = active
                    active = None
                    try:
                        result = future.result()
                    except BaseException:
                        context.__exit__(*sys.exc_info())
                        raise
                    else:
                        context.__exit__(None, None, None)
                    completed.add(job["id"])
                    writes.append(result["write_ms"])
                    if not job["background"]:
                        last_foreground_commit = max(last_foreground_commit, result["committed_at"])
                        foreground_latency.append((result["committed_at"] - started - job["arrival"]) * 1000)
                for job in tuple(pending):
                    if now - started < job["arrival"]:
                        continue
                    try:
                        traffic.enqueue(job["intent"], decisions[job["id"]], (job["id"],))
                    except Backpressure:
                        backpressure["background" if job["background"] else "foreground"] += 1
                    else:
                        pending.remove(job)
                        admitted.add(job["id"])
                        if active is not None and active[2]["background"] and not job["background"]:
                            arrivals_during_background += 1
                        if not job["background"]:
                            bg_count = sum(by_id[identity]["background"] for identity in admitted - completed
                                           if active is None or identity != active[2]["id"])
                            reserve_observed |= bg_count == QUEUE_LIMIT - RESERVE
                snapshot = traffic.snapshot()["sql"]
                queued_ids = admitted - completed
                if active is not None:
                    queued_ids = queued_ids - {active[2]["id"]}
                background_count = sum(by_id[identity]["background"] for identity in queued_ids)
                require(snapshot["queued"] == len(queued_ids), "queue tracking mismatch")
                require(snapshot["queued"] <= QUEUE_LIMIT and background_count <= QUEUE_LIMIT - RESERVE,
                        "queue or foreground reserve bound violated")
                maximum_queue = max(maximum_queue, snapshot["queued"])
                maximum_background = max(maximum_background, background_count)
                if active is None:
                    context = owner.traffic_dispatch(traffic)
                    dispatch = context.__enter__()
                    if dispatch is None:
                        context.__exit__(None, None, None)
                    else:
                        job = by_id[dispatch.path.name]
                        if job["background"]:
                            require(not any(not by_id[i]["background"] for i in queued_ids),
                                    "background bypassed queued foreground")
                            actual_start = time.perf_counter()
                            starts.append(actual_start)
                            background_wait.append((actual_start - started) * 1000)
                        try:
                            future = writer.submit(write_job, effect_path, job, scenario.hold_ms, transaction_active)
                        except BaseException:
                            context.__exit__(*sys.exc_info())
                            raise
                        active = (future, context, job)
                if active is not None or pending:
                    time.sleep(.001)
            wall, cpu = time.perf_counter() - started, time.process_time() - cpu_started
        finally:
            stop.set()
            if active is not None:
                try:
                    active[0].result(timeout=10)
                finally:
                    active[1].__exit__(None, None, None)
        reader_results = [future.result(timeout=10) for future in observations]
        require(all(r["reads"] > 0 and r["read_only_verified"] for r in reader_results), "reader failed")
        require(db.execute("SELECT id FROM foreground ORDER BY id").fetchall() ==
                [(i,) for i in range(scenario.foreground)], "foreground rows mismatch")
        for job in jobs:
            if job["background"]:
                rows = db.execute("SELECT batch,row_id,value FROM derived WHERE batch=? ORDER BY row_id",
                                  (job["rows"][0][0],)).fetchall()
                require(rows == list(job["rows"]), "batch rows mismatch")
        require(db.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "database corrupt")
        require(sum(r["event"] == "permit_consumed" for r in kernel.audit) == len(jobs), "permit count mismatch")
        require(all(not kernel.consume(decisions[j["id"]].permit, j["intent"]) for j in jobs), "replay accepted")
        require(kernel.verify_audit(), "audit invalid")
        require(traffic.snapshot()["sql"] == {"queued": 0, "active": 0, "dropped": 0}, "queue did not drain")
        if scenario.prefill:
            require(reserve_observed, "foreground was not admitted against saturated background quota")
        if scenario.name == "sustained_foreground":
            require(min(starts) >= last_foreground_commit, "background bypassed sustained foreground")
        if scenario.hold_ms:
            require(arrivals_during_background > 0, "slow batch did not overlap foreground arrivals")
            require(sum(r["reads_during_write_transaction"] for r in reader_results) > 0,
                    "readers made no progress during an open writer transaction")
        return {"scenario": scenario.name, "foreground_jobs": scenario.foreground,
                "batch_rows": scenario.batch_rows, "background_batches": scenario.batches,
                "readers": scenario.readers, "wall_ms": wall * 1000, "cpu_ms": cpu * 1000,
                "foreground_p50_ms": statistics.median(foreground_latency),
                "foreground_p95_ms": percentile(foreground_latency), "foreground_max_ms": max(foreground_latency),
                "background_wait_p95_ms": percentile(background_wait), "background_oldest_wait_ms": max(background_wait),
                "write_p95_ms": percentile(writes), "write_max_ms": max(writes),
                "queue_peak": maximum_queue, "background_queue_peak": maximum_background,
                "foreground_reserve_observed": reserve_observed,
                "admission_backpressure_attempts": backpressure,
                "foreground_admissions_during_active_background": arrivals_during_background,
                "concurrent_reads": sum(r["reads"] for r in reader_results),
                "reads_during_write_transaction": sum(r["reads_during_write_transaction"] for r in reader_results),
                "reader_max_ms": max(r["read_max_ms"] for r in reader_results),
                "peak_memory_mib": peak_memory_mib(), "effect_commits": len(jobs),
                "audit_valid": True, "replay_denied": True, "exact_rows": True, "queues_empty": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=SCENARIOS)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    if args.case:
        print(json.dumps(run_case(SCENARIOS[args.case])))
        return
    if not 1 <= args.repeats <= 5:
        parser.error("repeats must be in [1, 5]")
    rows = []
    for repeat in range(args.repeats):
        names = list(SCENARIOS)
        names = names[repeat % len(names):] + names[:repeat % len(names)]
        for name in names:
            result = subprocess.run([sys.executable, "-W", "error", str(Path(__file__).resolve()), "--case", name],
                                    capture_output=True, text=True, timeout=60)
            require(result.returncode == 0 and not result.stderr.strip(),
                    "stress child failed or warned: " + result.stderr + result.stdout)
            row = json.loads(result.stdout)
            rows.append(row)
            print(f"PASS {name} round {repeat + 1}: fg-p95={row['foreground_p95_ms']:.2f} ms "
                  f"bg-wait={row['background_oldest_wait_ms']:.2f} ms reads={row['concurrent_reads']}", flush=True)
    metrics = ("wall_ms", "cpu_ms", "foreground_p95_ms", "background_oldest_wait_ms", "write_max_ms",
               "queue_peak", "background_queue_peak", "concurrent_reads", "reads_during_write_transaction", "peak_memory_mib")
    summary = {name: {key: statistics.median(row[key] for row in rows if row["scenario"] == name)
                      for key in metrics} for name in SCENARIOS}
    report = {"python": platform.python_version(), "platform": platform.platform(),
              "timestamp_utc": datetime.now(timezone.utc).isoformat(), "summary": summary, "samples": rows,
              "queue_limit": QUEUE_LIMIT, "foreground_reserve": RESERVE,
              "limits": "Finite bounded fixtures; read observers bypass dispatch but are enforced read-only. No capacity guarantee.",
              "source_sha256": {name: sha256((REPO / name).read_bytes()).hexdigest() for name in
                  ("scripts/stress_idle_batching.py", "pulpo/traffic.py", "pulpo/kernel.py", "pulpo/state.py",
                   "pulpo/orchestrator.py", "pulpo/resources.py")}}
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print("Results: " + str(args.json.resolve()))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
