"""Read-only component evidence; never grants a vulnerability exception."""
from __future__ import annotations

import hashlib
import argparse
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

PACKAGES = ["libc6", "libc-bin", "libstdc++6", "libgcc-s1", "gcc-14-base",
            "libacl1", "perl-base", "ncurses-bin", "libncursesw6", "libtinfo6",
            "util-linux", "mount", "zlib1g"]
COMMANDS = ["infocmp", "mount", "umount", "nsenter", "getfacl", "setfacl", "chacl", "perl"]


def command(args: list[str]) -> dict:
    result = subprocess.run(args, capture_output=True, text=True, timeout=20)
    return {"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


def binary(path: str) -> dict:
    target = Path(path)
    metadata = target.stat()
    digest = hashlib.sha256()
    with target.open("rb") as stream:
        for block in iter(lambda: stream.read(131072), b""):
            digest.update(block)
    capabilities = os.getxattr(target, "security.capability").hex() if "security.capability" in os.listxattr(target) else None
    return {"path": path, "resolved": str(target.resolve()), "mode": oct(stat.S_IMODE(metadata.st_mode)),
            "setuid": bool(metadata.st_mode & stat.S_ISUID), "setgid": bool(metadata.st_mode & stat.S_ISGID),
            "file_capabilities": capabilities, "sha256": digest.hexdigest()}


def privileged_files() -> list[str]:
    found = set()
    for root in ["/usr", "/bin", "/sbin"]:
        for directory, _, names in os.walk(root):
            for name in names:
                path = Path(directory) / name
                metadata = path.lstat()
                if stat.S_ISREG(metadata.st_mode) and metadata.st_mode & (stat.S_ISUID | stat.S_ISGID):
                    found.add(str(path.resolve()))
    return sorted(found)


def main(require_hardened: bool = False) -> None:
    status = {}
    for line in Path("/proc/self/status").read_text().splitlines():
        key, _, value = line.partition(":")
        if key in {"CapEff", "NoNewPrivs"}:
            status[key] = value.strip()
    if os.geteuid() == 0 or status.get("CapEff") != "0000000000000000" or status.get("NoNewPrivs") != "1":
        raise RuntimeError("component evidence requires the non-root, no-capability runtime")
    packages = {}
    for package in PACKAGES:
        packages[package] = {
            "metadata": command(["dpkg-query", "-W", "-f=${Package}\t${Version}\t${Essential}\n", package]),
            "files": command(["dpkg-query", "-L", package]),
        }
    commands = {}
    for name in COMMANDS:
        path = shutil.which(name)
        commands[name] = binary(path) if path else {"present": False}
    privileged = privileged_files()
    if require_hardened and (privileged or commands["infocmp"].get("present") is not False):
        raise RuntimeError("unexpected privilege helper or infocmp in hardened service image")
    modules = {}
    perl = shutil.which("perl")
    for module in ["Pod::Text", "Archive::Tar"]:
        # These are fixed trusted module identifiers, never user-provided input.
        code = 'eval { require ' + module + '; 1 } or do { print STDERR $@; exit 4 }; print $' + module + '::VERSION, "\\n";'
        modules[module] = command([perl, "-e", code]) if perl else {"exit_code": 4, "stderr": "perl absent"}
    fstab = Path("/etc/fstab")
    entries = [line for line in fstab.read_text().splitlines() if line.strip() and not line.lstrip().startswith("#")] if fstab.exists() else []
    print(json.dumps({"schema": "pulpo.container-component-evidence.v1", "python": sys.version,
                      "effective_uid": os.geteuid(), "process_security": status,
                      "fstab_noncomment_entries": len(entries), "commands": commands,
                      "privileged_files": privileged, "hardened_required": require_hardened,
                      "privileged_scan_roots": ["/usr", "/bin", "/sbin"],
                      "perl_modules": modules, "packages": packages,
                      "claim": "component inventory only; no advisory waived"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-hardened", action="store_true")
    main(parser.parse_args().require_hardened)
