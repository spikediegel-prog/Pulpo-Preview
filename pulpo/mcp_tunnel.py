"""Fail-closed launcher for Pulpo over OpenAI Secure MCP Tunnel.

The tunnel is transport only. It is never an authority source and it receives no
Pulpo kernel, orchestrator, executor, policy, permit, canonical state backend,
credential, or ledger capability. The only MCP child it may launch is the
existing capability-stripped ``pulpo.mcp_plugin`` projection over stdio.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import hmac
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Mapping, Sequence

from .mcp_boundary import MCPBoundaryError
from .mcp_plugin import DEFAULT_SNAPSHOT_PATH, load_mcp_snapshot
from .transport import sanitized_transport_environment


class MCPTunnelBindingError(RuntimeError):
    """Raised when the secure tunnel binding cannot be constructed safely."""


DEFAULT_PROFILE = "pulpo-local-stdio"
_RUNTIME_KEY_ENV = "CONTROL_PLANE_API_KEY"
_TUNNEL_ID_ENV = "CONTROL_PLANE_TUNNEL_ID"
_SNAPSHOT_ENV = "PULPO_MCP_SNAPSHOT"
_TUNNEL_CLIENT_ENV = "PULPO_TUNNEL_CLIENT"
_TUNNEL_CLIENT_SHA256_ENV = "PULPO_TUNNEL_CLIENT_SHA256"
_TUNNEL_HEX_LENGTH = 32


def _required_text(value: str | None, reason: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise MCPTunnelBindingError(reason)
    return value


def validate_tunnel_id(value: str | None) -> str:
    """Accept exactly the tunnel-client control-plane identifier format."""

    tunnel_id = _required_text(value, "pulpo_tunnel_id_missing")
    prefix = "tunnel_"
    if not tunnel_id.startswith(prefix):
        raise MCPTunnelBindingError("pulpo_tunnel_id_invalid")
    suffix = tunnel_id[len(prefix) :]
    if (
        len(suffix) != _TUNNEL_HEX_LENGTH
        or suffix != suffix.lower()
        or any(character not in "0123456789abcdef" for character in suffix)
    ):
        raise MCPTunnelBindingError("pulpo_tunnel_id_invalid")
    return tunnel_id


def resolve_tunnel_client(
    candidate: str | None = None,
    expected_sha256: str | None = None,
) -> str:
    """Resolve tunnel-client and require an independently pinned file digest."""

    if not isinstance(expected_sha256, str):
        raise MCPTunnelBindingError("pulpo_tunnel_client_sha256_missing")
    if re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None:
        raise MCPTunnelBindingError("pulpo_tunnel_client_sha256_invalid")

    requested = _required_text(
        candidate or "tunnel-client",
        "pulpo_tunnel_client_invalid",
    )
    if os.sep in requested or (os.altsep and os.altsep in requested):
        path = Path(requested).expanduser()
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise MCPTunnelBindingError("pulpo_tunnel_client_missing") from exc
        if not resolved.is_file() or not os.access(resolved, os.X_OK):
            raise MCPTunnelBindingError("pulpo_tunnel_client_not_executable")
    else:
        found = shutil.which(requested)
        if found is None:
            raise MCPTunnelBindingError("pulpo_tunnel_client_missing")
        resolved = Path(found).resolve(strict=True)

    digest_state = sha256()
    try:
        with resolved.open("rb") as executable:
            for chunk in iter(lambda: executable.read(1024 * 1024), b""):
                digest_state.update(chunk)
    except OSError as exc:
        raise MCPTunnelBindingError("pulpo_tunnel_client_unreadable") from exc
    digest = digest_state.hexdigest()
    if not hmac.compare_digest(digest, expected_sha256):
        raise MCPTunnelBindingError("pulpo_tunnel_client_sha256_mismatch")
    return str(resolved)


def _open_pinned_tunnel_client(
    candidate: str | None,
    expected_sha256: str | None,
) -> tuple[str, int | None]:
    """Verify a client and, on Linux, retain the exact inode for execution."""

    if not sys.platform.startswith("linux"):
        return resolve_tunnel_client(candidate, expected_sha256), None
    if not isinstance(expected_sha256, str):
        raise MCPTunnelBindingError("pulpo_tunnel_client_sha256_missing")
    if re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None:
        raise MCPTunnelBindingError("pulpo_tunnel_client_sha256_invalid")

    requested = _required_text(candidate or "tunnel-client", "pulpo_tunnel_client_invalid")
    if os.sep in requested or (os.altsep and os.altsep in requested):
        path = Path(requested).expanduser()
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise MCPTunnelBindingError("pulpo_tunnel_client_missing") from exc
    else:
        found = shutil.which(requested)
        if found is None:
            raise MCPTunnelBindingError("pulpo_tunnel_client_missing")
        resolved = Path(found).resolve(strict=True)

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(resolved, flags)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or not metadata.st_mode & 0o111:
            raise MCPTunnelBindingError("pulpo_tunnel_client_not_executable")
        digest_state = sha256()
        with os.fdopen(os.dup(descriptor), "rb") as executable:
            for chunk in iter(lambda: executable.read(1024 * 1024), b""):
                digest_state.update(chunk)
        if not hmac.compare_digest(digest_state.hexdigest(), expected_sha256):
            raise MCPTunnelBindingError("pulpo_tunnel_client_sha256_mismatch")
        return f"/proc/self/fd/{descriptor}", descriptor
    except MCPTunnelBindingError:
        if "descriptor" in locals():
            os.close(descriptor)
        raise
    except OSError as exc:
        if "descriptor" in locals():
            os.close(descriptor)
        raise MCPTunnelBindingError("pulpo_tunnel_client_unreadable") from exc


def build_stdio_command(
    snapshot_path: str | os.PathLike[str],
    *,
    python_executable: str | None = None,
) -> str:
    """Build the exact stdio child command handed to tunnel-client."""

    target = Path(snapshot_path).expanduser()
    if not target.is_absolute():
        raise MCPTunnelBindingError("pulpo_tunnel_snapshot_path_invalid")
    executable = _required_text(
        python_executable or sys.executable,
        "pulpo_tunnel_python_invalid",
    )
    parts = [
        executable,
        "-m",
        "pulpo.mcp_plugin",
        "--snapshot",
        str(target),
    ]
    if os.name == "nt":
        return subprocess.list2cmdline(parts)
    return shlex.join(parts)


def _runtime_environment(
    env: Mapping[str, str] | None,
    *,
    profile_dir: str,
    tunnel_id: str,
) -> dict[str, str]:
    """Build a daemon environment that cannot override the admitted binding."""

    runtime = dict(os.environ if env is None else env)
    runtime_key = _required_text(
        runtime.get(_RUNTIME_KEY_ENV),
        "pulpo_tunnel_runtime_key_missing",
    )

    # tunnel-client gives environment variables precedence over profiles. Remove
    # every environment-level control-plane/MCP override before restoring only
    # the exact runtime key and tunnel id selected by this launcher. This blocks
    # ambient MCP_COMMAND, MCP_SERVER_URL, alternate control-plane hosts, or a
    # stale tunnel ID from silently changing the reviewed transport path.
    for name in tuple(runtime):
        if name.startswith("CONTROL_PLANE_") or name.startswith("MCP_"):
            runtime.pop(name, None)
    for name in (
        "OPENAI_ADMIN_KEY",
        "OPENAI_API_KEY",
        _TUNNEL_CLIENT_ENV,
        _TUNNEL_CLIENT_SHA256_ENV,
        "TUNNEL_CLIENT_CONFIG",
        "TUNNEL_CLIENT_PROFILE",
        "TUNNEL_CLIENT_PROFILE_FILE",
    ):
        runtime.pop(name, None)

    runtime = sanitized_transport_environment(runtime)
    runtime[_RUNTIME_KEY_ENV] = runtime_key
    runtime[_TUNNEL_ID_ENV] = tunnel_id
    runtime["TUNNEL_CLIENT_PROFILE_DIR"] = profile_dir
    return runtime


def run_secure_tunnel(
    *,
    tunnel_id: str | None,
    snapshot_path: str | os.PathLike[str] = DEFAULT_SNAPSHOT_PATH,
    tunnel_client: str = "tunnel-client",
    tunnel_client_sha256: str | None = None,
    profile: str = DEFAULT_PROFILE,
    doctor_only: bool = False,
    env: Mapping[str, str] | None = None,
) -> int:
    """Validate the frozen Pulpo projection, then run the official tunnel client.

    The profile is created in a process-private temporary directory and refers to
    the runtime API key only by environment variable. The key is never written to
    the profile or passed on the command line.
    """

    tunnel_id = validate_tunnel_id(tunnel_id)
    profile = _required_text(profile, "pulpo_tunnel_profile_invalid")
    if any(
        character
        not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
        for character in profile
    ):
        raise MCPTunnelBindingError("pulpo_tunnel_profile_invalid")

    snapshot = Path(snapshot_path).expanduser()
    if not snapshot.is_absolute():
        raise MCPTunnelBindingError("pulpo_tunnel_snapshot_path_invalid")

    # Reuse the admitted plugin boundary as the format/path gate. On Windows,
    # the operator must ensure the snapshot parent's ACL is trusted.
    load_mcp_snapshot(snapshot)

    source_environment = os.environ if env is None else env
    _required_text(source_environment.get(_RUNTIME_KEY_ENV), "pulpo_tunnel_runtime_key_missing")
    expected_client_sha256 = tunnel_client_sha256
    if expected_client_sha256 is None:
        expected_client_sha256 = source_environment.get(_TUNNEL_CLIENT_SHA256_ENV)
    mcp_command = build_stdio_command(snapshot)
    client, client_descriptor = _open_pinned_tunnel_client(
        tunnel_client, expected_client_sha256
    )
    process_options = (
        {"pass_fds": (client_descriptor,)}
        if client_descriptor is not None
        else {}
    )
    try:
        with tempfile.TemporaryDirectory(prefix="pulpo-tunnel-profile-") as profile_dir:
            runtime_env = _runtime_environment(
                env,
                profile_dir=profile_dir,
                tunnel_id=tunnel_id,
            )
            init_command = [
                client,
                "init",
                "--sample",
                "sample_mcp_stdio_local",
                "--profile",
                profile,
                "--profile-dir",
                profile_dir,
                "--tunnel-id",
                tunnel_id,
                "--mcp-command",
                mcp_command,
                "--health-listen-addr",
                "127.0.0.1:0",
            ]
            subprocess.run(
                init_command,
                check=True,
                env=runtime_env,
                **process_options,
            )
            subprocess.run(
                [client, "doctor", "--profile", profile, "--explain"],
                check=True,
                env=runtime_env,
                **process_options,
            )
            if doctor_only:
                return 0

            completed = subprocess.run(
                [client, "run", "--profile", profile],
                check=False,
                env=runtime_env,
                **process_options,
            )
            return completed.returncode
    finally:
        if client_descriptor is not None:
            os.close(client_descriptor)


def main(argv: Sequence[str] | None = None) -> int:
    """Validate and start Pulpo's private Secure MCP Tunnel binding."""

    parser = argparse.ArgumentParser(
        prog="pulpo-mcp-tunnel",
        description=(
            "Connect Pulpo's frozen MCP projection to an OpenAI Secure MCP Tunnel."
        ),
    )
    parser.add_argument(
        "--tunnel-id",
        default=os.environ.get(_TUNNEL_ID_ENV),
        help=f"OpenAI tunnel ID. Defaults to ${_TUNNEL_ID_ENV}.",
    )
    parser.add_argument(
        "--snapshot",
        default=os.environ.get(_SNAPSHOT_ENV, str(DEFAULT_SNAPSHOT_PATH)),
        help=(
            f"Absolute frozen snapshot path. Defaults to ${_SNAPSHOT_ENV} "
            f"or {DEFAULT_SNAPSHOT_PATH}."
        ),
    )
    parser.add_argument(
        "--tunnel-client",
        default=os.environ.get(_TUNNEL_CLIENT_ENV, "tunnel-client"),
        help=f"tunnel-client executable. Defaults to ${_TUNNEL_CLIENT_ENV} or PATH; its digest must be pinned separately.",
    )
    parser.add_argument(
        "--tunnel-client-sha256",
        default=os.environ.get(_TUNNEL_CLIENT_SHA256_ENV),
        help=f"Trusted lowercase SHA-256 of tunnel-client. Defaults to ${_TUNNEL_CLIENT_SHA256_ENV}.",
    )
    parser.add_argument(
        "--profile",
        default=DEFAULT_PROFILE,
        help="Ephemeral tunnel-client profile name.",
    )
    parser.add_argument(
        "--doctor-only",
        action="store_true",
        help="Validate tunnel connectivity and exit without starting the daemon.",
    )
    args = parser.parse_args(argv)

    try:
        return run_secure_tunnel(
            tunnel_id=args.tunnel_id,
            snapshot_path=args.snapshot,
            tunnel_client=args.tunnel_client,
            tunnel_client_sha256=args.tunnel_client_sha256,
            profile=args.profile,
            doctor_only=args.doctor_only,
        )
    except (MCPTunnelBindingError, MCPBoundaryError) as exc:
        print(f"pulpo_mcp_tunnel_error:{exc}", file=sys.stderr)
        return 2
    except subprocess.CalledProcessError as exc:
        print(f"pulpo_mcp_tunnel_command_failed:{exc.returncode}", file=sys.stderr)
        return 3


if __name__ == "__main__":  # pragma: no cover - console entrypoint
    raise SystemExit(main())
