"""Fresh-process bootstrap comparison; OS filesystem caches are not flushed."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import platform
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tempfile
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pulpo import GovernanceKernel, Policy, SQLiteKernelState

SECRET = b"benchmark-fixture-only"
POLICY = Policy(frozenset(), 0)


class FullState(SQLiteKernelState):
    verify_audit_bootstrap = None


def worker(path, variant):
    state = (FullState if variant == "full" else SQLiteKernelState)(path)
    try:
        start = perf_counter()
        kernel = GovernanceKernel(POLICY, secret=SECRET, state=state)
        elapsed = perf_counter() - start
        # Outside timing: validate the complete canonical chain independently.
        if not kernel.verify_audit():
            raise RuntimeError("benchmark chain invalid")
        print(json.dumps({"seconds": elapsed}))
    finally:
        state.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", type=int, nargs="+", default=[1000, 10000, 50000])
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--variant", choices=["full", "checkpoint", "suffix"])
    args = parser.parse_args()
    if args.worker:
        worker(args.worker, args.variant)
        return
    if args.repeats < 1 or min(args.history) < 1 or args.json is None:
        parser.error("positive history/repeats and --json required")
    output = {
        "python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
        "platform": platform.platform(), "repeats": args.repeats,
        "measurement": "Fresh process and connection; timed GovernanceKernel bootstrap only; OS caches not flushed; imports, state schema initialization, fixture construction and forced full proof excluded.",
        "source_sha256": {name: sha256((ROOT / name).read_bytes()).hexdigest()
                          for name in ("pulpo/state.py", "pulpo/kernel.py", "scripts/benchmark_audit_restart.py")},
        "results": [],
    }
    with tempfile.TemporaryDirectory() as directory:
        for history in args.history:
            seed = Path(directory) / "seed.sqlite3"
            seed.unlink(missing_ok=True)
            state = SQLiteKernelState(seed)
            with state._connection:
                state._connection.execute("BEGIN IMMEDIATE")
                state._append_many([("benchmark", {"index": i, "resource": "repo:benchmark",
                                    "detail": "x" * 100}) for i in range(history)], 100)
            GovernanceKernel(POLICY, state=state, secret=SECRET)
            state.close()
            samples = {variant: [] for variant in ("full", "checkpoint", "suffix")}
            for repeat in range(args.repeats):
                variants = list(samples) if repeat % 2 == 0 else list(reversed(samples))
                for variant in variants:
                    path = Path(directory) / (variant + ".sqlite3")
                    shutil.copyfile(seed, path)
                    if variant == "suffix":
                        state = SQLiteKernelState(path)
                        with state._connection:
                            state._connection.execute("BEGIN IMMEDIATE")
                            state._append_many([("suffix", {"index": i}) for i in range(20)], 200)
                        state.close()
                    result = subprocess.check_output([
                        sys.executable, str(Path(__file__).resolve()), "--worker", str(path),
                        "--variant", variant,
                    ], text=True)
                    samples[variant].append(json.loads(result)["seconds"])
            medians = {k: statistics.median(v) for k, v in samples.items()}
            output["results"].append({"history": history, "suffix_records": 20,
                                      "samples_seconds": samples, "median_seconds": medians,
                                      "checkpoint_speedup": medians["full"] / medians["checkpoint"],
                                      "suffix_speedup": medians["full"] / medians["suffix"]})
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
