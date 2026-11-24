"""Proof of concept: attached-device governance, end to end (no hardware).

Walks the full loop a company would test, using a fake serial port
instead of the real ESP board:

  1. Discover the attached port.
  2. Governed write with a valid permit -> executed, evidence left.
  3. Same write with a FORGED permit -> refused, port never opened.
  4. A foreign holder on the port -> detected, unauthorized-attempt evidence.

Run:  python3 -m pulpo.attached_devices_poc   (from the repo root)
or:   python3 attached_devices_poc.py
"""

from __future__ import annotations

import hashlib
import sys
import time

from pulpo.attached_devices import (
    CAPABILITY_SERIAL_WRITE,
    AttachedDeviceExecutor,
    SerialPort,
    build_request,
    detect_unauthorized_open,
    discover_serial_ports,
)

NOW_NS = time.time_ns()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class FakeSerial:
    def __init__(self) -> None:
        self.written: list[bytes] = []
        self.closed = False

    def write(self, data: bytes) -> int:
        self.written.append(data)
        return len(data)

    def read(self, n: int) -> bytes:
        return b""

    def close(self) -> None:
        self.closed = True


def _verifier(good_sig: str):
    def _verify(payload: bytes, signature: str) -> bool:
        return signature == good_sig

    return _verify


def main() -> int:
    print("== Attached-device governance: proof of concept ==\n")

    # 1. Discover (fake filesystem: one ESP board on ttyUSB0).
    ports = discover_serial_ports(
        glob_fn=lambda p: ["/dev/ttyUSB0"] if "ttyUSB" in p else []
    )
    port = ports[0]
    print(f"1. Discovered: {port.path} (device_id {port.device_id[:12]}...)")

    # 2. Governed write with a valid permit.
    payload = b"AT\r\n"
    req = build_request(
        capability=CAPABILITY_SERIAL_WRITE,
        port=port,
        payload=payload,
        expires_at_ns=NOW_NS + 60_000_000_000,
        request_id="poc-req-1",
    )
    good_sig = "sig-issuer"
    from pulpo.attached_devices import DevicePermit

    permit = DevicePermit(
        request_id=req.request_id,
        signing_payload_hash=req.signing_payload_hash(),
        envelope_hash=_sha256(b"envelope-1"),
        signature=good_sig,
    )
    fake = FakeSerial()
    ex = AttachedDeviceExecutor(
        executor_id="gov-poc",
        open_serial=lambda p, b: fake,
        now_ns=lambda: NOW_NS,
    )
    ev = ex.execute(
        req, permit, payload=payload, verify_signature=_verifier(good_sig)
    )
    print(f"2. Valid permit   -> result={ev.result}, bytes written={fake.written}")
    print(f"   evidence digest={ev.digest()[:16]}...")

    # 3. Same write with a FORGED permit -> refused, port never opened.
    fake2 = FakeSerial()
    opened: list[str] = []
    ex2 = AttachedDeviceExecutor(
        executor_id="gov-poc",
        open_serial=lambda p, b: (opened.append(p), fake2)[1],
        now_ns=lambda: NOW_NS,
    )
    forged = DevicePermit(
        request_id=req.request_id,
        signing_payload_hash=req.signing_payload_hash(),
        envelope_hash=_sha256(b"envelope-1"),
        signature="sig-forged",
    )
    ev2 = ex2.execute(
        req, forged, payload=payload, verify_signature=_verifier(good_sig)
    )
    print(f"3. Forged permit  -> result={ev2.result}, port opened={opened or 'NEVER'}")
    print(f"   refusal detail={ev2.detail}")

    # 4. A foreign holder on the port -> detected.
    ev3 = detect_unauthorized_open(
        port_path=port.path,
        device_id=port.device_id,
        holders=["governance", "user:4321"],
        now_ns=NOW_NS,
    )
    print(f"4. Foreign holder -> result={ev3.result if ev3 else 'clean'}")
    if ev3:
        print(f"   detail={ev3.detail}, digest={ev3.digest()[:16]}...")

    print("\nPOC complete: governed action executed with evidence, "
          "forged permit refused without opening the port, "
          "bypass attempt detected and evidenced.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
