"""Private WSL presentation preferences; never read remembered source files."""
from contextlib import contextmanager
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import stat

SCHEMA = "pulpo.control-center-session.v1"
LIMIT = 16384
PAGES = ("Overview", "Connections", "Governance", "Activity", "Evidence", "System")
TABS = ("Diagnostics", "Tuning & benchmarks", "Source health", "Setup readiness", "Configuration", "Troubleshooting", "Session setup")
SOURCES = ("Governance", "Evidence", "UniFi UDM", "NinjaOne", "CrowdStrike")
RANGES = ("overview", "system", "evidence")


def preference_path(profile):
    return Path(profile).with_name("control-center-session.json")


def validate(value):
    if (type(value) is not dict or set(value) != {"schema", "sources", "ranges", "page", "system_tab"}
            or value["schema"] != SCHEMA or value["page"] not in PAGES or value["system_tab"] not in TABS
            or type(value["sources"]) is not dict or not set(value["sources"]) <= set(SOURCES)
            or type(value["ranges"]) is not dict or set(value["ranges"]) != set(RANGES)):
        raise ValueError("invalid_preferences")
    for path in value["sources"].values():
        if (type(path) is not str or not 1 <= len(path) <= 4096 or not path.startswith("/")
                or path.startswith("//") or any(ord(c) < 32 or ord(c) == 127 for c in path)
                or ".." in PurePosixPath(path).parts):
            raise ValueError("invalid_source_location")
    if any(type(n) is not int or n not in {60, 900, 3600} for n in value["ranges"].values()):
        raise ValueError("invalid_range")
    return value


def _private_file(info):
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
            or info.st_mode & 0o077 or info.st_nlink != 1 or info.st_size > LIMIT):
        raise ValueError("unsafe_preferences_file")


@contextmanager
def _directory(path, create=False):
    if create: path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if info.st_uid != os.geteuid() or info.st_mode & 0o022:
            raise ValueError("unsafe_preferences_directory")
        yield fd
    finally:
        os.close(fd)


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value: raise ValueError("duplicate_field")
        value[key] = item
    return value


def _read_at(directory, name):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    with os.fdopen(fd, "rb") as handle:
        _private_file(os.fstat(handle.fileno()))
        raw = handle.read(LIMIT + 1)
        if len(raw) > LIMIT: raise ValueError("oversized_preferences")
    return validate(json.loads(raw, object_pairs_hook=_pairs))


def load(path):
    path = Path(path)
    try:
        with _directory(path) as directory:
            return _read_at(directory, path.name)
    except FileNotFoundError:
        return None


def save(path, value):
    raw = (json.dumps(validate(value), indent=2) + "\n").encode("utf-8")
    if len(raw) > LIMIT: raise ValueError("oversized_preferences")
    path = Path(path)
    with _directory(path, create=True) as directory:
        try: _read_at(directory, path.name)  # Never overwrite an unrelated or malformed file.
        except FileNotFoundError: pass
        temporary = ".session-" + secrets.token_hex(12) + ".tmp"
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path.name, src_dir_fd=directory, dst_dir_fd=directory)
        finally:
            try: os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError: pass


def forget(path):
    path = Path(path)
    try:
        with _directory(path) as directory:
            _read_at(directory, path.name)  # Forget only a validated preferences document.
            os.unlink(path.name, dir_fd=directory)
    except FileNotFoundError:
        pass
