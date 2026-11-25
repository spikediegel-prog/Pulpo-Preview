import unittest

from pulpo import GovernanceKernel, Policy
from pulpo.serial_device import (
    GovernedSerialWriter,
    SerialWrite,
    SerialWriteRejected,
)
from tests.authority_support import HmacTestVerifier, signed_envelope, trust_for, signed_policy_envelope


NOW = 7_100_000
SESSION = "serial-write-governed-proof-1"
PRINCIPAL = "agent:assistant"
PORT = "/dev/ttyUSB0"
PAYLOAD = b"AT\r\n"
BAUD = 115200
REPLY = b"# AT\r\nERROR: command \"AT\" not found :(\r\n"


class FakeSerialTransport:
    def __init__(self, *, port: str = PORT) -> None:
        self.expected_port = port
        self.opens = 0
        self.writes: list[bytes] = []

    def write(self, write: SerialWrite) -> bytes:
        self.opens += 1
        self.writes.append(write.payload)
        return REPLY


class SerialWriteGovernedTests(unittest.TestCase):
    """Software-only proof that the serial write gate requires an exact permit."""

    def setUp(self):
        self.verifier = HmacTestVerifier()
        self.policy = Policy(
            frozenset({"serial_write"}),
            0,
            frozenset({"serial_write"}),
            authority_trust=trust_for(self.verifier),
        )
        self.kernel = GovernanceKernel(
            self.policy,
            secret=b"serial-write-governed-proof-secret",
            approval_verifier=self.verifier, policy_envelope=signed_policy_envelope(self.policy, self.verifier),
            clock=lambda: NOW,
        )
        self.write = SerialWrite(PORT, PAYLOAD, BAUD)
        self.transport = FakeSerialTransport()
        self.writer = GovernedSerialWriter(self.kernel, self.transport)

    def _approve(
        self,
        write: SerialWrite | None = None,
        *,
        approval_id: str = "approval-serial-write-1",
        nonce: str = "approval-serial-write-nonce-1",
    ):
        target = self.write if write is None else write
        intent = target.intent(principal=PRINCIPAL, session_id=SESSION)
        envelope = signed_envelope(
            self.kernel,
            intent,
            self.verifier,
            now_ns=NOW,
            approval_id=approval_id,
            nonce=nonce,
        )
        return self.kernel.evaluate_with_approval(intent, envelope)

    def test_exact_permit_allows_one_write_and_consumes_it(self):
        decision = self._approve()
        self.assertEqual("allow", decision.outcome)
        reply = self.writer.execute(
            self.write,
            permit=decision.permit,
            principal=PRINCIPAL,
            session_id=SESSION,
        )
        self.assertEqual(REPLY, reply)
        self.assertEqual(1, self.transport.opens)
        self.assertEqual([PAYLOAD], self.transport.writes)

        with self.assertRaisesRegex(SerialWriteRejected, "permit rejected"):
            self.writer.execute(
                self.write,
                permit=decision.permit,
                principal=PRINCIPAL,
                session_id=SESSION,
            )
        self.assertEqual(1, self.transport.opens)

    def test_rejected_missing_or_consumed_permit_never_opens_port(self):
        with self.assertRaisesRegex(SerialWriteRejected, "permit missing"):
            self.writer.execute(
                self.write,
                permit="",
                principal=PRINCIPAL,
                session_id=SESSION,
            )
        self.assertEqual(0, self.transport.opens)

        other = SerialWrite(PORT, b"OTHER\r\n", BAUD)
        other_decision = self._approve(
            other,
            approval_id="approval-serial-write-other-1",
            nonce="approval-serial-write-other-nonce-1",
        )
        with self.assertRaisesRegex(SerialWriteRejected, "permit rejected"):
            self.writer.execute(
                self.write,
                permit=other_decision.permit,
                principal=PRINCIPAL,
                session_id=SESSION,
            )
        self.assertEqual(0, self.transport.opens)

        decision = self._approve()
        self.writer.execute(
            self.write,
            permit=decision.permit,
            principal=PRINCIPAL,
            session_id=SESSION,
        )
        self.assertEqual(1, self.transport.opens)
        with self.assertRaisesRegex(SerialWriteRejected, "permit rejected"):
            self.writer.execute(
                self.write,
                permit=decision.permit,
                principal=PRINCIPAL,
                session_id=SESSION,
            )
        self.assertEqual(1, self.transport.opens)

    def test_permit_for_one_port_does_not_authorise_another(self):
        decision = self._approve()
        other_port = SerialWrite("/dev/ttyUSB1", PAYLOAD, BAUD)
        transport = FakeSerialTransport(port="/dev/ttyUSB1")
        writer = GovernedSerialWriter(self.kernel, transport)
        with self.assertRaisesRegex(SerialWriteRejected, "permit rejected"):
            writer.execute(
                other_port,
                permit=decision.permit,
                principal=PRINCIPAL,
                session_id=SESSION,
            )
        self.assertEqual(0, transport.opens)

    def test_changed_payload_byte_rejects_old_permit(self):
        decision = self._approve()
        changed = SerialWrite(PORT, b"AT\rX", BAUD)
        with self.assertRaisesRegex(SerialWriteRejected, "permit rejected"):
            self.writer.execute(
                changed,
                permit=decision.permit,
                principal=PRINCIPAL,
                session_id=SESSION,
            )
        self.assertEqual(0, self.transport.opens)

    def test_reply_captured_and_execution_recorded_in_audit_chain(self):
        decision = self._approve()
        reply = self.writer.execute(
            self.write,
            permit=decision.permit,
            principal=PRINCIPAL,
            session_id=SESSION,
        )
        self.assertEqual(REPLY, reply)
        self.assertEqual([PAYLOAD], self.transport.writes)
        intent_hash = self.kernel.intent_hash(
            self.write.intent(principal=PRINCIPAL, session_id=SESSION)
        )
        consumed = [
            record
            for record in self.kernel.audit
            if record.get("event") == "permit_consumed"
            and record.get("payload", {}).get("intent_hash") == intent_hash
        ]
        self.assertEqual(1, len(consumed))


if __name__ == "__main__":
    unittest.main()
