"""Tests for the attached-device governance extension (generic USB-UART)."""

from __future__ import annotations

import hashlib
import unittest

from pulpo.attached_devices import (
    CAPABILITY_SERIAL_FLASH,
    CAPABILITY_SERIAL_READ,
    CAPABILITY_SERIAL_WRITE,
    AttachedDeviceExecutor,
    DeviceActionEvidence,
    DeviceGovernanceError,
    DeviceGovernanceRequest,
    DevicePermit,
    DevicePermitError,
    SerialPort,
    build_request,
    detect_unauthorized_open,
    discover_serial_ports,
    evidence_for_unauthorized_attempt,
    verify_device_permit,
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


_GOOD_SIG = "sig-good"
_NOW_NS = 1_700_000_000_000_000_000


def _verifier(expected_sig: str):
    def _verify(payload: bytes, signature: str) -> bool:
        return signature == expected_sig

    return _verify


def _port(path: str = "/dev/ttyUSB0") -> SerialPort:
    return SerialPort(path=path, vid="10c4", pid="ea60")


def _request(**overrides) -> DeviceGovernanceRequest:
    port = _port()
    payload = b"AT\r\n"
    base = {
        "capability": CAPABILITY_SERIAL_WRITE,
        "device_id": port.device_id,
        "port_path": port.path,
        "payload_sha256": _sha256(payload),
        "expires_at_ns": _NOW_NS + 60_000_000_000,
        "request_id": "req-1",
    }
    base.update(overrides)
    return DeviceGovernanceRequest(**base)


def _permit(request: DeviceGovernanceRequest, sig: str = _GOOD_SIG) -> DevicePermit:
    return DevicePermit(
        request_id=request.request_id,
        signing_payload_hash=request.signing_payload_hash(),
        envelope_hash=_sha256(b"envelope"),
        signature=sig,
    )


class FakeSerial:
    """A fake pyserial port: records writes, never touches hardware."""

    def __init__(self) -> None:
        self.written: list[bytes] = []
        self.closed = False
        self.opened = True

    def write(self, data: bytes) -> int:
        self.written.append(data)
        return len(data)

    def read(self, n: int) -> bytes:
        return b""

    def close(self) -> None:
        self.closed = True


class DiscoveryTests(unittest.TestCase):
    def test_discovers_sorted_ports(self):
        def fake_glob(pattern: str) -> list[str]:
            if "ttyUSB" in pattern:
                return ["/dev/ttyUSB1", "/dev/ttyUSB0"]
            return ["/dev/ttyACM0"]

        ports = discover_serial_ports(glob_fn=fake_glob)
        self.assertEqual(
            [p.path for p in ports],
            ["/dev/ttyACM0", "/dev/ttyUSB0", "/dev/ttyUSB1"],
        )

    def test_discovers_nothing_when_empty(self):
        self.assertEqual(discover_serial_ports(glob_fn=lambda p: []), [])

    def test_port_rejects_non_device_path(self):
        with self.assertRaises(DeviceGovernanceError):
            SerialPort(path="ttyUSB0")

    def test_port_rejects_bad_vid(self):
        with self.assertRaises(DeviceGovernanceError):
            SerialPort(path="/dev/ttyUSB0", vid="XYZ")

    def test_device_id_is_stable(self):
        self.assertEqual(_port().device_id, _port().device_id)
        self.assertNotEqual(_port("/dev/ttyUSB0").device_id, _port("/dev/ttyUSB1").device_id)


class RequestTests(unittest.TestCase):
    def test_build_request_binds_payload_hash(self):
        port = _port()
        req = build_request(
            capability=CAPABILITY_SERIAL_WRITE,
            port=port,
            payload=b"AT\r\n",
            expires_at_ns=_NOW_NS + 1000,
            request_id="req-1",
        )
        self.assertEqual(req.payload_sha256, _sha256(b"AT\r\n"))
        self.assertEqual(req.device_id, port.device_id)

    def test_rejects_unknown_capability(self):
        with self.assertRaises(DeviceGovernanceError):
            _request(capability="serial.teleport")

    def test_rejects_bad_hash(self):
        with self.assertRaises(DeviceGovernanceError):
            _request(payload_sha256="not-a-hash")

    def test_rejects_bad_expiry(self):
        with self.assertRaises(DeviceGovernanceError):
            _request(expires_at_ns=0)

    def test_signing_payload_is_stable(self):
        self.assertEqual(
            _request().signing_payload_hash(), _request().signing_payload_hash()
        )

    def test_is_expired(self):
        req = _request()
        self.assertFalse(req.is_expired(_NOW_NS))
        self.assertTrue(req.is_expired(req.expires_at_ns))


class PermitTests(unittest.TestCase):
    def test_valid_permit_verifies(self):
        req = _request()
        self.assertTrue(
            verify_device_permit(
                req,
                _permit(req),
                now_ns=_NOW_NS,
                verify_signature=_verifier(_GOOD_SIG),
            )
        )

    def test_wrong_request_id_refused(self):
        req = _request()
        permit = _permit(req)
        other = _request(request_id="req-2")
        with self.assertRaises(DevicePermitError):
            verify_device_permit(
                other, permit, now_ns=_NOW_NS, verify_signature=_verifier(_GOOD_SIG)
            )

    def test_wrong_payload_refused(self):
        req = _request()
        permit = _permit(req)
        other = _request(payload_sha256=_sha256(b"OTHER"))
        with self.assertRaises(DevicePermitError):
            verify_device_permit(
                other, permit, now_ns=_NOW_NS, verify_signature=_verifier(_GOOD_SIG)
            )

    def test_expired_refused(self):
        req = _request()
        with self.assertRaises(DevicePermitError):
            verify_device_permit(
                req,
                _permit(req),
                now_ns=req.expires_at_ns,
                verify_signature=_verifier(_GOOD_SIG),
            )

    def test_bad_signature_refused(self):
        req = _request()
        with self.assertRaises(DevicePermitError):
            verify_device_permit(
                req,
                _permit(req, sig="sig-forged"),
                now_ns=_NOW_NS,
                verify_signature=_verifier(_GOOD_SIG),
            )


class ExecutorTests(unittest.TestCase):
    def test_refused_permit_never_opens_port(self):
        req = _request()
        opened: list[str] = []

        def opener(path: str, baud: int):
            opened.append(path)
            return FakeSerial()

        ex = AttachedDeviceExecutor(
            executor_id="gov-1", open_serial=opener, now_ns=lambda: _NOW_NS
        )
        ev = ex.execute(
            req,
            _permit(req, sig="sig-forged"),
            payload=b"AT\r\n",
            verify_signature=_verifier(_GOOD_SIG),
        )
        self.assertEqual(ev.result, "refused")
        self.assertEqual(opened, [])

    def test_payload_mismatch_never_opens_port(self):
        req = _request()
        opened: list[str] = []

        def opener(path: str, baud: int):
            opened.append(path)
            return FakeSerial()

        ex = AttachedDeviceExecutor(
            executor_id="gov-1", open_serial=opener, now_ns=lambda: _NOW_NS
        )
        ev = ex.execute(
            req,
            _permit(req),
            payload=b"DIFFERENT",
            verify_signature=_verifier(_GOOD_SIG),
        )
        self.assertEqual(ev.result, "refused")
        self.assertEqual(opened, [])

    def test_valid_permit_writes_and_evidences(self):
        req = _request()
        fake = FakeSerial()
        ex = AttachedDeviceExecutor(
            executor_id="gov-1",
            open_serial=lambda p, b: fake,
            now_ns=lambda: _NOW_NS,
        )
        ev = ex.execute(
            req,
            _permit(req),
            payload=b"AT\r\n",
            verify_signature=_verifier(_GOOD_SIG),
        )
        self.assertEqual(ev.result, "executed")
        self.assertEqual(fake.written, [b"AT\r\n"])
        self.assertTrue(fake.closed)
        self.assertEqual(ev.permit_hash, _permit(req).envelope_hash)

    def test_flash_and_read_capabilities_execute(self):
        for cap in (CAPABILITY_SERIAL_FLASH, CAPABILITY_SERIAL_READ):
            req = _request(capability=cap)
            fake = FakeSerial()
            ex = AttachedDeviceExecutor(
                executor_id="gov-1",
                open_serial=lambda p, b: fake,
                now_ns=lambda: _NOW_NS,
            )
            ev = ex.execute(
                req,
                _permit(req),
                payload=b"AT\r\n",
                verify_signature=_verifier(_GOOD_SIG),
            )
            self.assertEqual(ev.result, "executed", cap)


class EvidenceTests(unittest.TestCase):
    def test_digest_is_deterministic(self):
        req = _request()
        ev1 = DeviceActionEvidence(
            request_id=req.request_id,
            device_id=req.device_id,
            port_path=req.port_path,
            capability=req.capability,
            payload_sha256=req.payload_sha256,
            permit_hash=_permit(req).envelope_hash,
            result="executed",
            timestamp_ns=_NOW_NS,
        )
        ev2 = DeviceActionEvidence(
            request_id=req.request_id,
            device_id=req.device_id,
            port_path=req.port_path,
            capability=req.capability,
            payload_sha256=req.payload_sha256,
            permit_hash=_permit(req).envelope_hash,
            result="executed",
            timestamp_ns=_NOW_NS,
        )
        self.assertEqual(ev1.digest(), ev2.digest())

    def test_rejects_unknown_result(self):
        req = _request()
        with self.assertRaises(DeviceGovernanceError):
            DeviceActionEvidence(
                request_id=req.request_id,
                device_id=req.device_id,
                port_path=req.port_path,
                capability=req.capability,
                payload_sha256=req.payload_sha256,
                permit_hash=None,
                result="maybe",
                timestamp_ns=_NOW_NS,
            )

    def test_unauthorized_attempt_evidence(self):
        ev = evidence_for_unauthorized_attempt(
            port_path="/dev/ttyUSB0",
            device_id=_port().device_id,
            timestamp_ns=_NOW_NS,
            detail="unauthorized_holder:1234",
        )
        self.assertEqual(ev.result, "unauthorized_attempt")
        self.assertIsNone(ev.permit_hash)
        self.assertEqual(ev.payload_sha256, _sha256(b""))


class DetectionTests(unittest.TestCase):
    def test_governance_holder_is_clean(self):
        self.assertIsNone(
            detect_unauthorized_open(
                port_path="/dev/ttyUSB0",
                device_id=_port().device_id,
                holders=["governance"],
                now_ns=_NOW_NS,
            )
        )

    def test_empty_holders_is_clean(self):
        self.assertIsNone(
            detect_unauthorized_open(
                port_path="/dev/ttyUSB0",
                device_id=_port().device_id,
                holders=[],
                now_ns=_NOW_NS,
            )
        )

    def test_foreign_holder_is_evidence(self):
        ev = detect_unauthorized_open(
            port_path="/dev/ttyUSB0",
            device_id=_port().device_id,
            holders=["governance", "user:4321"],
            now_ns=_NOW_NS,
        )
        self.assertIsNotNone(ev)
        assert ev is not None
        self.assertEqual(ev.result, "unauthorized_attempt")
        self.assertIn("user:4321", ev.detail)


if __name__ == "__main__":
    unittest.main()
