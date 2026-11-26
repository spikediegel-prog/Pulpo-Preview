"""Audit every declared Python extra without adding runtime dependencies."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import tomllib
import venv

PROJECTS = {".": "pulpo", "authority-service": "pulpo-independent-authority",
            "custody-service": "pulpo-hostile-worker-custody"}


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def profiles(root: Path) -> list[str]:
    result = []
    for directory, expected in PROJECTS.items():
        project = tomllib.loads((root / directory / "pyproject.toml").read_text())["project"]
        if canonical(project["name"]) != expected:
            raise ValueError("unexpected local project identity")
        extras = sorted(project.get("optional-dependencies", {}))
        path = "." if directory == "." else "./" + directory
        result.append(path + ("[" + ",".join(extras) + "]" if extras else ""))
    return result


def public_requirements(packages: list[dict]) -> dict[str, str]:
    result = {}
    seen = set()
    local = set(PROJECTS.values())
    for item in packages:
        name, version = canonical(item["name"]), item["version"]
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
            raise ValueError("invalid package name")
        if not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9.!+_-]+", version):
            raise ValueError("invalid package version")
        if name in seen:
            raise ValueError("duplicate distribution")
        seen.add(name)
        if name not in local:
            result[name] = version
    if not local.issubset(seen) or "pip" not in result:
        raise ValueError("incomplete installed project/tool inventory")
    return dict(sorted(result.items()))


def validate_report(report: dict, expected: dict[str, str]) -> int:
    audited = {}
    vulnerabilities = 0
    for item in report["dependencies"]:
        if item.get("skip_reason") or "version" not in item or not isinstance(item.get("vulns"), list):
            raise ValueError("scanner skipped or omitted dependency evidence")
        name = canonical(item["name"])
        if name in audited:
            raise ValueError("duplicate scanner package")
        audited[name] = item["version"]
        vulnerabilities += len(item["vulns"])
    if audited != expected:
        raise ValueError("scanner inventory/version mismatch")
    return vulnerabilities


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--constraints", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    selected = profiles(root)
    summary = {"python": sys.version, "profiles": selected,
               "constraints": str(args.constraints) if args.constraints else None,
               "scanner": "pip-audit==2.10.1", "status": "incomplete"}

    def save():
        (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    save()
    with tempfile.TemporaryDirectory(prefix="pulpo-dependency-audit-") as temporary:
        work = Path(temporary)
        for label in ["application", "scanner"]:
            venv.EnvBuilder(with_pip=True).create(work / label)
        def python(label):
            return str(work / label / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python"))
        def run(command, label, check=True):
            with (output / (label + ".log")).open("w") as log:
                code = subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT).returncode
            summary[label] = code
            save()
            if check and code:
                raise RuntimeError(label + " failed; see preserved log")
            return code
        app, scanner = python("application"), python("scanner")
        # Build tools are inventoried explicitly; they are not core requirements.
        run([app, "-m", "pip", "install", "pip==26.2.2", "setuptools==84.2.1", "wheel==0.48.0"], "bootstrap")
        command = [app, "-m", "pip", "install"]
        if args.constraints:
            command += ["-c", str(args.constraints.resolve())]
        run(command + selected, "install")
        run([app, "-m", "pip", "check"], "pip-check")
        code = "import importlib.metadata as m,json;print(json.dumps([{'name':d.metadata['Name'],'version':d.version} for d in m.distributions()]))"
        # Isolated mode excludes build-generated .egg-info in the checkout from
        # the installed-distribution inventory (otherwise local projects repeat).
        packages = json.loads(subprocess.check_output([app, "-I", "-c", code], cwd=root, text=True))
        (output / "installed.json").write_text(json.dumps(packages, indent=2) + "\n")
        expected = public_requirements(packages)
        requirements = output / "resolved-requirements.txt"
        requirements.write_text("".join(name + "==" + version + "\n" for name, version in expected.items()))
        summary["public_packages"] = len(expected)
        summary["local_projects"] = sorted(PROJECTS.values())
        run([scanner, "-m", "pip", "install", "pip==26.2.2", "pip-audit==2.10.1"], "scanner-install")
        report = output / "advisories.json"
        audit_code = run([scanner, "-m", "pip_audit", "-r", str(requirements), "--strict", "--no-deps", "--disable-pip",
                          "--progress-spinner", "off", "-f", "json", "-o", str(report)], "audit", check=False)
        findings = validate_report(json.loads(report.read_text()), expected)
        summary["advisory_records"] = findings
        summary["status"] = "passed" if not audit_code and not findings else "failed"
        save()
        return int(summary["status"] != "passed")


if __name__ == "__main__":
    raise SystemExit(main())
