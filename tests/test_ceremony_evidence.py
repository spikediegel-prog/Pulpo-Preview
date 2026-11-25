"""Kernel-enforced ceremony evidence; test signers are synthetic only."""

from contextlib import closing
from dataclasses import asdict, replace
import hashlib
import hmac
import importlib.util
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from pulpo import (
    ApprovalEnvelope,
    AuthorityClient,
    CeremonyEvidence,
    CeremonyTrust,
    Ed25519CeremonyVerifier,
    GovernanceKernel,
    Intent,
    P256CeremonyVerifier,
    Policy,
    SQLiteKernelState,
)
from pulpo.orchestrator import PulpoOrchestrator
from tests.authority_support import HmacTestVerifier, signed_envelope, trust_for, signed_policy_envelope


NOW = 1_000_000


class HmacCeremonyTestVerifier:
    """Same-process synthetic test double; not a human ceremony signer."""

    authority_id = "ceremony:test-owner"
    verifier_id = "ceremony-verifier:test-only"
    key_id = "ceremony-key:test-only:v1"
    algorithm = "hmac-sha256-test-only"
    key_fingerprint = hashlib.sha256(b"synthetic-ceremony-test-key").hexdigest()

    def __init__(self):
        self._secret = b"synthetic-test-only-ceremony-secret"

    def sign(self, payload):
        return hmac.new(self._secret, payload, hashlib.sha256).hexdigest()

    def verify(self, payload, signature):
        return hmac.compare_digest(self.sign(payload), signature)


class CeremonyEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.clock = [NOW]
        self.approval_verifier = HmacTestVerifier()
        self.ceremony_verifier = HmacCeremonyTestVerifier()
        self.ceremony_trust = CeremonyTrust(
            authority_id=self.ceremony_verifier.authority_id,
            verifier_id=self.ceremony_verifier.verifier_id,
            key_id=self.ceremony_verifier.key_id,
            algorithm=self.ceremony_verifier.algorithm,
            key_fingerprint=self.ceremony_verifier.key_fingerprint,
            method="synthetic-test-ceremony",
            max_evidence_ttl_ns=500,
        )
        self.policy = Policy(
            frozenset({"read", "push"}),
            100,
            frozenset({"push"}),
            authority_trust=trust_for(self.approval_verifier),
            ceremony_actions=frozenset({"push"}),
            ceremony_trust=self.ceremony_trust,
        )
        self.kernel = self.make_kernel()
        self.intent = Intent("agent:publisher", "push", "repo:origin/main", 0, "session:ceremony")

    def make_kernel(self, state=None, *, policy=None, ceremony_verifier=None):
        configured_policy = policy or self.policy
        if ceremony_verifier is None and configured_policy.ceremony_trust is not None:
            ceremony_verifier = self.ceremony_verifier
        return GovernanceKernel(
            configured_policy,
            secret=b"ceremony-proof-permit-secret",
            approval_verifier=self.approval_verifier, policy_envelope=signed_policy_envelope(configured_policy, self.approval_verifier),
            ceremony_verifier=ceremony_verifier,
            clock=lambda: self.clock[0],
            state=state,
        )

    def envelope(self, *, approval_id="approval-ceremony-1", nonce="approval-nonce-1",
                 issued_at_ns=NOW, ttl_ns=400):
        return signed_envelope(
            self.kernel,
            self.intent,
            self.approval_verifier,
            now_ns=issued_at_ns,
            ttl_ns=ttl_ns,
            approval_id=approval_id,
            nonce=nonce,
        )

    def evidence(self, envelope, *, evidence_id="ceremony-evidence-1",
                 issued_at_ns=NOW, expires_at_ns=NOW + 200, **changes):
        trust = self.kernel.policy.ceremony_trust
        values = {
            "evidence_id": evidence_id,
            "authority_id": trust.authority_id,
            "verifier_id": trust.verifier_id,
            "key_id": trust.key_id,
            "method": trust.method,
            "trust_hash": trust.trust_hash,
            "approval_id": envelope.approval_id,
            "envelope_hash": envelope.envelope_hash,
            "intent_hash": self.kernel.intent_hash(self.intent),
            "policy_hash": self.kernel.policy_hash,
            "principal": self.intent.principal,
            "session_id": self.intent.session_id,
            "approval_nonce": envelope.nonce,
            "issued_at_ns": issued_at_ns,
            "expires_at_ns": expires_at_ns,
            "signature": "",
        }
        values.update(changes)
        unsigned = CeremonyEvidence(**values)
        return replace(unsigned, signature=self.ceremony_verifier.sign(unsigned.signing_bytes()))

    def evaluate(self, envelope=None, evidence=None):
        envelope = envelope or self.envelope()
        return self.kernel.evaluate_with_approval(
            self.intent, envelope, ceremony_evidence=evidence
        )

    def test_missing_ceremony_denies_even_with_valid_approval_signature(self):
        decision = self.evaluate(evidence=None)
        self.assertEqual(("deny", "ceremony_evidence_missing"), (decision.outcome, decision.reason))
        self.assertIsNone(decision.permit)
        self.assertFalse(any(record["event"] == "approval_verified" for record in self.kernel.audit))

    def test_exact_ceremony_evidence_is_bound_and_recorded(self):
        envelope = self.envelope()
        evidence = self.evidence(envelope)
        decision = self.evaluate(envelope, evidence)
        self.assertEqual(("allow", "verified_approval"), (decision.outcome, decision.reason))
        self.assertTrue(self.kernel.consume(decision.permit, self.intent))
        verified = next(
            record["payload"] for record in self.kernel.audit
            if record["event"] == "approval_verified"
        )
        self.assertEqual(evidence.evidence_id, verified["ceremony_evidence_id"])
        self.assertEqual(evidence.evidence_hash, verified["ceremony_evidence_hash"])
        self.assertEqual(evidence.signing_payload_hash, verified["ceremony_signing_payload_hash"])
        self.assertEqual(self.ceremony_trust.key_fingerprint, verified["ceremony_key_fingerprint"])
        self.assertEqual("synthetic-test-ceremony", verified["ceremony_method"])

    def test_authority_poll_and_orchestrator_forward_ceremony_evidence(self):
        envelope = self.envelope()
        evidence = self.evidence(envelope)

        def transport(method, path, body):
            if method == "POST":
                return {
                    "request_id": "request:ceremony",
                    "approval_url": "https://authority.example.com/approval/request:ceremony",
                }
            return {
                "status": "approved",
                "envelope": asdict(envelope),
                "ceremony_evidence": asdict(evidence),
            }

        client = AuthorityClient("https://authority.example.com", transport=transport)
        orchestrator = PulpoOrchestrator(self.kernel, authority_client=client)
        target = orchestrator.lock_target("target:ceremony", self.intent)
        handle = orchestrator.request_target_approval(target, requested_ttl_ns=300)
        attempt = orchestrator.authorize_target(handle)

        self.assertEqual(evidence, attempt.poll.ceremony_evidence)
        self.assertEqual(("allow", "verified_approval"), (
            attempt.decision.outcome, attempt.decision.reason
        ))

    def test_ceremony_context_substitution_is_rejected(self):
        envelope = self.envelope()
        cases = (
            ({"authority_id": "ceremony:other"}, "ceremony_authority_mismatch"),
            ({"verifier_id": "ceremony-verifier:other"}, "ceremony_verifier_mismatch"),
            ({"key_id": "ceremony-key:other"}, "ceremony_key_mismatch"),
            ({"method": "other-ceremony"}, "ceremony_method_mismatch"),
            ({"trust_hash": "a" * 64}, "ceremony_trust_mismatch"),
            ({"approval_id": "approval-other"}, "ceremony_approval_mismatch"),
            ({"envelope_hash": "b" * 64}, "ceremony_envelope_mismatch"),
            ({"intent_hash": "c" * 64}, "ceremony_intent_mismatch"),
            ({"policy_hash": "d" * 64}, "ceremony_policy_mismatch"),
            ({"principal": "agent:other"}, "ceremony_principal_mismatch"),
            ({"session_id": "session:other"}, "ceremony_session_mismatch"),
            ({"approval_nonce": "nonce-other"}, "ceremony_nonce_mismatch"),
        )
        for changes, expected in cases:
            with self.subTest(expected=expected):
                evidence = self.evidence(envelope, **changes)
                decision = self.evaluate(envelope, evidence)
                self.assertEqual(("deny", expected), (decision.outcome, decision.reason))
                self.assertIsNone(decision.permit)

    def test_forged_and_missing_signatures_fail_closed(self):
        envelope = self.envelope()
        evidence = self.evidence(envelope)
        forged = replace(evidence, signature="00" * 32)
        missing = replace(evidence, signature="")
        self.assertEqual("ceremony_signature_invalid", self.evaluate(envelope, forged).reason)
        self.assertEqual("ceremony_signature_missing", self.evaluate(envelope, missing).reason)

    def test_expired_future_and_overlong_ceremony_evidence_are_denied(self):
        expired_envelope = self.envelope(issued_at_ns=NOW - 100, ttl_ns=400)
        expired = self.evidence(
            expired_envelope, issued_at_ns=NOW - 50, expires_at_ns=NOW
        )
        self.assertEqual("ceremony_expired", self.evaluate(expired_envelope, expired).reason)

        future_envelope = self.envelope()
        future = self.evidence(
            future_envelope, issued_at_ns=NOW + 1, expires_at_ns=NOW + 100
        )
        self.assertEqual(
            "ceremony_not_yet_valid", self.evaluate(future_envelope, future).reason
        )

        long_envelope = self.envelope(issued_at_ns=NOW - 400, ttl_ns=800)
        overlong = self.evidence(
            long_envelope, issued_at_ns=NOW - 400, expires_at_ns=NOW + 200
        )
        self.assertEqual(
            "ceremony_ttl_exceeded", self.evaluate(long_envelope, overlong).reason
        )

    def test_ceremony_evidence_cannot_precede_approval_envelope(self):
        envelope = self.envelope(issued_at_ns=NOW - 100, ttl_ns=400)
        evidence = self.evidence(
            envelope, issued_at_ns=NOW - 101, expires_at_ns=NOW + 100
        )
        self.assertEqual(
            "ceremony_precedes_approval", self.evaluate(envelope, evidence).reason
        )

    def test_expiry_during_ceremony_verification_denies(self):
        envelope = self.envelope(ttl_ns=100)
        evidence = self.evidence(envelope, expires_at_ns=NOW + 50)
        original_verify = self.ceremony_verifier.verify

        def verify_then_advance(payload, signature):
            valid = original_verify(payload, signature)
            self.clock[0] = NOW + 50
            return valid

        self.ceremony_verifier.verify = verify_then_advance
        decision = self.evaluate(envelope, evidence)
        self.assertEqual("ceremony_expired_during_verification", decision.reason)
        self.assertIsNone(decision.permit)

    def test_verifier_unavailable_and_untrusted_fail_closed(self):
        kernel = GovernanceKernel(
            self.policy,
            secret=b"ceremony-proof-permit-secret",
            approval_verifier=self.approval_verifier, policy_envelope=signed_policy_envelope(self.policy, self.approval_verifier),
            ceremony_verifier=None,
            clock=lambda: self.clock[0],
        )
        envelope = signed_envelope(kernel, self.intent, self.approval_verifier, now_ns=NOW)
        evidence = self.evidence(envelope)
        self.assertEqual(
            "ceremony_verifier_unavailable",
            kernel.evaluate_with_approval(
                self.intent, envelope, ceremony_evidence=evidence
            ).reason,
        )

        self.ceremony_verifier.key_id = "ceremony-key:substituted"
        envelope = self.envelope(approval_id="approval-other", nonce="nonce-other")
        evidence = self.evidence(envelope, evidence_id="evidence-other")
        self.assertEqual(
            "ceremony_verifier_untrusted",
            self.evaluate(envelope, evidence).reason,
        )

    def test_opt_in_policy_requires_approval_trust_and_distinct_ceremony_key(self):
        with self.assertRaisesRegex(ValueError, "subset of approval actions"):
            replace(self.policy, ceremony_actions=frozenset({"read"}))
        with self.assertRaisesRegex(ValueError, "pinned ceremony trust"):
            Policy(
                frozenset({"push"}), 100, frozenset({"push"}),
                authority_trust=trust_for(self.approval_verifier),
                ceremony_actions=frozenset({"push"}),
            )
        same_key = replace(
            self.ceremony_trust,
            key_fingerprint=self.policy.authority_trust.key_fingerprint,
        )
        with self.assertRaisesRegex(ValueError, "must differ"):
            replace(self.policy, ceremony_trust=same_key)

    def test_policy_hash_for_legacy_policy_is_unchanged(self):
        legacy = Policy(
            self.policy.allowed_actions,
            self.policy.max_cost,
            self.policy.approval_actions,
            self.policy.agent_grants,
            self.policy.authority_trust,
            self.policy.permit_ttl_ns,
        )
        payload = {
            "schema": "pulpo.policy.v1",
            "allowed_actions": sorted(legacy.allowed_actions),
            "max_cost": legacy.max_cost,
            "approval_actions": sorted(legacy.approval_actions),
            "agent_grants": [],
            "authority_trust": {
                "authority_id": self.policy.authority_trust.authority_id,
                "verifier_id": self.policy.authority_trust.verifier_id,
                "key_id": self.policy.authority_trust.key_id,
                "algorithm": self.policy.authority_trust.algorithm,
                "key_fingerprint": self.policy.authority_trust.key_fingerprint,
                "deployment_id": self.policy.authority_trust.deployment_id,
                "max_approval_ttl_ns": self.policy.authority_trust.max_approval_ttl_ns,
                "schema": self.policy.authority_trust.schema,
            },
            "permit_ttl_ns": legacy.permit_ttl_ns,
        }
        from pulpo.kernel import _canonical

        expected = hashlib.sha256(_canonical(payload)).hexdigest()
        self.assertEqual(expected, self.make_kernel(policy=legacy).policy_hash)
        self.assertNotEqual(legacy.ceremony_actions, self.policy.ceremony_actions)
        self.assertNotEqual(
            self.make_kernel(policy=legacy).policy_hash,
            self.kernel.policy_hash,
        )

    def test_unopted_action_keeps_existing_approval_behavior(self):
        policy = replace(self.policy, ceremony_actions=frozenset(), ceremony_trust=None)
        kernel = self.make_kernel(policy=policy)
        envelope = signed_envelope(kernel, self.intent, self.approval_verifier, now_ns=NOW)
        decision = kernel.evaluate_with_approval(
            self.intent, envelope, ceremony_evidence=object()
        )
        self.assertEqual(("allow", "verified_approval"), (decision.outcome, decision.reason))

    def test_evidence_replay_is_blocked_even_with_a_new_approval(self):
        first_envelope = self.envelope()
        first_evidence = self.evidence(first_envelope)
        self.assertEqual("allow", self.evaluate(first_envelope, first_evidence).outcome)

        second_envelope = self.envelope(
            approval_id="approval-ceremony-2", nonce="approval-nonce-2"
        )
        reused_evidence = self.evidence(
            second_envelope, evidence_id=first_evidence.evidence_id
        )
        decision = self.evaluate(second_envelope, reused_evidence)
        self.assertEqual(("deny", "ceremony_evidence_replayed"), (decision.outcome, decision.reason))

    def test_malformed_approval_audit_payload_fails_closed(self):
        self.kernel._state.append("approval_verified", [], NOW)
        envelope = self.envelope()
        evidence = self.evidence(envelope)
        with self.assertRaisesRegex(ValueError, "approval audit payload invalid"):
            self.evaluate(envelope, evidence)

    def test_sqlite_restart_preserves_ceremony_replay_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "kernel.sqlite3"
            state = SQLiteKernelState(path)
            kernel = self.make_kernel(state)
            envelope = signed_envelope(kernel, self.intent, self.approval_verifier, now_ns=NOW)
            evidence = self.evidence(envelope)
            self.assertEqual(
                "allow",
                kernel.evaluate_with_approval(
                    self.intent, envelope, ceremony_evidence=evidence
                ).outcome,
            )
            state.close()

            with SQLiteKernelState(path) as reopened:
                restarted = self.make_kernel(reopened)
                second_envelope = signed_envelope(
                    restarted, self.intent, self.approval_verifier, now_ns=NOW,
                    approval_id="approval-ceremony-2", nonce="approval-nonce-2",
                )
                second_evidence = self.evidence(
                    second_envelope, evidence_id=evidence.evidence_id
                )
                decision = restarted.evaluate_with_approval(
                    self.intent, second_envelope, ceremony_evidence=second_evidence
                )
                self.assertEqual(
                    ("deny", "ceremony_evidence_replayed"),
                    (decision.outcome, decision.reason),
                )
                self.assertTrue(restarted.verify_audit())

    def test_concurrent_distinct_approvals_cannot_reuse_one_ceremony_id(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "kernel.sqlite3"
            first_envelope = self.envelope()
            second_envelope = self.envelope(
                approval_id="approval-ceremony-2", nonce="approval-nonce-2"
            )
            first_evidence = self.evidence(first_envelope)
            second_evidence = self.evidence(
                second_envelope, evidence_id=first_evidence.evidence_id
            )
            barrier = threading.Barrier(2)
            results = []
            errors = []

            def evaluate(envelope, evidence):
                state = SQLiteKernelState(path)
                try:
                    kernel = self.make_kernel(state)
                    barrier.wait()
                    result = kernel.evaluate_with_approval(
                        self.intent, envelope, ceremony_evidence=evidence
                    )
                    results.append((result.outcome, result.reason))
                except Exception as exc:
                    errors.append(exc)
                finally:
                    state.close()

            workers = (
                threading.Thread(target=evaluate, args=(first_envelope, first_evidence)),
                threading.Thread(target=evaluate, args=(second_envelope, second_evidence)),
            )
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join()
            self.assertEqual([], errors)
            self.assertCountEqual(
                [("allow", "verified_approval"), ("deny", "ceremony_evidence_replayed")],
                results,
            )

    def test_failed_atomic_audit_write_does_not_consume_evidence_id(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "kernel.sqlite3"
            state = SQLiteKernelState(path)
            kernel = self.make_kernel(state)
            envelope = signed_envelope(kernel, self.intent, self.approval_verifier, now_ns=NOW)
            evidence = self.evidence(envelope)
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute("""
                    CREATE TRIGGER reject_approval_event
                    BEFORE INSERT ON audit
                    WHEN NEW.event = 'approval_verified'
                    BEGIN SELECT RAISE(ABORT, 'forced audit failure'); END
                """)
            with self.assertRaises(sqlite3.IntegrityError):
                kernel.evaluate_with_approval(
                    self.intent, envelope, ceremony_evidence=evidence
                )
            with closing(sqlite3.connect(path)) as connection:
                connection.execute("DROP TRIGGER reject_approval_event")
            second_envelope = signed_envelope(
                kernel, self.intent, self.approval_verifier, now_ns=NOW,
                approval_id="approval-ceremony-2", nonce="approval-nonce-2",
            )
            second_evidence = self.evidence(
                second_envelope, evidence_id=evidence.evidence_id
            )
            decision = kernel.evaluate_with_approval(
                self.intent, second_envelope, ceremony_evidence=second_evidence
            )
            self.assertEqual("allow", decision.outcome)
            state.close()


@unittest.skipUnless(
    importlib.util.find_spec("cryptography") is not None,
    "install pulpo[authority]",
)
class KeyDerivedCeremonyVerifierTests(unittest.TestCase):
    def test_ed25519_verifier_derives_fingerprint_and_verifies_without_signing(self):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        verifier = Ed25519CeremonyVerifier(
            authority_id="ceremony:test",
            verifier_id="ceremony-verifier:test",
            key_id="ceremony-key:test",
            public_key=public_key,
        )
        payload = b"synthetic ceremony evidence"
        signature = private_key.sign(payload).hex()
        self.assertEqual(hashlib.sha256(public_key).hexdigest(), verifier.key_fingerprint)
        self.assertTrue(verifier.verify(payload, signature))
        self.assertFalse(verifier.verify(payload + b" altered", signature))
        self.assertFalse(hasattr(verifier, "sign"))
        with self.assertRaises(AttributeError):
            verifier.key_fingerprint = "0" * 64

    def test_p256_verifier_derives_fingerprint_and_verifies_raw_signature(self):
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

        private_key = ec.generate_private_key(ec.SECP256R1())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )
        verifier = P256CeremonyVerifier(
            authority_id="ceremony:test",
            verifier_id="ceremony-verifier:test",
            key_id="ceremony-key:test",
            public_key=public_key,
        )
        payload = b"synthetic ceremony evidence"
        der = private_key.sign(payload, ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der)
        signature = r.to_bytes(32, "big").hex() + s.to_bytes(32, "big").hex()
        self.assertEqual(hashlib.sha256(public_key).hexdigest(), verifier.key_fingerprint)
        self.assertTrue(verifier.verify(payload, signature))
        self.assertFalse(verifier.verify(payload + b" altered", signature))
        self.assertFalse(hasattr(verifier, "sign"))
        with self.assertRaises(AttributeError):
            verifier.key_fingerprint = "0" * 64


if __name__ == "__main__":
    unittest.main()
