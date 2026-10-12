"""Compare recorded Linux serial/two-helper cycles to the prior four-helper run."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous", required=True, type=Path)
    parser.add_argument("--current", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    previous, current = [json.loads(path.read_text()) for path in (args.previous, args.current)]
    for report in (previous, current):
        if not report.get("platform", "").startswith("Linux"):
            raise ValueError("helper comparison requires Linux reports")
    for name in ("sizes", "repeats", "iterations", "surfaces", "files_per_surface", "file_bytes"):
        if previous["settings"][name] != current["settings"][name]:
            raise ValueError("workload mismatch: " + name)
    if previous["settings"]["workers"] != [0, 4] or current["settings"]["workers"] != [0, 2]:
        raise ValueError("expected serial/four and serial/two helper configurations")
    old = {row["history"]: row for row in previous["results"]}
    new = {row["history"]: row for row in current["results"]}
    if set(old) != set(new) or set(old) != set(current["settings"]["sizes"]):
        raise ValueError("missing record counts")
    rows = []
    lines = ["# Recorded Linux helper comparison", "",
             "Separate runs; serial is included as a control. No universal worker-count claim.", "",
             "| Records | Previous serial ms | Current serial ms | Four helpers ms | Two helpers ms | Two-helper largest stage |",
             "| ---: | ---: | ---: | ---: | ---: | --- |"]
    for size in sorted(old):
        before = {cycle["evidence_workers"]: cycle for cycle in old[size]["cycles"]}
        after = {cycle["evidence_workers"]: cycle for cycle in new[size]["cycles"]}
        if set(before) != {0, 4} or set(after) != {0, 2}:
            raise ValueError("missing helper cases")
        row = {"records": size,
               "previous_serial_ms": before[0]["stages"]["total_local_cycle"]["median_ms"],
               "current_serial_ms": after[0]["stages"]["total_local_cycle"]["median_ms"],
               "four_helpers_ms": before[4]["stages"]["total_local_cycle"]["median_ms"],
               "two_helpers_ms": after[2]["stages"]["total_local_cycle"]["median_ms"],
               "two_helpers_amortized_ms": after[2]["lifecycle"]["amortized_cycle_seconds"]["median_ms"],
               "two_helpers_largest_stage": after[2]["largest_stage_by_median"],
               "stages": {name: {"four_helpers_ms": value["median_ms"],
                                  "two_helpers_ms": after[2]["stages"][name]["median_ms"]}
                          for name, value in before[4]["stages"].items()}}
        rows.append(row)
        lines.append(f"| {size} | {row['previous_serial_ms']:.3f} | {row['current_serial_ms']:.3f} | "
                     f"{row['four_helpers_ms']:.3f} | {row['two_helpers_ms']:.3f} | {row['two_helpers_largest_stage']} |")
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "helper-comparison.json").write_text(json.dumps({"claim": "Recorded Linux helper comparison",
        "previous_platform": previous["platform"], "current_platform": current["platform"],
        "previous_python": previous["python"], "current_python": current["python"], "rows": rows}, indent=2) + "\n")
    (args.output / "helper-comparison.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
