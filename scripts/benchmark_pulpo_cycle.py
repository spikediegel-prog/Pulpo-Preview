#!/usr/bin/env python3
"""Measure Pulpo's local fixture cycle; no live authority or external effects.

Requires a Pulpo checkout including tests/authority_support.py. Uses temporary
databases only. Restart cases use fresh processes; OS caches are not flushed.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from hashlib import sha256
import json
import multiprocessing
import os
from pathlib import Path
import platform
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tempfile
from time import perf_counter

SECRET = b"local-benchmark-fixture-only"
NOW = 1_000_000


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def load(repo):
    require((repo / "pulpo/kernel.py").is_file(), "--repo must name a Pulpo checkout")
    require((repo / "tests/authority_support.py").is_file(), "checkout must include test fixtures")
    sys.path.insert(0, str(repo))


def make_kernel(state):
    from pulpo import GovernanceKernel, Policy
    from tests.authority_support import HmacTestVerifier, trust_for
    verifier = HmacTestVerifier()
    policy = Policy(frozenset({"fixture_write"}), 0, frozenset({"fixture_write"}),
                    authority_trust=trust_for(verifier))
    return GovernanceKernel(policy, secret=SECRET, approval_verifier=verifier,
                            clock=lambda: NOW, state=state), verifier


def seed(path, history):
    from pulpo import SQLiteKernelState
    state = SQLiteKernelState(path)
    try:
        with state._connection:
            state._connection.execute("BEGIN IMMEDIATE")
            state._append_many([("benchmark_fixture", {"index": i, "detail": "x" * 100})
                                for i in range(history)], NOW)
        kernel, _ = make_kernel(state)
        require(kernel.verify_audit(), "seed chain invalid")
    finally:
        state.close()


def restart_worker(path, variant):
    from pulpo import SQLiteKernelState
    class FullState(SQLiteKernelState):
        verify_audit_bootstrap = None
    state = (FullState if variant == "full" else SQLiteKernelState)(path)
    try:
        started = perf_counter()
        kernel, _ = make_kernel(state)
        elapsed = perf_counter() - started
        require(kernel.verify_audit(), "restart chain invalid")
        return elapsed
    finally:
        state.close()


def timed(samples, stage, operation):
    start = perf_counter()
    result = operation()
    samples.setdefault(stage, []).append(perf_counter() - start)
    return result


def cycle_case(path, directory, iterations, workers, surfaces, files, file_bytes,
               *, repo=None, mode="threads", resources=False, validate_snapshots=False):
    from pulpo import Intent, SQLiteKernelState
    from pulpo.effect_reconcile import (EffectEnvelope, ExecutionIdentity, SurfaceSpec,
        ParallelEvidenceCollector, bind_resource_to_effect_envelope,
        capture_envelope_surfaces, reconcile_effects)
    from tests.authority_support import signed_envelope
    state = SQLiteKernelState(path)
    collector = None
    sampler = None
    samples = {}
    lifecycle = {}
    resource_result = None
    startup_resources = None
    sampler_start = 0.0
    try:
        start = perf_counter()
        kernel, verifier = make_kernel(state)
        lifecycle["kernel_bootstrap_seconds"] = perf_counter() - start
        roots = []
        for index in range(surfaces):
            root = directory / f"surface-{index}"
            root.mkdir()
            for number in range(files):
                (root / f"file-{number}.bin").write_bytes(b"x" * file_bytes)
            roots.append(root)
        executable = directory / "fixture-executable.bin"
        executable.write_bytes(b"no-execution-benchmark-fixture")
        envelope = EffectEnvelope(
            executable_path=str(executable), executable_sha256=sha256(executable.read_bytes()).hexdigest(),
            argv=(str(executable),), workdir=str(directory), source_sha="fixture-only",
            profile="local-cycle-benchmark", expires_at_ns=NOW + 1000,
            surfaces=tuple(SurfaceSpec(str(root), "writable") for root in roots))
        identity = ExecutionIdentity(envelope.executable_path, envelope.executable_sha256,
            envelope.argv, envelope.workdir, envelope.source_sha, envelope.profile)
        intent = Intent("agent:benchmark-fixture", "fixture_write",
            bind_resource_to_effect_envelope("fixture:temporary-files", envelope), 0, "benchmark-session")

        # One collector lasts for the entire measured batch. Process creation is
        # lazy: first_capture includes spawn/import/IPC, setup alone does not.
        if resources:
            import psutil
            from benchmark_evidence_processes import ProcessTreeSampler
            sampler_start = perf_counter()
            sampler = ProcessTreeSampler(psutil, 0.02)
            sampler.start()
        start = perf_counter()
        if mode == "processes":
            from benchmark_evidence_processes import ProcessCollector
            collector = ProcessCollector(repo, workers)
        else:
            collector = ParallelEvidenceCollector(workers=workers)
        lifecycle["collector_setup_seconds"] = perf_counter() - start
        start = perf_counter()
        warm = capture_envelope_surfaces(envelope, collector=collector)
        lifecycle["first_capture_seconds"] = perf_counter() - start
        if sampler is not None:
            startup_resources = sampler.finish(perf_counter() - sampler_start, os.cpu_count() or 1)
            sampler = None
        if validate_snapshots:
            require(warm == capture_envelope_surfaces(envelope), "first capture differs from serial")
        if resources:
            sampler = ProcessTreeSampler(psutil, 0.02)
            sampler_start = perf_counter()
            sampler.start()
        batch_start = perf_counter()
        fixture_hash = sha256(b"x" * file_bytes).hexdigest()
        for index in range(iterations):
            approval = signed_envelope(kernel, intent, verifier, now_ns=NOW,
                approval_id=f"fixture-approval-{index}", nonce=f"fixture-nonce-{index}")
            if validate_snapshots:
                reference_before = capture_envelope_surfaces(envelope)
            cycle_start = perf_counter()
            decision = timed(samples, "approval_and_permit_issue",
                lambda: kernel.evaluate_with_approval(intent, approval))
            require(decision.outcome == "allow" and decision.permit, "fixture approval denied")
            consumed = timed(samples, "durable_permit_consumption",
                lambda: kernel.consume(decision.permit, intent))
            require(consumed, "fixture permit not consumed")
            before = timed(samples, "evidence_capture_before",
                lambda: capture_envelope_surfaces(envelope, collector=collector))
            timed(samples, "simulated_file_effect",
                lambda: (roots[0] / "effect.bin").write_bytes(str(index).encode()))
            after = timed(samples, "evidence_capture_after",
                lambda: capture_envelope_surfaces(envelope, collector=collector))
            def reconcile():
                result = reconcile_effects(envelope, identity, before, after,
                    execution_started_ns=NOW, observation_complete=True)
                return result, result.reconciliation_hash
            result, digest = timed(samples, "reconciliation_and_digest", reconcile)
            require(result.status == "verified" and result.unauthorized_effects == 0,
                    "fixture reconciliation failed")
            # Same canonical append seam used by the existing local effect proof;
            # it is exercised only against this disposable test database.
            payload = {**asdict(result), "reconciliation_hash": digest,
                       "authority_effect": "none", "fixture": True}
            timed(samples, "canonical_evidence_append",
                lambda: state.append("effect_reconciled", payload, NOW))
            samples.setdefault("total_local_cycle", []).append(perf_counter() - cycle_start)
            # Validate returned content/order outside the timed cycle. Canonical
            # snapshot equality is additionally checked in --self-test.
            for snapshot_set, effect_value in ((before, index - 1), (after, index)):
                require(len(snapshot_set) == len(roots), "missing surface snapshot")
                for root_index, snapshot in enumerate(snapshot_set):
                    require(snapshot.root == str(roots[root_index]) and snapshot.role == "writable"
                            and snapshot.exists, "surface identity/order mismatch")
                    expected = {f"file-{n}.bin": fixture_hash for n in range(files)}
                    if root_index == 0 and effect_value >= 0:
                        expected["effect.bin"] = sha256(str(effect_value).encode()).hexdigest()
                    actual = {entry.relative_path: entry.content_sha256
                              for entry in snapshot.entries if entry.kind == "file"}
                    require(actual == expected, "fixture snapshot content mismatch")
            if validate_snapshots:
                require(before == reference_before, "before snapshot differs from serial")
                require(after == capture_envelope_surfaces(envelope), "after snapshot differs from serial")
        batch_wall = perf_counter() - batch_start
        if sampler is not None:
            resource_result = sampler.finish(batch_wall, os.cpu_count() or 1)
            resource_result["startup"] = startup_resources
            sampler = None
        lifecycle["steady_batch_wall_seconds"] = batch_wall
        require(kernel.verify_audit(), "final fixture chain invalid")
        require(not kernel.consume(decision.permit, intent), "permit replay accepted")
        require(kernel.evaluate_with_approval(intent, approval).outcome == "deny", "approval replay accepted")
        require(kernel.verify_audit(), "chain invalid after replay checks")
    finally:
        try:
            if sampler is not None:
                sampler.finish(max(perf_counter() - sampler_start, 1e-9), os.cpu_count() or 1)
            if collector is not None:
                start = perf_counter()
                collector.close()
                lifecycle["collector_shutdown_seconds"] = perf_counter() - start
        finally:
            state.close()
    lifecycle["startup_and_shutdown_seconds"] = sum(lifecycle[key] for key in (
        "kernel_bootstrap_seconds", "collector_setup_seconds", "first_capture_seconds",
        "collector_shutdown_seconds"))
    lifecycle["amortized_cycle_seconds"] = (
        sum(samples["total_local_cycle"]) + lifecycle["startup_and_shutdown_seconds"]) / iterations
    return samples, lifecycle, resource_result


def cycle_self_test(repo):
    import pulpo.effect_reconcile as evidence
    from benchmark_evidence_processes import self_test
    self_test(evidence, repo)
    with tempfile.TemporaryDirectory(prefix="pulpo-cycle-self-test-") as scratch:
        base = Path(scratch)
        source = base / "seed.sqlite3"
        seed(source, 20)
        for mode, workers in (("threads", 0), ("threads", 2), ("processes", 1), ("processes", 2)):
            directory = base / f"{mode}-{workers}"
            directory.mkdir()
            database = directory / "state.sqlite3"
            shutil.copyfile(source, database)
            samples, lifecycle, _ = cycle_case(database, directory, 3, workers, 4, 2, 128,
                repo=repo, mode=mode, validate_snapshots=True)
            require(len(samples["total_local_cycle"]) == 3, "missing cycle samples")
            require(lifecycle["amortized_cycle_seconds"] > 0, "missing lifecycle measurement")
            # Reopen the resulting canonical state and force full verification.
            restart_worker(database, "checkpoint")
            restart_worker(database, "full")
            print(f"PASS full cycle {mode}/{workers}: serial equality, reconciliation, "
                  "canonical audit, permit/approval replay denial, restart, shutdown")


def summarize(samples):
    return {stage: {"median_ms": statistics.median(values) * 1000,
                    "min_ms": min(values) * 1000, "max_ms": max(values) * 1000,
                    "samples_seconds": values} for stage, values in samples.items()}


def git_metadata(repo):
    metadata = {"git_commit": None, "git_status": None, "git_metadata_errors": []}
    for field, arguments in (("git_commit", ["rev-parse", "HEAD"]),
                             ("git_status", ["status", "--porcelain"])):
        try:
            result = subprocess.run(["git", "-C", str(repo), *arguments],
                                    capture_output=True, text=True)
            if result.returncode == 0:
                metadata[field] = result.stdout.strip() if field == "git_commit" else result.stdout
            else:
                metadata["git_metadata_errors"].append(result.stderr.strip())
        except OSError as exc:
            metadata["git_metadata_errors"].append(str(exc))
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--sizes", nargs="+", type=int, default=[1000, 10000, 50000])
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--workers", nargs="+", type=int, default=[0, 4], help="0=serial evidence; >1=parallel")
    parser.add_argument("--processes", nargs="+", type=int, default=[],
                        help="Optional persistent process collectors; requires sibling process benchmark")
    parser.add_argument("--resources", action="store_true",
                        help="Sample coordinator + children CPU/RAM (automatically enabled with --processes)")
    parser.add_argument("--self-test", action="store_true", help="Run disposable correctness fixtures only")
    parser.add_argument("--surfaces", type=int, default=4)
    parser.add_argument("--files-per-surface", type=int, default=20)
    parser.add_argument("--file-bytes", type=int, default=4096)
    parser.add_argument("--json", type=Path, default=Path("cycle-results.json"))
    parser.add_argument("--worker-db", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--worker-variant", choices=["full", "checkpoint"], help=argparse.SUPPRESS)
    args = parser.parse_args()
    repo = args.repo.resolve()
    load(repo)
    if args.worker_db:
        print(json.dumps({"seconds": restart_worker(args.worker_db, args.worker_variant)}))
        return
    if args.self_test:
        cycle_self_test(repo)
        return
    if args.processes:
        args.resources = True
    if args.resources:
        try:
            import psutil
            from benchmark_evidence_processes import ProcessTreeSampler, ProcessCollector
        except ImportError as exc:
            parser.error(f"Resource/process comparison requires psutil and benchmark_evidence_processes.py: {exc}")
    if args.processes and min(args.processes) < 1:
        parser.error("process worker counts must be positive")
    if len(set(args.processes)) != len(args.processes):
        parser.error("process worker counts must be unique")
    if min(args.sizes + [args.repeats, args.iterations, args.surfaces,
                         args.files_per_surface, args.file_bytes]) < 1 or min(args.workers) < 0:
        parser.error("sizes/counts must be positive; workers must be nonnegative")
    if len(set(args.workers)) != len(args.workers):
        parser.error("worker counts must be unique")
    provenance = git_metadata(repo)
    if provenance["git_metadata_errors"]:
        print("Git provenance unavailable; source hashes will still be recorded.")
    output = {"schema": "pulpo.local-cycle-benchmark.v2", "claim": "Recorded synthetic fixture measurements",
        **provenance,
        "python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
        "platform": platform.platform(), "cpu_count": os.cpu_count(),
        "settings": {key: value for key, value in vars(args).items()
                     if key not in {"repo", "json", "worker_db", "worker_variant"}},
        "source_sha256": {name: sha256((repo / name).read_bytes()).hexdigest() for name in
            ("pulpo/kernel.py", "pulpo/state.py", "pulpo/effect_reconcile.py", "tests/authority_support.py")},
        "process_helper_sha256": sha256(Path(__file__).with_name("benchmark_evidence_processes.py").read_bytes()).hexdigest()
            if args.processes or args.resources else None,
        "script_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "boundaries": ["No live authority/network/executable invocation; test-only approval verifier.",
            "Fixture setup and approval signing excluded. No evidence of deployed security or external latency.",
            "Restart: fresh process/connection; state schema initialization excluded; OS caches not flushed.",
            "Cycle: warm process and evidence cache; SQLite FULL durability unchanged; raw samples retained.",
            "Process workers receive surface specs only; canonical SQLite writes stay in the coordinator.",
            "Lifecycle reports kernel bootstrap, setup, first capture including lazy spawn, and shutdown separately.",
            "Amortized cycle = (sum timed cycles + lifecycle overhead) / iterations; excludes fixture creation, signing, and postchecks.",
            "Resource samples cover the steady batch, including signing and postchecks, excluding startup and final full verification.",
            "Peak sum RSS can double-count shared pages; 20ms sampling can miss peaks; CPU is aggregate, not core affinity.",
            "First capture uses a warm coordinator and OS caches; it is not a cold machine startup measurement.",
            "The append stage measures canonical storage, not a domain-specific admission controller."],
        "results": []}
    from pulpo import SQLiteKernelState
    with tempfile.TemporaryDirectory(prefix="pulpo-cycle-benchmark-") as scratch:
        base = Path(scratch)
        for history in args.sizes:
            seed_path = base / "seed.sqlite3"
            seed_path.unlink(missing_ok=True)
            seed(seed_path, history)
            restart = {name: [] for name in ("full", "checkpoint", "checkpoint_plus_20")}
            configs = [("threads", w) for w in args.workers] + [("processes", w) for w in args.processes]
            cycle_samples = {config: {} for config in configs}
            lifecycle_samples = {config: {} for config in configs}
            resource_samples = {config: [] for config in configs}
            for repeat in range(args.repeats):
                for name in list(restart)[::1 if repeat % 2 == 0 else -1]:
                    path = base / "restart.sqlite3"
                    shutil.copyfile(seed_path, path)
                    if name == "checkpoint_plus_20":
                        state = SQLiteKernelState(path)
                        try:
                            with state._connection:
                                state._connection.execute("BEGIN IMMEDIATE")
                                state._append_many([("fixture_suffix", {"index": i}) for i in range(20)], NOW)
                        finally:
                            state.close()
                    result = subprocess.check_output([sys.executable, str(Path(__file__).resolve()),
                        "--repo", str(repo), "--worker-db", str(path), "--worker-variant",
                        "full" if name == "full" else "checkpoint"], text=True)
                    restart[name].append(json.loads(result)["seconds"])
                order = configs if repeat % 2 == 0 else list(reversed(configs))
                for mode, workers in order:
                    # Remove each disposable case promptly to bound disk usage.
                    with tempfile.TemporaryDirectory(prefix=f"cycle-{mode}-{workers}-", dir=base) as case:
                        directory = Path(case)
                        path = directory / "state.sqlite3"
                        shutil.copyfile(seed_path, path)
                        samples, lifecycle, resource = cycle_case(path, directory, args.iterations, workers,
                            args.surfaces, args.files_per_surface, args.file_bytes,
                            repo=repo, mode=mode, resources=args.resources)
                    config = (mode, workers)
                    for stage, values in samples.items():
                        cycle_samples[config].setdefault(stage, []).extend(values)
                    for stage, value in lifecycle.items():
                        lifecycle_samples[config].setdefault(stage, []).append(value)
                    if resource is not None:
                        resource_samples[config].append(resource)
            result = {"history": history, "restart": summarize(restart), "cycles": []}
            for (mode, workers), samples in cycle_samples.items():
                config = (mode, workers)
                stats = summarize(samples)
                lifecycle = summarize(lifecycle_samples[config])
                stages = [s for s in stats if s != "total_local_cycle"]
                slowest = max(stages, key=lambda s: stats[s]["median_ms"])
                resources = resource_samples[config]
                resource_summary = None if not resources else {
                    "median_cpu_equivalents": statistics.median(r["average_cpu_cores_equivalent"] for r in resources),
                    "peak_sum_rss_mib": max(r["peak_sum_rss_mib"] for r in resources),
                    "startup_peak_sum_rss_mib": max(r["startup"]["peak_sum_rss_mib"] for r in resources),
                    "sampling_errors": sum(r["sampling_errors"] + r["startup"]["sampling_errors"] for r in resources)}
                result["cycles"].append({"evidence_mode": mode, "evidence_workers": workers, "stages": stats,
                    "lifecycle": lifecycle, "resource_summary": resource_summary,
                    "resource_samples": resources, "largest_stage_by_median": slowest})
                label = "serial" if workers == 0 else mode
                memory = "" if resource_summary is None else f" | peak RSS={resource_summary['peak_sum_rss_mib']:.1f} MiB"
                print(f"{history:>6} records | {label}/{workers} | "
                      f"cycle={stats['total_local_cycle']['median_ms']:.3f} ms | "
                      f"first={lifecycle['first_capture_seconds']['median_ms']:.1f} ms | "
                      f"amortized={lifecycle['amortized_cycle_seconds']['median_ms']:.3f} ms"
                      f"{memory} | largest={slowest}")
            output["results"].append(result)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(f"Results: {args.json.resolve()}")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
