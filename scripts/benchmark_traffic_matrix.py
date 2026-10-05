"""Measure both PTC gains and costs across a controlled local workload matrix.

Real disposable SQLite effects/canonical state; API-style effects are delayed
in-process fixtures. Timing includes admission, dispatch, final verification and
cleanup. Memory measurements run separately so tracing cannot bias timings.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import random
import statistics

from demo_traffic import run


CASES = {
    "sql_burst_then_api": dict(sql_jobs=24, api_jobs=12),
    "api_burst_then_sql": dict(sql_jobs=24, api_jobs=12, order="api_first"),
    "interleaved": dict(sql_jobs=24, api_jobs=12, order="interleaved"),
    "sql_only": dict(sql_jobs=36, api_jobs=0),
    "api_only": dict(sql_jobs=0, api_jobs=36),
    "tiny_mixed": dict(sql_jobs=2, api_jobs=2),
    "fast_mixed": dict(sql_jobs=24, api_jobs=12, sql_delay=0, api_delay=0),
    "sql_heavy": dict(sql_jobs=72, api_jobs=12),
    "slow_api": dict(sql_jobs=24, api_jobs=12, api_delay=0.03),
}
METRICS = ("wall_seconds", "total_wall_seconds", "admission_seconds",
           "scheduling_admission_seconds", "dispatch_cpu_seconds", "total_cpu_seconds",
           "mean_completion_seconds", "p95_completion_seconds")


def percentile(values, fraction):
    return sorted(values)[round((len(values) - 1) * fraction)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=9)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cases", nargs="+", choices=tuple(CASES), default=list(CASES))
    args = parser.parse_args()
    if not 3 <= args.repeats <= 20:
        parser.error("repeats must be 3..20")
    report = {"classification": "Recorded controlled local fixture measurements",
              "python": platform.python_version(), "platform": platform.platform(),
              "repeats": args.repeats, "cases": {},
              "scope": "Real disposable SQL writes; local API-style fake; no external providers",
              "method": "One warm-up per mode/case excluded; alternating FIFO/PTC order; identical effects and lane capacities; separate traced-memory runs",
              "limitations": ["Local wall time and CPU; host contention is uncontrolled",
                 "Bootstrap intervals describe sample variation, not production certainty",
                 "Python allocation peaks exclude SQLite native allocations and process RSS",
                 "Fixture total includes DB creation, policy/permit issuance, effects, verification and cleanup",
                 "Each mode receives preauthorized jobs in a burst; no live arrival stream",
                 "Portfolio weights each listed scenario once; not an estimate of actual user traffic"]}
    for name in args.cases:
        options = CASES[name]
        for mode in ("fifo", "ptc"):
            run(mode, **options)
        samples = {"fifo": [], "ptc": []}
        for repeat in range(args.repeats):
            modes = ("fifo", "ptc") if repeat % 2 == 0 else ("ptc", "fifo")
            for mode in modes:
                samples[mode].append(run(mode, **options))
        memory = {mode: run(mode, memory=True, **options) for mode in samples}
        all_rows = [row for mode in samples for row in samples[mode]] + list(memory.values())
        if len({row["exact_effects_digest"] for row in all_rows}) != 1:
            raise RuntimeError(f"effects differ: {name}")
        medians = {mode: {metric: statistics.median(row[metric] for row in values)
                          for metric in METRICS} for mode, values in samples.items()}
        gains = [100 * (1 - p["total_wall_seconds"] / f["total_wall_seconds"])
                 for f, p in zip(samples["fifo"], samples["ptc"])]
        rng = random.Random(1749)
        boot = [statistics.median(rng.choices(gains, k=len(gains))) for _ in range(2000)]
        median = lambda mode, metric: medians[mode][metric]
        reduction = 100 * (1 - median("ptc", "total_wall_seconds") / median("fifo", "total_wall_seconds"))
        entry = {"parameters": options, "samples": samples, "medians": medians,
                 "total_wall_reduction_percent": reduction,
                 "dispatch_wall_reduction_percent": 100 * (1 - median("ptc", "wall_seconds") / median("fifo", "wall_seconds")),
                 "total_cpu_change_percent": 100 * (median("ptc", "total_cpu_seconds") / median("fifo", "total_cpu_seconds") - 1),
                 "paired_reduction_percent": gains,
                 "paired_median_reduction_95pct_bootstrap_interval": [percentile(boot, .025), percentile(boot, .975)],
                 "memory_samples": memory,
                 "python_peak_allocation_delta_bytes": memory["ptc"]["peak_python_allocation_bytes"] - memory["fifo"]["peak_python_allocation_bytes"],
                 "identical_exact_effects": True}
        report["cases"][name] = entry
        print(f"{name}: fixture total {median('fifo', 'total_wall_seconds') * 1000:.1f} -> "
              f"{median('ptc', 'total_wall_seconds') * 1000:.1f} ms; "
              f"reduction {reduction:+.1f}%; CPU change {entry['total_cpu_change_percent']:+.1f}%", flush=True)
    portfolio = {mode: sum(case["medians"][mode]["total_wall_seconds"] for case in report["cases"].values())
                 for mode in ("fifo", "ptc")}
    report["one_of_each_scenario_portfolio"] = {"median_total_seconds_sum": portfolio,
        "reduction_percent": 100 * (1 - portfolio["ptc"] / portfolio["fifo"])}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Results: {args.output.resolve()}", flush=True)


if __name__ == "__main__":
    main()
