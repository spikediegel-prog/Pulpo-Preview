"""Smoke-test the standalone preview executable without Python on its PATH."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import uuid


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("exe", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args()
    exe = args.exe.resolve()
    sandbox = args.work_dir.resolve() / uuid.uuid4().hex
    sandbox.mkdir(parents=True)
    env = os.environ.copy()
    env["PATH"] = str(Path(env.get("SystemRoot", r"C:\Windows")) / "System32")
    env["PYTHONPATH"] = ""
    env.pop("PYTHONHOME", None)
    env["LOCALAPPDATA"] = str(sandbox / "user-data")
    records = []

    def check(name, arguments, *, exit_code=0, report=None, status=None):
        run = subprocess.run(
            [str(exe), *arguments], cwd=sandbox, env=env, input="\n",
            capture_output=True, text=True, timeout=120,
        )
        (sandbox / (name + ".log")).write_text(run.stdout + run.stderr, encoding="utf-8")
        if run.returncode != exit_code:
            raise RuntimeError(f"{name}: exit {run.returncode}: {run.stdout} {run.stderr}")
        if report:
            data = json.loads((sandbox / report).read_text(encoding="utf-8"))
            if not (
                data["ready_for_test_use"] and data["audit_verification"]["status"] == "PASS"
                and data["authority_effect"] == "none" and data["governance_changes"] == "none"
                and data["production_readiness_claim"] is False
                and data["profile"]["status"] == status
            ):
                raise RuntimeError(f"{name}: setup evidence boundary mismatch")
        records.append({"case": name, "exit_code": run.returncode, "result": "PASS"})
        print(name, "PASS", flush=True)

    check("help", ["--help"])
    check("setup-help", ["setup", "--help"])
    check("quick-start", [], report="user-data/PulpoPreview/setup-report.json", status="CONSERVATIVE_FALLBACK")
    check("fallback", ["setup", "--no-calibrate", "--profile", "fallback.json", "--json-report", "fallback-report.json"], report="fallback-report.json", status="CONSERVATIVE_FALLBACK")
    check("calibration", ["setup", "--profile", "calibrated.json", "--calibration-sizes", "512", "--batch-sizes", "256", "--repeats", "1", "--json-report", "calibrated-report.json"], report="calibrated-report.json", status="CALIBRATED")
    check("reuse", ["setup", "--profile", "calibrated.json", "--no-calibrate", "--json-report", "reuse-report.json"], report="reuse-report.json", status="LOADED")
    check("invalid-command", ["missing-command"], exit_code=2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({
        "classification": "Verified executable smoke tests",
        "exe_sha256": hashlib.sha256(exe.read_bytes()).hexdigest(),
        "size_bytes": exe.stat().st_size,
        "python_and_source_not_on_search_path": True,
        "tests": records,
        "scope": "Bundled setup CLI and bounded multiprocessing calibration; not a full Windows suite pass or production proof.",
    }, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
