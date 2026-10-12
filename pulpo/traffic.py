"""Ephemeral, bounded scheduling hints; never an authority or execution plane.

The trusted execution owner registers equivalent paths for exact intents. PTC
can choose among those paths but cannot invent a target, consume a permit, or
invoke a side effect. A queued decision is a claim, not dispatch authorization.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from math import isfinite
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
    foreground_reserve: int = 1

    def __post_init__(self):
        if not self.name or self.kind not in {"sql", "api"}:
            raise ValueError("lane requires a name and sql/api kind")
        for value in (self.concurrency, self.queue_limit):
            if type(value) is not int or not 1 <= value <= 1024:
                raise ValueError("lane bounds must be integers in [1, 1024]")
        if (type(self.min_dispatch_interval) not in (int, float)
                or not 0 <= self.min_dispatch_interval <= 1):
            raise ValueError("dispatch interval must be finite and in [0, 1] seconds")
        if (type(self.foreground_reserve) is not int
                or not 0 <= self.foreground_reserve <= self.queue_limit):
            raise ValueError("foreground reserve must be an integer in [0, queue_limit]")


@dataclass(frozen=True)
class Path:
    name: str
    lane: str
    intent: Intent
    background: bool = False

    def __post_init__(self):
        if type(self.background) is not bool:
            raise ValueError("background classification must be an exact boolean")


@dataclass(frozen=True)
class Work:
    intent: Intent
    permit: str
    paths: tuple[str, ...]
    background: bool = False


@dataclass(frozen=True)
class Dispatch:
    work: Work
    path: Path


@dataclass(frozen=True)
class _Queued:
    work: Work
    expires_at: float


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
                    api_queue_limit: int = 16, clock: Callable[[], float] = monotonic,
                    queue_ttl_seconds: float | None = None,
                    sql_foreground_reserve: int = 1, api_foreground_reserve: int = 1):
        """Selected local profile: one SQL writer, two API slots, zero pacing.

        Preserve lane isolation for mixed/interleaved work without the SQL
        delays rejected by the shaping benchmark. Queue bounds and an optional
        routing-only queue TTL can vary. Exact path registration and canonical dispatch
        checks are identical to the explicit experimental constructor.
        """
        return cls((Lane("sql", "sql", 1, sql_queue_limit,
                         foreground_reserve=sql_foreground_reserve),
                    Lane("api", "api", 2, api_queue_limit,
                         foreground_reserve=api_foreground_reserve)), paths, clock=clock,
                   queue_ttl_seconds=queue_ttl_seconds)

    def __init__(self, lanes: tuple[Lane, ...], paths: tuple[Path, ...],
                 *, clock: Callable[[], float] = monotonic,
                 queue_ttl_seconds: float | None = None):
        if queue_ttl_seconds is not None and (
                type(queue_ttl_seconds) not in (int, float)
                or not 0 < queue_ttl_seconds <= 300 or not isfinite(queue_ttl_seconds)):
            raise ValueError("queue TTL must be finite and in (0, 300] seconds")
        if not callable(clock):
            raise ValueError("scheduling clock must be callable")
        self._queue_ttl_seconds = queue_ttl_seconds
        self._last_now = -1.0
        self._lanes = {lane.name: lane for lane in lanes}
        self._paths = {path.name: path for path in paths}
        self._has_background = any(path.background for path in paths)
        self._foreground_lanes = {path.lane for path in paths if not path.background}
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
        self._dropped = {name: 0 for name in self._lanes}

    def _now(self):
        now = self._clock()
        try:
            invalid = (type(now) not in (int, float) or not isfinite(now)
                       or now < 0 or now < self._last_now)
        except OverflowError:
            invalid = True
        if invalid:
            raise ValueError("invalid or regressing scheduling clock")
        self._last_now = now
        return now

    @staticmethod
    def _head(queue):
        entry = queue[0]
        return entry.work if type(entry) is _Queued else entry

    def _expire(self, now):
        if self._queue_ttl_seconds is None:
            return
        for lane, queue in self._queues.items():
            if not self._has_background:
                while queue and now >= queue[0].expires_at:
                    queue.popleft()
                    self._dropped[lane] += 1
                continue
            # Foreground priority can reorder admission deadlines. Inspect all
            # bounded entries so older background work still expires on time.
            remaining = deque(entry for entry in queue if now < entry.expires_at)
            self._dropped[lane] += len(queue) - len(remaining)
            self._queues[lane] = remaining

    def _foreground_pending(self):
        return (any(queue and not self._head(queue).background for queue in self._queues.values())
                or any(not dispatch.work.background for dispatch in self._active.values()))

    def _busy(self, lane):
        return sum(d.path.lane == lane for d in self._active.values())

    def _eligible(self, work):
        return [self._paths[name] for name in work.paths]

    def _can_enqueue(self, path, work):
        lane = self._lanes[path.lane]
        queue = self._queues[path.lane]
        if len(queue) >= lane.queue_limit:
            return False
        if not work.background or path.lane not in self._foreground_lanes:
            return True
        background_count = sum(
            (entry.work if type(entry) is _Queued else entry).background
            for entry in queue)
        return background_count < lane.queue_limit - lane.foreground_reserve

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
        classifications = {self._paths[name].background for name in paths}
        if len(classifications) != 1:
            raise ValueError("equivalent paths must have the same background classification")
        work = Work(intent, decision.permit, paths, classifications.pop())
        with self._lock:
            now = self._now()
            self._expire(now)
            available = [p for p in self._eligible(work)
                         if self._can_enqueue(p, work)]
            if not available:
                raise Backpressure("queues saturated")
            path = min(available, key=lambda p: (
                max(self._paused[p.lane], self._ready_at[p.lane]) > now,
                (len(self._queues[p.lane]) + self._busy(p.lane))
                / self._lanes[p.lane].concurrency, p.name))
            entry = work if self._queue_ttl_seconds is None else _Queued(work, now + self._queue_ttl_seconds)
            queue = self._queues[path.lane]
            if work.background or not self._has_background:
                queue.append(entry)
            else:
                # FIFO within each class, foreground before queued background.
                position = next((index for index, queued in enumerate(queue)
                                 if (queued.work if type(queued) is _Queued else queued).background), len(queue))
                queue.insert(position, entry)

    def acquire(self) -> tuple[int, Dispatch] | None:
        with self._lock:
            now = self._now()
            self._expire(now)
            foreground_pending = self._has_background and self._foreground_pending()
            # Round-robin lane order prevents a busy lane monopolizing dispatch.
            for lane in self._queues:
                queue = self._queues[lane]
                if not queue:
                    continue
                work = self._head(queue)
                if work.background and foreground_pending:
                    continue
                available = [p for p in self._eligible(work)
                             if self._busy(p.lane) < self._lanes[p.lane].concurrency
                             and max(self._paused[p.lane], self._ready_at[p.lane]) <= now]
                if not available:
                    continue
                path = min(available, key=lambda p: (
                    self._busy(p.lane) / self._lanes[p.lane].concurrency, p.name))
                queue.popleft()
                self._next += 1
                dispatch = Dispatch(work, path)
                self._active[self._next] = dispatch
                self._ready_at[path.lane] = now + self._lanes[path.lane].min_dispatch_interval
                # Move this queue to the end without mutating during iteration.
                self._queues = {k: v for k, v in self._queues.items() if k != lane} | {lane: queue}
                return self._next, dispatch
            return None

    def ready_delay(self) -> float | None:
        """Earliest unoccupied queued path's timer delay, without consuming work.

        The owner can wait for this timer or an occupied slot's completion.
        Optional queue expiry is also a wake deadline, even with occupied slots.
        None means no free-path or enabled expiry deadline remains. No worker or
        sleep is owned by PTC; scheduling time never decides permit lifetime.
        """
        with self._lock:
            now = self._now()
            self._expire(now)
            foreground_pending = self._has_background and self._foreground_pending()
            delays = [max(0.0, max(self._paused[p.lane], self._ready_at[p.lane]) - now)
                      for queue in self._queues.values() if queue
                      if not self._head(queue).background or not foreground_pending
                      for p in self._eligible(self._head(queue))
                      if self._busy(p.lane) < self._lanes[p.lane].concurrency]
            if self._queue_ttl_seconds is not None:
                delays.extend(entry.expires_at - now for queue in self._queues.values() for entry in queue)
            return min(delays) if delays else None

    def release(self, token: int) -> None:
        with self._lock:
            if type(token) is not int or token not in self._active:
                raise ValueError("unknown or released slot")
            del self._active[token]

    def pause(self, lane: str, seconds: float) -> None:
        """Trusted owner signals contention; this delays but never retries work."""
        if type(seconds) not in (int, float) or not 0 <= seconds <= 60 or not isfinite(seconds):
            raise ValueError("cooldown must be in [0, 60] seconds")
        with self._lock:
            if lane not in self._lanes:
                raise ValueError("unknown lane")
            self._paused[lane] = max(self._paused[lane], self._now() + seconds)

    def snapshot(self) -> dict[str, dict[str, int]]:
        with self._lock:
            self._expire(self._now())
            return {name: {"queued": len(self._queues[name]), "active": self._busy(name),
                           "dropped": self._dropped[name]}
                    for name in self._lanes}
