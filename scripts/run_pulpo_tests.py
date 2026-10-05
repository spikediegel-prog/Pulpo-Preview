#!/usr/bin/env python3
"""Run existing Pulpo suites and save logs; propagate any failing suite."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--suite", choices=["focused", "core", "authority", "custody", "all"], default="focused")
    parser.add_argument("--log-dir", type=Path, default=Path("pulpo-test-results"))
    args = parser.parse_args()
    repo = args.repo.resolve()
    if not (repo / "pulpo/kernel.py").is_file():
        parser.error("--repo must name a Pulpo checkout")
    commands = {
        "focused": ["tests.test_audit_checkpoint", "tests.test_persistence", "tests.test_kernel",
                    "tests.test_evidence_tuning", "tests.test_setup",
                    "tests.test_parallel_performance", "tests.test_effect_reconcile",
                    "tests.test_governed_effect_boundary", "tests.test_constitutional_sequences"],
        "core": ["discover", "-s", "tests"],
        "authority": ["discover", "-s", "authority-service/tests"],
        "custody": ["discover", "-s", "custody-service/tests"],
    }
    suites = ["core", "authority", "custody"] if args.suite == "all" else [args.suite]
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(str(p) for p in
        (repo, repo / "authority-service/src", repo / "custody-service/src"))
    args.log_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for suite in suites:
        command = [sys.executable, "-W", "error", "-m", "unittest", *commands[suite], "-v"]
        log = args.log_dir / f"{suite}.log"
        with log.open("w", encoding="utf-8") as handle:
            result = subprocess.run(command, cwd=repo, env=env, stdout=handle, stderr=subprocess.STDOUT)
        print(f"{suite}: {'PASS' if result.returncode == 0 else 'FAIL'} — {log.resolve()}")
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
        summary = [line for line in lines if line.startswith(("Ran ", "OK", "FAILED"))]
        for line in summary:
            print("  " + line)
        results.append({"suite": suite, "returncode": result.returncode,
                        "summary": summary, "log": str(log.resolve()),
                        "log_sha256": sha256(log.read_bytes()).hexdigest()})
    report = {"python": platform.python_version(), "platform": platform.platform(),
              "repo": str(repo), "results": results}
    (args.log_dir / "summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(1 if any(r["returncode"] for r in results) else 0)


if __name__ == "__main__":
    main()
