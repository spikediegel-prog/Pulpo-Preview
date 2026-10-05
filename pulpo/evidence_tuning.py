"""Bounded evidence performance settings. No authority or canonical writers.

Process collection is deliberately benchmark-only. Persisted settings contain
only a thread count; every loaded value is checked again, never trusted by digest.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from functools import lru_cache
import json
import os
from pathlib import Path
import platform
import sys
import tempfile

SCHEMA = "pulpo.evidence-performance.v1"
MAX_THREADS = 16


def default_profile_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    else:
        base = Path.home() / ".config"
    return base / "PulpoPreview" / "evidence-performance.json"


def machine() -> dict:
    return {"platform": platform.platform(), "python": platform.python_version(),
            "logical_cpus": os.cpu_count() or 1}


def thread_limit() -> int:
    return min(MAX_THREADS, os.cpu_count() or 1)


@lru_cache(maxsize=1)
def source_digest() -> str:
    digest = sha256()
    paths = [Path(sys.executable)] if getattr(sys, "frozen", False) else [
        Path(__file__).with_name(name) for name in ("effect_reconcile.py", "evidence_tuning.py")]
    for path in paths:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class EvidenceSettings:
    workers: int = 2

    def validate(self):
        if type(self.workers) is not int or not 0 <= self.workers <= thread_limit():
            raise ValueError(f"Evidence workers must be an integer from 0 to {thread_limit()}")
        return self


def recommended() -> EvidenceSettings:
    return EvidenceSettings(min(2, thread_limit()))


def _strict_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate configuration key")
        result[key] = value
    return result


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _read_profile(path, *, allow_stale=False):
    # Validation is shared by runtime resolution and explicit rollback.
    with path.open("rb") as handle:
        content = handle.read(16385)
    if len(content) > 16384:
        raise ValueError("Profile too large")
    document = json.loads(content.decode("utf-8"), object_pairs_hook=_strict_pairs)
    if type(document) is not dict or set(document) != {
        "schema", "machine", "source_sha256", "settings", "previous_settings", "digest"
    }:
        raise ValueError("Invalid profile fields")
    payload = {key: value for key, value in document.items() if key != "digest"}
    if document["schema"] != SCHEMA:
        raise ValueError("Unknown profile schema")
    if not allow_stale and document["machine"] != machine():
        raise ValueError("Profile is stale")
    if not allow_stale and document["source_sha256"] != source_digest():
        raise ValueError("Collector implementation changed")
    if document["digest"] != sha256(_canonical(payload)).hexdigest():
        raise ValueError("Profile digest mismatch")
    settings = document["settings"]
    if type(settings) is not dict or set(settings) != {"workers"}:
        raise ValueError("Unsupported performance control")
    EvidenceSettings(**settings).validate()
    previous = document["previous_settings"]
    if previous is not None:
        if type(previous) is not dict or set(previous) != {"workers"}:
            raise ValueError("Invalid previous settings")
        EvidenceSettings(**previous).validate()
    return document


def load_settings(path: Path | str | None = None) -> EvidenceSettings:
    """Untrusted/missing/stale profiles fall back to complete thread collection."""
    path = Path(path) if path is not None else default_profile_path()
    try:
        return EvidenceSettings(**_read_profile(path)["settings"])
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        return recommended()


def check_settings(settings: EvidenceSettings) -> None:
    """Fresh canonical equality, errors and edits; never use a stored PASS flag."""
    settings.validate()
    from .effect_reconcile import (ParallelEvidenceCollector, SurfaceSpec,
                                  capture_surface)
    from types import SimpleNamespace
    with tempfile.TemporaryDirectory(prefix="pulpo-tuning-check-") as temporary:
        root = Path(temporary)
        surfaces = []
        for index in range(4):
            directory = root / str(index)
            directory.mkdir()
            (directory / "content.bin").write_bytes(b"original")
            surfaces.append(SurfaceSpec(str(directory), "evidence"))
        envelope = SimpleNamespace(surfaces=tuple(surfaces))
        collector = ParallelEvidenceCollector(workers=settings.workers)
        try:
            def compare():
                actual = collector.capture(envelope)
                expected = tuple(capture_surface(surface) for surface in surfaces)
                if actual != expected:
                    raise ValueError("Collector differs from canonical serial evidence")
            compare()
            compare()
            edited = root / "0/content.bin"
            old_stat = edited.stat()
            edited.write_bytes(b"modified")
            os.utime(edited, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))
            compare()
            (root / "1/added.bin").write_bytes(b"added")
            (root / "2/content.bin").unlink()
            compare()
            try:
                collector.capture(SimpleNamespace(surfaces=(object(),)))
            except AttributeError:
                pass
            else:
                raise ValueError("Malformed surface was accepted")
            compare()
        finally:
            collector.close()


def save_settings(settings: EvidenceSettings, path: Path | str | None = None) -> Path:
    """Save a local hint only after fresh validation; replace atomically."""
    check_settings(settings)
    destination = Path(path) if path is not None else default_profile_path()
    try:
        previous = _read_profile(destination)["settings"]
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        previous = None
    return _write_settings(settings, destination, previous)


def _write_settings(settings, destination, previous):
    payload = {"schema": SCHEMA, "machine": machine(), "source_sha256": source_digest(),
               "settings": asdict(settings), "previous_settings": previous}
    document = {**payload, "digest": sha256(_canonical(payload)).hexdigest()}
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".evidence-", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(document, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, destination)
    finally:
        Path(name).unlink(missing_ok=True)
    return destination


def refresh_settings(path: Path | str | None = None) -> Path:
    """Upgrade a performance hint only after bounds and fresh snapshot checks."""
    path = Path(path) if path is not None else default_profile_path()
    document = _read_profile(path, allow_stale=True)
    if document["machine"] == machine() and document["source_sha256"] == source_digest():
        return path
    settings = EvidenceSettings(**document["settings"])
    check_settings(settings)
    previous = document["previous_settings"]
    if previous is not None:
        check_settings(EvidenceSettings(**previous))
    return _write_settings(settings, path, previous)


def restore_previous(path: Path | str | None = None) -> Path:
    path = Path(path) if path is not None else default_profile_path()
    previous = _read_profile(path)["previous_settings"]
    if previous is None:
        raise ValueError("No valid previous setting is recorded")
    return save_settings(EvidenceSettings(**previous), path)


def create_collector(path: Path | str | None = None):
    from .effect_reconcile import ParallelEvidenceCollector
    return ParallelEvidenceCollector(workers=load_settings(path).workers)
