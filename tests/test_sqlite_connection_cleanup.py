"""Operation-owned connections close after success, denial and rollback."""
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from pulpo.commerce import DomainPurchaseOrder
from pulpo.custody import SQLiteGovernanceCustody
from pulpo.custody_evidence import CustodyEvidenceViolation, SQLiteCustodyEvidenceConvergence
from pulpo.proposal_commitment import SQLiteProposalCommitments, ProposalCommitmentViolation
from pulpo.state import SQLiteKernelState


class ConnectionCleanupTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "fixture.sqlite3"
        self.connections = []

    def track(self, original):
        def connect(instance):
            connection = original(instance)
            self.connections.append(connection)
            return connection
        return connect

    def assert_closed(self):
        self.assertTrue(self.connections)
        for connection in self.connections:
            with self.assertRaises(sqlite3.ProgrammingError):
                connection.execute("SELECT 1")

    def test_evidence_initialization_and_reads_close_connections(self):
        state = SQLiteKernelState(self.path)
        state.close()
        custody = SQLiteGovernanceCustody(self.path, signing_secret=b"cleanup-fixture")
        cls = SQLiteCustodyEvidenceConvergence
        with patch.object(cls, "_connect", self.track(cls._connect)):
            evidence = cls(custody)
            self.assertEqual(evidence.pending_count(), 0)
            self.assertEqual(evidence.canonical_event_count("a" * 64), 0)
        self.assert_closed()

    def test_proposal_commit_denial_and_early_return_close_connections(self):
        order = DomainPurchaseOrder(
            request_id="cleanup", request_hash="a" * 64,
            quote_id="quote", quote_hash="b" * 64, principal="fixture",
            domain="example.test", registrar="fixture", purchase_price_cents=100,
            renewal_price_cents=100, owner_ref="owner://fixture", privacy_required=True,
            prohibited_upsells=(), credential_ref="credential://fixture", expires_at_ns=100,
        )
        cls = SQLiteProposalCommitments
        with patch.object(cls, "_connect", self.track(cls._connect)):
            store = cls(self.path)
            proposal = store.create(order, availability_hash="c" * 64,
                                    created_at_ns=1, expires_at_ns=100)
            self.assertEqual(store.create(order, availability_hash="c" * 64,
                                          created_at_ns=1, expires_at_ns=100), proposal)
            with self.assertRaises(ProposalCommitmentViolation):
                store.claim(proposal.commitment_id, now_ns=100)
            claimed, claimed_order = store.claim(proposal.commitment_id, now_ns=2)
            self.assertEqual(claimed.state, store.CLAIMED)
            self.assertEqual(claimed_order, order)
            self.assertEqual(store.order_for_hash(order.order_hash), order)
            with self.assertRaises(ProposalCommitmentViolation):
                store.claim(proposal.commitment_id, now_ns=3)
        self.assert_closed()

    def test_failed_evidence_initialization_closes_connection(self):
        custody = SQLiteGovernanceCustody(self.path, signing_secret=b"cleanup-fixture")
        cls = SQLiteCustodyEvidenceConvergence
        with patch.object(cls, "_connect", self.track(cls._connect)):
            with self.assertRaisesRegex(CustodyEvidenceViolation, "canonical_audit_missing"):
                cls(custody)
        self.assert_closed()
