"""Exact serial write projection for the attached-device governance proof.

This module holds no device driver and performs no serial I/O itself. It only
freezes the exact outbound consequence object and delegates authorization to the
canonical GovernanceKernel. The real transport is a thin pyserial wrapper; tests
run on a fake transport with no hardware.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol

from .kernel import Decision, GovernanceKernel, Intent


SERIAL_WRITE_ACTION = "serial_write"


def _normalize_port(port: str) -> str:
    if not isinstance(port, str) or not port:
        raise ValueError("serial port must be a non-empty string")
    return port


def _normalize_baud(baud: int) -> int:
    if isinstance(baud, bool) or not isinstance(baud, int) or baud <= 0:
        raise ValueError("serial baud must be a positive integer")
    return baud


@dataclass(frozen=True)
class SerialWrite:
    """Exact outbound serial consequence object for serial.write v0."""

    port: str
    payload: bytes
    baud: int = 115200
    schema: str = "pulpo.serial-write.v0"

    def __post_init__(self) -> None:
        object.__setattr__(self, "port", _normalize_port(self.port))
        if not isinstance(self.payload, (bytes, bytearray)) or not self.payload:
            raise ValueError("serial payload must be non-empty bytes")
        object.__setattr__(self, "payload", bytes(self.payload))
        object.__setattr__(self, "baud", _normalize_baud(self.baud))
        if self.schema != "pulpo.serial-write.v0":
            raise ValueError("unsupported serial write schema")

    @property
    def payload_hash(self) -> str:
        return sha256(self.payload).hexdigest()

    @property
    def resource(self) -> str:
        return f"serial:port:{self.port}:write:sha256:{self.payload_hash}"

    def intent(self, *, principal: str, session_id: str) -> Intent:
        return Intent(
            principal=principal,
            action=SERIAL_WRITE_ACTION,
            resource=self.resource,
            cost=0,
            session_id=session_id,
        )


class SerialTransport(Protocol):
    expected_port: str

    def write(self, write: SerialWrite) -> bytes: ...


class SerialWriteRejected(RuntimeError):
    pass


class PySerialTransport:
    """Thin pyserial wrapper; the only place pyserial is imported."""

    def __init__(self, *, port: str, baud: int = 115200, timeout: float = 1.0) -> None:
        self.expected_port = port
        self._baud = baud
        self._timeout = timeout

    def write(self, write: SerialWrite) -> bytes:
        import serial

        with serial.Serial(write.port, write.baud, timeout=self._timeout) as ser:
            ser.write(write.payload)
            return ser.read(4096)


class GovernedSerialWriter:
    """Execution gate that consumes an exact serial.write permit."""

    def __init__(self, kernel: GovernanceKernel, transport: SerialTransport) -> None:
        self._kernel = kernel
        self._transport = transport

    def evaluate(self, write: SerialWrite, *, principal: str, session_id: str) -> Decision:
        return self._kernel.evaluate(write.intent(principal=principal, session_id=session_id))

    def _validate_transport_scope(self, write: SerialWrite) -> None:
        if getattr(self._transport, "expected_port", None) != write.port:
            raise SerialWriteRejected("serial transport port mismatch")

    def execute(
        self,
        write: SerialWrite,
        *,
        permit: str,
        principal: str,
        session_id: str,
    ) -> bytes:
        self._validate_transport_scope(write)
        intent = write.intent(principal=principal, session_id=session_id)
        if not isinstance(permit, str) or not permit:
            raise SerialWriteRejected("serial write permit missing")
        if not self._kernel.consume(permit, intent):
            raise SerialWriteRejected("serial write permit rejected")
        return self._transport.write(write)
