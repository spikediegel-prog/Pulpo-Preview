"""FIFO vs PTC with identical synthetic service costs and canonical permits.

No live SQL effects, provider calls, credentials or signing keys. This discrete
event fixture measures scheduling head-of-line blocking, not real throughput.
Both flows share sql=1/api=2 slots, the same intents, costs and one-use checks.
Host elapsed time is reported separately from simulated service makespan.
"""
from __future__ import annotations

import argparse
from collections import deque
from contextlib import contextmanager
import json
from pathlib import Path as FilePath
import platform
import statistics
import sys
from time import perf_counter

sys.path.insert(0, str(FilePath(__file__).resolve().parents[1]))
from pulpo import GovernanceKernel, Intent, Policy
from pulpo.orchestrator import PulpoOrchestrator
from pulpo.traffic import Path, TrafficControl


def run(mode, count, mixed):
    kernel = GovernanceKernel(Policy(frozenset({"fixture"}), 0), secret=b"fixture-only")
    owner = PulpoOrchestrator(kernel)
    sql = Intent("fixture", "fixture", "fixture:sql:exact")
    api = Intent("fixture", "fixture", "fixture:api:exact")
    traffic = TrafficControl.for_sql_api((Path("sql", "sql", sql), Path("api", "api", api)),
                                        sql_queue_limit=count, api_queue_limit=count)
    workload = [sql if not mixed or i < count // 2 else api for i in range(count)]
    fifo = deque()
    for intent in workload:
        decision = kernel.evaluate(intent)
        lane = "sql" if intent == sql else "api"
        if mode == "ptc":
            traffic.enqueue(intent, decision, (lane,))
        else:
            fifo.append((intent, decision.permit, lane))
    active = []
    completed = 0
    now = 0
    occupancy = {"sql": 0, "api": 0}
    limits = {"sql": 1, "api": 2}
    finished = []

    @contextmanager
    def baseline(intent, permit):
        if not kernel.consume(permit, intent):
            raise RuntimeError("baseline permit rejected")
        yield

    start = perf_counter()
    while completed < count:
        while True:
            if mode == "ptc":
                context = owner.traffic_dispatch(traffic)
                dispatch = context.__enter__()
                if dispatch is None:
                    context.__exit__(None, None, None)
                    break
                lane = dispatch.path.lane
            else:
                if not fifo or occupancy[fifo[0][2]] == limits[fifo[0][2]]:
                    break
                intent, permit, lane = fifo.popleft()
                context = baseline(intent, permit)
                context.__enter__()
            occupancy[lane] += 1
            if occupancy[lane] > limits[lane]:
                raise RuntimeError("concurrency exceeded")
            # Identical artificial service duration for each intent in both modes.
            active.append((now + (1 if lane == "sql" else 8), lane, context))
        if not active:
            raise RuntimeError("deadlock")
        now = min(item[0] for item in active)
        pending = []
        for end, lane, context in active:
            if end == now:
                context.__exit__(None, None, None)
                occupancy[lane] -= 1
                completed += 1
                finished.append(now)
            else:
                pending.append((end, lane, context))
        active = pending
    elapsed = perf_counter() - start
    if sum(r["event"] == "permit_consumed" for r in kernel.audit) != count:
        raise RuntimeError("one-use evidence mismatch")
    if not kernel.verify_audit() or any(occupancy.values()):
        raise RuntimeError("invalid final state")
    return {"makespan_service_units": now,
            "mean_completion_service_units": statistics.mean(finished),
            "host_dispatch_seconds": elapsed, "completed": completed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output", type=FilePath)
    args = parser.parse_args()
    if not 2 <= args.count <= 1024 or not 1 <= args.repeats <= 20:
        parser.error("count must be 2..1024 and repeats 1..20")
    report = {"classification": "Recorded synthetic fixture measurement",
              "python": platform.python_version(), "platform": platform.platform(),
              "count": args.count, "repeats": args.repeats,
              "limitations": "Simulated service costs; no real provider/SQL throughput claim.",
              "cases": {}}
    for name, mixed in (("mixed_sql_burst_then_api", True), ("sql_only_control", False)):
        report["cases"][name] = {}
        for mode in ("fifo", "ptc"):
            samples = [run(mode, args.count, mixed) for _ in range(args.repeats)]
            report["cases"][name][mode] = {"samples": samples,
                "median_host_dispatch_seconds": statistics.median(
                    s["host_dispatch_seconds"] for s in samples)}
    result = json.dumps(report, indent=2)
    print(result)
    if args.output:
        args.output.write_text(result + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
