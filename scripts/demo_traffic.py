"""Try PTC against real disposable SQLite writes and a delayed API-style fake.

No network traffic, real provider credentials, or production state. Governance
and scheduling remain on the owning thread; effect workers get exact intents
only. FIFO and PTC execute identical jobs with identical SQL/API slot limits.
"""
from __future__ import annotations

import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from contextlib import closing, contextmanager
import hashlib
import json
from pathlib import Path as FilePath
import sqlite3
import statistics
import sys
import tempfile
from time import perf_counter, process_time, sleep
import tracemalloc

sys.path.insert(0, str(FilePath(__file__).resolve().parents[1]))
from pulpo import GovernanceKernel, Intent, Policy, SQLiteKernelState
from pulpo.orchestrator import PulpoOrchestrator
from pulpo.traffic import Lane, Path, TrafficControl


def _run(mode, sql_jobs=24, api_jobs=12, order="sql_first", sql_delay=0.002,
         api_delay=0.01, sql_interval=0.0):
    with tempfile.TemporaryDirectory(prefix="pulpo-ptc-demo-") as tmp:
        directory = FilePath(tmp)
        effect_db = directory / "effects.sqlite"
        with closing(sqlite3.connect(effect_db)) as connection, connection:
            connection.execute("CREATE TABLE effects (resource TEXT PRIMARY KEY)")
        state = SQLiteKernelState(directory / "governance.sqlite")
        try:
            kernel = GovernanceKernel(Policy(frozenset({"fixture_write"}), 0),
                                      secret=b"disposable-demo-only", state=state)
            owner = PulpoOrchestrator(kernel)
            jobs = [("sql", Intent("fixture", "fixture_write", f"fixture:sql:{i}"))
                    for i in range(sql_jobs)]
            jobs += [("api", Intent("fixture", "fixture_write", f"fixture:api:provider-a:{i}"))
                     for i in range(api_jobs)]
            if order == "api_first":
                jobs = jobs[sql_jobs:] + jobs[:sql_jobs]
            elif order == "interleaved":
                sqls, apis = jobs[:sql_jobs], jobs[sql_jobs:]
                jobs = [group[index] for index in range(max(sql_jobs, api_jobs))
                        for group in (sqls, apis) if index < len(group)]
            elif order != "sql_first":
                raise ValueError("unknown arrival order")
            traffic = None
            if mode == "ptc":
                paths = tuple(Path(intent.resource, lane, intent) for lane, intent in jobs)
                if sql_interval == 0:
                    traffic = TrafficControl.for_sql_api(paths,
                        sql_queue_limit=max(1, sql_jobs), api_queue_limit=max(1, api_jobs))
                else:
                    # Explicit benchmark-only alternative, never the selected profile.
                    traffic = TrafficControl((Lane("sql", "sql", 1, max(1, sql_jobs), sql_interval),
                                              Lane("api", "api", 2, max(1, api_jobs))), paths)
            fifo = deque()
            admission_started = perf_counter()
            scheduling_admission_seconds = 0.0
            for lane, intent in jobs:
                decision = kernel.evaluate(intent)
                scheduled = perf_counter()
                if mode == "ptc":
                    traffic.enqueue(intent, decision, (intent.resource,))
                else:
                    fifo.append((lane, intent, decision.permit))
                scheduling_admission_seconds += perf_counter() - scheduled
            admission_seconds = perf_counter() - admission_started
            limits = {"sql": 1, "api": 2}
            occupancy = dict.fromkeys(limits, 0)
            maximum = dict.fromkeys(limits, 0)
            active = {}
            receipts = []
            completed = []

            def effect(lane, intent):
                if lane == "sql":
                    if not intent.resource.startswith("fixture:sql:"):
                        raise RuntimeError("SQL target mismatch")
                    with closing(sqlite3.connect(effect_db)) as connection, connection:
                        connection.execute("INSERT INTO effects VALUES (?)", (intent.resource,))
                    if sql_delay:
                        sleep(sql_delay)
                else:
                    if not intent.resource.startswith("fixture:api:provider-a:"):
                        raise RuntimeError("API target mismatch")
                    # Delayed in-process API-style adapter, never a network call.
                    if api_delay:
                        sleep(api_delay)
                return lane, intent.resource

            @contextmanager
            def fifo_dispatch(intent, permit):
                if not kernel.consume(permit, intent):
                    raise RuntimeError("FIFO permit rejected")
                yield

            started = perf_counter()
            cpu_started = process_time()
            with ThreadPoolExecutor(max_workers=3) as workers:
                while len(completed) < len(jobs):
                    while True:
                        if mode == "ptc":
                            context = owner.traffic_dispatch(traffic)
                            dispatch = context.__enter__()
                            if dispatch is None:
                                context.__exit__(None, None, None)
                                break
                            lane, intent = dispatch.path.lane, dispatch.work.intent
                        else:
                            if not fifo or occupancy[fifo[0][0]] == limits[fifo[0][0]]:
                                break
                            lane, intent, permit = fifo.popleft()
                            context = fifo_dispatch(intent, permit)
                            context.__enter__()
                        occupancy[lane] += 1
                        maximum[lane] = max(maximum[lane], occupancy[lane])
                        if occupancy[lane] > limits[lane]:
                            raise RuntimeError("concurrency exceeded")
                        try:
                            future = workers.submit(effect, lane, intent)
                        except BaseException:
                            occupancy[lane] -= 1
                            context.__exit__(*sys.exc_info())
                            raise
                        active[future] = (lane, intent, context)
                    if not active:
                        delay = traffic.ready_delay() if mode == "ptc" else None
                        if delay is not None and delay > 0:
                            sleep(delay)
                            continue
                        raise RuntimeError("traffic deadlock")
                    delay = traffic.ready_delay() if mode == "ptc" else None
                    done, _ = wait(active, timeout=delay, return_when=FIRST_COMPLETED)
                    for future in done:
                        lane, intent, context = active.pop(future)
                        try:
                            result_lane, resource = future.result()
                            if (result_lane, resource) != (lane, intent.resource):
                                raise RuntimeError("effect result target mismatch")
                            if lane == "api":
                                receipts.append(resource)
                            completed.append(perf_counter() - started)
                        finally:
                            occupancy[lane] -= 1
                            context.__exit__(None, None, None)
            elapsed = perf_counter() - started
            dispatch_cpu_seconds = process_time() - cpu_started
            with closing(sqlite3.connect(effect_db)) as connection, connection:
                rows = [row[0] for row in connection.execute("SELECT resource FROM effects ORDER BY resource")]
            observed = sorted(rows + receipts)
            expected = sorted(intent.resource for _, intent in jobs)
            consumed = sum(record["event"] == "permit_consumed" for record in kernel.audit)
            if observed != expected or consumed != len(jobs) or not kernel.verify_audit():
                raise RuntimeError("effect or canonical evidence mismatch")
            if any(occupancy.values()) or (mode == "ptc" and any(
                    item["active"] or item["queued"] for item in traffic.snapshot().values())):
                raise RuntimeError("slots or queued work remain")
            return {"mode": mode, "wall_seconds": elapsed,
                    "admission_seconds": admission_seconds,
                    "scheduling_admission_seconds": scheduling_admission_seconds,
                    "dispatch_cpu_seconds": dispatch_cpu_seconds,
                    "mean_completion_seconds": statistics.mean(completed),
                    "p95_completion_seconds": sorted(completed)[max(0, (95 * len(completed) + 99) // 100 - 1)],
                    "sql_rows": len(rows), "api_style_receipts": len(receipts),
                    "canonical_permits_consumed": consumed, "audit_valid": True,
                    "max_concurrency": maximum, "final_slots": occupancy,
                    "exact_effects_digest": hashlib.sha256(json.dumps(observed).encode()).hexdigest()}
        finally:
            state.close()


def run(mode, sql_jobs=24, api_jobs=12, order="sql_first", sql_delay=0.002,
        api_delay=0.01, *, memory=False, sql_interval=0.0):
    if mode not in {"fifo", "ptc"} or not 1 <= sql_jobs + api_jobs <= 1024:
        raise ValueError("valid mode and 1..1024 jobs required")
    if min(sql_jobs, api_jobs, sql_delay, api_delay) < 0:
        raise ValueError("job counts and delays must be nonnegative")
    if memory:
        tracemalloc.start()
    start, cpu = perf_counter(), process_time()
    try:
        result = _run(mode, sql_jobs, api_jobs, order, sql_delay, api_delay, sql_interval)
        result["total_wall_seconds"] = perf_counter() - start
        result["total_cpu_seconds"] = process_time() - cpu
        if memory:
            result["peak_python_allocation_bytes"] = tracemalloc.get_traced_memory()[1]
        return result
    finally:
        if memory:
            tracemalloc.stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output", type=FilePath)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 20:
        parser.error("repeats must be 1..20")
    results = {mode: [] for mode in ("fifo", "ptc")}
    # Alternate first-run order to reduce warm-up/order bias.
    for iteration in range(args.repeats):
        for mode in (("fifo", "ptc") if iteration % 2 == 0 else ("ptc", "fifo")):
            results[mode].append(run(mode))
    digests = {row["exact_effects_digest"] for samples in results.values() for row in samples}
    if len(digests) != 1:
        raise RuntimeError("FIFO/PTC effects differ")
    medians = {mode: statistics.median(row["wall_seconds"] for row in samples)
               for mode, samples in results.items()}
    report = {"classification": "Recorded local fixture wall-time measurement",
              "scope": "Real disposable SQLite writes; delayed in-process API-style fake; no network",
              "repeats": args.repeats, "samples": results, "median_wall_seconds": medians,
              "ptc_reduction_percent": 100 * (1 - medians["ptc"] / medians["fifo"]),
              "identical_exact_effects": True}
    text = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "samples"}, indent=2))


if __name__ == "__main__":
    main()
