#!/usr/bin/env python3
"""Read-only filesystem pressure observation; no quota, admission or pruning API."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
import sys
import time

from scripts.check_network_exposure import publish_report


@dataclass(frozen=True)
class Limits:
    warn_percent: int = 85
    critical_percent: int = 95
    min_free_bytes: int = 0
    min_free_inodes: int = 0

    def __post_init__(self):
        if (any(type(value) is not int for value in asdict(self).values())
                or not 0 < self.warn_percent < self.critical_percent <= 100
                or self.min_free_bytes < 0 or self.min_free_inodes < 0):
            raise ValueError("invalid pressure thresholds")


def pressure(total, available, minimum, limits):
    if available == 0 or available < minimum or (total - available) * 100 >= total * limits.critical_percent:
        return "critical"
    if (total - available) * 100 >= total * limits.warn_percent:
        return "warning"
    return "ok"


def capacity_observation(value, limits):
    fields = ("f_frsize", "f_blocks", "f_bfree", "f_bavail", "f_flag")
    if (any(type(getattr(value, name, None)) is not int for name in fields)
            or value.f_frsize <= 0 or not 0 < value.f_blocks < 2**63
            or not 0 <= value.f_bavail <= value.f_bfree <= value.f_blocks or value.f_flag < 0):
        return {"state": "unknown", "reasons": ["byte_accounting_unavailable_or_invalid"]}
    total = value.f_blocks * value.f_frsize
    available = value.f_bavail * value.f_frsize
    byte_state = pressure(total, available, limits.min_free_bytes, limits)
    result = {"bytes": {"state": byte_state, "total": total,
        "allocated": (value.f_blocks - value.f_bfree) * value.f_frsize,
        "available_non_privileged": available,
        "reserved_free": (value.f_bfree - value.f_bavail) * value.f_frsize,
        "unavailable_percent": round((total - available) * 100 / total, 2)},
        "read_only_filesystem": bool(value.f_flag & os.ST_RDONLY), "reasons": []}
    if byte_state != "ok":
        result["reasons"].append("byte_headroom_" + byte_state)
    inode_fields = ("f_files", "f_ffree", "f_favail")
    if (all(type(getattr(value, name, None)) is int for name in inode_fields)
            and 0 < value.f_files < 2**63 and 0 <= value.f_favail <= value.f_ffree <= value.f_files):
        inode_state = pressure(value.f_files, value.f_favail, limits.min_free_inodes, limits)
        result["inodes"] = {"state": inode_state, "total": value.f_files, "available_non_privileged": value.f_favail,
                            "unavailable_percent": round((value.f_files - value.f_favail) * 100 / value.f_files, 2)}
        if inode_state != "ok":
            result["reasons"].append("inode_headroom_" + inode_state)
    else:
        inode_state = "unknown"
        result["inodes"] = {"state": "unknown"}
        result["reasons"].append("inode_accounting_unavailable_or_invalid")
    if result["read_only_filesystem"]:
        result["reasons"].append("filesystem_read_only")
    states = {byte_state, inode_state}
    result["state"] = ("critical" if result["read_only_filesystem"] or "critical" in states else
                       "unknown" if "unknown" in states else "warning" if "warning" in states else "ok")
    return result


def open_directory(path):
    """Walk directory descriptors without following a symlink in any component."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    descriptor = os.open("/", flags)
    try:
        for component in path.parts[1:]:
            child = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def observe(path, limits=Limits(), expected_device=None):
    path = Path(path)
    if (not path.is_absolute() or str(path).startswith("//") or ".." in path.parts
            or len(str(path)) > 4096 or any(ord(c) < 32 or ord(c) == 127 for c in str(path))):
        raise ValueError("existing absolute directory required")
    if expected_device is not None and (type(expected_device) is not str
            or re.fullmatch(r"[0-9]{1,10}:[0-9]{1,10}", expected_device) is None):
        raise ValueError("expected device must be MAJOR:MINOR")
    report = {"schema": "pulpo.storage-pressure.v1", "classification": "Recorded",
        "path": str(path), "observed_at_ns": time.time_ns(), "limits": asdict(limits),
        "scope": "shared filesystem capacity; not an evidence quota", "enforcement": "not_assessed",
        "write_probe": "not_performed", "directory_write_permission": "not_assessed",
        "quota_enforcement": "not_implemented", "canonical_pruning": "unavailable",
        "expected_device": expected_device, "mount_export_identity": "not_verified"}
    descriptor = None
    try:
        descriptor = open_directory(path)
        before = os.fstat(descriptor)
        device = f"{os.major(before.st_dev)}:{os.minor(before.st_dev)}"
        report["observed_device"] = device
        if expected_device is not None and device != expected_device:
            report.update(state="unknown", reasons=["unexpected_storage_device"])
            return report
        capacity = os.fstatvfs(descriptor)
        after_descriptor = open_directory(path)
        try:
            after = os.fstat(after_descriptor)
        finally:
            os.close(after_descriptor)
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            report.update(state="unknown", reasons=["directory_changed_during_observation"])
            return report
        report.update(capacity_observation(capacity, limits))
        return report
    except OSError:
        report.update(state="unknown", reasons=["directory_observation_unavailable"])
        return report
    finally:
        if descriptor is not None:
            os.close(descriptor)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, required=True, help="Existing directory; no file reads or creation")
    parser.add_argument("--expected-device", help="Optional trusted device expectation as MAJOR:MINOR")
    parser.add_argument("--warn-percent", type=int, default=85)
    parser.add_argument("--critical-percent", type=int, default=95)
    parser.add_argument("--min-free-bytes", type=int, default=0)
    parser.add_argument("--min-free-inodes", type=int, default=0)
    parser.add_argument("--evidence", type=Path, help="New absolute diagnostic report path; never replaces an existing file")
    args = parser.parse_args(argv)
    if not sys.platform.startswith("linux"):
        parser.error("Linux required")
    try:
        limits = Limits(args.warn_percent, args.critical_percent, args.min_free_bytes, args.min_free_inodes)
        if args.evidence is not None and not args.evidence.is_absolute():
            raise ValueError("absolute report path required")
        report = observe(args.path, limits, args.expected_device)
        payload = json.dumps(report, sort_keys=True)
        if args.evidence is not None:
            publish_report(args.evidence, payload)
        print(payload)
        return 0 if report["state"] == "ok" else 1 if report["state"] in ("warning", "critical") else 2
    except (OSError, ValueError):
        print("pulpo_storage_pressure_error: invalid input or report publication failed; no storage remediation performed", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
