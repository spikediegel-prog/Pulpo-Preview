from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from pulpo import GovernanceKernel, Intent, Policy, PulpoOrchestrator, SQLiteKernelState
from pulpo.database_activity import ObservedConnection
from pulpo.evidence_export import export_evidence_observation, freeze_evidence_observation
from pulpo.evidence_observation import AIUsage, ActivityHistory, EvidenceObservation, freshness, load_observation
from pulpo.ollama_proposal import request_local_proposal, request_local_proposal_with_usage
from tests.test_ollama_proposal import MODEL, replies


class DatabaseActivityTests(unittest.TestCase):
    def connection(self):
        connection = sqlite3.connect(":memory:", factory=ObservedConnection)
        self.addCleanup(connection.close)
        connection.execute("CREATE TABLE items (id INTEGER PRIMARY KEY)")
        return connection

    def test_completed_calls_commits_and_rollbacks_preserve_sql_semantics(self):
        c = self.connection()
        with c:
            c.executemany("INSERT INTO items VALUES (?)", [(1,), (2,)])
        self.assertEqual({"reads": 0, "writes": 2, "commits": 1, "rollbacks": 0, "errors": 0}, c.activity)
        with self.assertRaises(sqlite3.IntegrityError):
            with c:
                c.execute("INSERT INTO items VALUES (3)")
                c.execute("INSERT INTO items VALUES (1)")
        self.assertEqual([(1,), (2,)], c.execute("SELECT * FROM items").fetchall())
        self.assertEqual(1, c.activity["rollbacks"])
        self.assertEqual(1, c.activity["errors"])
        self.assertEqual(1, c.activity["commits"])
        c.commit()  # No transaction: not a commit event.
        self.assertEqual(1, c.activity["commits"])
        c.execute("BEGIN")
        c.execute("SELECT * FROM items").fetchall()
        c.commit()
        self.assertEqual(2, c.activity["commits"])
        self.assertNotIn("sql", vars(c))

    def test_failed_commit_never_counts_as_successful_commit(self):
        c = self.connection()
        c.execute("PRAGMA foreign_keys = ON")
        c.execute("CREATE TABLE child (id INTEGER REFERENCES items(id) DEFERRABLE INITIALLY DEFERRED)")
        with self.assertRaises(sqlite3.IntegrityError):
            with c:
                c.execute("INSERT INTO child VALUES (99)")
        self.assertEqual(0, c.activity["commits"])
        self.assertEqual(1, c.activity["errors"])
        self.assertEqual(1, c.activity["rollbacks"])
        self.assertEqual([], c.execute("SELECT * FROM child").fetchall())


class EvidenceProjectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "state.sqlite"
        self.path = Path(self.temp.name) / "observation.json"
        self.backend = SQLiteKernelState(self.db)
        self.addCleanup(self.backend.close)
        self.kernel = GovernanceKernel(Policy(frozenset({"read"}), 0), secret=b"test-only", state=self.backend)
        self.owner = PulpoOrchestrator(self.kernel)

    def test_real_owner_observation_is_redacted_bounded_and_does_not_mutate_database(self):
        intent = Intent("agent:test", "read", "fixture-private", 0)
        decision = self.kernel.evaluate(intent)
        self.kernel.consume(decision.permit, intent)
        self.kernel.consume(decision.permit, intent)
        self.kernel.evaluate(Intent("agent:test", "delete", "fixture-private", 0))
        # Canonical rejection reason fixtures include expiry during verification.
        for reason in ("approval_expired", "approval_expired_during_verification", "approval_nonce_replayed"):
            self.backend.append("approval_rejected", {"reason": reason}, 123)
        for _ in range(30):
            self.backend.append("private-event", {"permit": "DO_NOT_EXPORT", "prompt": "DO_NOT_EXPORT"}, 123)
        audit_before = self.kernel.audit
        bytes_before = self.db.read_bytes()
        writes_before = self.backend._connection.activity["writes"]
        for _ in range(3):
            snapshot = export_evidence_observation(self.owner, self.path, check_database=True,
                                                    ai=AIUsage("Ollama", 12, 5, scope="latest_completed_request"))
            self.assertEqual("ok", snapshot.health)
            self.assertEqual(1, snapshot.allowed)
            self.assertEqual(1, snapshot.denied)
            self.assertEqual(1, snapshot.permit_consumed)
            self.assertEqual(1, snapshot.permit_rejected)
            self.assertEqual(2, snapshot.approval_expired)
            self.assertEqual(1, snapshot.approval_replayed)
            self.assertEqual(24, len(snapshot.events))
            self.assertEqual(snapshot, load_observation(self.path))
            self.assertEqual(bytes_before, self.db.read_bytes())
        self.assertEqual(audit_before, self.kernel.audit)
        self.assertEqual(writes_before, self.backend._connection.activity["writes"])
        raw = self.path.read_text()
        for private in ("DO_NOT_EXPORT", "fixture-private", decision.permit, str(self.db)):
            self.assertNotIn(private, raw)
        self.assertLess(self.path.stat().st_size, 16384)
        self.assertIsNone(snapshot.ai.cost_microusd)

    @unittest.skipUnless(os.name == "posix", "owner publication filesystem contract")
    def test_failed_export_preserves_evidence_and_consumed_permit(self):
        intent = Intent("agent:test", "read", "test-only", 0)
        decision = self.kernel.evaluate(intent)
        self.assertTrue(self.kernel.consume(decision.permit, intent))
        export_evidence_observation(self.owner, self.path)
        original = self.path.read_bytes()
        audit = self.kernel.audit
        writes = self.backend._connection.activity["writes"]
        with patch("pulpo.mcp_boundary.os.replace", side_effect=OSError("TEST ONLY storage unavailable")):
            from pulpo.mcp_boundary import MCPBoundaryError
            with self.assertRaisesRegex(MCPBoundaryError, "commit_unknown"):
                export_evidence_observation(self.owner, self.path)
        self.assertEqual(original, self.path.read_bytes())
        self.assertEqual(audit, self.kernel.audit)
        self.assertEqual(writes, self.backend._connection.activity["writes"])
        self.assertTrue(self.kernel.verify_audit())
        self.assertFalse(self.kernel.consume(decision.permit, intent))

    def test_owner_transaction_and_wrong_dependency_are_rejected(self):
        with self.assertRaises(TypeError):
            freeze_evidence_observation(self.kernel)
        self.backend._connection.execute("BEGIN")
        with self.assertRaisesRegex(ValueError, "idle_owner"):
            freeze_evidence_observation(self.owner)
        self.backend._connection.rollback()

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX FIFO required")
    def test_protected_reader_rejects_fifo_without_waiting_for_writer(self):
        os.mkfifo(self.path)
        with self.assertRaises(ValueError):
            load_observation(self.path)

    def test_in_memory_owner_does_not_fabricate_database_or_ai_telemetry(self):
        memory = PulpoOrchestrator(GovernanceKernel(Policy(frozenset({"read"}), 0)))
        snapshot = freeze_evidence_observation(memory, check_database=True)
        for key in ("reads", "writes", "commits", "database_bytes", "volume_free"):
            self.assertIsNone(getattr(snapshot, key))
        self.assertEqual("not_checked", snapshot.health)
        self.assertEqual(AIUsage(), snapshot.ai)

    def test_parser_rejects_extra_private_malformed_and_oversized_fields_without_rewrite(self):
        good = asdict(export_evidence_observation(self.owner, self.path))
        variants = [dict(good, permit="PRIVATE"), dict(good, reads=True), dict(good, volume_total=1),
                    dict(good, events=[{"payload": "PRIVATE"}]), dict(good, ai={"prompt": "PRIVATE"}),
                    dict(good, ai=dict(good["ai"], cost_microusd=-1)), dict(good, health="verified")]
        for value in variants:
            raw = json.dumps(value)
            self.path.write_text(raw)
            self.path.chmod(0o600)
            with self.assertRaises((ValueError, TypeError)):
                load_observation(self.path)
            self.assertEqual(raw, self.path.read_text())


class ActivityHistoryTests(unittest.TestCase):
    def sample(self, **changes):
        return replace(EvidenceObservation("a" * 32, 100_000_000_000, True, 0, reads=10, writes=20, commits=3), **changes)

    def test_rates_duplicate_replay_reset_and_source_change(self):
        h = ActivityHistory()
        first = self.sample()
        h.add(first)
        self.assertIsNone(h.points[-1][1]["reads"])
        next_sample = self.sample(observed_at_ns=102_000_000_000, reads=16, writes=24, commits=5)
        h.add(next_sample)
        self.assertEqual({"reads": 3, "writes": 2, "commits": 1}, h.points[-1][1])
        self.assertFalse(h.add(next_sample))
        with self.assertRaises(ValueError): h.add(replace(next_sample, reads=17))
        with self.assertRaises(ValueError): h.add(first)
        h.add(self.sample(observed_at_ns=104_000_000_000, reads=1))
        self.assertIsNone(h.points[-1][1]["reads"])
        h.add(self.sample(source_id="b" * 32, observed_at_ns=106_000_000_000))
        self.assertEqual(1, len(h.points))

    def test_gap_missing_metrics_bounded_history_and_freshness(self):
        h = ActivityHistory()
        for index in range(1810):
            h.add(self.sample(observed_at_ns=(100 + index * 20) * 10**9, reads=None))
        self.assertEqual(1801, len(h.points))
        self.assertTrue(all(value is None for value in h.points[-1][1].values()))
        self.assertEqual("stale", freshness(self.sample(), 120_000_000_000))
        self.assertEqual("clock mismatch", freshness(self.sample(), 90_000_000_000))


class AIUsageTests(unittest.TestCase):
    def test_existing_proposal_api_unchanged_and_new_usage_is_provider_reported(self):
        response = replies()
        response[-1].update(prompt_eval_count=14, eval_count=8)
        with patch("pulpo.ollama_proposal._request", side_effect=response):
            content, usage = request_local_proposal_with_usage("fixture", MODEL)
        self.assertEqual(14, usage.input_tokens)
        self.assertEqual(8, usage.output_tokens)
        self.assertIsNone(usage.cost_microusd)
        with patch("pulpo.ollama_proposal._request", side_effect=replies()):
            self.assertEqual(content, request_local_proposal("fixture", MODEL))

    def test_missing_or_bad_usage_never_invents_counts_or_rejects_valid_proposal(self):
        for value in (None, True, -1, "14", 2**90):
            response = replies()
            response[-1].update(prompt_eval_count=value, eval_count=value)
            with patch("pulpo.ollama_proposal._request", side_effect=response):
                _, usage = request_local_proposal_with_usage("fixture", MODEL)
            self.assertIsNone(usage.input_tokens)
            self.assertIsNone(usage.output_tokens)


if __name__ == "__main__":
    unittest.main()
