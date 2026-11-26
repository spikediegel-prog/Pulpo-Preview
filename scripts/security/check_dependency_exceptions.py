"""Apply the bounded dependency exception record to scanner findings.

The scans still run in full and still report everything. This module is
the gate: a blocking finding is admitted only when an exception entry
names the exact ID, scanner, package and installed version, and the
entry has not expired. A new ID, an expired entry, or a package version
change fails the gate. An entry that no longer matches any finding is a
warning, not a pass — it must be reviewed and removed, but it admits
nothing on its own.

No VEX statement, no severity reduction, no suppression file. The scans
are not marked passed; the run records "admitted with N named
exceptions, expiring <date>".
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path

SCHEMA = "pulpo.dependency-exceptions.v1"
BLOCKING_SEVERITIES = {"High", "Critical"}
REQUIRED_ENTRY_FIELDS = {"id", "scanner", "severity", "packages", "fix_available",
                         "exposure", "evidence", "expires", "accepted_by",
                         "accepted_on", "review"}


def _parse_date(value: object, field: str) -> datetime.date:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a YYYY-MM-DD string")
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{field} is not a valid YYYY-MM-DD date: {value!r}") from None


def load_exceptions(path: Path) -> dict:
    """Load and strictly validate the exception record. Fail closed."""
    record = json.loads(path.read_text())
    if not isinstance(record, dict):
        raise ValueError("exception record must be a JSON object")
    if record.get("schema") != SCHEMA:
        raise ValueError(f"exception record schema must be {SCHEMA!r}")
    entries = record.get("exceptions")
    if not isinstance(entries, list) or not entries:
        raise ValueError("exception record must list at least one exception")
    seen: set[tuple[str, str, str, str]] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("exception entry must be an object")
        missing = REQUIRED_ENTRY_FIELDS - entry.keys()
        if missing:
            raise ValueError(f"exception entry {entry.get('id')!r} misses {sorted(missing)}")
        if entry["scanner"] not in ("grype", "pip-audit"):
            raise ValueError(f"exception {entry['id']!r} has unknown scanner {entry['scanner']!r}")
        if entry["severity"] not in BLOCKING_SEVERITIES:
            raise ValueError(f"exception {entry['id']!r} severity must be High or Critical")
        if entry["fix_available"] is not False:
            raise ValueError(f"exception {entry['id']!r} must have fix_available false")
        packages = entry["packages"]
        if not isinstance(packages, list) or not packages:
            raise ValueError(f"exception {entry['id']!r} must list at least one package")
        for package in packages:
            if not isinstance(package, dict) or set(package) != {"name", "version"}:
                raise ValueError(f"exception {entry['id']!r} has a malformed package entry")
            if not isinstance(package["name"], str) or not package["name"]:
                raise ValueError(f"exception {entry['id']!r} has an empty package name")
            if not isinstance(package["version"], str) or not package["version"]:
                raise ValueError(f"exception {entry['id']!r} has an empty package version")
            key = (entry["id"], entry["scanner"], package["name"], package["version"])
            if key in seen:
                raise ValueError(f"duplicate exception for {key}")
            seen.add(key)
        _parse_date(entry["expires"], f"expires of {entry['id']!r}")
        _parse_date(entry["accepted_on"], f"accepted_on of {entry['id']!r}")
    return record


def grype_blocking(report: dict) -> list[dict]:
    """Blocking (High/Critical) findings from a Grype JSON report."""
    if not isinstance(report, dict) or not isinstance(report.get("matches"), list):
        raise ValueError("grype report must be an object with a matches list")
    findings = []
    for match in report["matches"]:
        if not isinstance(match, dict):
            raise ValueError("grype match must be an object")
        vulnerability = match.get("vulnerability")
        artifact = match.get("artifact")
        if not isinstance(vulnerability, dict) or not isinstance(artifact, dict):
            raise ValueError("grype match misses vulnerability or artifact")
        severity = vulnerability.get("severity")
        if severity not in BLOCKING_SEVERITIES:
            continue
        finding = {"id": vulnerability.get("id"), "scanner": "grype",
                   "package": artifact.get("name"), "version": artifact.get("version"),
                   "severity": severity}
        if not all(isinstance(finding[k], str) and finding[k] for k in
                   ("id", "package", "version")):
            raise ValueError("grype blocking match misses id, package, or version")
        findings.append(finding)
    return findings


def pip_audit_blocking(report: dict) -> list[dict]:
    """Every pip-audit advisory is blocking (the audit runs --strict)."""
    if not isinstance(report, dict) or not isinstance(report.get("dependencies"), list):
        raise ValueError("pip-audit report must be an object with a dependencies list")
    findings = []
    for item in report["dependencies"]:
        if item.get("skip_reason") or "version" not in item or not isinstance(item.get("vulns"), list):
            raise ValueError("scanner skipped or omitted dependency evidence")
        for vuln in item["vulns"]:
            if not isinstance(vuln, dict) or not isinstance(vuln.get("id"), str):
                raise ValueError("pip-audit advisory misses an id")
            findings.append({"id": vuln["id"], "scanner": "pip-audit",
                             "package": item["name"], "version": item["version"],
                             "severity": "High"})
    return findings


def evaluate(findings: list[dict], record: dict,
             today: datetime.date) -> dict:
    """Match findings against the exception record.

    Returns admitted findings (with the entry that admits them),
    unadmitted findings (with the reason), expired matches, and entries
    that matched nothing.
    """
    by_id: dict[str, list[dict]] = {}
    for entry in record["exceptions"]:
        by_id.setdefault(entry["id"], []).append(entry)
    admitted: list[dict] = []
    unadmitted: list[dict] = []
    expired: list[dict] = []
    used: set[int] = set()
    for finding in findings:
        matched = None
        version_mismatch = False
        for entry in by_id.get(finding["id"], []):
            if entry["scanner"] != finding["scanner"]:
                continue
            if any(p["name"] == finding["package"] and p["version"] == finding["version"]
                   for p in entry["packages"]):
                matched = entry
                break
            version_mismatch = True
        if matched is None:
            reason = "version mismatch with the exception record" if version_mismatch \
                else "not listed in the exception record"
            unadmitted.append({**finding, "reason": reason})
            continue
        used.add(id(matched))
        if today > _parse_date(matched["expires"], "expires"):
            expired.append({**finding, "expires": matched["expires"]})
        else:
            admitted.append({**finding, "expires": matched["expires"]})
    unused = [entry for entry in record["exceptions"] if id(entry) not in used]
    return {"admitted": admitted, "unadmitted": unadmitted,
            "expired": expired, "unused": unused}


def summarize(result: dict) -> str:
    lines = []
    admitted, unadmitted, expired = result["admitted"], result["unadmitted"], result["expired"]
    if admitted:
        ids = sorted({f["id"] for f in admitted})
        expiry = min(f["expires"] for f in admitted)
        lines.append(f"Admitted with {len(admitted)} named exception(s) "
                     f"({len(ids)} unique IDs), expiring {expiry}: {', '.join(ids)}")
    if unadmitted:
        lines.append(f"UNADMITTED findings ({len(unadmitted)}):")
        for f in unadmitted:
            lines.append(f"  - {f['id']} {f['package']} {f['version']} "
                         f"({f['scanner']}, {f['severity']}): {f['reason']}")
    if expired:
        lines.append(f"EXPIRED exceptions covering live findings ({len(expired)}):")
        for f in expired:
            lines.append(f"  - {f['id']} {f['package']} {f['version']} expired {f['expires']}")
    if result["unused"]:
        ids = sorted({e["id"] for e in result["unused"]})
        lines.append(f"WARNING: {len(result['unused'])} exception entr(ies) matched no "
                     f"finding and must be reviewed and removed: {', '.join(ids)}")
    if not admitted and not unadmitted and not expired:
        lines.append("No blocking findings.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exceptions", type=Path, required=True)
    parser.add_argument("--grype", type=Path, action="append", default=[])
    parser.add_argument("--pip-audit", type=Path, action="append", default=[])
    parser.add_argument("--today", type=str, default=None,
                        help="YYYY-MM-DD override for the expiry check (tests only)")
    args = parser.parse_args()
    if not args.grype and not args.pip_audit:
        parser.error("at least one --grype or --pip-audit report is required")
    today = _parse_date(args.today, "--today") if args.today else datetime.date.today()
    record = load_exceptions(args.exceptions)
    findings: list[dict] = []
    for path in args.grype:
        findings.extend(grype_blocking(json.loads(path.read_text())))
    for path in args.pip_audit:
        findings.extend(pip_audit_blocking(json.loads(path.read_text())))
    result = evaluate(findings, record, today)
    summary = summarize(result)
    print(summary)
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as handle:
            handle.write("## Dependency exception gate\n\n```\n" + summary + "\n```\n")
    return 0 if not result["unadmitted"] and not result["expired"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
