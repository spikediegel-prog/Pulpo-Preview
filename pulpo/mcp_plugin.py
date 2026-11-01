"""Portable, capability-stripped Pulpo MCP plugin entrypoint.

The plugin consumes only a frozen ``MCPReadSnapshot`` exported by trusted
Pulpo. It never receives a kernel, orchestrator, authority client, executor,
policy object, trusted clock, canonical state backend, credential, permit, or
ledger reference.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
from typing import Any, Sequence

from .mcp_boundary import MCPBoundaryError, MCPReadSnapshot, create_mcp_server


DEFAULT_SNAPSHOT_PATH = Path.home() / ".pulpo" / "mcp-read-snapshot.json"
_MAX_SNAPSHOT_BYTES = 16_384
_SNAPSHOT_FIELDS = frozenset(
    {
        "policy_hash",
        "audit_valid",
        "audit_records",
        "audit_tip",
        "source_schema",
        "schema",
    }
)


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            raise ValueError("duplicate_json_key")
        document[key] = value
    return document


def _read_windows_snapshot(target: Path) -> str:
    """Read an immutable leaf while holding non-reparse ancestors against rename.

    Windows has no directory-relative os.open. Native read-only handles reject
    reparse points and omit delete sharing on each ancestor. The leaf also omits
    write sharing. Access still requires the trusted parent's Windows ACL; these
    flags do not claim to implement POSIX owner-private permissions.
    """
    import ctypes
    from ctypes import wintypes
    import msvcrt

    class FileInformation(ctypes.Structure):
        _fields_ = [
            ("attributes", wintypes.DWORD),
            ("creation", wintypes.FILETIME),
            ("access", wintypes.FILETIME),
            ("write", wintypes.FILETIME),
            ("volume", wintypes.DWORD),
            ("size_high", wintypes.DWORD),
            ("size_low", wintypes.DWORD),
            ("links", wintypes.DWORD),
            ("index_high", wintypes.DWORD),
            ("index_low", wintypes.DWORD),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                       wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    info = kernel.GetFileInformationByHandle
    info.argtypes = [wintypes.HANDLE, ctypes.POINTER(FileInformation)]
    info.restype = wintypes.BOOL
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL
    invalid = ctypes.c_void_p(-1).value
    handles = []
    descriptor = -1

    def open_checked(path: Path, *, directory: bool):
        error = "mcp_plugin_snapshot_parent_invalid" if directory else "mcp_plugin_snapshot_open_failed"
        # OPEN_EXISTING; no write/delete access; OPEN_REPARSE_POINT on every component.
        handle = create(str(path), 0x80 if directory else 0x80000000,
                        3 if directory else 1, None, 3,
                        0x00200000 | (0x02000000 if directory else 0), None)
        if handle == invalid:
            raise MCPBoundaryError(error) from ctypes.WinError(ctypes.get_last_error())
        handles.append(handle)
        metadata = FileInformation()
        if not info(handle, ctypes.byref(metadata)):
            raise MCPBoundaryError(error) from ctypes.WinError(ctypes.get_last_error())
        if metadata.attributes & 0x400 or bool(metadata.attributes & 0x10) != directory:
            raise MCPBoundaryError(error)
        return handle

    try:
        # Reject noncanonical spellings before traversing (including '..').
        if os.path.normcase(str(target)) != os.path.normcase(os.path.abspath(target)):
            raise MCPBoundaryError("mcp_plugin_snapshot_path_invalid")
        for parent in reversed(target.parents):
            open_checked(parent, directory=True)
        leaf = open_checked(target, directory=False)
        try:
            descriptor = msvcrt.open_osfhandle(leaf, os.O_RDONLY | os.O_BINARY)
        except OSError as exc:
            raise MCPBoundaryError("mcp_plugin_snapshot_open_failed") from exc
        handles.pop()  # Ownership transferred to the descriptor.
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > _MAX_SNAPSHOT_BYTES:
            raise MCPBoundaryError("mcp_plugin_snapshot_invalid")
        try:
            with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
                descriptor = -1
                return stream.read(_MAX_SNAPSHOT_BYTES + 1)
        except (OSError, UnicodeError) as exc:
            raise MCPBoundaryError("mcp_plugin_snapshot_invalid") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        for handle in reversed(handles):
            close(handle)


def read_snapshot_document(
    path: str | os.PathLike[str] = DEFAULT_SNAPSHOT_PATH,
) -> dict:
    """Load an exact frozen snapshot without write capability.

    POSIX mode bits are checked here. On Windows, trust depends on the ACLs of
    the parent directory; the reader does not inspect or set a Windows DACL.
    """

    if not isinstance(path, (str, os.PathLike)) or isinstance(path, bytes):
        raise MCPBoundaryError("mcp_plugin_snapshot_path_invalid")
    target = Path(path).expanduser()
    if not target.is_absolute() or not target.name or "\x00" in target.name:
        raise MCPBoundaryError("mcp_plugin_snapshot_path_invalid")

    parent = target.parent
    try:
        parent_metadata = parent.lstat()
    except OSError as exc:
        raise MCPBoundaryError("mcp_plugin_snapshot_parent_invalid") from exc
    if stat.S_ISLNK(parent_metadata.st_mode) or not stat.S_ISDIR(parent_metadata.st_mode):
        raise MCPBoundaryError("mcp_plugin_snapshot_parent_invalid")
    if os.name == "posix":
        # File mode alone does not prevent another local user from replacing
        # the snapshot through a writable parent directory. Require a trusted
        # owner (the running user or root) and no group/world write access.
        trusted_owners = {os.geteuid(), 0}
        if (
            parent_metadata.st_uid not in trusted_owners
            or stat.S_IMODE(parent_metadata.st_mode) & 0o022
        ):
            raise MCPBoundaryError("mcp_plugin_snapshot_parent_permissions_invalid")

    if os.name == "nt":
        raw = _read_windows_snapshot(target)
    else:
        directory_descriptor = -1
        file_descriptor = -1
        try:
            directory_flags = os.O_RDONLY
            directory_flags |= getattr(os, "O_CLOEXEC", 0)
            directory_flags |= getattr(os, "O_DIRECTORY", 0)
            directory_flags |= getattr(os, "O_NOFOLLOW", 0)
            try:
                directory_descriptor = os.open(parent, directory_flags)
                opened_parent = os.fstat(directory_descriptor)
            except OSError as exc:
                raise MCPBoundaryError("mcp_plugin_snapshot_parent_invalid") from exc
            if (
                not stat.S_ISDIR(opened_parent.st_mode)
                or opened_parent.st_dev != parent_metadata.st_dev
                or opened_parent.st_ino != parent_metadata.st_ino
            ):
                raise MCPBoundaryError("mcp_plugin_snapshot_parent_invalid")

            file_flags = os.O_RDONLY
            file_flags |= getattr(os, "O_CLOEXEC", 0)
            file_flags |= getattr(os, "O_NOFOLLOW", 0)
            # A substituted FIFO/device must not block before fstat rejects it.
            file_flags |= getattr(os, "O_NONBLOCK", 0)
            try:
                file_descriptor = os.open(
                    target.name,
                    file_flags,
                    dir_fd=directory_descriptor,
                )
                metadata = os.fstat(file_descriptor)
            except OSError as exc:
                raise MCPBoundaryError("mcp_plugin_snapshot_open_failed") from exc
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > _MAX_SNAPSHOT_BYTES:
                raise MCPBoundaryError("mcp_plugin_snapshot_invalid")
            if os.name == "posix" and stat.S_IMODE(metadata.st_mode) & 0o077:
                raise MCPBoundaryError("mcp_plugin_snapshot_permissions_invalid")

            try:
                with os.fdopen(file_descriptor, "r", encoding="utf-8") as handle:
                    file_descriptor = -1
                    raw = handle.read(_MAX_SNAPSHOT_BYTES + 1)
            except (OSError, UnicodeError) as exc:
                raise MCPBoundaryError("mcp_plugin_snapshot_invalid") from exc
        finally:
            if file_descriptor >= 0:
                os.close(file_descriptor)
            if directory_descriptor >= 0:
                os.close(directory_descriptor)

    if len(raw) > _MAX_SNAPSHOT_BYTES:
        raise MCPBoundaryError("mcp_plugin_snapshot_invalid")
    try:
        document = json.loads(raw, object_pairs_hook=_unique_json_object)
    except (json.JSONDecodeError, ValueError) as exc:
        raise MCPBoundaryError("mcp_plugin_snapshot_invalid") from exc
    if type(document) is not dict:
        raise MCPBoundaryError("mcp_plugin_snapshot_invalid")
    return document


def load_mcp_snapshot(path=DEFAULT_SNAPSHOT_PATH) -> MCPReadSnapshot:
    """Load the unchanged exact MCP contract using the shared protected reader."""
    document = read_snapshot_document(path)
    if set(document) != _SNAPSHOT_FIELDS:
        raise MCPBoundaryError("mcp_plugin_snapshot_invalid")

    try:
        return MCPReadSnapshot(**document)
    except (TypeError, ValueError) as exc:
        raise MCPBoundaryError("mcp_plugin_snapshot_invalid") from exc


def create_plugin_server(
    snapshot_path: str | os.PathLike[str] = DEFAULT_SNAPSHOT_PATH,
):
    """Create the existing capability-stripped MCP server from a frozen file."""

    return create_mcp_server(load_mcp_snapshot(snapshot_path))


def main(argv: Sequence[str] | None = None) -> int:
    """Run the local portable plugin over MCP stdio."""

    parser = argparse.ArgumentParser(
        prog="pulpo-mcp-plugin",
        description="Run Pulpo's frozen read/proposal MCP projection.",
    )
    parser.add_argument(
        "--snapshot",
        default=str(DEFAULT_SNAPSHOT_PATH),
        help="Absolute path to a trusted exported pulpo.mcp-read-snapshot.v0 file.",
    )
    args = parser.parse_args(argv)

    server = create_plugin_server(args.snapshot)
    server.run(transport="stdio")
    return 0


if __name__ == "__main__":  # pragma: no cover - console entrypoint
    raise SystemExit(main())
