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
    parser.add_argument("--installer", type=Path, help="optional installer script to exercise in isolated user data")
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
        return run.stdout

    check("help", ["--help"])
    check("setup-help", ["setup", "--help"])
    check("quick-start", [], report="user-data/PulpoPreview/setup-report.json", status="CONSERVATIVE_FALLBACK")
    check("tune-help", ["tune", "--help"])
    check("tune-custom", ["tune", "--workers", "1"])
    if json.loads(check("tune-show", ["tune", "--show"]))["workers"] != 1:
        raise RuntimeError("Custom setting not retained")
    check("quick-start-preserves-custom", [])
    if json.loads(check("custom-after-launch", ["tune", "--show"]))["workers"] != 1:
        raise RuntimeError("Quick start replaced custom settings")
    profile = sandbox / "user-data/PulpoPreview/evidence-performance.json"
    document = json.loads(profile.read_text(encoding="utf-8"))
    document["source_sha256"] = "0" * 64
    payload = {key: value for key, value in document.items() if key != "digest"}
    document["digest"] = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    profile.write_text(json.dumps(document), encoding="utf-8")
    check("upgrade-revalidation", ["tune", "--refresh"])
    if json.loads(check("custom-after-upgrade", ["tune", "--show"]))["workers"] != 1:
        raise RuntimeError("Upgrade lost custom setting")
    check("invalid-worker", ["tune", "--workers", "99999"], exit_code=2)
    check("bundled-tkinter", ["tune", "--gui-check"])
    check("fallback", ["setup", "--no-calibrate", "--profile", "fallback.json", "--json-report", "fallback-report.json"], report="fallback-report.json", status="CONSERVATIVE_FALLBACK")
    check("calibration", ["setup", "--profile", "calibrated.json", "--calibration-sizes", "512", "--batch-sizes", "256", "--repeats", "1", "--json-report", "calibrated-report.json"], report="calibrated-report.json", status="CALIBRATED")
    check("reuse", ["setup", "--profile", "calibrated.json", "--no-calibrate", "--json-report", "reuse-report.json"], report="reuse-report.json", status="LOADED")
    check("invalid-command", ["missing-command"], exit_code=2)
    if args.installer:
        import shutil
        powershell = shutil.which("pwsh") or str(Path(env["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe")
        for name in ("installer-first", "installer-upgrade"):
            if name == "installer-upgrade":
                document = json.loads(profile.read_text(encoding="utf-8"))
                document["source_sha256"] = "0" * 64
                payload = {key: value for key, value in document.items() if key != "digest"}
                document["digest"] = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                profile.write_text(json.dumps(document), encoding="utf-8")
            run = subprocess.run([powershell, "-NoProfile", "-File", str(args.installer.resolve()),
                                  "-NoShortcuts"], cwd=sandbox, env=env,
                                  capture_output=True, text=True, timeout=120)
            (sandbox / (name + ".log")).write_text(run.stdout + run.stderr, encoding="utf-8")
            if run.returncode:
                raise RuntimeError(f"{name}: {run.stdout} {run.stderr}")
            installed = sandbox / "user-data/Programs/PulpoPreview/pulpo-preview.exe"
            if hashlib.sha256(installed.read_bytes()).hexdigest() != hashlib.sha256(exe.read_bytes()).hexdigest():
                raise RuntimeError("Installer executable mismatch")
            shown = subprocess.check_output([str(installed), "tune", "--show"], env=env, cwd=sandbox, text=True)
            if json.loads(shown)["workers"] != 1:
                raise RuntimeError("Installer lost custom setting")
            records.append({"case": name, "exit_code": run.returncode, "result": "PASS"})
            print(name, "PASS", flush=True)
        original_profile = profile.read_bytes()
        original_exe = installed.read_bytes()
        run = subprocess.run([powershell, "-NoProfile", "-File", str(args.installer.resolve()),
                              "-NoShortcuts", "-Mode", "Custom", "-Workers", "99999"],
                             cwd=sandbox, env=env, capture_output=True, text=True, timeout=120)
        (sandbox / "installer-rejects-unsafe-count.log").write_text(run.stdout + run.stderr, encoding="utf-8")
        if run.returncode == 0 or profile.read_bytes() != original_profile or installed.read_bytes() != original_exe:
            raise RuntimeError("Invalid installer setting changed profile or executable")
        records.append({"case": "installer-rejects-unsafe-count", "exit_code": run.returncode, "result": "PASS"})
        print("installer-rejects-unsafe-count PASS", flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({
        "classification": "Verified executable smoke tests",
        "exe_sha256": hashlib.sha256(exe.read_bytes()).hexdigest(),
        "size_bytes": exe.stat().st_size,
        "python_and_source_not_on_search_path": True,
        "tests": records,
        "scope": "Bundled setup/tuning CLI, Tcl/Tk widget construction, saved-choice upgrade migration, optional isolated installer; not visual GUI approval or production proof.",
    }, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
