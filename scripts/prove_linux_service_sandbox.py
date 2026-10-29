#!/usr/bin/env python3
"""Disposable systemd service proof; never installs a production unit.

No human signer, real provider credential, live database or outbound provider
route is used. User mode is a capability probe; --system stages root-owned code
and uses DynamicUser. Successful runtime checks, not settings, establish proof.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "custody-service/src")]


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def write_denied(path):
    try:
        descriptor = os.open(path, os.O_WRONLY)  # No truncation or write.
    except PermissionError:
        return True
    except OSError as exc:
        return exc.errno == 30  # EROFS.
    else:
        os.close(descriptor)
        return False


def worker(config_path):
    from pulpo import GovernanceKernel, Intent, Policy, SQLiteKernelState

    config = json.loads(config_path.read_text())
    state = Path(config["PULPO_CUSTODY_STATE_PATH"]).parent
    environment = {**os.environ, **config, "PYTHONPATH": os.pathsep.join(sys.path[:2]),
                   "PYTHONDONTWRITEBYTECODE": "1"}
    checks = {}
    checks["code_write_denied"] = write_denied(ROOT / "pyproject.toml")
    checks["config_write_denied"] = write_denied(config_path)
    checks["home_credentials_hidden"] = not (Path.home() / ".ssh").exists()
    status = Path("/proc/self/status").read_text()
    checks["no_new_privileges"] = "NoNewPrivs:\t1" in status
    checks["no_effective_capabilities"] = "CapEff:\t0000000000000000" in status
    checks["non_root"] = os.getuid() != 0
    if config.get("PULPO_E1_SYSTEM_FIXTURE") == "1":
        checks["code_root_owned"] = (ROOT / "pyproject.toml").stat().st_uid == 0
        checks["configuration_root_owned"] = config_path.stat().st_uid == 0
    with socket.socket() as sock:
        sock.settimeout(1)
        try:
            sock.connect(("192.0.2.1", 443))  # Documentation-only address.
        except OSError as exc:
            checks["external_route_denied"] = exc.errno in (101, 100, 13)
        else:
            checks["external_route_denied"] = False
    checks["only_loopback_interface"] = set(socket.if_nameindex()) == {(1, "lo")}
    (state / "write-probe").write_text("synthetic fixture")
    checks["state_writable"] = True

    # Actual custody entrypoint must fail before creating state if authority is
    # absent or malformed. No private signing material is constructed.
    for label, value in (("missing", None), ("malformed", "not-hex")):
        negative = dict(environment)
        negative["PULPO_CUSTODY_STATE_PATH"] = str(state / (label + ".sqlite3"))
        if value is None:
            negative.pop("PULPO_AUTHORITY_PUBLIC_KEY_HEX")
        else:
            negative["PULPO_AUTHORITY_PUBLIC_KEY_HEX"] = value
        result = subprocess.run([sys.executable, "-c", "import pulpo_custody_service.main"],
                                env=negative, capture_output=True, text=True, timeout=10)
        checks[label + "_authority_startup_denied"] = (
            result.returncode != 0 and "RuntimeConfigError" in result.stderr
            and not Path(negative["PULPO_CUSTODY_STATE_PATH"]).exists())

    # Separate, explicitly synthetic canonical-kernel fixture. The saved permit
    # never leaves the disposable state directory or becomes a service API.
    permit_file = state / "fixture-permit"
    intent = Intent("agent:e1-fixture", "read", "local:e1-fixture", 0, "e1")
    with SQLiteKernelState(state / "restart-fixture.sqlite3") as backend:
        kernel = GovernanceKernel(Policy(frozenset({"read"}), 0),
            secret=bytes.fromhex(config["PULPO_KERNEL_SECRET_HEX"]), state=backend)
        before = len(kernel.audit)
        if permit_file.exists():
            checks["spent_permit_replay_denied"] = not kernel.consume(permit_file.read_text(), intent)
            phase = "restart"
        else:
            permit = kernel.evaluate(intent).permit
            require(permit is not None, "fixture permit missing")
            require(kernel.consume(permit, intent), "fixture consume failed")
            permit_file.write_text(permit)
            phase = "initial"
        checks["canonical_audit_valid"] = kernel.verify_audit()
        checks["prior_evidence_preserved"] = len(kernel.audit) > before
        checks["forbidden_action_denied"] = kernel.evaluate(
            Intent("agent:e1-fixture", "purchase_domain", "example.invalid")).outcome == "deny"
        audit_rows = len(kernel.audit)

    require(all(checks.values()), "service confinement or kernel check failed: " +
            ",".join(k for k, v in checks.items() if not v))
    child = subprocess.Popen([sys.executable, "-m", "uvicorn", "pulpo_custody_service.main:app",
        "--host", "127.0.0.1", "--port", "18081", "--workers", "1", "--no-access-log"],
        env=environment)

    def stop(_signum, _frame):
        if child.poll() is None:
            child.terminate()
        child.wait(timeout=8)
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        deadline = time.monotonic() + 15
        while True:
            require(child.poll() is None, "custody app exited before health")
            try:
                with opener.open("http://127.0.0.1:18081/health", timeout=1) as response:
                    checks["actual_custody_health"] = json.load(response) == {
                        "status": "ok", "authority_effect": "none"}
                break
            except OSError:
                require(time.monotonic() < deadline, "custody readiness timeout")
                time.sleep(.1)
        request = urllib.request.Request("http://127.0.0.1:18081/v1/domain-attempts",
            data=b'{"proposal_commitment_id":"synthetic-unknown"}',
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            opener.open(request, timeout=2).close()
            checks["unapproved_unknown_commitment_denied"] = False
        except urllib.error.HTTPError as exc:
            checks["unapproved_unknown_commitment_denied"] = exc.code == 403
        require(all(checks.values()), "custody health or rejection check failed")
        report = {"phase": phase, "checks": checks, "audit_rows": audit_rows,
                  "pid": os.getpid(), "uid": os.getuid(), "passed": True}
        pending = state / f"report-{os.getpid()}.pending"
        pending.write_text(json.dumps(report, indent=2))
        pending.replace(state / f"report-{os.getpid()}.json")
        while child.poll() is None:
            time.sleep(.2)
        raise RuntimeError("custody child exited unexpectedly")
    finally:
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=8)


def run(output, *, system=False, runtime=None):
    require(sys.platform == "linux", "Linux required")
    require((os.getuid() == 0) == system, "--system requires root; user proof must run without root")
    require(not output.exists() and output.is_absolute(), "new absolute evidence path required")
    name = "pulpo-e1-" + secrets.token_hex(5)
    unit = name + ".service"
    manager = [] if system else ["--user"]
    result = {"classification": "Recorded", "unit": unit, "runs": [], "passed": False,
              "base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "boundary": ("Disposable system service with DynamicUser, root-owned staging and no external network."
                           if system else "Same-UID user-service probe; confinement must be independently checked."),
              "launcher_uid": os.getuid()}
    scratch = tempfile.TemporaryDirectory(prefix="pulpo-e1-service-", dir="/run" if system else Path.home())
    folder = Path(scratch.name)
    folder.chmod(0o755 if system else 0o700)
    state = Path("/run") / name if system else folder / "state"
    configuration = folder / "configuration"
    if not system:
        state.mkdir(mode=0o700)
    configuration.mkdir(mode=0o755 if system else 0o700)
    source = ROOT
    python = Path(sys.executable)
    if system:
        require(runtime is not None and (runtime / "bin/python").exists(), "explicit Python venv runtime required")
        source = folder / "source"
        source.mkdir()
        for relative in ("pulpo", "custody-service/src"):
            origin = ROOT / relative
            require(not any(p.is_symlink() for p in origin.rglob("*")), "source symlink staging rejected")
            shutil.copytree(origin, source / relative)
        shutil.copyfile(ROOT / "pyproject.toml", source / "pyproject.toml")
        (source / "scripts").mkdir()
        shutil.copyfile(Path(__file__), source / "scripts/prove_linux_service_sandbox.py")
        # Only the explicit Python environment is staged; never the user's home,
        # SSH material, application preferences, live state, or signing keys.
        shutil.copytree(runtime, folder / "runtime", symlinks=True)
        python = folder / "runtime/bin/python"
        # Source modes from user checkout may be group-writable. Root ownership
        # and removal of group/other writes make staging immutable to DynamicUser.
        for staged in folder.rglob("*"):
            if not staged.is_symlink():
                staged.chmod(staged.stat().st_mode & ~0o022)
    config_path = configuration / "sandbox.json"
    # Only synthetic non-signing secrets and a public fixture key. No human
    # signing key or authentic Name.com credential exists in this proof.
    config = {"PULPO_E1_SYSTEM_FIXTURE": "1" if system else "0",
        "PULPO_CUSTODY_STATE_PATH": str(state / "custody.sqlite3"),
        "PULPO_KERNEL_SECRET_HEX": secrets.token_hex(32),
        "PULPO_CUSTODY_SECRET_HEX": secrets.token_hex(32),
        "PULPO_AUTHORITY_PUBLIC_KEY_HEX": bytes(range(32)).hex(),
        "PULPO_AUTHORITY_ID": "authority:e1-fixture", "PULPO_AUTHORITY_VERIFIER_ID": "verifier:e1-fixture",
        "PULPO_AUTHORITY_KEY_ID": "key:e1-public-fixture", "PULPO_AUTHORITY_DEPLOYMENT_ID": "deployment:e1-disposable",
        "PULPO_AUTHORITY_MAX_TTL_SECONDS": "300", "PULPO_PILOT_BUDGET_CENTS": "1",
        "PULPO_OWNER_REF": "owner://e1-disposable", "NAMECOM_SANDBOX_USERNAME": "e1-fixture-test",
        "NAMECOM_SANDBOX_EXECUTOR_TOKEN": "not-a-credential-executor",
        "NAMECOM_SANDBOX_OBSERVER_TOKEN": "not-a-credential-observer"}
    config_path.write_text(json.dumps(config))
    config_path.chmod(0o644 if system else 0o600)  # Synthetic values only.
    properties = {"NoNewPrivileges": "yes", "ProtectSystem": "strict", "ProtectHome": "tmpfs",
        "PrivateTmp": "yes", "PrivateDevices": "yes", "PrivateNetwork": "yes", "UMask": "0077",
        "RestrictAddressFamilies": "AF_UNIX AF_INET AF_INET6", "CapabilityBoundingSet": "",
        "KillMode": "control-group", "TimeoutStopSec": "10", "Restart": "no", "TasksMax": "64",
        "MemoryMax": "512M", "WorkingDirectory": str(source),
        "BindReadOnlyPaths": " ".join((str(source), str(python.parent.parent), str(configuration))),
        "BindPaths": str(state)}
    if system:
        properties.update(DynamicUser="yes", RuntimeDirectory=name, RuntimeDirectoryMode="0700",
                          RuntimeDirectoryPreserve="restart")
    command = ["systemd-run", *manager, "--collect", "--service-type=exec", "--unit=" + unit]
    for name, value in properties.items():
        command.extend(["--property", name + "=" + value])
    command.extend([str(python), "-B", str(source / "scripts/prove_linux_service_sandbox.py"), "--worker", str(config_path)])
    try:
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=20)
        for iteration in range(2):
            if iteration:
                subprocess.run(["systemctl", *manager, "restart", unit], check=True, timeout=20)
            deadline = time.monotonic() + 25
            while len(list(state.glob("report-*.json"))) <= iteration:
                require(time.monotonic() < deadline, "service proof timeout")
                time.sleep(.1)
            reports = [json.loads(p.read_text()) for p in state.glob("report-*.json")]
            result["runs"] = sorted(reports, key=lambda r: r["audit_rows"])
        result["properties"] = subprocess.check_output(["systemctl", *manager, "show", unit,
            *["--property=" + key for key in properties]], text=True, timeout=10).splitlines()
        require(result["runs"][1]["phase"] == "restart", "restart fixture was not reused")
        require(result["runs"][0]["pid"] != result["runs"][1]["pid"], "service process did not restart")
        if system:
            require(all(r["uid"] != 0 and r["uid"] != int(os.environ.get("SUDO_UID", "0"))
                        for r in result["runs"]), "dedicated service identity not established")
        result["passed"] = True
    except Exception as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
        if isinstance(exc, subprocess.CalledProcessError):
            result["command_stderr"] = exc.stderr
        result["journal"] = subprocess.run(["journalctl", *manager, "-u", unit, "-n", "35", "--no-pager"],
            capture_output=True, text=True, timeout=10).stdout
        raise
    finally:
        subprocess.run(["systemctl", *manager, "stop", unit], capture_output=True, timeout=20)
        active = subprocess.run(["systemctl", *manager, "is-active", unit], capture_output=True, text=True, timeout=10)
        result["unit_stopped"] = active.stdout.strip() in ("inactive", "failed", "unknown")
        scratch.cleanup()
        result["disposable_files_removed"] = not folder.exists()
        if system:
            result["runtime_directory_removed"] = not state.exists()
            result["passed"] = result["passed"] and result["runtime_directory_removed"]
        result["passed"] = result["passed"] and result["unit_stopped"] and result["disposable_files_removed"]
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x") as stream:
            json.dump(result, stream, indent=2)
        output.chmod(0o600)
        if system and os.environ.get("SUDO_UID") and os.environ.get("SUDO_GID"):
            os.chown(output, int(os.environ["SUDO_UID"]), int(os.environ["SUDO_GID"]))
    require(result["passed"], "sandbox proof or cleanup failed; inspect evidence")
    print(json.dumps({"passed": result["passed"], "evidence": str(output)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--system", action="store_true", help="Root launcher; service uses DynamicUser, never root")
    parser.add_argument("--runtime", type=Path, help="Explicit existing Python venv to stage for system proof")
    args = parser.parse_args()
    if args.worker:
        worker(args.worker)
    else:
        require(args.evidence is not None, "--evidence required")
        run(args.evidence, system=args.system, runtime=args.runtime)
