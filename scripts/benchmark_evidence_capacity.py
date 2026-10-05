#!/usr/bin/env python3
"""Compare evidence throughput and capacity at a fixed capture-time budget.

The reusable pool is a benchmark-only candidate. Every capture still invokes
Pulpo's canonical capture_surface, rereading metadata and hashing file contents.
Fixtures are temporary. No kernel state, approvals, or external effects are used.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
from threading import RLock
from time import perf_counter


def load(repo):
    if not (repo / "pulpo/effect_reconcile.py").is_file():
        raise SystemExit("--repo must name a Pulpo checkout")
    sys.path.insert(0, str(repo))
    import pulpo.effect_reconcile as evidence
    return evidence


def reusable_type(evidence):
    class ReusablePoolCollector(evidence.ParallelEvidenceCollector):
        """Experimental reader with explicit close; no canonical writer."""
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self._pool = None
            self._lifecycle_lock = RLock()
            self._closed = False

        def capture(self, envelope):
            with self._lifecycle_lock:
                if self._closed:
                    raise RuntimeError("collector closed")
                surfaces = tuple(envelope.surfaces)
                if self.workers <= 1 or len(surfaces) <= 1:
                    return tuple(evidence.capture_surface(s, digest_cache=self.cache) for s in surfaces)
                if self._pool is None:
                    self._pool = ThreadPoolExecutor(max_workers=self.workers)
                # Submit under the lifecycle lock so close cannot race submission.
                pending = list(self._pool.map(self._capture_one, surfaces))
                return tuple(pending)

        def _capture_one(self, surface):
            return evidence.capture_surface(surface, digest_cache=self.cache)

        def close(self):
            with self._lifecycle_lock:
                if self._closed:
                    return
                self._closed = True
                pool, self._pool = self._pool, None
                if pool is not None:
                    pool.shutdown(wait=True)
                self.cache.clear()
    return ReusablePoolCollector


def envelope_for(evidence, directory, surfaces):
    return evidence.EffectEnvelope(executable_path=str(Path(__file__).resolve()),
        executable_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        argv=("benchmark-only-no-execution",), workdir=str(directory),
        source_sha="synthetic-fixture", profile="evidence-capacity-benchmark",
        expires_at_ns=1, surfaces=tuple(surfaces))


def make_fixture(evidence, directory, surface_count, files, file_bytes):
    specs, paths = [], []
    content = b"x" * file_bytes
    for index in range(surface_count):
        root = directory / f"surface-{index}"
        root.mkdir()
        specs.append(evidence.SurfaceSpec(str(root), "evidence"))
        for number in range(files):
            path = root / f"file-{number:06d}.bin"
            path.write_bytes(content)
            paths.append(path)
    return envelope_for(evidence, directory, specs), paths


def measure(operation, repeats):
    samples = []
    for _ in range(repeats):
        start = perf_counter()
        operation()
        samples.append(perf_counter() - start)
    return {"median_ms": statistics.median(samples) * 1000,
            "min_ms": min(samples) * 1000, "max_ms": max(samples) * 1000,
            "samples_seconds": samples}


def metadata_scan(envelope):
    # Diagnostic only: directory enumeration and lstat, without file reads,
    # snapshot serialization, canonical digests, or authoritative evidence.
    count = 0
    for spec in envelope.surfaces:
        stack = [Path(spec.root)]
        while stack:
            path = stack.pop()
            path.lstat()
            count += 1
            if path.is_dir() and not path.is_symlink():
                stack.extend(path.iterdir())
    return count


def file_hashes(paths):
    # Diagnostic only: serial file reads/hashes, no snapshot metadata/digest.
    for path in paths:
        digest = sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        digest.digest()


def configuration_list(workers):
    configurations = [("serial", 0)]
    for number in workers:
        if number > 1:
            configurations.extend([("current_pool", number), ("reused_pool", number)])
    return configurations


def self_test(evidence):
    from unittest.mock import patch
    candidate = reusable_type(evidence)
    checks = []
    with tempfile.TemporaryDirectory(prefix="pulpo-evidence-self-test-") as scratch:
        directory = Path(scratch)
        envelope, paths = make_fixture(evidence, directory, 3, 2, 8)
        for name, workers in configuration_list([2, 4]):
            collector_type = candidate if name == "reused_pool" else evidence.ParallelEvidenceCollector
            collector = collector_type(workers=workers, cache_entries=16)
            try:
                expected = evidence.capture_envelope_surfaces(envelope)
                if collector.capture(envelope) != expected:
                    raise RuntimeError(f"snapshot mismatch: {name}/{workers}")
                if collector.capture(envelope) != expected:
                    raise RuntimeError(f"repeat/order mismatch: {name}/{workers}")
                pool = getattr(collector, "_pool", None)
                if name == "reused_pool":
                    collector.capture(envelope)
                    if pool is None or collector._pool is not pool:
                        raise RuntimeError("pool was not reused")
                path = paths[0]
                stamp = path.stat()
                original = path.read_bytes()
                path.write_bytes(b"z" * len(original))
                os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
                changed = collector.capture(envelope)
                if changed[0].entries == expected[0].entries or changed != evidence.capture_envelope_surfaces(envelope):
                    raise RuntimeError("same-size, restored-mtime edit hidden")
                path.write_bytes(original)
                os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
                fresh = collector.capture(envelope)
                added = Path(envelope.surfaces[1].root) / "added.bin"
                added.write_bytes(b"new")
                if collector.capture(envelope) == fresh:
                    raise RuntimeError("new file hidden")
                added.unlink()
                path.unlink()
                if collector.capture(envelope) == fresh:
                    raise RuntimeError("deleted file hidden")
                path.write_bytes(original)
                with patch.object(evidence, "_entry_from_lstat", side_effect=PermissionError("fixture")):
                    try:
                        collector.capture(envelope)
                    except evidence.EffectReconciliationError:
                        pass
                    else:
                        raise RuntimeError("read failure silently accepted")
                if collector.capture(envelope) != evidence.capture_envelope_surfaces(envelope):
                    raise RuntimeError("collector failed to recover after observation error")
                checks.append(f"{name}/{workers}: equality, ordering, repeated capture, content edits, additions, deletions, read errors")
            finally:
                collector.close()
                collector.close()
            if name == "reused_pool":
                if collector._pool is not None:
                    raise RuntimeError("pool remains after close")
                try:
                    collector.capture(envelope)
                except RuntimeError:
                    pass
                else:
                    raise RuntimeError("closed candidate accepted capture")
    for check in checks:
        print("PASS " + check)
    print("PASS candidate pool reuse, shutdown, idempotent close, and capture-after-close rejection")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--self-test", action="store_true", help="validate the experimental collector; no benchmark")
    parser.add_argument("--files-per-surface", nargs="+", type=int, default=[20, 30, 40, 80, 200])
    parser.add_argument("--file-bytes", nargs="+", type=int, default=[4096, 65536])
    parser.add_argument("--surfaces", type=int, default=4)
    parser.add_argument("--workers", nargs="+", type=int, default=[2, 4, 8])
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--captures-per-repeat", type=int, default=3)
    parser.add_argument("--budget-ms", type=float, default=20.0, help="time budget for ONE complete capture")
    parser.add_argument("--tolerance-percent", type=float, default=10.0)
    parser.add_argument("--json", type=Path, default=Path("evidence-capacity.json"))
    args = parser.parse_args()
    evidence = load(args.repo.resolve())
    if args.self_test:
        self_test(evidence)
        return
    if min(args.files_per_surface + args.file_bytes + [args.surfaces, args.repeats,
        args.captures_per_repeat]) < 1 or min(args.workers) < 0 or args.budget_ms <= 0 or args.tolerance_percent < 0:
        parser.error("workload counts and budget must be positive; workers/tolerance nonnegative")
    if any(len(set(values)) != len(values) for values in
           (args.files_per_surface, args.file_bytes, args.workers)):
        parser.error("workload lists and worker counts must contain unique values")
    configs = configuration_list(args.workers)
    candidate = reusable_type(evidence)
    repo = args.repo.resolve()
    try:
        commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    output = {"schema": "pulpo.evidence-capacity.v1", "claim": "Recorded synthetic measurements; candidate remains Proposed",
        "python": platform.python_version(), "platform": platform.platform(), "cpu_count": os.cpu_count(),
        "git_commit": commit, "source_sha256": sha256((repo / "pulpo/effect_reconcile.py").read_bytes()).hexdigest(),
        "script_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "settings": {k: v for k, v in vars(args).items() if k not in {"repo", "json"}},
        "boundaries": ["Capture-only reader; no authority, execution, canonical mutation, or external provider.",
            "All canonical captures reread current metadata and hash every file; cache semantics unchanged.",
            "Fixture generation and equality checks excluded; setup/first capture/close recorded separately.",
            "Warm OS caches; repeated steady captures; no physical cold-disk claim.",
            "Diagnostics omit canonical evidence operations and are not an additive breakdown.",
            "Capacity is largest TESTED workload under median time limit, not extrapolated maximum or tail guarantee.",
            "Workers parallelize surfaces; effective concurrency is limited by surface count."],
        "results": [], "capacity": []}
    with tempfile.TemporaryDirectory(prefix="pulpo-evidence-capacity-") as scratch:
        base = Path(scratch)
        for file_bytes in args.file_bytes:
            for files in args.files_per_surface:
                with tempfile.TemporaryDirectory(dir=base) as directory:
                    envelope, paths = make_fixture(evidence, Path(directory), args.surfaces, files, file_bytes)
                    expected = evidence.capture_envelope_surfaces(envelope)
                    diagnostics = {"metadata_scan_only": measure(lambda: metadata_scan(envelope), args.repeats),
                                   "serial_file_read_hash_only": measure(lambda: file_hashes(paths), args.repeats)}
                    collected = {(name, n): {stage: [] for stage in ("setup", "first_capture", "steady_capture", "close")}
                                 for name, n in configs}
                    for repeat in range(args.repeats):
                        order = configs if repeat % 2 == 0 else list(reversed(configs))
                        for name, workers in order:
                            collector_type = candidate if name == "reused_pool" else evidence.ParallelEvidenceCollector
                            start = perf_counter()
                            collector = collector_type(workers=workers, cache_entries=32)
                            samples = collected[(name, workers)]
                            samples["setup"].append(perf_counter() - start)
                            try:
                                start = perf_counter()
                                snapshots = collector.capture(envelope)
                                samples["first_capture"].append(perf_counter() - start)
                                if snapshots != expected:
                                    raise RuntimeError(f"first snapshot mismatch: {name}/{workers}")
                                for _ in range(args.captures_per_repeat):
                                    start = perf_counter()
                                    snapshots = collector.capture(envelope)
                                    samples["steady_capture"].append(perf_counter() - start)
                                    if snapshots != expected:
                                        raise RuntimeError(f"snapshot mismatch: {name}/{workers}")
                            finally:
                                start = perf_counter()
                                collector.close()
                                samples["close"].append(perf_counter() - start)
                    results = []
                    for (name, workers), samples in collected.items():
                        stats = {stage: {"median_ms": statistics.median(v) * 1000,
                            "max_ms": max(v) * 1000, "samples_seconds": v} for stage, v in samples.items()}
                        seconds = stats["steady_capture"]["median_ms"] / 1000
                        result = {"variant": name, "workers": workers,
                            "effective_surface_concurrency": min(max(1, workers), args.surfaces),
                            "timings": stats, "files_per_second": len(paths) / seconds,
                            "mib_per_second": len(paths) * file_bytes / (1024 ** 2) / seconds}
                        results.append(result)
                        print(f"{len(paths):5d} files x {file_bytes:6d} bytes | {name:12s}/{workers} | "
                              f"{seconds * 1000:8.3f} ms | {result['files_per_second']:9.0f} files/s")
                    output["results"].append({"files_per_surface": files, "surfaces": args.surfaces,
                        "total_files": len(paths), "file_bytes": file_bytes, "diagnostics": diagnostics, "variants": results})
    limit = args.budget_ms * (1 + args.tolerance_percent / 100)
    for file_bytes in args.file_bytes:
        for name, workers in configs:
            matching = [(case, variant) for case in output["results"] if case["file_bytes"] == file_bytes
                for variant in case["variants"] if variant["variant"] == name and variant["workers"] == workers]
            fitting = [(case, variant) for case, variant in matching if variant["timings"]["steady_capture"]["median_ms"] <= limit]
            best = max(fitting, key=lambda item: item[0]["total_files"]) if fitting else None
            capacity = {"file_bytes": file_bytes, "variant": name, "workers": workers,
                        "budget_ms": args.budget_ms, "tolerance_limit_ms": limit,
                        "largest_tested_files_within_budget": best[0]["total_files"] if best else None,
                        "median_ms": best[1]["timings"]["steady_capture"]["median_ms"] if best else None,
                        "grid_limit_reached": bool(best and best[0]["total_files"] == max(c["total_files"] for c, _ in matching))}
            output["capacity"].append(capacity)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(f"\nCapacity per capture: {args.budget_ms:g} ms + {args.tolerance_percent:g}% tolerance")
    for row in output["capacity"]:
        amount = row["largest_tested_files_within_budget"]
        print(f"  {row['variant']}/{row['workers']}, {row['file_bytes']} bytes/file: "
              f"{amount if amount is not None else 'no tested workload fits'} files")
    print(f"Results: {args.json.resolve()}")


if __name__ == "__main__":
    main()
