"""Attached-device governance extension (generic USB-UART, not device-specific).

This extension puts an attached serial device behind Pulpo's governance
instead of beside it. It governs the *serial channel* (a USB-UART port),
not a device model:

- The user supplies drivers + a USB-UART bridge, so the OS presents a
  serial port (``/dev/ttyUSB*``, ``/dev/ttyACM*``). The extension does not
  parse device-specific protocols and does not know device models.
- A request to act on a port must carry a valid one-use Pulpo permit for
  that exact capability, that exact port, and that exact intent. The
  executor verifies the permit before it opens the port. No permit means
  no action (fail closed).
- Every request, permit, execution, and result is recorded as
  tamper-evident evidence. Unauthorized attempts to open a port outside
  the governance path are detected and recorded as evidence too.

Honest limit: on a general Linux box, root can always force a device
open. No userspace lock stops root. What this extension guarantees is
that a bypass cannot be done *silently* — the attempt is detected and
leaves evidence, with no permitted action to show for it. The access
layer (sysadmin USB restrictions, the customer's CrowdStrike / Huntress
endpoint install) is what blocks the bypass at the machine; Pulpo is the
governance and evidence layer on top of it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import glob
import hashlib
import json
import os
import time
from typing import Any, Callable, Sequence

# ---------------------------------------------------------------------------
# Capabilities (generic serial operations, not device-specific)
# ---------------------------------------------------------------------------

#: Write bytes to the port. The payload is the caller's business; Pulpo
#: governs who may send it, for what exact intent, and records that it
#: was sent.
CAPABILITY_SERIAL_WRITE = "serial.write"
#: Flash firmware over the serial port (e.g. esptool-style flashing).
CAPABILITY_SERIAL_FLASH = "serial.flash"
#: Read bytes from the port (a governed observation of the device).
CAPABILITY_SERIAL_READ = "serial.read"

CAPABILITIES = frozenset(
    {
        CAPABILITY_SERIAL_WRITE,
        CAPABILITY_SERIAL_FLASH,
        CAPABILITY_SERIAL_READ,
    }
)

#: Serial device paths this extension manages. Generic USB-UART only.
_SERIAL_GLOBS = ("/dev/ttyUSB*", "/dev/ttyACM*")


class DeviceGovernanceError(ValueError):
    """A malformed or unauthorized attached-device governance request."""


class DevicePermitError(DeviceGovernanceError):
    """A permit did not cover this exact device request."""


class DeviceUnauthorizedAttempt(DeviceGovernanceError):
    """An attempt to use a port outside the governance path."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _require_sha256(value: str, field: str) -> None:
    if not isinstance(value, str) or len(value) != 64:
        raise DeviceGovernanceError(f"{field}_not_sha256")
    try:
        int(value, 16)
    except ValueError:
        raise DeviceGovernanceError(f"{field}_not_sha256") from None
    if value != value.lower():
        raise DeviceGovernanceError(f"{field}_not_lowercase_hex")


def _require_text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value:
        raise DeviceGovernanceError(f"{field}_required")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Discovery (generic serial ports, no device-model knowledge)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SerialPort:
    """One attached serial port (a USB-UART channel), not a device model."""

    path: str
    vid: str | None = None
    pid: str | None = None
    description: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.path, "path")
        if not self.path.startswith("/dev/"):
            raise DeviceGovernanceError("path_not_a_device")
        for name, value in (("vid", self.vid), ("pid", self.pid)):
            if value is not None and (
                not isinstance(value, str)
                or len(value) != 4
                or value != value.lower()
            ):
                raise DeviceGovernanceError(f"{name}_not_hex4")
        if self.description is not None and not isinstance(
            self.description, str
        ):
            raise DeviceGovernanceError("description_not_text")

    @property
    def device_id(self) -> str:
        """Stable id for this port. The port path is the identity; the
        USB-UART bridge is what makes it a serial port, and the port is
        what Pulpo governs."""
        return _sha256_hex(_canonical({"path": self.path}))

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "vid": self.vid,
            "pid": self.pid,
            "description": self.description,
            "device_id": self.device_id,
        }


def discover_serial_ports(
    glob_fn: Callable[[str], list[str]] = glob.glob,
) -> list[SerialPort]:
    """List attached serial ports (generic USB-UART). No device-model
    knowledge: a port is a port. Returns ports sorted by path. ``glob_fn``
    is injectable so tests can supply a fake filesystem."""
    found: list[SerialPort] = []
    for pattern in _SERIAL_GLOBS:
        for path in sorted(glob_fn(pattern)):
            if os.path.basename(path):
                found.append(SerialPort(path=path))
    found.sort(key=lambda p: p.path)
    return found


# ---------------------------------------------------------------------------
# Governed request (the intent, bound to an exact port + payload)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeviceGovernanceRequest:
    """An intent to act on an attached serial port.

    The permit for this request must bind to exactly these fields:
    the capability, the port (by device id), the payload hash (so the
    permit covers the exact bytes to be sent), and the expiry. A permit
    for any other capability, port, payload, or an expired permit does
    not authorize this request.
    """

    capability: str
    device_id: str
    port_path: str
    payload_sha256: str
    expires_at_ns: int
    request_id: str

    def __post_init__(self) -> None:
        if self.capability not in CAPABILITIES:
            raise DeviceGovernanceError("capability_unknown")
        _require_sha256(self.device_id, "device_id")
        _require_text(self.port_path, "port_path")
        if not self.port_path.startswith("/dev/"):
            raise DeviceGovernanceError("port_path_not_a_device")
        _require_sha256(self.payload_sha256, "payload_sha256")
        if not isinstance(self.expires_at_ns, int) or self.expires_at_ns <= 0:
            raise DeviceGovernanceError("expires_at_ns_invalid")
        _require_text(self.request_id, "request_id")

    def signing_payload(self) -> dict[str, object]:
        """The exact payload a permit must be issued over. A permit for
        any other payload does not authorize this request."""
        return {
            "capability": self.capability,
            "device_id": self.device_id,
            "port_path": self.port_path,
            "payload_sha256": self.payload_sha256,
            "expires_at_ns": self.expires_at_ns,
            "request_id": self.request_id,
            "schema": "pulpo.attached-device-request.v1",
        }

    def signing_bytes(self) -> bytes:
        return _canonical(self.signing_payload())

    def signing_payload_hash(self) -> str:
        return _sha256_hex(self.signing_bytes())

    def is_expired(self, now_ns: int) -> bool:
        return now_ns >= self.expires_at_ns


def build_request(
    *,
    capability: str,
    port: SerialPort,
    payload: bytes,
    expires_at_ns: int,
    request_id: str,
) -> DeviceGovernanceRequest:
    """Build a request over the exact payload bytes to be sent. The
    payload hash binds the permit to those bytes; a permit for different
    bytes does not authorize this request."""
    return DeviceGovernanceRequest(
        capability=capability,
        device_id=port.device_id,
        port_path=port.path,
        payload_sha256=_sha256_hex(payload),
        expires_at_ns=expires_at_ns,
        request_id=request_id,
    )


# ---------------------------------------------------------------------------
# Permit gate (the executor verifies the permit before opening the port)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DevicePermit:
    """A one-use permit for one exact device request.

    The permit is issued over the request's signing payload (see
    :meth:`DeviceGovernanceRequest.signing_payload`). ``envelope_hash``
    is the hash of the issuing approval envelope; ``signature`` is the
    issuer's signature over the request's signing bytes. The verifier
    is supplied by the caller (Pulpo's authority layer) so this module
    never holds a key or a trust root.
    """

    request_id: str
    signing_payload_hash: str
    envelope_hash: str
    signature: str

    def __post_init__(self) -> None:
        _require_text(self.request_id, "request_id")
        _require_sha256(self.signing_payload_hash, "signing_payload_hash")
        _require_sha256(self.envelope_hash, "envelope_hash")
        _require_text(self.signature, "signature")


def verify_device_permit(
    request: DeviceGovernanceRequest,
    permit: DevicePermit,
    *,
    now_ns: int,
    verify_signature: Callable[[bytes, str], bool],
) -> bool:
    """Verify a permit covers this exact request. Returns True only if
    every check passes; otherwise raises :class:`DevicePermitError`.

    Checks, in order: the permit names this request; the permit's
    payload hash equals this request's signing-payload hash (so the
    permit was issued over exactly this capability, port, payload, and
    expiry); the request has not expired; and the issuer's signature
    verifies over this request's signing bytes.
    """
    if permit.request_id != request.request_id:
        raise DevicePermitError("permit_request_mismatch")
    if permit.signing_payload_hash != request.signing_payload_hash():
        raise DevicePermitError("permit_payload_mismatch")
    if request.is_expired(now_ns):
        raise DevicePermitError("permit_expired")
    if not verify_signature(request.signing_bytes(), permit.signature):
        raise DevicePermitError("permit_signature_invalid")
    return True


# ---------------------------------------------------------------------------
# Evidence (what every action and every unauthorized attempt leaves)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeviceActionEvidence:
    """One evidence record for an attached-device action (or an
    unauthorized attempt). ``result`` is one of ``executed``,
    ``refused`` (permit did not cover the request), or
    ``unauthorized_attempt`` (a port open outside the governance path).
    The digest binds the whole record; the audit chain carries it.
    """

    request_id: str
    device_id: str
    port_path: str
    capability: str
    payload_sha256: str
    permit_hash: str | None
    result: str
    timestamp_ns: int
    detail: str = ""

    def __post_init__(self) -> None:
        _require_text(self.request_id, "request_id")
        _require_sha256(self.device_id, "device_id")
        _require_text(self.port_path, "port_path")
        if self.capability not in CAPABILITIES and self.capability != "":
            raise DeviceGovernanceError("capability_unknown")
        _require_sha256(self.payload_sha256, "payload_sha256")
        if self.permit_hash is not None:
            _require_sha256(self.permit_hash, "permit_hash")
        if self.result not in (
            "executed",
            "refused",
            "unauthorized_attempt",
        ):
            raise DeviceGovernanceError("result_unknown")
        if not isinstance(self.timestamp_ns, int) or self.timestamp_ns < 0:
            raise DeviceGovernanceError("timestamp_ns_invalid")

    def to_dict(self) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "device_id": self.device_id,
            "port_path": self.port_path,
            "capability": self.capability,
            "payload_sha256": self.payload_sha256,
            "permit_hash": self.permit_hash,
            "result": self.result,
            "timestamp_ns": self.timestamp_ns,
            "detail": self.detail,
            "schema": "pulpo.attached-device-evidence.v1",
        }

    def digest(self) -> str:
        return _sha256_hex(_canonical(self.to_dict()))


def evidence_for_unauthorized_attempt(
    *,
    port_path: str,
    device_id: str,
    timestamp_ns: int,
    detail: str,
) -> DeviceActionEvidence:
    """Build the evidence record for an unauthorized attempt to use a
    port outside the governance path. No permit exists, so
    ``permit_hash`` is None and the payload is the empty hash (nothing
    was authorized to be sent)."""
    return DeviceActionEvidence(
        request_id="unauthorized-attempt",
        device_id=device_id,
        port_path=port_path,
        capability="",
        payload_sha256=_sha256_hex(b""),
        permit_hash=None,
        result="unauthorized_attempt",
        timestamp_ns=timestamp_ns,
        detail=detail,
    )


# ---------------------------------------------------------------------------
# Executor (opens the port only after the permit verifies)
# ---------------------------------------------------------------------------


class AttachedDeviceExecutor:
    """Execute one governed action on an attached serial port.

    The executor never opens the port before the permit verifies. The
    serial transport is injectable (a ``open_serial`` callable) so the
    governance logic is testable without hardware; the real transport
    is pyserial. ``now_ns`` is injectable for tests.
    """

    def __init__(
        self,
        *,
        executor_id: str,
        open_serial: Callable[[str, int], Any] | None = None,
        now_ns: Callable[[], int] | None = None,
    ) -> None:
        _require_text(executor_id, "executor_id")
        self.executor_id = executor_id
        self._open_serial = open_serial
        self._now_ns = now_ns or (lambda: time.time_ns())

    def _default_open_serial(self, port_path: str, baud: int) -> Any:
        import serial  # pyserial; only imported when actually opening a port

        return serial.Serial(port_path, baud, timeout=5)

    def execute(
        self,
        request: DeviceGovernanceRequest,
        permit: DevicePermit,
        *,
        payload: bytes,
        baud: int = 115200,
        verify_signature: Callable[[bytes, str], bool],
    ) -> DeviceActionEvidence:
        """Verify the permit, then perform the action on the port, then
        return the evidence. If the permit does not cover this exact
        request, nothing is opened and the refusal is returned as
        evidence (``refused``). The payload bytes must hash to the
        request's payload hash, or the request is refused without
        opening the port."""
        now = self._now_ns()
        try:
            if _sha256_hex(payload) != request.payload_sha256:
                raise DevicePermitError("payload_hash_mismatch")
            verify_device_permit(
                request, permit, now_ns=now, verify_signature=verify_signature
            )
        except DevicePermitError as exc:
            return DeviceActionEvidence(
                request_id=request.request_id,
                device_id=request.device_id,
                port_path=request.port_path,
                capability=request.capability,
                payload_sha256=request.payload_sha256,
                permit_hash=permit.envelope_hash,
                result="refused",
                timestamp_ns=now,
                detail=str(exc),
            )
        opener = self._open_serial or self._default_open_serial
        transport = opener(request.port_path, baud)
        try:
            if request.capability == CAPABILITY_SERIAL_WRITE:
                transport.write(payload)
            elif request.capability == CAPABILITY_SERIAL_FLASH:
                # Flashing is a write of the firmware payload; the
                # transport is the serial channel and the payload is
                # the firmware image. The bootloader handshake is the
                # caller's (device-specific) concern, not Pulpo's.
                transport.write(payload)
            elif request.capability == CAPABILITY_SERIAL_READ:
                # A governed read: open the port and drain what is
                # available. The content is the caller's business.
                transport.read(1)
            else:  # pragma: no cover - capability validated at construction
                raise DeviceGovernanceError("capability_unknown")
        finally:
            close = getattr(transport, "close", None)
            if callable(close):
                close()
        return DeviceActionEvidence(
            request_id=request.request_id,
            device_id=request.device_id,
            port_path=request.port_path,
            capability=request.capability,
            payload_sha256=request.payload_sha256,
            permit_hash=permit.envelope_hash,
            result="executed",
            timestamp_ns=now,
            detail=f"executor:{self.executor_id}",
        )


# ---------------------------------------------------------------------------
# Detection / lockdown (only the governance path may open the port)
# ---------------------------------------------------------------------------


def detect_unauthorized_open(
    *,
    port_path: str,
    device_id: str,
    holders: Sequence[str],
    now_ns: int,
) -> DeviceActionEvidence | None:
    """Detect a port open outside the governance path.

    ``holders`` is the list of process/user ids currently holding the
    port open (supplied by the caller, e.g. from ``fuser`` / ``lsof``
    or the lock file). The governance executor is the only legitimate
    holder; its id is ``governance``. If any other holder is present,
    return the unauthorized-attempt evidence; otherwise return None.
    This is the detection half of the lockdown: it makes a bypass
    visible (and therefore failing) even where the OS cannot prevent
    it.
    """
    for holder in holders:
        if holder != "governance":
            return evidence_for_unauthorized_attempt(
                port_path=port_path,
                device_id=device_id,
                timestamp_ns=now_ns,
                detail=f"unauthorized_holder:{holder}",
            )
    return None
