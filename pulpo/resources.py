"""Explicit owner-scoped cleanup; no global sweeper or background executor."""
from contextlib import ExitStack
from typing import Protocol, TypeVar


class Closeable(Protocol):
    def close(self) -> None: ...


T = TypeVar("T", bound=Closeable)


class ResourceScope:
    """Close explicitly owned resources in reverse registration order.

    Register only resources owned by this caller. Stop using them before leaving
    the scope. All registered closes are attempted even if one raises; cleanup
    errors propagate. This scope never commits, flushes work, retries effects,
    removes files, or takes ownership of resources implicitly.
    """

    def __init__(self) -> None:
        self._stack = ExitStack()
        self._owned: dict[int, Closeable] = {}
        self._closed = False
        self._entered = False

    def own(self, resource: T) -> T:
        if self._closed:
            raise RuntimeError("resource scope is closed")
        if not callable(getattr(resource, "close", None)):
            raise TypeError("owned resource must provide close()")
        if id(resource) not in self._owned:
            self._stack.callback(resource.close)
            self._owned[id(resource)] = resource
        return resource

    def close(self) -> None:
        self.__exit__(None, None, None)

    def __enter__(self) -> "ResourceScope":
        if self._closed or self._entered:
            raise RuntimeError("resource scope cannot be reused or nested")
        self._entered = True
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self._closed:
            return False
        # Mark terminal before callbacks so cleanup cannot register more work.
        self._closed = True
        try:
            return self._stack.__exit__(exc_type, exc, tb)
        finally:
            self._owned.clear()
