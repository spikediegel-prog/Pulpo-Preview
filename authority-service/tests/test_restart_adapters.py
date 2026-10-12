from __future__ import annotations

from dataclasses import asdict, replace
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import test_service
from pulpo_authority_service import AuthorityConfig, AuthorityService
from pulpo_authority_service.restart_adapters import DirectoryEvidenceSink, SQLiteRestartState


class FailNthSQLiteRestartState(SQLiteRestartState):
    def __init__(self, *args, **kwargs):
        self.persist_calls = 0
        self.fail_on_persist = None
        super().__init__(*args, **kwargs)

    def _persist_locked(self):
        self.persist_calls += 1
        if self.fail_on_persist == self.persist_calls:
            raise RuntimeError("forced durable commit failure")
        return super()._persist_locked()


class AuthorityRestartAdapterTests(unittest.TestCase):
    def setUp(self):
        fixture = test_service.AuthorityServiceTests(
            methodName="test_one_exact_verified_ceremony_produces_one_kernel_usable_envelope"
        )
        fixture.setUp()
        self.fixture = fixture
        self.clock = [test_service.NOW]

    def _service(self, state, evidence, *, tokens=None):
        if tokens is None:
            tokens = iter(("unused-request", "unused-approval", "unused-nonce"))
        return AuthorityService(
            AuthorityConfig(
                self.fixture.service_trust,
                "example.com",
                "https://authority.example.com",
            ),
            state,
            self.fixture.webauthn,
            test_service.Ed25519TestSigner(
                self.fixture.private_key,
                self.fixture.approval_verifier,
            ),
            evidence,
            clock=lambda: self.clock[0],
            random_token=lambda _: next(tokens),
        )

    def _credentials(self):
        return (self.fixture.primary, self.fixture.recovery)

    def test_operation_connections_close_after_initialization_and_restart(self):
        original = sqlite3.connect
        captured = []
        def connect(*args, **kwargs):
            connection = original(*args, **kwargs)
            captured.append(connection)
            return connection
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "authority.sqlite3"
            with patch("pulpo_authority_service.restart_adapters.sqlite3.connect", connect):
                state = SQLiteRestartState(database, self._credentials())
                state.sequence = 1
                restarted = SQLiteRestartState(database, self._credentials())
                self.assertEqual(1, restarted.sequence)
            self.assertTrue(captured)
            for connection in captured:
                with self.assertRaises(sqlite3.ProgrammingError):
                    connection.execute("SELECT 1")

    def test_interrupted_transaction_entry_releases_connection_and_mutex(self):
        with tempfile.TemporaryDirectory() as directory:
            state = SQLiteRestartState(Path(directory) / "authority.sqlite3", self._credentials())
            captured = []
            original = sqlite3.connect
            def connect(*args, **kwargs):
                connection = original(*args, **kwargs)
                captured.append(connection)
                return connection
            with patch("pulpo_authority_service.restart_adapters.sqlite3.connect", connect), \
                 patch.object(state, "_reload_locked", side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    with state.lock:
                        self.fail("interrupted entry reached transaction body")
            self.assertIsNone(state._active_connection)
            self.assertEqual(0, state._depth)
            with self.assertRaises(sqlite3.ProgrammingError):
                captured[0].execute("SELECT 1")
            def probe():
                acquired = state._mutex.acquire(timeout=.5)
                if acquired:
                    state._mutex.release()
                return acquired
            with ThreadPoolExecutor(max_workers=1) as executor:
                self.assertTrue(executor.submit(probe).result(timeout=2))

    def test_pending_request_and_challenge_survive_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = SQLiteRestartState(root / "authority.sqlite3", self._credentials())
            evidence = DirectoryEvidenceSink(root / "evidence")
            service = self._service(
                state,
                evidence,
                tokens=iter(("request-restart", "approval-restart", "nonce-restart")),
            )
            request_id, _ = service.request_approval(self.fixture.request)
            challenge = service.challenge(request_id)

            restarted_state = SQLiteRestartState(root / "authority.sqlite3", self._credentials())
            restarted = self._service(restarted_state, DirectoryEvidenceSink(root / "evidence"))

            self.assertEqual({"status": "pending"}, restarted.poll(request_id))
            self.assertEqual(challenge, restarted.challenge(request_id))
            self.assertEqual(test_service.NOW, restarted_state.last_time_ns)

    def test_approved_envelope_sequence_and_evidence_survive_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = SQLiteRestartState(root / "authority.sqlite3", self._credentials())
            evidence = DirectoryEvidenceSink(root / "evidence")
            service = self._service(
                state,
                evidence,
                tokens=iter(("request-approved", "approval-approved", "nonce-approved")),
            )
            request_id, _ = service.request_approval(self.fixture.request)
            envelope = service.approve(
                request_id,
                self.fixture.primary.credential_id,
                "raw-assertion-json",
            )

            restarted_state = SQLiteRestartState(root / "authority.sqlite3", self._credentials())
            restarted = self._service(restarted_state, DirectoryEvidenceSink(root / "evidence"))
            polled = restarted.poll(request_id)

            self.assertEqual("approved", polled["status"])
            self.assertEqual(asdict(envelope), polled["envelope"])
            self.assertEqual(1, restarted_state.sequence)
            self.assertEqual(5, restarted_state.credentials[self.fixture.primary.credential_id].sign_count)
            self.assertEqual(1, len(tuple((root / "evidence").glob("*.json"))))

    def test_expiry_and_trusted_time_do_not_regress_after_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = SQLiteRestartState(root / "authority.sqlite3", self._credentials())
            service = self._service(
                state,
                DirectoryEvidenceSink(root / "evidence"),
                tokens=iter(
                    (
                        "request-expired",
                        "approval-expired",
                        "nonce-expired",
                        "request-pending",
                        "approval-pending",
                        "nonce-pending",
                    )
                ),
            )
            expired_id, _ = service.request_approval(self.fixture.request)
            pending_id, _ = service.request_approval(self.fixture.request)
            self.clock[0] = test_service.NOW + self.fixture.request.requested_ttl_ns
            self.assertEqual("expired", service.poll(expired_id)["status"])

            restarted_state = SQLiteRestartState(root / "authority.sqlite3", self._credentials())
            restarted = self._service(restarted_state, DirectoryEvidenceSink(root / "evidence"))
            self.assertEqual("expired", restarted.poll(expired_id)["status"])

            self.clock[0] = test_service.NOW - 1
            with self.assertRaisesRegex(RuntimeError, "rollback"):
                restarted.poll(pending_id)

    def test_evidence_durable_final_state_commit_interrupted_resumes_after_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = FailNthSQLiteRestartState(root / "authority.sqlite3", self._credentials())
            evidence = DirectoryEvidenceSink(root / "evidence")
            service = self._service(
                state,
                evidence,
                tokens=iter(("request-crash", "approval-crash", "nonce-crash")),
            )
            request_id, _ = service.request_approval(self.fixture.request)

            # The next persist durably reserves evidence_pending. Fail the
            # following persist, after the evidence object exists but before the
            # request can become approved.
            state.fail_on_persist = state.persist_calls + 2
            with self.assertRaisesRegex(RuntimeError, "forced durable commit failure"):
                service.approve(
                    request_id,
                    self.fixture.primary.credential_id,
                    "raw-assertion-json",
                )

            record = state.requests[request_id]
            self.assertEqual("evidence_pending", record.status)
            self.assertEqual(1, state.sequence)
            self.assertIsNotNone(record.envelope)
            self.assertIsNotNone(record.evidence_bundle)
            self.assertIsNone(record.evidence_hash)
            self.assertEqual(1, len(tuple((root / "evidence").glob("*.json"))))
            self.assertEqual(1, len(self.fixture.webauthn.calls))

            restarted_state = SQLiteRestartState(root / "authority.sqlite3", self._credentials())
            restarted = self._service(restarted_state, DirectoryEvidenceSink(root / "evidence"))
            polled = restarted.poll(request_id)

            self.assertEqual("approved", polled["status"])
            self.assertEqual(1, restarted_state.sequence)
            self.assertEqual(1, len(tuple((root / "evidence").glob("*.json"))))
            self.assertEqual(1, len(self.fixture.webauthn.calls))
            self.assertIsNone(restarted_state.requests[request_id].evidence_bundle)

    def test_evidence_pending_retry_ignores_new_assertion_and_reuses_durable_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = SQLiteRestartState(root / "authority.sqlite3", self._credentials())
            service = self._service(
                state,
                test_service.FailingEvidenceSink(),
                tokens=iter(("request-resume", "approval-resume", "nonce-resume")),
            )
            request_id, _ = service.request_approval(self.fixture.request)

            with self.assertRaisesRegex(RuntimeError, "authority evidence unavailable"):
                service.approve(
                    request_id,
                    self.fixture.primary.credential_id,
                    "first-verified-assertion",
                )
            self.assertEqual(1, len(self.fixture.webauthn.calls))

            service.evidence = DirectoryEvidenceSink(root / "evidence")
            envelope = service.approve(
                request_id,
                self.fixture.primary.credential_id,
                "different-retry-assertion-must-be-ignored",
            )

            self.assertTrue(envelope.signature)
            self.assertEqual(1, len(self.fixture.webauthn.calls))
            objects = tuple((root / "evidence").glob("*.json"))
            self.assertEqual(1, len(objects))
            evidence_text = objects[0].read_text()
            self.assertIn("first-verified-assertion", evidence_text)
            self.assertNotIn("different-retry-assertion-must-be-ignored", evidence_text)

    def test_snapshot_tamper_fails_closed_on_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "authority.sqlite3"
            SQLiteRestartState(database, self._credentials())
            with closing(sqlite3.connect(database)) as connection, connection:
                payload = connection.execute(
                    "SELECT payload FROM authority_state WHERE singleton = 1"
                ).fetchone()[0]
                connection.execute(
                    "UPDATE authority_state SET payload = ? WHERE singleton = 1",
                    (payload.replace('"sequence":0', '"sequence":9'),),
                )
                connection.commit()

            with self.assertRaisesRegex(RuntimeError, "integrity failure"):
                SQLiteRestartState(database, self._credentials())

    def test_bootstrap_credential_substitution_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "authority.sqlite3"
            SQLiteRestartState(database, self._credentials())
            substituted = replace(self.fixture.primary, public_key=b"attacker-key")

            with self.assertRaisesRegex(RuntimeError, "conflicts"):
                SQLiteRestartState(database, (substituted, self.fixture.recovery))


if __name__ == "__main__":
    unittest.main()
