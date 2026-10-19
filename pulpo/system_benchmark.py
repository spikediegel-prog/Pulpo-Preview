"""Disposable process comparisons. No kernel, canonical store or authority client."""
from hashlib import sha256
import math
import multiprocessing
from pathlib import Path
import platform
import statistics
import shutil
import sys
import tempfile
import time

from . import evidence_tuning as tuning


class BenchmarkCancelled(ValueError):
    pass


class BenchmarkCleanupError(RuntimeError):
    pass


def profile_token(path):
    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(16385)
    except FileNotFoundError:
        return "missing"
    if len(raw) > 16384:
        raise ValueError("Profile exceeds the bounded read limit; inspect it before benchmarking")
    return sha256(raw).hexdigest()


def implementation_digest():
    result = sha256(tuning.source_digest().encode())
    if not getattr(sys, "frozen", False):
        for filename in ("system_benchmark.py", "tuning_app.py"):
            result.update(Path(__file__).with_name(filename).read_bytes())
    return result.hexdigest()


def peak_rss_bytes():
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes
            class Counters(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
                    (key, ctypes.c_size_t) for key in ("peak", "working", "peak_paged", "paged",
                                                      "peak_nonpaged", "nonpaged", "pagefile", "peak_pagefile")]
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.GetCurrentProcess.restype = wintypes.HANDLE
            query = ctypes.WinDLL("psapi", use_last_error=True).GetProcessMemoryInfo
            query.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
            query.restype = wintypes.BOOL
            value = Counters()
            value.cb = ctypes.sizeof(value)
            if not query(kernel.GetCurrentProcess(), ctypes.byref(value), value.cb):
                return None
            return value.peak
        import resource
        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return value if sys.platform == "darwin" else value * 1024
    except (OSError, ImportError, ValueError):
        return None


def _measure(workers, workspace, channel):
    # All child-created temporary fixtures stay beneath the parent's owned dir,
    # including correctness checks. Parent cleans only after confirmed shutdown.
    tempfile.tempdir = workspace
    try:
        from .tuning_app import benchmark_threads
        row = benchmark_threads(workers, repeats=1)
        row["peak_process_rss_bytes"] = peak_rss_bytes()
        channel.send(("result", row))
    except Exception:
        channel.send(("error", "Correctness or measurement failed; candidate cannot be saved"))
    finally:
        channel.close()


def measure_case(workers, stop, deadline):
    context = multiprocessing.get_context("spawn")
    base = Path(tempfile.gettempdir()).resolve()
    if shutil.disk_usage(base).free < 16 * 1024**2:
        raise ValueError("Less than 16 MiB free on the temporary volume; benchmark not started")
    workspace = Path(tempfile.mkdtemp(prefix="pulpo-system-benchmark-", dir=base))
    if workspace.resolve().parent != base:
        raise ValueError("Unexpected benchmark workspace")
    try:
        read, write = context.Pipe(duplex=False)
        child = context.Process(target=_measure, args=(workers, str(workspace), write))
        started = False
        try:
            if stop.is_set():
                raise BenchmarkCancelled("Cancelled; no setting saved")
            if time.monotonic() >= deadline:
                raise TimeoutError("Comparison exceeded 45 seconds; no setting saved")
            child.start()
            started = True
            write.close()
            while not read.poll(.05):
                if stop.is_set():
                    raise BenchmarkCancelled("Cancelled; no setting saved")
                if time.monotonic() >= deadline:
                    raise TimeoutError("Comparison exceeded 45 seconds; no setting saved")
                if not child.is_alive():
                    raise ValueError("Benchmark worker stopped without a complete result")
            kind, row = read.recv()
            child.join(3)
            if kind != "result" or child.exitcode != 0:
                raise ValueError("Correctness or worker cleanup failed; no setting saved")
            return row
        finally:
            if started:
                if child.is_alive():
                    child.terminate()
                    child.join(3)
                if child.is_alive():
                    child.kill()
                    child.join(3)
                if child.is_alive():
                    # Do not remove a workspace still in use by an unknown worker.
                    workspace = None  # Retain fixtures; never remove live-worker data.
                    raise BenchmarkCleanupError("Worker termination unverified; fixtures retained; operator investigation required")
                child.close()
            read.close()
            write.close()
    finally:
        if workspace is not None:
            shutil.rmtree(workspace)


def summarize(rows):
    seconds = [row["samples_seconds"][0] for row in rows]
    if len(seconds) != 5 or any(not math.isfinite(v) or v <= 0 for v in seconds):
        raise ValueError("Incomplete or invalid repetitions")
    if any(row["correctness"] != "PASS" for row in rows):
        raise ValueError("Correctness failed")
    median = statistics.median(seconds)
    peaks = [row["peak_process_rss_bytes"] for row in rows]
    return {"workers": rows[0]["workers"], "median_ms": median * 1000,
            "min_ms": min(seconds) * 1000, "max_ms": max(seconds) * 1000,
            "variation_percent": (max(seconds) - min(seconds)) / median * 100,
            "files_per_second": rows[0]["files"] / median,
            "cpu_core_percent": sum(row["process_cpu_seconds"] for row in rows) / sum(seconds) * 100,
            "peak_process_rss_bytes": max(peaks) if all(v is not None for v in peaks) else None,
            "fixture_payload_bytes": rows[0]["fixture_bytes"], "samples_seconds": seconds}


def classify(baseline, candidate):
    if candidate["max_ms"] < baseline["min_ms"] and candidate["median_ms"] < baseline["median_ms"] * .95:
        return "Faster"
    if candidate["min_ms"] > baseline["max_ms"] and candidate["median_ms"] > baseline["median_ms"] * 1.05:
        return "Slower"
    return "Inconclusive"


def compare_settings(profile, candidate, stop, progress):
    candidate = tuning.EvidenceSettings(candidate).validate().workers
    token = profile_token(profile)
    baseline = tuning.load_settings(profile).workers
    if candidate == baseline:
        raise ValueError("Choose a candidate different from the current worker count")
    source = implementation_digest()
    cases = {"baseline": [], "candidate": []}
    deadline = time.monotonic() + 45
    for repetition in range(5):
        order = ("baseline", "candidate") if repetition % 2 == 0 else ("candidate", "baseline")
        for name in order:
            if stop.is_set():
                raise BenchmarkCancelled("Cancelled; no setting saved")
            progress(f"Run {repetition + 1}/5 · {name} · disposable fixtures")
            cases[name].append(measure_case(baseline if name == "baseline" else candidate, stop, deadline))
    if stop.is_set():
        raise BenchmarkCancelled("Cancelled; no setting saved")
    if profile_token(profile) != token or source != implementation_digest():
        raise ValueError("Profile or benchmark implementation changed; compare again")
    first, second = summarize(cases["baseline"]), summarize(cases["candidate"])
    return {"schema": "pulpo.system-comparison.v1", "claim": "Recorded disposable capture-only comparison",
            "machine": tuning.machine(), "environment": "WSL Linux VM" if "microsoft" in platform.release().lower() else platform.system(),
            "source_sha256": source, "profile_token": token, "baseline": first, "candidate": second,
            "classification": "Inconclusive" if baseline <= 1 and candidate <= 1 else classify(first, second),
            "correctness": "PASS", "repetitions": 5,
            "authority_effect": "none", "completed_at": time.time(), "workload": "64 files, 4 MiB payload; capture-only"}


def save_candidate(report, profile):
    # Only the session's completed report reaches this function; no report import.
    if (report is None or report.get("correctness") != "PASS" or not 0 <= time.time() - report["completed_at"] <= 900
            or report["source_sha256"] != implementation_digest() or report["machine"] != tuning.machine()
            or report["profile_token"] != profile_token(profile)
            or report["baseline"]["workers"] != tuning.load_settings(profile).workers):
        raise ValueError("Comparison missing or stale; compare again before saving")
    return tuning.save_settings(tuning.EvidenceSettings(report["candidate"]["workers"]), profile,
                                fallback_previous=tuning.EvidenceSettings(report["baseline"]["workers"]))


def run_task(operation, arguments, messages, stop):
    """Thread target intentionally holds no Tk objects or UI callbacks."""
    try:
        if operation == "compare":
            result = compare_settings(*arguments, stop, lambda text: messages.put(("progress", text)))
        elif operation == "save":
            result = str(save_candidate(*arguments))
        elif operation == "undo":
            result = str(tuning.restore_previous(*arguments))
        else:
            raise ValueError("Unsupported operation")
        messages.put(("result", (operation, result)))
    except BenchmarkCancelled as exc:
        messages.put(("cancelled", str(exc)))
    except BenchmarkCleanupError as exc:
        messages.put(("blocked", str(exc)))
    except Exception as exc:
        messages.put(("error", str(exc)))
    finally:
        messages.put(("done", None))
