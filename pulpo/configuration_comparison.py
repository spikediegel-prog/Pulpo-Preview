"""Bounded performance-profile observations and report applicability, not authority."""
from dataclasses import dataclass
from pathlib import Path
import math
import stat
import time

from . import evidence_tuning as tuning
from . import system_benchmark as benchmark


@dataclass(frozen=True)
class ConfigurationSnapshot:
    checked_at: float
    workers: int | None
    previous_workers: int | None
    status: str
    profile_token: str | None
    source_sha256: str | None
    machine: tuple


def inspect_configuration(profile):
    """Explicit bounded observation of the already-configured performance profile.

    Uses existing validation/fallback semantics, never a database or source export.
    A read race, non-regular file or oversized profile cannot supply a context.
    No file mtime is promoted into a configuration change time.
    """
    now = time.time()
    try:
        path = Path(profile)
        try:
            if not stat.S_ISREG(path.lstat().st_mode):
                raise ValueError("non_regular_profile")
        except FileNotFoundError:
            pass
        token = benchmark.profile_token(path)
        previous = None
        if token == "missing":
            workers, status = tuning.recommended().workers, "No saved profile · serial default"
        else:
            try:
                document = tuning._read_profile(path)
                workers, status = document["settings"]["workers"], "Saved profile accepted"
                previous = document["previous_settings"]
                previous = previous["workers"] if previous is not None else None
            except (OSError, ValueError, TypeError, KeyError, RecursionError):
                workers, status = tuning.recommended().workers, "Profile not accepted · serial fallback"
        if benchmark.profile_token(path) != token:
            raise ValueError("profile_changed_during_check")
        source, machine = benchmark.implementation_digest(), tuple(sorted(tuning.machine().items()))
        return ConfigurationSnapshot(now, workers, previous, status, token, source, machine)
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        return ConfigurationSnapshot(now, None, None, "Profile observation unavailable · check again", None, None, ())


def candidate_workers(text):
    try:
        return tuning.EvidenceSettings(int(text)).validate().workers
    except (ValueError, TypeError, OverflowError):
        return None


def collector_mode(workers):
    return "Unknown" if workers is None else "Serial" if workers <= 1 else "Threads"


def applicability(snapshot, candidate, report, now=None):
    """Match a session report to the last explicit context check, never save it."""
    if candidate is None:
        return "Invalid proposal · choose a supported integer"
    if snapshot is None or snapshot.profile_token is None:
        return "Unknown · re-check current settings"
    if candidate == snapshot.workers:
        return "No worker-count change · choose a different candidate to compare"
    if report is None:
        return "No comparison for this proposal · run a benchmark"
    try:
        if (report["schema"] != "pulpo.system-comparison.v1" or report["correctness"] != "PASS"
                or report["authority_effect"] != "none" or report["repetitions"] != 5
                or report["classification"] not in {"Faster", "Slower", "Inconclusive"}
                or type(report["baseline"]["workers"]) is not int
                or type(report["candidate"]["workers"]) is not int):
            raise ValueError("invalid_report")
        if report["candidate"]["workers"] != candidate:
            return "Candidate changed · compare again"
        if report["profile_token"] != snapshot.profile_token or report["baseline"]["workers"] != snapshot.workers:
            return "Current profile changed · compare again"
        if report["machine"] != dict(snapshot.machine):
            return "Machine context changed · compare again"
        if report["source_sha256"] != snapshot.source_sha256:
            return "Benchmark implementation changed · compare again"
        completed = report["completed_at"]
        if type(completed) not in (int, float) or not math.isfinite(completed):
            raise ValueError("invalid_time")
        age = (time.time() if now is None else now) - completed
        if age < 0:
            return "Clock mismatch · compare again"
        if age > 900:
            return "Comparison expired after 15 minutes · compare again"
        for row in (report["baseline"], report["candidate"]):
            for key in ("median_ms", "min_ms", "max_ms"):
                if type(row[key]) not in (int, float) or not math.isfinite(row[key]) or row[key] <= 0:
                    raise ValueError("invalid_measurement")
            if not row["min_ms"] <= row["median_ms"] <= row["max_ms"]:
                raise ValueError("invalid_range")
        return "Applicable to last checked context"
    except (KeyError, TypeError, ValueError, OverflowError):
        return "Incomplete or invalid comparison · compare again"


@dataclass(frozen=True)
class LocalConfigurationChange:
    operation: str
    before_workers: int | None
    after_workers: int | None
    received_at: float
