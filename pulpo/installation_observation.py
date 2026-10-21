"""Explicit local validation owner for read-only installed-package checks.

Not imported by Control Center. No repair, provider call, signing credential,
arbitrary command or production state is accepted. This cooperative local
application uses the existing kernel; it is not a hostile-process sandbox.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import stat
import tempfile
import time

from .kernel import AgentGrant, GovernanceKernel, Intent, Policy
from .orchestrator import PulpoOrchestrator
from .state import SQLiteKernelState
from .mcp_boundary import export_mcp_snapshot
from .evidence_export import export_evidence_observation

SYSTEM_ROOT = Path("/")
SYSTEM_UID = 0
MANIFEST = "usr/share/doc/pulpo-control-center/build-manifest.json"
ACTION = "installation.inspect"
PRINCIPAL = "agent:local-installation-check"
MAX_FILE = 8 * 1024 * 1024
MAX_TOTAL = 32 * 1024 * 1024


def _read_system_file(relative, limit=MAX_FILE):
    """Bounded descriptor-relative read; reject links and writable system paths."""
    parts = PurePosixPath(relative).parts
    if not parts or PurePosixPath(relative).is_absolute() or any(
            not re.fullmatch(r"[A-Za-z0-9_.-]+", part) or part in {".", ".."} for part in parts):
        raise ValueError("invalid_system_path")
    directory = os.open(SYSTEM_ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        for part in parts[:-1]:
            parent = os.fstat(directory)
            if parent.st_uid != SYSTEM_UID or parent.st_mode & 0o022:
                raise ValueError("untrusted_system_directory")
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory)
            os.close(directory)
            directory = child
        parent = os.fstat(directory)
        if parent.st_uid != SYSTEM_UID or parent.st_mode & 0o022:
            raise ValueError("untrusted_system_directory")
        descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=directory)
        try:
            before = os.fstat(descriptor)
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != SYSTEM_UID
                    or before.st_mode & 0o022 or before.st_nlink != 1 or before.st_size > limit):
                raise ValueError("untrusted_or_oversized_system_file")
            chunks, size = [], 0
            while True:
                chunk = os.read(descriptor, min(65536, limit + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > limit:
                    raise ValueError("system_file_grew_over_limit")
            after = os.fstat(descriptor)
            identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
            if identity(before) != identity(after):
                raise ValueError("system_file_changed_during_read")
            return b"".join(chunks)
        finally:
            os.close(descriptor)
    finally:
        os.close(directory)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_manifest_key")
        result[key] = value
    return result


def _allowed_file(name):
    if type(name) is not str or len(name) > 240:
        return False
    parts = PurePosixPath(name).parts
    if name != "/".join(parts) or any(part in {".", ".."} or not re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in parts):
        return False
    if name.startswith("usr/lib/pulpo-control-center/pulpo_control_center/"):
        return name.endswith(".py") or name.startswith("usr/lib/pulpo-control-center/pulpo_control_center/assets/") and name.endswith(".png")
    return name in {"usr/bin/pulpo-control-center", "usr/share/applications/pulpo-control-center.desktop",
        "usr/share/icons/hicolor/128x128/apps/pulpo-control-center.png", "usr/share/doc/pulpo-control-center/README.ubuntu"}


def load_inventory():
    # Bootstrap input: public root-owned installed package metadata, not a
    # caller-selected file, canonical database, key or second audit source.
    raw = _read_system_file(MANIFEST, 256 * 1024)
    document = json.loads(raw, object_pairs_hook=_unique_object)
    if (type(document) is not dict or set(document) != {"schema", "package", "version", "source_revision", "files"}
            or type(document["schema"]) is not int or document["schema"] != 1
            or document["package"] != "pulpo-control-center"
            or type(document["version"]) is not str or not re.fullmatch(r"[0-9A-Za-z.+~_-]{1,64}", document["version"])
            or type(document["source_revision"]) is not str or not re.fullmatch(r"[a-f0-9]{40}", document["source_revision"])
            or type(document["files"]) is not dict or not 1 <= len(document["files"]) <= 128):
        raise ValueError("invalid_installation_manifest")
    for name, digest in document["files"].items():
        if not _allowed_file(name) or type(digest) is not str or not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError("invalid_manifest_file_entry")
    return document, hashlib.sha256(raw).hexdigest()


def inspect_file(kernel, manifest_hash, name, expected_hash, session, limit=MAX_FILE):
    """One fixed local read after the existing one-use permit gate, never a callback."""
    if not _allowed_file(name):
        raise ValueError("file_outside_installation")
    intent = Intent(PRINCIPAL, ACTION, f"installation:{manifest_hash}:{name}", 0, session)
    decision = kernel.evaluate(intent)
    if decision.outcome != "allow" or not decision.permit:
        return "denied", 0
    if not kernel.consume(decision.permit, intent):
        return "rejected", 0
    try:
        raw = _read_system_file(name, limit)
    except (OSError, ValueError):
        return "unavailable", 0
    return ("match" if hashlib.sha256(raw).hexdigest() == expected_hash else "mismatch"), len(raw)


def run(*, cycles=30, interval=2):
    if platform.system() != "Linux" or os.geteuid() == 0:
        raise ValueError("Run as your ordinary Ubuntu/WSL desktop user, without sudo")
    if type(cycles) is not int or not 1 <= cycles <= 60 or type(interval) is not int or not 1 <= interval <= 10:
        raise ValueError("Use 1..60 cycles and a 1..10 second interval")
    inventory, digest = load_inventory()  # Fail before allocating state if no installed package exists.
    folder = Path(tempfile.mkdtemp(prefix="pulpo-LOCAL-VALIDATION-"))
    governance, evidence = folder / "LOCAL-VALIDATION-governance.json", folder / "LOCAL-VALIDATION-evidence.json"
    (folder / "LOCAL-VALIDATION.txt").write_text(
        "Read-only installed-package validation, not production enforcement.\n"
        "Only public governance/evidence JSON projections may be selected in Control Center.\n"
        "Mark Evidence as Test observations. Source labels are not authenticated provenance.\n"
        "Private temporary canonical state is removed after this process closes.\n"
        "Exports become historical after publication stops.\n", encoding="utf-8")
    print("LOCAL VALIDATION — measured package reads; no production enforcement claim", flush=True)
    print(f"Governance: {governance}\nEvidence: {evidence}", flush=True)
    failed = False
    try:
        with tempfile.TemporaryDirectory(prefix="private-state-", dir=folder) as private:
            backend = SQLiteKernelState(Path(private) / "installation.sqlite")
            try:
                grant = AgentGrant(PRINCIPAL, frozenset({ACTION}), (f"installation:{digest}:",), 0)
                owner = PulpoOrchestrator(GovernanceKernel(Policy(frozenset({ACTION}), 0, agent_grants=(grant,)), state=backend))
                for index in range(cycles):
                    # A package change ends the run rather than silently expanding its frozen scope.
                    if load_inventory()[1] != digest:
                        raise ValueError("Installed manifest changed; stop and explicitly start a new check")
                    counts, total = Counter(), 0
                    for name, expected in sorted(inventory["files"].items()):
                        outcome, size = inspect_file(owner.kernel, digest, name, expected, f"installation-cycle-{index + 1}",
                                                     min(MAX_FILE, MAX_TOTAL - total))
                        counts[outcome] += 1
                        total += size
                    if load_inventory()[1] != digest:
                        raise ValueError("Installed manifest changed during scan; no new observation published")
                    failed |= any(counts[key] for key in ("mismatch", "unavailable", "denied", "rejected"))
                    export_mcp_snapshot(owner, governance)
                    observation = export_evidence_observation(owner, evidence, check_database=True)
                    print(json.dumps({"classification": "LOCAL VALIDATION", "cycle": index + 1,
                        "package_version": inventory["version"], "files": dict(counts), "bytes_read": total,
                        "audit_valid": observation.audit_valid,
                        "limits": "Manifest comparison only; source-reported audit integrity is not enforcement verification"}), flush=True)
                    if not observation.audit_valid:
                        raise ValueError("Canonical audit check failed")
                    if index + 1 < cycles:
                        time.sleep(interval)
            finally:
                backend.close()
    finally:
        print("LOCAL VALIDATION STOPPED — any published exports are historical; current rates will expire.", flush=True)
    return folder, int(failed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycles", type=int, default=30)
    parser.add_argument("--interval", type=int, default=2)
    args = parser.parse_args()
    try:
        return run(cycles=args.cycles, interval=args.interval)[1]
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, TypeError, RecursionError) as error:
        print(f"Local validation stopped: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
