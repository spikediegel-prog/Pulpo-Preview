#!/usr/bin/env python3
"""Disposable synthetic archive experiment. No live source/store or prune CLI.

Only Pulpo's existing setup-calibration rows are accepted. Local receipts are
untrusted copy observations, never authority, archive admission or deletion rights.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import selectors
import secrets
import signal
import stat
import subprocess
import sys
import tempfile

from pulpo.audit_parallel import AuditVerificationEngine
from pulpo.setup import synthetic_audit_rows
from scripts.check_network_exposure import publish_report
from scripts.check_storage_pressure import open_directory

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "pulpo.synthetic-archive-prototype.v1"
SOURCE = "fixture:setup-calibration-only"
RECEIPT = "pulpo.synthetic-local-copy-observation.v1"
MAX_BYTES = 1_048_576


class PrototypeError(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise PrototypeError(reason)


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


@dataclass(frozen=True, slots=True)
class FixturePin:
    records: int
    size: int
    digest: str
    tip: str
    producer_commit: str

    def __post_init__(self):
        require(type(self.records) is int and 1 <= self.records <= 256, "fixture_count_invalid")
        require(type(self.size) is int and 0 < self.size <= MAX_BYTES, "fixture_size_invalid")
        for value in (self.digest, self.tip):
            require(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value), "fixture_hash_invalid")
        require(type(self.producer_commit) is str and re.fullmatch(r"[0-9a-f]{40}", self.producer_commit),
                "fixture_provenance_invalid")


def build_fixture(count=8):
    require(type(count) is int and 1 <= count <= 256, "fixture_count_invalid")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    rows = synthetic_audit_rows(count)
    payload = canonical({"schema": SCHEMA, "fixture_only": True, "source_id": SOURCE,
        "producer_commit": commit, "first_sequence": 1, "last_sequence": count,
        "previous_hash": "0" * 64, "tip_hash": rows[-1][4], "rows": rows})
    pin = FixturePin(count, len(payload), sha256(payload).hexdigest(), rows[-1][4], commit)
    verify_package(payload, pin)
    return payload, pin


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, "duplicate_json_key")
        value[key] = item
    return value


def verify_package(payload, pin):
    require(type(pin) is FixturePin and type(payload) is bytes, "fixture_input_invalid")
    require(len(payload) == pin.size and len(payload) <= MAX_BYTES and sha256(payload).hexdigest() == pin.digest,
            "archive_bytes_do_not_match_owner_fixture_pin")
    try:
        value = json.loads(payload, object_pairs_hook=unique_object,
                           parse_constant=lambda _value: (_ for _ in ()).throw(PrototypeError("nonfinite_json")))
        require(type(value) is dict and set(value) == {"schema", "fixture_only", "source_id", "producer_commit",
            "first_sequence", "last_sequence", "previous_hash", "tip_hash", "rows"}, "archive_shape_invalid")
        require(value["schema"] == SCHEMA and value["fixture_only"] is True and value["source_id"] == SOURCE
            and value["producer_commit"] == pin.producer_commit and type(value["first_sequence"]) is int
            and value["first_sequence"] == 1 and type(value["last_sequence"]) is int
            and value["last_sequence"] == pin.records and value["previous_hash"] == "0" * 64
            and value["tip_hash"] == pin.tip, "archive_manifest_pin_mismatch")
        rows = value["rows"]
        require(type(rows) is list and len(rows) == pin.records, "archive_range_incomplete")
        # Canonical verifier, no forked digest/chain algorithm and no state writer.
        with AuditVerificationEngine(workers=0, cache_size=0) as verifier:
            require(verifier.verify_rows(rows), "canonical_chain_rejected")
        require(rows == [list(row) for row in synthetic_audit_rows(pin.records)], "nonfixture_content_rejected")
        require(payload == canonical(value), "archive_encoding_not_exact")
    except (TypeError, KeyError, UnicodeError, json.JSONDecodeError) as exc:
        raise PrototypeError("archive_encoding_invalid") from exc
    return True


def open_store(root):
    root = Path(root)
    require(root.is_absolute() and ".." not in root.parts and not str(root).startswith("//"), "store_path_invalid")
    fd = open_directory(root)
    try:
        metadata = os.fstat(fd)
        require(metadata.st_uid == os.getuid() and not metadata.st_mode & 0o077,
                "fixture_store_must_be_private_and_owned")
    except BaseException:
        os.close(fd)
        raise
    return fd


def read_object(fd, name):
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=fd)
    try:
        before = os.fstat(descriptor)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid()
                and not before.st_mode & 0o077 and 0 < before.st_size <= MAX_BYTES, "archive_file_boundary_invalid")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            payload = stream.read(MAX_BYTES + 1)
        after = os.fstat(descriptor)
        require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), "archive_changed_during_read")
        return payload
    finally:
        os.close(descriptor)


def write_all(fd, payload):
    offset = 0
    while offset < len(payload):
        written = os.write(fd, payload[offset:offset + 4096])
        require(written > 0, "archive_write_stalled")
        offset += written
    os.fsync(fd)


def sync_directory(fd):
    os.fsync(fd)


def local_observation(fd, pin):
    metadata = os.fstat(fd)
    return {"schema": RECEIPT, "kind": "local_reopen_observation_only", "source_id": SOURCE,
        "archive_sha256": pin.digest, "archive_bytes": pin.size, "records": pin.records,
        "tip_hash": pin.tip, "producer_commit": pin.producer_commit,
        "store_id": f"{metadata.st_dev}:{metadata.st_ino}",
        "durability": "local_fsync_and_reopen_observed", "pruning_authorized": False,
        "authority_effect": "none"}


def publish_fixture(root, payload, pin):
    verify_package(payload, pin)
    fd = open_store(root)
    temporary = ".pending-" + secrets.token_hex(12)
    name = pin.digest + ".archive.json"
    created = False
    try:
        try:
            existing = read_object(fd, name)
        except FileNotFoundError:
            stream = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                             0o600, dir_fd=fd)
            try:
                write_all(stream, payload)
            finally:
                os.close(stream)
            try:
                os.link(temporary, name, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
                created = True
            except FileExistsError:
                # Concurrent identical retry is acceptable only after exact reread.
                pass
            existing = read_object(fd, name)
        require(existing == payload, "existing_archive_conflict_preserved")
        verify_package(existing, pin)
        object_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
        try:
            os.fsync(object_fd)
        finally:
            os.close(object_fd)
        # Failure after linking is commit/durability unknown; retain the object.
        sync_directory(fd)
        verify_package(read_object(fd, name), pin)
        receipt = local_observation(fd, pin)
        return {"created": created, "receipt": receipt}
    except OSError as exc:
        raise PrototypeError("local_publication_or_durability_unknown") from exc
    finally:
        try:
            os.unlink(temporary, dir_fd=fd)
        except FileNotFoundError:
            pass
        finally:
            os.close(fd)


def check_local_receipt(root, receipt, pin):
    require(type(receipt) is dict and type(pin) is FixturePin, "receipt_unavailable_or_invalid")
    fd = open_store(root)
    try:
        expected = local_observation(fd, pin)
        require(set(receipt) == set(expected)
                and all(type(receipt[key]) is type(value) and receipt[key] == value for key, value in expected.items())
                and receipt.get("pruning_authorized") is False,
                "receipt_pin_or_store_mismatch")
        verify_package(read_object(fd, pin.digest + ".archive.json"), pin)
    except OSError as exc:
        raise PrototypeError("receipt_readback_unavailable") from exc
    finally:
        os.close(fd)
    return {"local_copy_observed": True, "pruning_authorized": False, "authority_effect": "none"}


def interrupted_fixture_transfer(root):
    # The only killed PID is this child writing its own disposable synthetic file.
    code = """import os,sys
from pathlib import Path
from scripts.prototype_evidence_archive import build_fixture
payload,_=build_fixture(8)
with (Path(sys.argv[1])/'.interrupted.pending').open('xb') as stream:
    stream.write(payload[:len(payload)//2]);stream.flush();os.fsync(stream.fileno())
    print('ready',flush=True);sys.stdin.readline()
"""
    child = subprocess.Popen([sys.executable, "-c", code, str(root)], cwd=ROOT, text=True,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout, selectors.EVENT_READ)
            require(bool(selector.select(10)), "interrupted_fixture_timeout")
        require(child.stdout.readline().strip() == "ready", "interrupted_fixture_not_ready")
        child.kill()
        _stdout, stderr = child.communicate(timeout=10)
        require(child.returncode == -signal.SIGKILL and not stderr, "interrupted_fixture_failed")
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate(timeout=10)


def run_prototype():
    from unittest.mock import patch
    payload, pin = build_fixture(8)
    original = sha256(payload).hexdigest()
    checks = {}
    with tempfile.TemporaryDirectory(prefix="pulpo-synthetic-archive-", dir=ROOT.parent) as folder:
        base = Path(folder)
        def store(name):
            path = base / name
            path.mkdir(mode=0o700)
            return path
        good = store("good")
        first = publish_fixture(good, payload, pin)
        checks["local_fsync_reopen"] = check_local_receipt(good, first["receipt"], pin)["local_copy_observed"]
        checks["duplicate_is_idempotent"] = not publish_fixture(good, payload, pin)["created"]
        # Deliberately discard a caller's acknowledgment; retry must not overwrite.
        lost = store("lost-ack")
        publish_fixture(lost, payload, pin)
        retry = publish_fixture(lost, payload, pin)
        checks["lost_ack_retry"] = not retry["created"] and check_local_receipt(lost, retry["receipt"], pin)["local_copy_observed"]
        def rejects(operation):
            try:
                operation()
            except (PrototypeError, OSError):
                return True
            return False
        altered = dict(first["receipt"], archive_sha256="f" * 64)
        checks["wrong_ack_rejected"] = rejects(lambda: check_local_receipt(good, altered, pin))
        checks["missing_ack_rejected"] = rejects(lambda: check_local_receipt(good, None, pin))
        checks["receipt_cannot_grant_pruning"] = rejects(lambda: check_local_receipt(good, dict(first["receipt"], pruning_authorized=True), pin))
        checks["wrong_store_rejected"] = rejects(lambda: check_local_receipt(lost, first["receipt"], pin))
        bad = store("corrupt")
        received = publish_fixture(bad, payload, pin)
        target = bad / (pin.digest + ".archive.json")
        target.write_bytes(payload[:-1] + b"X")
        checks["corrupt_readback_rejected"] = rejects(lambda: check_local_receipt(bad, received["receipt"], pin))
        checks["corrupt_retry_not_overwritten"] = rejects(lambda: publish_fixture(bad, payload, pin)) and target.read_bytes() != payload
        short_payload, _short_pin = build_fixture(4)
        checks["valid_shorter_prefix_rejected"] = rejects(lambda: verify_package(short_payload, pin))
        uncertain = store("sync-unknown")
        with patch(__name__ + ".sync_directory", side_effect=OSError("synthetic sync failure")):
            checks["directory_sync_failure_no_ack"] = rejects(lambda: publish_fixture(uncertain, payload, pin))
        checks["uncertain_object_preserved"] = (uncertain / (pin.digest + ".archive.json")).exists()
        recovered = publish_fixture(uncertain, payload, pin)
        checks["uncertain_retry_reverified"] = check_local_receipt(uncertain, recovered["receipt"], pin)["local_copy_observed"]
        full = store("write-full")
        with patch(__name__ + ".write_all", side_effect=OSError(28, "synthetic full")):
            checks["write_failure_no_object_or_ack"] = rejects(lambda: publish_fixture(full, payload, pin)) and not list(full.iterdir())
        interrupted = store("interrupted")
        interrupted_fixture_transfer(interrupted)
        checks["interruption_left_no_final_object"] = not list(interrupted.glob("*.archive.json"))
        resumed = publish_fixture(interrupted, payload, pin)
        checks["partial_file_ignored_on_retry"] = check_local_receipt(interrupted, resumed["receipt"], pin)["local_copy_observed"]
        checks["source_bytes_and_pin_preserved"] = sha256(payload).hexdigest() == original == pin.digest
    checks["disposable_fixture_cleanup"] = not Path(folder).exists()
    require(all(value is True for value in checks.values()), "synthetic_archive_proof_failed")
    return {"schema": "pulpo.synthetic-archive-proof.v1", "classification": "Recorded", "passed": True,
        "source_commit": pin.producer_commit, "records": pin.records, "archive_bytes": pin.size,
        "archive_sha256": pin.digest, "checks": checks, "canonical_pruning": "unavailable",
        "boundary": "Local synthetic calibration prefix only; no live export or independent remote receipt."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    output = parser.add_mutually_exclusive_group(required=True)
    output.add_argument("--evidence", type=Path)
    output.add_argument("--evidence-dir", type=Path)
    args = parser.parse_args(argv)
    if not sys.platform.startswith("linux") or os.getuid() == 0:
        parser.error("run as an ordinary Linux user")
    try:
        if args.evidence_dir:
            require(args.evidence_dir.is_absolute() and args.evidence_dir.is_dir(), "existing evidence directory required")
            args.evidence = args.evidence_dir / ("synthetic-archive-" + secrets.token_hex(12) + ".json")
        require(args.evidence.is_absolute(), "absolute new evidence path required")
        report = run_prototype()
        publish_report(args.evidence, json.dumps(report, sort_keys=True))
        print(json.dumps({"passed": True, "evidence": str(args.evidence), "checks": len(report["checks"])}))
        return 0
    except (OSError, PrototypeError):
        print("synthetic_archive_proof_failed: inspect fixture/test evidence; no canonical remediation performed", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
