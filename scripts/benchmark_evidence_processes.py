#!/usr/bin/env python3
"""Compare serial, two-thread, and spawned-process evidence collection.

Requires psutil for benchmark CPU/RAM sampling. --self-test uses only the
standard library and Pulpo. All observations are of temporary fixture files.
The process collector is experimental and lives only in this benchmark.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from hashlib import sha256
import argparse
import json
import multiprocessing
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
from threading import Event, Thread
from time import perf_counter
from types import SimpleNamespace

_worker_evidence = None
_worker_cache = None


def load(repo):
    if not (repo / "pulpo/effect_reconcile.py").is_file():
        raise SystemExit("--repo must name a Pulpo checkout")
    sys.path.insert(0, str(repo))
    import pulpo.effect_reconcile as evidence
    return evidence


def worker_init(repo):
    global _worker_evidence, _worker_cache
    _worker_evidence = load(Path(repo))
    _worker_cache = _worker_evidence.ShardedEvidenceDigestCache(shards=8, max_entries=32)


def worker_capture(surface):
    # Only a surface specification crosses into workers, never a kernel,
    # canonical writer, permit, approval, or signing credential.
    return _worker_evidence.capture_surface(surface, digest_cache=_worker_cache)


class ProcessCollector:
    def __init__(self, repo, workers):
        self.pool = ProcessPoolExecutor(max_workers=workers,
            mp_context=multiprocessing.get_context("spawn"),
            initializer=worker_init, initargs=(str(repo),))
        self.closed = False

    def capture(self, envelope):
        if self.closed:
            raise RuntimeError("collector closed")
        # map preserves surface order. Transfer of complete canonical snapshots
        # and coordinator deserialization are INCLUDED in capture timings.
        return tuple(self.pool.map(worker_capture, envelope.surfaces, chunksize=1))

    def close(self):
        if not self.closed:
            self.closed = True
            self.pool.shutdown(wait=True, cancel_futures=True)


def make_fixture(evidence, directory, surface_count, files, file_bytes):
    surfaces, paths = [], []
    content = b"x" * file_bytes
    for number in range(surface_count):
        root = directory / f"surface-{number}"
        root.mkdir()
        surfaces.append(evidence.SurfaceSpec(str(root), "evidence"))
        for index in range(files):
            path = root / f"file-{index:06d}.bin"
            path.write_bytes(content)
            paths.append(path)
    envelope = evidence.EffectEnvelope(
        executable_path=str(Path(__file__).resolve()),
        executable_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        argv=("benchmark-fixture-no-execution",), workdir=str(directory),
        source_sha="synthetic-fixture", profile="evidence-process-benchmark",
        expires_at_ns=1, surfaces=tuple(surfaces))
    return envelope, paths


def create_collector(name, workers, evidence, repo):
    if name == "processes":
        return ProcessCollector(repo, workers)
    return evidence.ParallelEvidenceCollector(workers=workers, cache_entries=32)


class ProcessTreeSampler:
    """Sample this benchmark and descendants, not unrelated applications."""
    def __init__(self, psutil, interval):
        self.psutil = psutil
        self.root = psutil.Process(os.getpid())
        self.interval = interval
        self.stop_event = Event()
        self.thread = None
        self.baseline = {}
        self.last_cpu = {}
        self.peak_rss = 0
        self.peak_processes = 0
        self.samples = 0
        self.errors = 0

    def snapshot(self):
        try:
            processes = [self.root, *self.root.children(recursive=True)]
        except self.psutil.Error:
            processes = [self.root]
            self.errors += 1
        cpu, rss, count = {}, 0, 0
        for process in processes:
            try:
                key = (process.pid, process.create_time())
                times = process.cpu_times()
                cpu[key] = times.user + times.system
                rss += process.memory_info().rss
                count += 1
            except self.psutil.Error:
                self.errors += 1
        self.last_cpu.update(cpu)
        self.peak_rss = max(self.peak_rss, rss)
        self.peak_processes = max(self.peak_processes, count)
        self.samples += 1
        return cpu

    def start(self):
        self.baseline = self.snapshot()
        def sample():
            while not self.stop_event.wait(self.interval):
                self.snapshot()
        self.thread = Thread(target=sample, daemon=True)
        self.thread.start()

    def finish(self, wall_seconds, logical_cpus):
        self.stop_event.set()
        self.thread.join()
        self.snapshot()
        cpu_seconds = sum(max(0.0, total - self.baseline.get(key, 0.0))
                          for key, total in self.last_cpu.items())
        return {"cpu_seconds": cpu_seconds,
            "average_cpu_cores_equivalent": cpu_seconds / wall_seconds,
            "average_percent_logical_cpu_capacity": 100 * cpu_seconds / wall_seconds / logical_cpus,
            "peak_sum_rss_mib": self.peak_rss / 1024 ** 2,
            "peak_process_count": self.peak_processes,
            "sample_count": self.samples, "sampling_errors": self.errors}


def self_test(evidence, repo):
    with tempfile.TemporaryDirectory(prefix="pulpo-process-self-test-") as scratch:
        envelope, paths = make_fixture(evidence, Path(scratch), 4, 2, 16)
        for name, workers in [("serial", 0), ("threads", 2), ("processes", 1), ("processes", 2)]:
            collector = create_collector(name, workers, evidence, repo)
            try:
                expected = evidence.capture_envelope_surfaces(envelope)
                if collector.capture(envelope) != expected or collector.capture(envelope) != expected:
                    raise RuntimeError(f"snapshot/order/repeat mismatch: {name}/{workers}")
                path = paths[0]
                original = path.read_bytes()
                stamp = path.stat()
                path.write_bytes(b"z" * len(original))
                os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
                changed = collector.capture(envelope)
                expected_changed = evidence.capture_envelope_surfaces(envelope)
                if changed == expected or changed != expected_changed:
                    raise RuntimeError("same-size restored-mtime edit hidden")
                added = Path(envelope.surfaces[1].root) / "added.bin"
                added.write_bytes(b"new")
                if collector.capture(envelope) != evidence.capture_envelope_surfaces(envelope):
                    raise RuntimeError("new file mismatch")
                added.unlink()
                path.unlink()
                if collector.capture(envelope) != evidence.capture_envelope_surfaces(envelope):
                    raise RuntimeError("deleted file mismatch")
                path.write_bytes(original)
                # A bad worker input must propagate an exception, never return
                # partial evidence or an apparently successful empty snapshot.
                try:
                    collector.capture(SimpleNamespace(surfaces=(object(),)))
                except AttributeError:
                    pass
                else:
                    raise RuntimeError("worker error silently accepted")
                if collector.capture(envelope) != evidence.capture_envelope_surfaces(envelope):
                    raise RuntimeError("collector did not recover after worker error")
                print(f"PASS {name}/{workers}: full snapshot equality, order, repeat, content edits, add/delete, error propagation")
            finally:
                collector.close()
                collector.close()
            if name == "processes":
                try:
                    collector.capture(envelope)
                except RuntimeError:
                    pass
                else:
                    raise RuntimeError("closed process collector accepted capture")
    print("PASS process pool shutdown, idempotent close, and capture-after-close rejection")


def describe(values):
    return {"median": statistics.median(values), "min": min(values),
            "max": max(values), "samples": values}


def measure_variant(name, workers, evidence, repo, envelope, expected, args, psutil):
    started = perf_counter()
    collector = create_collector(name, workers, evidence, repo)
    setup = perf_counter() - started
    sampler = None
    try:
        started = perf_counter()
        first = collector.capture(envelope)
        first_seconds = perf_counter() - started
        if first != expected:
            raise RuntimeError(f"first snapshot mismatch: {name}/{workers}")
        # Processes are alive before CPU baselines are taken. Initialization and
        # first capture are separately recorded, not silently amortized away.
        sampler = ProcessTreeSampler(psutil, args.sample_interval)
        sampler.start()
        captures = []
        began = perf_counter()
        try:
            while len(captures) < args.minimum_captures or perf_counter() - began < args.measure_seconds:
                start = perf_counter()
                result = collector.capture(envelope)
                captures.append(perf_counter() - start)
                if result != expected:
                    raise RuntimeError(f"steady snapshot mismatch: {name}/{workers}")
        finally:
            wall = perf_counter() - began
            resources = sampler.finish(wall, psutil.cpu_count(logical=True) or 1)
            sampler = None
        return {"setup_seconds": setup, "first_capture_seconds": first_seconds,
            "capture_seconds": captures, "measurement_wall_seconds": wall,
            "captures_per_measurement_second": len(captures) / wall,
            "resources": resources}
    finally:
        started = perf_counter()
        collector.close()
        # Returned dictionary is subsequently populated with close timing by
        # the caller only on success; shutdown still runs when observation fails.
        measure_variant.last_close_seconds = perf_counter() - started


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--processes", type=int, nargs="+", default=[1, 2, 4, 8])
    parser.add_argument("--surfaces", type=int, default=32)
    parser.add_argument("--files-per-surface", type=int, nargs="+", default=[4, 16])
    parser.add_argument("--file-bytes", type=int, nargs="+", default=[4096, 65536])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--measure-seconds", type=float, default=1.0)
    parser.add_argument("--minimum-captures", type=int, default=5)
    parser.add_argument("--sample-interval", type=float, default=0.05)
    parser.add_argument("--json", type=Path, default=Path("evidence-processes.json"))
    args = parser.parse_args()
    repo = args.repo.resolve()
    evidence = load(repo)
    if args.self_test:
        self_test(evidence, repo)
        return
    counts = args.files_per_surface + args.file_bytes + [args.surfaces, args.repeats, args.minimum_captures]
    if min(counts) <= 0 or min(args.processes) < 1 or max(args.processes) > 32:
        parser.error("positive counts required; process counts must be 1..32")
    if min(args.measure_seconds, args.sample_interval) <= 0:
        parser.error("measurement and sampling intervals must be positive")
    if any(len(set(v)) != len(v) for v in (args.processes, args.files_per_surface, args.file_bytes)):
        parser.error("workload lists must contain unique values")
    try:
        import psutil
    except ImportError:
        raise SystemExit("CPU/RAM sampling requires psutil. Install with: python -m pip install psutil")
    try:
        commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"],
                                         stderr=subprocess.DEVNULL, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    configs = [("serial", 0), ("threads", 2), *[("processes", n) for n in args.processes]]
    output = {"schema": "pulpo.evidence-process-benchmark.v1",
        "claim": "Recorded fixture observations; process collector remains Proposed",
        "machine": {"python": platform.python_version(), "platform": platform.platform(),
                    "physical_cores": psutil.cpu_count(logical=False),
                    "logical_cpus": psutil.cpu_count(logical=True),
                    "memory_mib": psutil.virtual_memory().total / 1024 ** 2},
        "git_commit": commit,
        "source_sha256": sha256((repo / "pulpo/effect_reconcile.py").read_bytes()).hexdigest(),
        "script_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "settings": {k: v for k, v in vars(args).items() if k not in {"repo", "json"}},
        "boundaries": ["Temporary files only; no canonical writer, credentials, kernel, execution, or external provider.",
            "Only surface specifications and complete canonical snapshots cross process boundaries.",
            "Each observation rereads metadata and file contents; every result must equal canonical serial capture.",
            "Spawn on all operating systems; IPC and deserialization included in capture timings.",
            "Process pools reused during each measurement; setup/first capture/shutdown reported separately.",
            "Steady warm-OS-cache measurements; CPU phase includes equality checks and sampler overhead.",
            "CPU cores equivalent = benchmark-process-tree CPU seconds / phase wall seconds, not pinned physical cores.",
            "CPU utilization is average phase occupancy; it does not identify which physical cores were used.",
            "RSS is sampled sum over processes, counts shared pages repeatedly, and may miss brief peaks.",
            "Thread mode is the current two-worker collector, including its per-capture pool creation.",
            "Worker concurrency is limited by surface count; this is capture-only, not full governed-cycle proof."],
        "results": []}
    print("files  bytes/file  variant/workers    capture_ms  files/sec  CPU equivalents  peak RSS MiB")
    with tempfile.TemporaryDirectory(prefix="pulpo-evidence-processes-") as scratch:
        base = Path(scratch)
        for file_bytes in args.file_bytes:
            for files in args.files_per_surface:
                with tempfile.TemporaryDirectory(dir=base) as directory:
                    envelope, paths = make_fixture(evidence, Path(directory), args.surfaces, files, file_bytes)
                    expected = evidence.capture_envelope_surfaces(envelope)
                    repetitions = {config: [] for config in configs}
                    for repeat in range(args.repeats):
                        order = configs if repeat % 2 == 0 else list(reversed(configs))
                        for name, workers in order:
                            result = measure_variant(name, workers, evidence, repo, envelope,
                                                     expected, args, psutil)
                            result["close_seconds"] = measure_variant.last_close_seconds
                            repetitions[(name, workers)].append(result)
                    variants = []
                    for (name, workers), runs in repetitions.items():
                        per_repeat = [statistics.median(run["capture_seconds"]) for run in runs]
                        median = statistics.median(per_repeat)
                        occupancy = describe([run["resources"]["average_cpu_cores_equivalent"] for run in runs])
                        peak_rss = max(run["resources"]["peak_sum_rss_mib"] for run in runs)
                        variant = {"variant": name, "workers": workers,
                            "effective_surface_concurrency": min(max(1, workers), args.surfaces),
                            "capture_median_ms": median * 1000,
                            "per_repeat_median_ms": [v * 1000 for v in per_repeat],
                            "files_per_second": len(paths) / median,
                            "mib_per_second": len(paths) * file_bytes / 1024 ** 2 / median,
                            "cpu_cores_equivalent": occupancy, "peak_sum_rss_mib": peak_rss,
                            "setup_seconds": describe([run["setup_seconds"] for run in runs]),
                            "first_capture_seconds": describe([run["first_capture_seconds"] for run in runs]),
                            "close_seconds": describe([run["close_seconds"] for run in runs]),
                            "runs": runs}
                        variants.append(variant)
                        print(f"{len(paths):5d}  {file_bytes:10d}  {name:9s}/{workers:<2d}  "
                              f"{median * 1000:10.3f}  {len(paths) / median:9.0f}  "
                              f"{occupancy['median']:15.2f}  {peak_rss:12.1f}")
                    thread_time = next(v["capture_median_ms"] for v in variants if v["variant"] == "threads")
                    for variant in variants:
                        variant["speedup_vs_two_threads"] = thread_time / variant["capture_median_ms"]
                    output["results"].append({"total_files": len(paths), "file_bytes": file_bytes,
                                              "surfaces": args.surfaces, "variants": variants})
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(f"Results: {args.json.resolve()}")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
