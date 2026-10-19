"""Read-only local OS resource observations. No Pulpo state or authority access."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
import os
from pathlib import Path
import platform
import shutil
import time


@dataclass(frozen=True)
class Metric:
    percent: float | None = None
    used: int | None = None
    total: int | None = None
    reason: str = "Not observed"


@dataclass(frozen=True)
class ResourceSample:
    observed_at: float
    monotonic_time: float
    source: str
    volume: str
    cpu: Metric
    memory: Metric
    storage: Metric


def utilization(used: int, total: int) -> Metric:
    if type(used) is not int or type(total) is not int or total <= 0 or not 0 <= used <= total:
        raise ValueError("Invalid resource capacity")
    return Metric(100 * used / total, used, total, "")


def level(value: float | None) -> str:
    """Resource attention thresholds only, never a governance score."""
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 100:
        return "Unknown"
    return "Attention" if value >= 90 else "Elevated" if value >= 75 else "Normal"


def linux_cpu(raw: str) -> tuple[int, int]:
    fields = raw.split()
    if not fields or fields[0] != "cpu" or not 5 <= len(fields) <= 11:
        raise ValueError("Invalid aggregate CPU statistics")
    counters = [int(value) for value in fields[1:]]
    if any(value < 0 for value in counters):
        raise ValueError("Invalid CPU counter")
    # guest/guest_nice are already included in user/nice; do not count twice.
    accounted = counters[:8]
    return sum(accounted), counters[3] + (counters[4] if len(counters) > 4 else 0)


def linux_memory(raw: str) -> Metric:
    values = {}
    for line in raw.splitlines():
        parts = line.split()
        if parts and parts[0] in ("MemTotal:", "MemAvailable:"):
            if len(parts) != 3 or parts[2] != "kB" or parts[0] in values:
                raise ValueError("Invalid memory statistics")
            values[parts[0]] = int(parts[1]) * 1024
    total, available = values["MemTotal:"], values["MemAvailable:"]
    if not 0 <= available <= total:
        raise ValueError("Invalid available memory")
    return utilization(total - available, total)


def _read_bounded(path: str, size: int) -> str:
    with open(path, encoding="ascii") as handle:
        result = handle.read(size + 1)
    if len(result) > size:
        raise ValueError("Resource statistics exceed bound")
    return result


def _windows_resources():
    """Windows OS counters; no process inspection or optional dependency."""
    import ctypes
    from ctypes import wintypes

    class MemoryStatus(ctypes.Structure):
        _fields_ = [("length", wintypes.DWORD), ("load", wintypes.DWORD)] + [
            (name, ctypes.c_ulonglong) for name in
            ("total", "available", "page_total", "page_available", "virtual_total", "virtual_available", "extended")]

    idle, kernel, user = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
    if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
        raise OSError("Windows CPU counters unavailable")
    integer = lambda value: (value.dwHighDateTime << 32) | value.dwLowDateTime
    cpu = integer(kernel) + integer(user), integer(idle)
    memory = MemoryStatus()
    memory.length = ctypes.sizeof(memory)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
        return cpu, Metric(reason="Windows memory statistics unavailable")
    return cpu, utilization(memory.total - memory.available, memory.total)


class ResourceSampler:
    """Each CPU value is an observed counter delta; the first value is unknown."""

    def __init__(self):
        self.previous_cpu = None
        self.volume = Path.home().anchor if os.name == "nt" else "/"
        self.source = "Linux / WSL" if "microsoft" in platform.release().lower() else platform.system()

    def sample(self) -> ResourceSample:
        cpu, memory = Metric(reason="CPU statistics unavailable"), Metric(reason="Memory statistics unavailable")
        counters = None
        if platform.system() == "Linux":
            try:
                with open("/proc/stat", encoding="ascii") as handle:
                    first = handle.readline(4097)
                if len(first) > 4096:
                    raise ValueError("CPU statistics exceed bound")
                counters = linux_cpu(first)
            except (OSError, ValueError, UnicodeError):
                pass
            try:
                memory = linux_memory(_read_bounded("/proc/meminfo", 65536))
            except (OSError, ValueError, KeyError, UnicodeError):
                pass
        elif os.name == "nt":
            try:
                counters, memory = _windows_resources()
            except (OSError, ValueError):
                pass
        if counters is None:
            self.previous_cpu = None
        else:
            if self.previous_cpu is None:
                cpu = Metric(reason="Collecting first CPU interval")
            else:
                total, idle = (value - previous for value, previous in zip(counters, self.previous_cpu))
                if total > 0 and 0 <= idle <= total:
                    cpu = Metric(percent=100 * (total - idle) / total, reason="")
                else:
                    cpu = Metric(reason="CPU counters reset or interval unavailable")
            self.previous_cpu = counters
        try:
            disk = shutil.disk_usage(self.volume)
            storage = utilization(disk.used, disk.total)
        except (OSError, ValueError):
            storage = Metric(reason="Selected-volume statistics unavailable")
        return ResourceSample(time.time(), time.monotonic(), self.source, self.volume, cpu, memory, storage)


class ResourceHistory:
    """Bounded, session-only observations. None and time gaps remain gaps."""
    def __init__(self):
        self.samples = deque(maxlen=1801)  # at 2 seconds: at most one hour

    def append(self, sample: ResourceSample):
        if self.samples and sample.monotonic_time <= self.samples[-1].monotonic_time:
            raise ValueError("Resource sample time must advance")
        self.samples.append(sample)

    def points(self, name: str, seconds: int, now: float):
        if name not in ("cpu", "memory", "storage") or seconds not in (60, 900, 3600):
            raise ValueError("Unsupported graph selection")
        return [(sample.monotonic_time, getattr(sample, name).percent)
                for sample in self.samples if now - seconds <= sample.monotonic_time <= now]
