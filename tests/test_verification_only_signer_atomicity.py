"""Finding 7 (Codex P1 on PR #420) — a verification-only audit signer
must never leave canonical state mutated without its signed record.

``CompositeAuditSigner`` with no signer raises on every ``sign()``.
The in-memory backend's mutating transitions recorded their mutations
FIRST and appended the signed audit record LAST, so the raise landed
after the mutation: ``consume_permit`` left the permit spent with no
``permit_consumed`` record, and the sibling transitions (permit
issuance, directive binding, directive activation/revocation) shared
the ordering. The fix makes every in-memory transition probe signing
availability before its first mutation, so a failed signing leaves
the state byte-identical.

The SQLite backend never shared the defect — every transition runs
inside a BEGIN IMMEDIATE transaction whose rollback on the same raise
discards the mutations — and two tests below pin that disposition.

Regression shape (per the verification report,
``p1-verification-2026-11-27.md`` Finding 7): with a verification-only
composite installed, each transition raises AND the state is
byte-identical to before the call.

Preview adaptation: Preview has no lease support and no directive
budgets, so the two lease tests and every budget assertion are
dropped here (7 tests: 5 in-memory, 2 SQLite). ``snapshot()`` covers
Preview's in-memory containers only, and deep-copies the audit —
Preview's ``InMemoryKernelState.audit`` returns the live list, unlike
canonical's detached copies. Authority evidence is a plain dict, as
Preview's ``activate_directive`` / ``revoke_directive`` take it.
"""

from __future__ import annotations

from copy import deepcopy
import tempfile
import unittest

from pulpo.directives import Directive
from pulpo.state import (
    ApprovalUse,
    CompositeAuditSigner,
    InMemoryKernelState,
    SQLiteKernelState,
)

NOW = 1_000_000
PERMIT = "permit-1"
INTENT_HASH = "intent-1"


class _StubVerifier:
    """One era's verifier half, without the cryptography extra: the
    composite below is verification-only because it has NO signer,
    which is the whole of the defect's trigger — its sign() raises
    the exact RuntimeError before any verifier is consulted. (The
    real Ed25519-backed composite is exercised in
    tests/test_audit_signing_ed25519.py; this file must also run in
    the zero-dependency CI job.)"""

    algorithm = "ed25519"

    def sign(self, record_hash: str) -> str:
        raise RuntimeError("verifier is verification-only")

    def verify(self, record_hash: str, signature) -> bool:
        return False


def verify_only_signer() -> CompositeAuditSigner:
    return CompositeAuditSigner(verifiers=[_StubVerifier()])


def make_directive(**overrides) -> Directive:
    values = dict(
        directive_id="dir-1",
        version=1,
        issuer_authority_id="authority:test-owner",
        principal="agent:worker",
        allowed_actions=frozenset({"push"}),
        resource_prefixes=("repo:",),
        max_cost=100,
        issued_at_ns=1,
        expires_at_ns=10_000_000,
    )
    values.update(overrides)
    return Directive(**values)


def evidence(operation: str, directive: Directive) -> dict[str, object]:
    return {
        "operation": operation,
        "directive_id": directive.directive_id,
        "directive_version": directive.version,
        "directive_hash": directive.directive_hash,
        "authority_id": directive.issuer_authority_id,
    }


def snapshot(state: InMemoryKernelState) -> dict:
    """Every canonical container of the in-memory backend, detached."""
    return {
        "issued": deepcopy(state._issued),
        "permit_context": deepcopy(state._permit_context),
        "spent": deepcopy(state._spent),
        "approval_ids": deepcopy(state._approval_ids),
        "approval_nonces": deepcopy(state._approval_nonces),
        "directives": deepcopy(state._directives),
        "permit_directives": deepcopy(state._permit_directives),
        "audit": deepcopy(state.audit),
    }


def bound_state() -> InMemoryKernelState:
    """An issued permit bound to an active directive."""
    directive = make_directive()
    state = InMemoryKernelState()
    state.issue_permit(PERMIT, INTENT_HASH, "allow", NOW)
    state.activate_directive(directive, evidence("activate_directive", directive), NOW)
    state.bind_permit_to_directive(PERMIT, INTENT_HASH, directive.permit_binding, NOW)
    return state


class VerificationOnlySignerAtomicityTests(unittest.TestCase):
    def test_consume_permit_leaves_state_byte_identical(self):
        state = bound_state()
        before = snapshot(state)
        state.audit_signer = verify_only_signer()
        with self.assertRaises(RuntimeError):
            state.consume_permit(PERMIT, INTENT_HASH, NOW)
        self.assertEqual(snapshot(state), before)
        self.assertNotIn(PERMIT, state._spent)
        self.assertEqual(len(state.audit), 3)
        # The permit was never spent: with the signer removed the
        # same consumption succeeds (pre-fix it returned False —
        # permit_rejected — because the spend had survived).
        state.audit_signer = None
        self.assertTrue(state.consume_permit(PERMIT, INTENT_HASH, NOW))

    def test_issue_permit_with_approval_leaves_state_byte_identical(self):
        state = InMemoryKernelState()
        before = snapshot(state)
        state.audit_signer = verify_only_signer()
        approval = ApprovalUse(
            approval_id="approval:1",
            nonce="nonce:1",
            audit_payload={"approval_id": "approval:1"},
            ceremony_evidence_id="evidence:1",
        )
        with self.assertRaises(RuntimeError):
            state.issue_permit(PERMIT, INTENT_HASH, "allow", NOW, approval=approval)
        self.assertEqual(snapshot(state), before)
        self.assertEqual(state._issued, {})
        self.assertEqual(state._approval_ids, set())

    def test_bind_permit_to_directive_leaves_state_byte_identical(self):
        directive = make_directive()
        state = InMemoryKernelState()
        state.issue_permit(PERMIT, INTENT_HASH, "allow", NOW)
        state.activate_directive(directive, evidence("activate_directive", directive), NOW)
        before = snapshot(state)
        state.audit_signer = verify_only_signer()
        with self.assertRaises(RuntimeError):
            state.bind_permit_to_directive(PERMIT, INTENT_HASH, directive.permit_binding, NOW)
        self.assertEqual(snapshot(state), before)
        self.assertEqual(state._permit_directives, {})

    def test_activate_directive_leaves_state_byte_identical(self):
        directive = make_directive()
        state = InMemoryKernelState()
        before = snapshot(state)
        state.audit_signer = verify_only_signer()
        with self.assertRaises(RuntimeError):
            state.activate_directive(directive, evidence("activate_directive", directive), NOW)
        self.assertEqual(snapshot(state), before)
        self.assertEqual(state._directives, {})

    def test_revoke_directive_leaves_state_byte_identical(self):
        directive = make_directive()
        state = InMemoryKernelState()
        state.activate_directive(directive, evidence("activate_directive", directive), NOW)
        before = snapshot(state)
        state.audit_signer = verify_only_signer()
        with self.assertRaises(RuntimeError):
            state.revoke_directive(
                directive.directive_id,
                directive.version,
                evidence("revoke_directive", directive),
                NOW,
            )
        self.assertEqual(snapshot(state), before)
        self.assertEqual(
            state.directive_status(directive.directive_id, directive.version, directive.directive_hash),
            "active",
        )


class SQLiteVerificationOnlySignerTests(unittest.TestCase):
    """Disposition evidence: the SQLite backend's transitions run
    inside BEGIN IMMEDIATE transactions, so the same signing raise
    rolls the mutations back — it never shared Finding 7."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.state = SQLiteKernelState(f"{self._tmp.name}/state.db")

    def tearDown(self):
        self.state.close()
        self._tmp.cleanup()

    def test_sqlite_consume_permit_rolls_back(self):
        self.state.issue_permit(PERMIT, INTENT_HASH, "allow", NOW)
        audit_before = self.state.audit
        self.state.audit_signer = verify_only_signer()
        with self.assertRaises(RuntimeError):
            self.state.consume_permit(PERMIT, INTENT_HASH, NOW)
        self.assertEqual(self.state.audit, audit_before)
        self.state.audit_signer = None
        self.assertTrue(self.state.consume_permit(PERMIT, INTENT_HASH, NOW))

    def test_sqlite_issue_permit_rolls_back(self):
        self.state.audit_signer = verify_only_signer()
        with self.assertRaises(RuntimeError):
            self.state.issue_permit(PERMIT, INTENT_HASH, "allow", NOW)
        self.assertEqual(self.state.audit, [])
        self.state.audit_signer = None
        self.assertIsNone(self.state.issue_permit(PERMIT, INTENT_HASH, "allow", NOW))


if __name__ == "__main__":
    unittest.main()
