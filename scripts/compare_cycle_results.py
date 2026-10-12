"""Compare recorded cycle reports without attributing differences to an OS alone."""
import argparse
import json
from pathlib import Path

SETTINGS = {"sizes": [1000, 10000, 50000], "workers": [0, 4], "repeats": 5,
            "iterations": 10, "surfaces": 4, "files_per_surface": 20, "file_bytes": 4096}


def compare(windows, linux):
    if not windows.get("platform", "").startswith("Windows") or not linux.get("platform", "").startswith("Linux"):
        raise ValueError("comparison requires a recorded Windows baseline and Linux run")
    for report in (windows, linux):
        for key, value in SETTINGS.items():
            if report["settings"].get(key) != value:
                raise ValueError("original workload setting mismatch: " + key)
    original = {(result["history"], cycle["evidence_workers"]): cycle
                for result in windows["results"] for cycle in result["cycles"]}
    current = {(result["history"], cycle["evidence_workers"]): cycle
               for result in linux["results"] for cycle in result["cycles"]}
    expected = {(size, workers) for size in SETTINGS["sizes"] for workers in SETTINGS["workers"]}
    if set(original) != expected or set(current) != expected:
        raise ValueError("missing or unexpected size/worker combination")
    rows = []
    for key in sorted(expected):
        before, after = original[key], current[key]
        stages = {name: {"windows_ms": values["median_ms"],
                         "linux_ms": after["stages"][name]["median_ms"]}
                  for name, values in before["stages"].items()}
        rows.append({"records": key[0], "workers": key[1], "stages": stages,
                     "windows_cycle_ms": stages["total_local_cycle"]["windows_ms"],
                     "linux_cycle_ms": stages["total_local_cycle"]["linux_ms"],
                     "windows_amortized_ms": before["lifecycle"]["amortized_cycle_seconds"]["median_ms"],
                     "linux_amortized_ms": after["lifecycle"]["amortized_cycle_seconds"]["median_ms"],
                     "linux_largest_stage": after["largest_stage_by_median"]})
    return {"claim": "Recorded workload comparison; not an isolated OS experiment",
            "settings_match": True, "settings": SETTINGS,
            "windows_python": windows["python"], "linux_python": linux["python"],
            "windows_sqlite": windows["sqlite"], "linux_sqlite": linux["sqlite"],
            "limits": "Local code includes read-chunk and lifecycle changes since the original baseline; Python, SQLite and storage differ. OS caches are not flushed.",
            "rows": rows,
            "restart": {"windows": {str(r["history"]): r["restart"] for r in windows["results"]},
                        "linux": {str(r["history"]): r["restart"] for r in linux["results"]}}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--windows", required=True, type=Path)
    parser.add_argument("--linux", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = compare(json.loads(args.windows.read_text()), json.loads(args.linux.read_text()))
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "overall-cycle-comparison.json").write_text(json.dumps(result, indent=2) + "\n")
    lines = ["# Recorded overall-cycle comparison", "", result["limits"], "",
             "| Records | Workers | Original Windows cycle ms | Current Linux cycle ms | Linux amortized ms | Linux largest stage |",
             "| ---: | ---: | ---: | ---: | ---: | --- |"]
    for row in result["rows"]:
        lines.append(f"| {row['records']} | {row['workers']} | {row['windows_cycle_ms']:.3f} | "
                     f"{row['linux_cycle_ms']:.3f} | {row['linux_amortized_ms']:.3f} | {row['linux_largest_stage']} |")
    (args.output / "overall-cycle-comparison.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
