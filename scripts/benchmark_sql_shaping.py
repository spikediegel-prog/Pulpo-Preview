"""Tune only PTC SQL spacing on disposable fixtures, then check fresh samples.

No SQLite pragmas, durability, transaction, kernel or authority semantics change.
Settings are measured hints, never automatically installed or made defaults.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import statistics

from demo_traffic import run

CASES = {
    "sql_only": dict(sql_jobs=24, api_jobs=0),
    "interleaved": dict(sql_jobs=24, api_jobs=12, order="interleaved"),
    "slow_api": dict(sql_jobs=24, api_jobs=12, api_delay=0.03),
}
SETTINGS = {"unpaced": 0.0, "5ms": 0.005, "20ms": 0.02}


def summarize(samples):
    totals = [s["total_wall_seconds"] for s in samples]
    median = statistics.median(totals)
    return {"median_total_seconds": median,
            "median_dispatch_seconds": statistics.median(s["wall_seconds"] for s in samples),
            "relative_median_absolute_deviation": statistics.median(abs(s - median) for s in totals) / median,
            "min_total_seconds": min(totals), "max_total_seconds": max(totals),
            "median_p95_completion_seconds": statistics.median(s["p95_completion_seconds"] for s in samples)}


def measure(names, repeats):
    result = {}
    for case, options in CASES.items():
        samples = {name: [] for name in names}
        for repeat in range(repeats):
            # Rotate order instead of always giving one setting the first run.
            order = names[repeat % len(names):] + names[:repeat % len(names)]
            for name in order:
                samples[name].append(run("ptc", sql_interval=SETTINGS[name], **options))
        if len({s["exact_effects_digest"] for values in samples.values() for s in values}) != 1:
            raise RuntimeError("shaping changed exact effects")
        result[case] = {name: {"samples": values, "summary": summarize(values)}
                        for name, values in samples.items()}
        print(case + ": " + ", ".join(f"{name} {item['summary']['median_total_seconds'] * 1000:.1f} ms"
                                     for name, item in result[case].items()), flush=True)
    return result


def assess(result, candidate):
    cases = {}
    for case, settings in result.items():
        baseline = settings["unpaced"]["summary"]
        shaped = settings[candidate]["summary"]
        cases[case] = {
            "time_change_percent": 100 * (shaped["median_total_seconds"] / baseline["median_total_seconds"] - 1),
            "baseline_relative_mad": baseline["relative_median_absolute_deviation"],
            "shaped_relative_mad": shaped["relative_median_absolute_deviation"],
        }
    total = lambda name: sum(settings[name]["summary"]["median_total_seconds"] for settings in result.values())
    jitter = lambda name: sum(settings[name]["summary"]["relative_median_absolute_deviation"] for settings in result.values())
    return {"cases": cases, "portfolio_time_change_percent": 100 * (total(candidate) / total("unpaced") - 1),
            "jitter_ratio": jitter(candidate) / max(jitter("unpaced"), 1e-12),
            "passes_local_hint_rule": all(c["time_change_percent"] <= 5 for c in cases.values())
                                      and jitter(candidate) <= 0.9 * jitter("unpaced")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--holdout-repeats", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 3 <= args.repeats <= 15 or not 3 <= args.holdout_repeats <= 15:
        parser.error("repeat counts must be 3..15")
    for options in CASES.values():
        for interval in SETTINGS.values():
            run("ptc", sql_interval=interval, **options)
    training = measure(list(SETTINGS), args.repeats)
    assessed = {name: assess(training, name) for name in SETTINGS if name != "unpaced"}
    # Hold out the candidate with the least portfolio slowdown even when neither
    # passes training. A fresh recheck can reject an apparent tuning benefit.
    candidate = min(assessed, key=lambda name: assessed[name]["portfolio_time_change_percent"])
    print(f"Fresh validation of {candidate} against unpaced", flush=True)
    holdout = measure(["unpaced", candidate], args.holdout_repeats)
    validation = assess(holdout, candidate)
    supported = assessed[candidate]["passes_local_hint_rule"] and validation["passes_local_hint_rule"]
    report = {"classification": "Recorded local SQL shaping experiment",
              "python": platform.python_version(), "settings_seconds": SETTINGS,
              "training": training, "training_assessment": assessed,
              "holdout_candidate": candidate, "holdout": holdout, "holdout_assessment": validation,
              "measured_local_hint": candidate if supported else "unpaced",
              "default_changed": False,
              "decision_rule": "Candidate must show at least 10% lower summed relative MAD and no case more than 5% slower, in both training and fresh validation",
              "limitations": ["Small, noisy local fixture sample; no universal optimum or production certainty",
                  "Actual SQL writes; delayed in-process API-style fake; no network",
                  "One SQL slot, two API slots, same exact jobs and canonical checks for every setting",
                  "Spacing caps SQL start rate; it does not batch, retry, change durability or repair SQLite",
                  "No automatic activation; zero spacing remains the default"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Measured local hint: {report['measured_local_hint']}; default unchanged", flush=True)


if __name__ == "__main__":
    main()
