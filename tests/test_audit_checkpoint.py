import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from pulpo import GovernanceKernel, Policy, SQLiteKernelState, StateIntegrityError


class AuditCheckpointTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "state.sqlite3"
        self.state = SQLiteKernelState(self.path)
        self.addCleanup(self.state.close)
        for i in range(3):
            self.state.append("sample", {"i": i}, i)
        self.kernel()

    def kernel(self, secret=b"checkpoint-test-only"):
        return GovernanceKernel(Policy(frozenset(), 0), state=self.state, secret=secret)

    def checkpoint(self):
        return json.loads(self.state._connection.execute(
            "SELECT checkpoint_json FROM audit_verification_checkpoint"
        ).fetchone()[0])

    def write_checkpoint(self, value):
        with self.state._connection:
            self.state._connection.execute(
                "UPDATE audit_verification_checkpoint SET checkpoint_json = ?", (value,)
            )

    def test_reopen_uses_cache_and_forced_verify_still_reads_full_chain(self):
        before = self.state.audit
        self.state.close()
        self.state = SQLiteKernelState(self.path)
        self.addCleanup(self.state.close)
        with patch.object(GovernanceKernel, "verify_audit", side_effect=AssertionError("full path")):
            kernel = self.kernel()
        self.assertEqual(before, self.state.audit)
        self.assertTrue(kernel.verify_audit())
        with self.state._connection:
            self.state._connection.execute("UPDATE audit SET payload_json = '{}' WHERE sequence = 1")
        self.assertFalse(kernel.verify_audit())

    def test_absent_deleted_and_changed_secret_fall_back(self):
        for action in ("delete", "secret"):
            if action == "delete":
                with self.state._connection:
                    self.state._connection.execute("DELETE FROM audit_verification_checkpoint")
            original = GovernanceKernel.verify_audit
            with patch.object(GovernanceKernel, "verify_audit", autospec=True, side_effect=original) as full:
                self.kernel(b"changed-secret" if action == "secret" else b"checkpoint-test-only")
                full.assert_called_once()

    def test_malformed_corrupt_mismatched_and_stale_cache_fall_back(self):
        valid = self.checkpoint()
        variants = ["{broken", "null", "[]", "42", "{}"]
        for field, value in (("schema", "old"), ("sequence", 999), ("sequence", True),
                             ("head", "f" * 64), ("prefix_digest", "a" * 64),
                             ("mac", "0" * 64), ("extra", 1)):
            variants.append(json.dumps({**valid, field: value}))
        for value in variants:
            with self.subTest(value=value):
                self.write_checkpoint(value)
                original = GovernanceKernel.verify_audit
                with patch.object(GovernanceKernel, "verify_audit", autospec=True, side_effect=original) as full:
                    self.kernel()
                    full.assert_called_once()

    def test_historical_tamper_including_checkpoint_row_fails_closed(self):
        for sequence in (1, 3):
            with self.subTest(sequence=sequence):
                original = self.state._connection.execute("SELECT payload_json FROM audit WHERE sequence = ?", (sequence,)).fetchone()[0]
                with self.state._connection:
                    self.state._connection.execute("UPDATE audit SET payload_json = '{}' WHERE sequence = ?", (sequence,))
                with self.assertRaises(StateIntegrityError):
                    self.kernel()
                with self.state._connection:
                    self.state._connection.execute("UPDATE audit SET payload_json = ? WHERE sequence = ?", (original, sequence))

    def test_recomputed_unkeyed_prefix_digest_cannot_hide_tamper(self):
        from hashlib import sha256
        from pulpo.state import _canonical
        with self.state._connection:
            self.state._connection.execute("UPDATE audit SET payload_json = '{}' WHERE sequence = 1")
        rows = self.state._connection.execute("SELECT * FROM audit ORDER BY sequence").fetchall()
        forged = self.checkpoint()
        forged["prefix_digest"] = sha256(_canonical(rows)).hexdigest()
        self.write_checkpoint(json.dumps(forged))
        with self.assertRaises(StateIntegrityError):
            self.kernel()

    def test_suffix_verification_and_refresh(self):
        self.state.append("after", {"new": True}, 10)
        with patch.object(GovernanceKernel, "verify_audit", side_effect=AssertionError("full path")):
            self.kernel()
        self.assertEqual(4, self.checkpoint()["sequence"])
        self.assertTrue(self.kernel().verify_audit())

    def test_tamper_after_checkpoint_fails_closed(self):
        self.state.append("after", {}, 10)
        with self.state._connection:
            self.state._connection.execute("UPDATE audit SET previous_hash = ? WHERE sequence = 4", ("0" * 64,))
        with self.assertRaises(StateIntegrityError):
            self.kernel()
        self.assertEqual(3, self.checkpoint()["sequence"])

    def test_malformed_audit_before_and_after_checkpoint_fails_closed(self):
        self.state.append("after", {}, 10)
        for sequence in (4, 1):
            with self.subTest(sequence=sequence):
                original = self.state._connection.execute("SELECT payload_json FROM audit WHERE sequence = ?", (sequence,)).fetchone()[0]
                with self.state._connection:
                    self.state._connection.execute("UPDATE audit SET payload_json = '{bad' WHERE sequence = ?", (sequence,))
                with self.assertRaises(StateIntegrityError):
                    self.kernel()
                with self.state._connection:
                    self.state._connection.execute("UPDATE audit SET payload_json = ? WHERE sequence = ?", (original, sequence))

    def test_truncation_and_sequence_changes_invalidate_cache(self):
        original = GovernanceKernel.verify_audit
        with self.state._connection:
            self.state._connection.execute("DELETE FROM audit WHERE sequence = 3")
        with patch.object(GovernanceKernel, "verify_audit", autospec=True, side_effect=original) as full:
            self.kernel()
            full.assert_called_once()
        self.assertEqual(2, self.checkpoint()["sequence"])
        with self.state._connection:
            self.state._connection.execute("UPDATE audit SET sequence = 9 WHERE sequence = 2")
        with patch.object(GovernanceKernel, "verify_audit", autospec=True, side_effect=original) as full:
            self.kernel()
            full.assert_called_once()

    def test_unavailable_checkpoint_write_fails_closed_and_rolls_back(self):
        self.state.append("suffix", {}, 10)
        self.state._connection.executescript("""
            CREATE TRIGGER reject_checkpoint BEFORE INSERT ON audit_verification_checkpoint
            BEGIN SELECT RAISE(ABORT, 'checkpoint failure'); END;
        """)
        with self.assertRaises(StateIntegrityError):
            self.kernel()
        self.assertFalse(self.state._connection.in_transaction)
        self.assertEqual(3, self.checkpoint()["sequence"])

    def test_bootstrap_snapshot_blocks_overlapping_append_until_publication(self):
        with self.state._connection:
            self.state._connection.execute("DELETE FROM audit_verification_checkpoint")
        validating, release, appended = threading.Event(), threading.Event(), threading.Event()
        errors = []

        def bootstrap():
            state = SQLiteKernelState(self.path)
            try:
                def full_verify():
                    validating.set()
                    if not release.wait(3):
                        raise RuntimeError("snapshot test timeout")
                    return GovernanceKernel.verify_audit(kernel)
                # Construct a kernel without bootstrap to provide the normal full verifier.
                with patch.object(state, "verify_audit_bootstrap", None):
                    kernel = GovernanceKernel(Policy(frozenset(), 0), state=state)
                self.assertTrue(state.verify_audit_bootstrap(b"checkpoint-test-only", full_verify))
            except Exception as exc:
                errors.append(exc)
            finally:
                state.close()

        def append():
            state = SQLiteKernelState(self.path)
            try:
                state.append("concurrent", {}, 20)
                appended.set()
            except Exception as exc:
                errors.append(exc)
            finally:
                state.close()

        first = threading.Thread(target=bootstrap)
        second = threading.Thread(target=append)
        first.start()
        try:
            self.assertTrue(validating.wait(3))
            second.start()
            self.assertFalse(appended.wait(0.1))
        finally:
            release.set()
            first.join(5)
            if second.ident is not None:
                second.join(5)
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual([], errors)
        self.assertTrue(appended.is_set())
        self.assertEqual(3, self.checkpoint()["sequence"])
        self.assertTrue(self.kernel().verify_audit())
        self.assertEqual(4, self.checkpoint()["sequence"])


if __name__ == "__main__":
    unittest.main()
