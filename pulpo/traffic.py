"""Ephemeral, bounded scheduling hints; never an authority or execution plane.

The trusted execution owner registers equivalent paths for exact intents. PTC
can choose among those paths but cannot invent a target, consume a permit, or
invoke a side effect. A queued decision is a claim, not dispatch authorization.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from threading import RLock
from time import monotonic
from typing import Callable

from .kernel import Decision, GovernanceKernel, Intent


class Backpressure(RuntimeError):
    """Caller must wait or return to governance; no permit has been consumed."""


@dataclass(frozen=True)
class Lane:
    name: str
    kind: str
    concurrency: int = 1
    queue_limit: int = 16
    min_dispatch_interval: float = 0.0

    def __post_init__(self):
        if not self.name or self.kind not in {"sql", "api"}:
            raise ValueError("lane requires a name and sql/api kind")
        for value in (self.concurrency, self.queue_limit):
            if type(value) is not int or not 1 <= value <= 1024:
                raise ValueError("lane bounds must be integers in [1, 1024]")
        if (type(self.min_dispatch_interval) not in (int, float)
                or not 0 <= self.min_dispatch_interval <= 1):
            raise ValueError("dispatch interval must be finite and in [0, 1] seconds")


@dataclass(frozen=True)
class Path:
    name: str
    lane: str
    intent: Intent


@dataclass(frozen=True)
class Work:
    intent: Intent
    permit: str
    paths: tuple[str, ...]


@dataclass(frozen=True)
class Dispatch:
    work: Work
    path: Path


class TrafficControl:
    """One trusted owner's scheduling helper, with no canonical writer.

    Queues and occupied slots are bounded per lane. Least outstanding work
    selects an equivalent path at admission and again at dispatch. A cooldown
    senses contention before dispatch only; there are no post-effect retries.
    Construction/configuration belongs to the trusted execution owner, never
    an untrusted transport. Register only interchangeable paths already allowed
    by existing execution policy; path names do not confer provider authority.
    """

    @classmethod
    def for_sql_api(cls, paths: tuple[Path, ...], *, sql_queue_limit: int = 16,
                    api_queue_limit: int = 16, clock: Callable[[], float] = monotonic):
        """Selected local profile: one SQL writer, two API slots, zero pacing.

        Preserve lane isolation for mixed/interleaved work without the SQL
        delays rejected by the shaping benchmark. Only queue bounds can vary
        through this profile. Exact path registration and canonical dispatch
        checks are identical to the explicit experimental constructor.
        """
        return cls((Lane("sql", "sql", 1, sql_queue_limit),
                    Lane("api", "api", 2, api_queue_limit)), paths, clock=clock)

    def __init__(self, lanes: tuple[Lane, ...], paths: tuple[Path, ...],
                 *, clock: Callable[[], float] = monotonic):
        self._lanes = {lane.name: lane for lane in lanes}
        self._paths = {path.name: path for path in paths}
        if not lanes or len(self._lanes) != len(lanes):
            raise ValueError("lanes must be nonempty and unique")
        if not paths or len(self._paths) != len(paths):
            raise ValueError("paths must be nonempty and unique")
        if any(not p.name or p.lane not in self._lanes for p in paths):
            raise ValueError("path must reference a registered lane")
        self._queues = {name: deque() for name in self._lanes}
        self._active: dict[int, Dispatch] = {}
        self._next = 0
        self._paused = {name: 0.0 for name in self._lanes}
        self._ready_at = {name: 0.0 for name in self._lanes}
        self._clock = clock
        self._lock = RLock()

    def _busy(self, lane):
        return sum(d.path.lane == lane for d in self._active.values())

    def _eligible(self, work):
        return [self._paths[name] for name in work.paths]

    def enqueue(self, intent: Intent, decision: Decision,
                paths: tuple[str, ...]) -> None:
        # Structural admission only. Forged, expired, revoked or spent claims
        # still have to pass the canonical kernel at dispatch time.
        if (decision.outcome != "allow" or not decision.permit
                or decision.intent_hash != GovernanceKernel.intent_hash(intent)):
            raise ValueError("authorized decision required")
        paths = tuple(paths)
        if not paths or len(set(paths)) != len(paths):
            raise ValueError("permitted paths must be nonempty and unique")
        if any(name not in self._paths or self._paths[name].intent != intent
               for name in paths):
            raise ValueError("path target mismatch")
        work = Work(intent, decision.permit, paths)
        with self._lock:
            available = [p for p in self._eligible(work)
                         if len(self._queues[p.lane]) < self._lanes[p.lane].queue_limit]
            if not available:
                raise Backpressure("queues saturated")
            path = min(available, key=lambda p: (
                max(self._paused[p.lane], self._ready_at[p.lane]) > self._clock(),
                (len(self._queues[p.lane]) + self._busy(p.lane))
                / self._lanes[p.lane].concurrency, p.name))
            self._queues[path.lane].append(work)

    def acquire(self) -> tuple[int, Dispatch] | None:
        with self._lock:
            # Round-robin lane order prevents a busy lane monopolizing dispatch.
            for lane in self._queues:
                queue = self._queues[lane]
                if not queue:
                    continue
                work = queue[0]
                available = [p for p in self._eligible(work)
                             if self._busy(p.lane) < self._lanes[p.lane].concurrency
                             and max(self._paused[p.lane], self._ready_at[p.lane]) <= self._clock()]
                if not available:
                    continue
                path = min(available, key=lambda p: (
                    self._busy(p.lane) / self._lanes[p.lane].concurrency, p.name))
                queue.popleft()
                self._next += 1
                dispatch = Dispatch(work, path)
                self._active[self._next] = dispatch
                self._ready_at[path.lane] = self._clock() + self._lanes[path.lane].min_dispatch_interval
                # Move this queue to the end without mutating during iteration.
                self._queues = {k: v for k, v in self._queues.items() if k != lane} | {lane: queue}
                return self._next, dispatch
            return None

    def ready_delay(self) -> float | None:
        """Earliest unoccupied queued path's timer delay, without consuming work.

        The owner can wait for this timer or an occupied slot's completion.
        None means no queued path has a free slot. No worker or sleep is owned
        by PTC, and this clock never decides canonical permit lifetime.
        """
        with self._lock:
            now = self._clock()
            delays = [max(0.0, max(self._paused[p.lane], self._ready_at[p.lane]) - now)
                      for queue in self._queues.values() if queue
                      for p in self._eligible(queue[0])
                      if self._busy(p.lane) < self._lanes[p.lane].concurrency]
            return min(delays) if delays else None

    def release(self, token: int) -> None:
        with self._lock:
            if token not in self._active:
                raise ValueError("unknown or released slot")
            del self._active[token]

    def pause(self, lane: str, seconds: float) -> None:
        """Trusted owner signals contention; this delays but never retries work."""
        if not isinstance(seconds, (int, float)) or not 0 <= seconds <= 60:
            raise ValueError("cooldown must be in [0, 60] seconds")
        with self._lock:
            if lane not in self._lanes:
                raise ValueError("unknown lane")
            self._paused[lane] = max(self._paused[lane], self._clock() + seconds)

    def snapshot(self) -> dict[str, dict[str, int]]:
        with self._lock:
            return {name: {"queued": len(self._queues[name]), "active": self._busy(name)}
                    for name in self._lanes}
