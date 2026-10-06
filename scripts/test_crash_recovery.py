"""Disposable Linux process-crash and SQLite failure tests; no live effects.

This tests process termination, not machine power loss or actual fsync failure.
The comparison loads only the exact baseline backend from Git, not a historical
whole-system replay. All databases are created in a private temporary directory.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import random
import selectors
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pulpo import GovernanceKernel, Policy, SQLiteKernelState, StateIntegrityError
from pulpo.state import ApprovalUse
import pulpo.state as candidate_module

SECRET = b"public-crash-test-fixture-only"
PAYLOAD = {"id": "new", "classification": "CONSEQUENCE_UNKNOWN", "reusable": False}
STAGES = {
    "issue": ("after_approval", "after_permit", "after_first_audit", "before_commit",
              "after_commit_before_ack", "after_ack"),
    "consume": ("after_spent", "before_commit", "after_commit_before_ack", "after_ack"),
    "unique": ("before_insert", "before_commit", "after_commit_before_ack", "after_ack"),
    "replay": ("during_scan", "after_commit_before_ack", "after_ack"),
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def backend(variant, revision):
    if variant == "candidate":
        return candidate_module, SQLiteKernelState
    source = subprocess.check_output(["git", "show", revision + ":pulpo/state.py"], cwd=ROOT)
    module = types.ModuleType("pulpo._crash_baseline")
    sys.modules[module.__name__] = module
    exec(compile(source, "git:" + revision + ":pulpo/state.py", "exec"), module.__dict__)
    return module, module.SQLiteKernelState


def kernel(state):
    return GovernanceKernel(Policy(frozenset(), 0), state=state, secret=SECRET)


def prepare(state_type, path, operation):
    state = state_type(path)
    try:
        if operation == "consume":
            state.issue_permit("permit", "intent", "fixture", 1,
                               ApprovalUse("approval", "nonce", {"fixture": True}))
        elif operation in ("unique", "replay"):
            with state._connection:
                state._connection.execute("BEGIN IMMEDIATE")
                state._append_many([("reconciled", {"id": i,
                    "classification": "CONSEQUENCE_UNKNOWN", "reusable": False})
                    for i in range(128)], 1)
        kernel(state)
    finally:
        state.close()


def perform(state, operation, large=False):
    if operation == "issue":
        payload = {"fixture": True}
        if large:
            payload["detail"] = "x" * 262144
        return state.issue_permit("permit", "intent", "fixture", 2,
                                  ApprovalUse("approval", "nonce", payload))
    if operation == "consume":
        return state.consume_permit("permit", "intent", 2)
    if operation == "replay":
        return state.append_unique("reconciled", "id", 0,
            {"id": 0, "classification": "SUCCESS_VERIFIED", "reusable": True}, 2)
    payload = dict(PAYLOAD)
    if large:
        payload["detail"] = "x" * 262144
    return state.append_unique("reconciled", "id", "new", payload, 2)


def worker(args):
    module, state_type = backend(args.variant, args.compare_ref)
    state = state_type(args.database)
    try:
        kernel(state)

        def emit(kind, stage):
            print(json.dumps({"kind": kind, "stage": stage,
                              "acknowledged": kind == "ack" or stage == "after_ack"}), flush=True)

        def stop(stage):
            if args.stage == stage:
                emit("ready", stage)
                while True:
                    signal.pause()

        def trace(sql):
            if sql.startswith("COMMIT"):
                stop("before_commit")
            if args.operation == "issue":
                if sql.startswith("INSERT INTO permits"):
                    stop("after_approval")
                if sql.startswith("INSERT INTO audit"):
                    stop("after_first_audit" if "'decision'" in sql else "after_permit")
            elif sql.startswith("INSERT INTO audit"):
                stop("after_spent" if args.operation == "consume" else "before_insert")

        state._connection.set_trace_callback(trace)
        if args.stage == "during_scan":
            original_loads = module.json.loads
            count = 0

            def loads(*values, **kwargs):
                nonlocal count
                result = original_loads(*values, **kwargs)
                count += 1
                if count == 16:
                    stop("during_scan")
                return result

            module.json.loads = loads
        if args.stage == "random":
            emit("ready", "armed")
            require(sys.stdin.readline().strip() == "go", "worker missing go signal")
        result = perform(state, args.operation, large=args.stage == "random")
        if args.operation == "replay":
            require(result["classification"] == "CONSEQUENCE_UNKNOWN" and not result["reusable"],
                    "replay promoted unknown consequence")
        stop("after_commit_before_ack")
        # This ready message is itself the parent-observed acknowledgment.
        if args.stage == "after_ack":
            stop("after_ack")
        emit("ack", "returned")
        if args.stage == "random":
            while True:
                signal.pause()
        stop("after_ack")
        raise RuntimeError("requested crash stage was never reached")
    finally:
        state.close()


def recovered(state_type, path, operation, expectation):
    state = state_type(path)
    try:
        require(state._connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)],
                "SQLite integrity_check failed")
        proof = kernel(state)
        require(proof.verify_audit(), "full canonical chain proof failed")
        audit = state.audit
        permit = state._connection.execute("SELECT intent_hash, spent FROM permits WHERE permit='permit'").fetchone()
        if operation == "issue":
            approval = state.approval_replay_reason("approval", "nonce")
            events = [r["event"] for r in audit]
            committed = permit == ("intent", 0)
            require((committed and approval == "approval_id_replayed" and events == ["approval_verified", "decision"])
                    or (permit is None and approval is None and events == []), "partial issuance recovered")
        elif operation == "consume":
            require(permit is not None and permit[0] == "intent", "seed permit lost")
            committed = permit[1] == 1
            require([r["event"] for r in audit] == ["approval_verified", "decision"]
                    + (["permit_consumed"] if committed else []), "partial consumption recovered")
        else:
            matches = [r["payload"] for r in audit if r["event"] == "reconciled" and r["payload"].get("id") == "new"]
            committed = bool(matches)
            require(len(matches) <= 1 and len(audit) == 128 + int(committed), "partial or duplicated unique record")
            require(all(r["payload"]["classification"] == "CONSEQUENCE_UNKNOWN"
                        and r["payload"]["reusable"] is False for r in audit), "unknown consequence promoted")
            if operation == "replay":
                require(not committed, "replay created a new identity")
        if expectation != "either":
            require(committed == (expectation == "committed"), "acknowledgment/transaction boundary violated")

        # Fresh-restart probes use only disposable fixture identities.
        if operation == "issue":
            if not committed:
                require(perform(state, operation) is None, "rolled-back approval cannot be retried")
            require(state.issue_permit("other", "intent", "fixture", 3,
                ApprovalUse("approval", "different", {})) == "approval_id_replayed", "approval replay accepted")
            require(state.issue_permit("other", "intent", "fixture", 3,
                ApprovalUse("different", "nonce", {})) == "approval_nonce_replayed", "nonce replay accepted")
        elif operation == "consume":
            require(state.consume_permit("permit", "intent", 3) == (not committed), "spent status incorrect")
            require(not state.consume_permit("permit", "intent", 4), "permit replay accepted")
        else:
            identity = 0 if operation == "replay" else "new"
            if operation == "unique" and not committed:
                require(perform(state, operation) is None, "rolled-back unique append cannot be retried")
            changes = state._connection.total_changes
            result = state.append_unique("reconciled", "id", identity,
                {"id": identity, "classification": "SUCCESS_VERIFIED", "reusable": True}, 3)
            require(result["classification"] == "CONSEQUENCE_UNKNOWN" and not result["reusable"], "replay replaced evidence")
            require(state._connection.total_changes == changes, "replay wrote new evidence")
        require(proof.verify_audit(), "replay probes broke chain")
        return {"committed_before_probe": committed, "audit_rows_before_probe": len(audit)}
    finally:
        state.close()


def fresh_verify(args):
    _, state_type = backend(args.variant, args.compare_ref)
    print(json.dumps(recovered(state_type, args.database, args.operation, args.expectation)))


def kill_case(args, state_type, path, operation, stage, rng):
    prepare(state_type, path, operation)
    command = [sys.executable, '-W', 'error', str(Path(__file__).resolve()), '--worker',
               '--database', str(path), '--variant', args.variant, '--compare-ref', args.compare_ref,
               '--operation', operation, '--stage', stage]
    child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True)
    delay = None
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout, selectors.EVENT_READ)
            require(bool(selector.select(args.timeout)), "worker did not reach checkpoint in time")
        ready = json.loads(child.stdout.readline())
        require(ready['kind'] == 'ready', "worker emitted unexpected checkpoint")
        require(ready['stage'] == ('armed' if stage == 'random' else stage), "wrong crash checkpoint")
        if stage == "random":
            child.stdin.write('go\n')
            child.stdin.flush()
            delay = rng.uniform(0, 0.012)
            time.sleep(delay)
        child.kill()  # Only this child PID; no machine or WSL shutdown.
        stdout, stderr = child.communicate(timeout=args.timeout)
        require(child.returncode == -signal.SIGKILL, "worker was not killed by SIGKILL")
        require(not stderr, "worker error before crash: " + stderr)
        acknowledged = ready['acknowledged'] or any(json.loads(line).get('kind') == 'ack'
                                                    for line in stdout.splitlines() if line.strip())
        if operation == "replay":
            expectation = "absent"
        elif acknowledged or stage == "after_commit_before_ack":
            expectation = "committed"
        elif stage == "random":
            expectation = "either"
        else:
            expectation = "absent"
        result = subprocess.run([sys.executable, '-W', 'error', str(Path(__file__).resolve()), '--verify',
            '--database', str(path), '--variant', args.variant, '--compare-ref', args.compare_ref,
            '--operation', operation, '--expectation', expectation], capture_output=True, text=True,
            timeout=args.timeout, check=True)
        require(not result.stderr, "restart verification emitted errors: " + result.stderr)
        return {'operation': operation, 'stage': stage, 'acknowledged': acknowledged,
                'expected': expectation, 'kill_delay_seconds': delay, **json.loads(result.stdout)}
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=args.timeout)


def storage_faults(state_type, directory):
    results = []
    for operation in ("issue", "consume", "unique"):
        for fault in ("audit_insert_abort", "commit_locked", "sqlite_full"):
            path = directory / f'{operation}-{fault}.sqlite3'
            prepare(state_type, path, operation)
            state = state_type(path)
            try:
                before = state.audit
                snapshot = state._connection.execute("SELECT * FROM permits ORDER BY permit").fetchall()
                approvals = state._connection.execute("SELECT * FROM approvals ORDER BY approval_id").fetchall()
                reader = None
                if fault == "audit_insert_abort":
                    state._connection.execute("CREATE TRIGGER fail_audit BEFORE INSERT ON audit "
                        "BEGIN SELECT RAISE(ABORT, 'injected audit insert failure'); END")
                elif fault == "commit_locked":
                    state._connection.execute("PRAGMA busy_timeout=10")
                    reader = sqlite3.connect(path)
                    reader.execute("BEGIN")
                    reader.execute("SELECT COUNT(*) FROM audit").fetchone()
                else:
                    # Force actual SQLITE_FULL via a connection-local page limit.
                    pages = state._connection.execute("PRAGMA page_count").fetchone()[0]
                    state._connection.execute(f"PRAGMA max_page_count={pages}")
                try:
                    if fault != "sqlite_full":
                        perform(state, operation)
                    elif operation == "issue":
                        state.issue_permit("permit", "intent", "fixture", 2,
                            ApprovalUse("approval", "nonce", {"detail": "x" * 2097152}))
                    elif operation == "unique":
                        state.append_unique("reconciled", "id", "new", PAYLOAD | {"detail": "x" * 2097152}, 2)
                    else:
                        # Legitimately issue a large synthetic permit before the
                        # failure snapshot; consumption must append another large record.
                        huge = "x" * 2097152
                        state._connection.execute("PRAGMA max_page_count=1073741823")
                        state.issue_permit("large-permit", huge, "fixture", 1,
                            ApprovalUse("large-approval", "large-nonce", {"fixture": True}))
                        before = state.audit
                        snapshot = state._connection.execute("SELECT * FROM permits ORDER BY permit").fetchall()
                        approvals = state._connection.execute("SELECT * FROM approvals ORDER BY approval_id").fetchall()
                        pages = state._connection.execute("PRAGMA page_count").fetchone()[0]
                        state._connection.execute(f"PRAGMA max_page_count={pages}")
                        state.consume_permit("large-permit", huge, 2)
                except sqlite3.Error as exc:
                    expected = {'audit_insert_abort': sqlite3.SQLITE_CONSTRAINT,
                                'commit_locked': sqlite3.SQLITE_BUSY, 'sqlite_full': sqlite3.SQLITE_FULL}[fault]
                    require(exc.sqlite_errorcode & 255 == expected, f"wrong injected failure: {exc}")
                    error_name = exc.sqlite_errorname
                else:
                    raise RuntimeError("storage fault did not fire")
                finally:
                    if reader is not None:
                        reader.rollback()
                        reader.close()
                require(not state._connection.in_transaction, "failure left transaction open")
                require(state.audit == before, "failure partially published audit")
                require(state._connection.execute("SELECT * FROM permits ORDER BY permit").fetchall() == snapshot,
                        "failure partially changed permit state")
                require(state._connection.execute("SELECT * FROM approvals ORDER BY approval_id").fetchall() == approvals,
                        "failure partially changed replay guards")
                require(kernel(state).verify_audit(), "failure broke canonical chain")
                results.append({'operation': operation, 'fault': fault, 'sqlite_error': error_name, 'passed': True})
            finally:
                state.close()
    return results


def tamper_controls(state_type, directory):
    results = []
    for field, value in (("payload_json", '{"tampered":true}'), ("payload_json", '{bad'), ("hash", '0' * 64)):
        path = directory / ('tamper-' + str(len(results)) + '.sqlite3')
        prepare(state_type, path, "consume")
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute(f"UPDATE audit SET {field}=? WHERE sequence=1", (value,))
        state = state_type(path)
        try:
            try:
                kernel(state)
            except StateIntegrityError:
                results.append({'field': field, 'malformed': value == '{bad', 'rejected': True})
            else:
                raise RuntimeError('tampered evidence accepted at restart')
        finally:
            state.close()
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compare-ref', default='ee88a8ea5aa5496c06afaa82ec31db30c2e4e1fc')
    parser.add_argument('--rounds', type=int, default=10)
    parser.add_argument('--seed', type=int, default=20261005)
    parser.add_argument('--timeout', type=float, default=20)
    parser.add_argument('--json', type=Path)
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('--database', type=Path)
    parser.add_argument('--variant', choices=('baseline', 'candidate'), default='candidate')
    parser.add_argument('--operation', choices=tuple(STAGES))
    parser.add_argument('--stage')
    parser.add_argument('--expectation', choices=('absent', 'committed', 'either'))
    args = parser.parse_args()
    require(sys.platform.startswith('linux'), 'Run in Linux/WSL; SIGKILL semantics are required')
    if args.worker:
        worker(args)
        return
    if args.verify:
        fresh_verify(args)
        return
    require(args.rounds > 0 and args.timeout > 0 and args.json is not None, 'positive rounds/timeout and --json required')
    revision = subprocess.check_output(['git', 'rev-parse', '--verify', args.compare_ref + '^{commit}'], cwd=ROOT, text=True).strip()
    args.compare_ref = revision
    report = {'classification': 'Recorded', 'base_revision': revision, 'python': platform.python_version(),
              'sqlite': sqlite3.sqlite_version, 'platform': platform.platform(), 'seed': args.seed,
              'rounds': args.rounds, 'variants': [], 'source_sha256': {
                  name: sha256((ROOT / name).read_bytes()).hexdigest()
                  for name in ('pulpo/state.py', 'pulpo/kernel.py', 'scripts/test_crash_recovery.py')},
              'boundaries': ['Disposable synthetic fixture databases only; no live credentials or provider effects.',
                  'Process SIGKILL and real SQLite FULL/BUSY/trigger errors; not physical power loss or actual fsync fault injection.',
                  'Storage-layer unknown-consequence replay preservation; not a simulated external provider recovery.',
                  'Current-head backend comparison, not whole historical-system temporal replay.',
                  'Whole valid-database rollback protection and production performance remain Unknown.']}
    args.json.parent.mkdir(parents=True, exist_ok=True)
    try:
        for variant in ('baseline', 'candidate'):
            args.variant = variant
            _, state_type = backend(variant, revision)
            result = {'variant': variant, 'crashes': [], 'storage_faults': [], 'tamper_controls': []}
            report['variants'].append(result)
            rng = random.Random(args.seed)
            with tempfile.TemporaryDirectory(prefix='pulpo-crash-fixtures-') as scratch:
                directory = Path(scratch)
                for iteration in range(args.rounds):
                    for operation, stages in STAGES.items():
                        for stage in (*stages, 'random'):
                            path = directory / f'{iteration}-{operation}-{stage}.sqlite3'
                            case = kill_case(args, state_type, path, operation, stage, rng)
                            result['crashes'].append(case | {'round': iteration})
                    print(f'{variant}: crash round {iteration + 1}/{args.rounds} passed', flush=True)
                result['storage_faults'] = storage_faults(state_type, directory)
                result['tamper_controls'] = tamper_controls(state_type, directory)
            print(f'{variant}: {len(result["crashes"])} crashes, 9 storage failures, 3 tamper controls PASS', flush=True)
        report['classification'] = 'Verified'
        report['passed'] = True
    except Exception as exc:
        report['passed'] = False
        report['error'] = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        args.json.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
