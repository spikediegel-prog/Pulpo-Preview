#!/usr/bin/env python3
"""Emit a Gladiator verdict echo for one completed assessment record.

This is the only supported emission entry point for the verdict echo. It
loads a ``GladiatorRecord`` and a kernel audit from files, derives
eligibility from ``completion_eligible`` and the projection from
``audit_references_present`` against that audit, renders the echo, and
writes the structured verdict event once to the output directory.

It never accepts eligibility, projection, or verdict outcomes from the
record file or the workload: those are recomputed here from the kernel
audit. Enforcement-consequence evidence is supplied by the operator as a
separate ``--evidence`` file and is recorded verbatim in the structured
event as operator-supplied, including its source label.

Exit codes mirror ``run_gladiator_tournament.py``: 0 emitted (or already
emitted), 2 expected-revision mismatch, 3 source tree not clean, 4 bad
input or output inside the source checkout. Runner failures emit nothing.
"""

from __future__ import annotations

import argparse
from dataclasses import fields as dataclass_fields
import json
import subprocess
import sys
from pathlib import Path

# The repository root is the parent of this script's directory; importing
# pulpo from it mirrors run_gladiator_tournament.py.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pulpo import GovernanceKernel, Policy  # noqa: E402
from pulpo.gladiator_audit_projection import audit_references_present  # noqa: E402
from pulpo.gladiator_gate import GladiatorRecord, completion_eligible  # noqa: E402
from pulpo.gladiator_verdict_echo import EnforcementEvidence, emit  # noqa: E402


def _git(*args: str, cwd: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(cwd), *args], text=True
    ).strip()


def _load_json(path: Path, what: str) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"{what} is not readable JSON: {path}: {exc}")


def _load_record(path: Path) -> GladiatorRecord:
    data = _load_json(path, "record file")
    if not isinstance(data, dict):
        raise SystemExit(f"record file must contain one JSON object: {path}")
    known = {f.name for f in dataclass_fields(GladiatorRecord)}
    unknown = sorted(set(data) - known)
    if unknown:
        raise SystemExit(f"record file has unknown fields: {unknown}")
    missing = sorted(known - set(data))
    if missing:
        raise SystemExit(f"record file is missing fields: {missing}")
    # JSON has no tuples: the gate requires tuple fields, so coerce the
    # list fields back before constructing. Anything else is a malformed
    # record, not an echo.
    for name in ("teams", "battle_refs", "unresolved_risks"):
        value = data[name]
        if not isinstance(value, list) or not all(
            isinstance(item, str) for item in value
        ):
            raise SystemExit(f"record file field {name!r} must be a list of strings")
        data[name] = tuple(value)
    try:
        return GladiatorRecord(**data)
    except TypeError as exc:
        raise SystemExit(f"record file does not describe a GladiatorRecord: {exc}")


def _load_audit(path: Path, kernel: GovernanceKernel) -> None:
    data = _load_json(path, "audit file")
    if not isinstance(data, list):
        raise SystemExit(f"audit file must contain a JSON list: {path}")
    for entry in data:
        if not isinstance(entry, dict):
            raise SystemExit("audit file entries must be JSON objects")
        event = entry.get("event")
        payload = entry.get("payload")
        timestamp_ns = entry.get("timestamp_ns", 1)
        if not isinstance(event, str) or not isinstance(payload, dict):
            raise SystemExit("audit file entries need a string event and a payload object")
        if not isinstance(timestamp_ns, int) or isinstance(timestamp_ns, bool):
            raise SystemExit("audit file timestamp_ns must be an integer")
        kernel._state.append(event, payload, timestamp_ns)


def _load_evidence(path: Path | None) -> EnforcementEvidence:
    if path is None:
        return EnforcementEvidence()
    data = _load_json(path, "evidence file")
    if not isinstance(data, dict):
        raise SystemExit(f"evidence file must contain one JSON object: {path}")
    known = {f.name for f in dataclass_fields(EnforcementEvidence)}
    unknown = sorted(set(data) - known)
    if unknown:
        raise SystemExit(f"evidence file has unknown fields: {unknown}")
    for key, value in data.items():
        if key != "source" and type(value) is not bool:
            raise SystemExit(f"evidence file field {key!r} must be a boolean")
    if "source" in data and (
        type(data["source"]) is not str or not data["source"].strip()
    ):
        raise SystemExit("evidence file source must be a non-empty string")
    return EnforcementEvidence(**data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-revision", required=True)
    parser.add_argument("--timestamp")
    args = parser.parse_args(argv)

    repo = args.repo.resolve()
    out = args.output.resolve()
    if out == repo or repo in out.parents:
        print("Evidence output must be outside the source checkout", file=sys.stderr)
        return 4
    try:
        actual = _git("rev-parse", "HEAD", cwd=repo)
    except subprocess.CalledProcessError:
        print(f"Not a git checkout: {repo}", file=sys.stderr)
        return 4
    if actual != args.expected_revision:
        print("Source revision differs from the requested proof object", file=sys.stderr)
        return 2
    try:
        status = _git("status", "--short", cwd=repo)
    except subprocess.CalledProcessError:
        print(f"Cannot read git status: {repo}", file=sys.stderr)
        return 4
    if status.strip():
        print("Requires clean canonical source", file=sys.stderr)
        return 3

    record = _load_record(args.record)
    kernel = GovernanceKernel(Policy(frozenset({"read"}), 0))
    _load_audit(args.audit, kernel)
    evidence = _load_evidence(args.evidence)

    eligible = completion_eligible(
        record,
        expected_object=record.object_id,
        expected_revision=args.expected_revision,
    )
    projection = audit_references_present(
        kernel,
        record,
        expected_object=record.object_id,
        expected_revision=args.expected_revision,
    )
    result = emit(
        record,
        eligible=eligible,
        projection_passed=projection,
        enforcement=evidence,
        output_dir=out,
        timestamp=args.timestamp,
    )
    if result.emitted:
        print(result.text)
    else:
        print(f"verdict event already emitted: {result.path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
