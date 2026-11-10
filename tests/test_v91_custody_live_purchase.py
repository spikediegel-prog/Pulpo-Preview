"""v9.1 slice 1: route the live purchase through the custody coordinator.

Verification report (2026-11-09) section 6a/6b(c)(d): on the live orchestrator
path, `adapter.purchase` raising left no unknown outcome anywhere in the
canonical audit chain -- the permit was already spent and the uncertainty
existed only as a raised exception -- and nothing re-read permit/directive/
policy/expiry state between consumption and the provider call.

These tests prove the slice-1 fix in `DomainCommerceExecutor.execute`:

(a) a live-path purchase attempt that raises after consume records a
    `purchase_consequence_unknown` event in the canonical audit (durable
    evidence, not just a raised exception);
(b) the pre-purchase revalidation refuses when permit/directive/policy/expiry
    state changed between consume and purchase;
(c) the happy path still succeeds exactly as before;
(d) a retry after an uncertain outcome is blocked, not silently retried.

The coordinator route is covered too: when a `GovernedDomainAttemptCoordinator`
is supplied, consumption runs through it (locked-target resolution, canonical
consume, audit-tip check, custody attempt) and the unknown-outcome record
carries the custody attempt id. The custody attempt itself stays
`attempt_authorized`: the custody state machine has no
`attempt_authorized -> reconciliation_required` edge, so the canonical audit
event is the reconciliation-required record for the live path.
"""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from pulpo.commerce import (
    BudgetAccount,
    CommerceViolation,
    DomainCommerceExecutor,
    DomainPurchaseRequest,
    DomainQuote,
    RegistrarResult,
    SQLiteBudgetAccount,
    assess_quote,
    purchase_intent,
)
from pulpo.custody import SQLiteGovernanceCustody
from pulpo.custody_domain import GovernedDomainAttemptCoordinator
from pulpo.directives import (
    Directive,
    DirectiveAuthorityController,
    GovernedDirectiveProjection,
)
from pulpo.kernel import GovernanceKernel, Policy
from pulpo.orchestrator import PulpoOrchestrator
from pulpo.state import InMemoryKernelState, SQLiteKernelState
from tests.authority_support import HmacTestVerifier, signed_envelope, trust_for

NOW = 8_000_000
OPERATOR = "operator:owner"


class FakeRegistrar:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def purchase(self, order, *, max_charge_cents):
        self.calls += 1
        return self.result


class UncertainRegistrar:
    def __init__(self):
        self.calls = 0

    def purchase(self, order, *, max_charge_cents):
        del order, max_charge_cents
        self.calls += 1
        raise ConnectionError("provider result is unknown")


class HookedBudget:
    """BudgetState delegate that runs a hook inside mark_attempted.

    The hook simulates state changing between permit consumption and the
    provider call: exactly the window the pre-purchase revalidation closes.
    """

    def __init__(self, wrapped, hook):
        self._wrapped = wrapped
        self._hook = hook

    def require_active(self, reservation_id, order, *, now_ns):
        return self._wrapped.require_active(reservation_id, order, now_ns=now_ns)

    def mark_attempted(self, reservation_id):
        self._hook()
        return self._wrapped.mark_attempted(reservation_id)

    def reconcile(self, reservation_id, payment):
        return self._wrapped.reconcile(reservation_id, payment)

    def __getattr__(self, name):
        return getattr(self._wrapped, name)


def audit_events(kernel, event):
    return [record for record in kernel.audit if record.get("event") == event]


class LivePurchaseCustodyTests(unittest.TestCase):
    def order(self, domain="pulpo-live-purchase.example", *, price=2_000):
        request = DomainPurchaseRequest(
            request_id=f"request-v91:{domain}",
            principal="agent:commerce",
            acceptable_domains=(domain,),
            max_purchase_cents=3_000,
            max_renewal_cents=2_500,
            approved_registrar="name.com",
            owner_ref="owner://iron-ember",
            privacy_required=True,
            prohibited_upsells=("hosting",),
            expires_at_ns=NOW + 100_000,
        )
        quote = DomainQuote(
            quote_id=f"quote:{domain}",
            domain=domain,
            registrar="name.com",
            purchase_price_cents=price,
            renewal_price_cents=2_400,
            owner_ref="owner://iron-ember",
            privacy_enabled=True,
            upsells=(),
            expires_at_ns=NOW + 50_000,
        )
        assessment = assess_quote(
            request,
            quote,
            credential_ref="credential://name-com/v91-live-purchase",
            now_ns=NOW,
        )
        self.assertIsNotNone(assessment.order)
        return assessment.order

    def kernel_with(self, order, *, state=None, clock=None, permit_ttl_ns=None):
        policy_kwargs = {}
        if permit_ttl_ns is not None:
            policy_kwargs["permit_ttl_ns"] = permit_ttl_ns
        kernel = GovernanceKernel(
            Policy(frozenset({"purchase_domain"}), 3_000, **policy_kwargs),
            secret=b"test-secret",
            clock=clock or (lambda: NOW),
            state=state,
        )
        permit = kernel.evaluate(purchase_intent(order)).permit
        self.assertIsNotNone(permit)
        return kernel, permit

    # (a) Unknown outcome becomes durable canonical evidence.
    def test_uncertain_live_purchase_records_unknown_outcome_in_canonical_audit(self):
        order = self.order()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "kernel.sqlite3"
            state = SQLiteKernelState(path)
            self.addCleanup(state.close)
            kernel, permit = self.kernel_with(order, state=state)
            budget = SQLiteBudgetAccount(path)
            reservation = budget.reserve(order, now_ns=NOW)
            uncertain = UncertainRegistrar()

            with self.assertRaisesRegex(ConnectionError, "unknown"):
                DomainCommerceExecutor().execute(
                    kernel, order, permit, uncertain, budget,
                    reservation.reservation_id, now_ns=NOW,
                )
            self.assertEqual(1, uncertain.calls)

            unknown = audit_events(kernel, "purchase_consequence_unknown")
            self.assertEqual(1, len(unknown))
            payload = unknown[0]["payload"]
            self.assertEqual(order.order_hash, payload["order_hash"])
            self.assertEqual(kernel.intent_hash(purchase_intent(order)), payload["intent_hash"])
            self.assertEqual(reservation.reservation_id, payload["reservation_id"])
            self.assertEqual("external_consequence_not_yet_verified", payload["reason"])
            self.assertEqual("ConnectionError", payload["error"])
            consumed = audit_events(kernel, "permit_consumed")
            self.assertEqual(1, len(consumed))
            self.assertLess(
                kernel.audit.index(consumed[0]),
                kernel.audit.index(unknown[0]),
            )
            self.assertTrue(kernel.verify_audit())

            # The record survives a restart of the canonical state.
            reopened = SQLiteKernelState(path)
            self.addCleanup(reopened.close)
            reopened_kernel = GovernanceKernel(
                Policy(frozenset({"purchase_domain"}), 3_000),
                secret=b"test-secret",
                clock=lambda: NOW,
                state=reopened,
            )
            self.assertEqual(1, len(audit_events(reopened_kernel, "purchase_consequence_unknown")))
            self.assertTrue(reopened_kernel.verify_audit())

    def test_uncertain_live_purchase_records_unknown_outcome_in_memory_state(self):
        order = self.order()
        kernel, permit = self.kernel_with(order)
        budget = BudgetAccount()
        reservation = budget.reserve(order, now_ns=NOW)
        uncertain = UncertainRegistrar()

        with self.assertRaisesRegex(ConnectionError, "unknown"):
            DomainCommerceExecutor().execute(
                kernel, order, permit, uncertain, budget,
                reservation.reservation_id, now_ns=NOW,
            )
        unknown = audit_events(kernel, "purchase_consequence_unknown")
        self.assertEqual(1, len(unknown))
        self.assertEqual(order.order_hash, unknown[0]["payload"]["order_hash"])
        self.assertTrue(kernel.verify_audit())

    def test_uncertain_live_purchase_records_unknown_outcome_via_orchestrator(self):
        order = self.order()
        kernel, permit = self.kernel_with(order)
        orchestrator = PulpoOrchestrator(kernel)
        budget = BudgetAccount()
        reservation = budget.reserve(order, now_ns=NOW)
        uncertain = UncertainRegistrar()

        with self.assertRaisesRegex(ConnectionError, "unknown"):
            orchestrator.execute_domain_purchase(
                order, permit, uncertain, budget,
                reservation.reservation_id, now_ns=NOW,
            )
        unknown = audit_events(kernel, "purchase_consequence_unknown")
        self.assertEqual(1, len(unknown))
        self.assertEqual("external_consequence_not_yet_verified", unknown[0]["payload"]["reason"])

    # (b) Pre-purchase revalidation refuses state that changed after consume.
    def test_pre_purchase_revalidation_refuses_revoked_directive(self):
        verifier = HmacTestVerifier()
        kernel = GovernanceKernel(
            Policy(
                frozenset({"purchase_domain", "activate_directive", "revoke_directive"}),
                3_000,
                frozenset({"activate_directive", "revoke_directive"}),
                authority_trust=trust_for(verifier),
            ),
            secret=b"test-secret",
            approval_verifier=verifier,
            clock=lambda: NOW,
        )
        order = self.order()
        intent = purchase_intent(order)
        directive = Directive(
            directive_id="directive-v91-live",
            version=1,
            issuer_authority_id=verifier.authority_id,
            principal=intent.principal,
            allowed_actions=frozenset({"purchase_domain"}),
            resource_prefixes=("commerce:domain:",),
            max_cost=3_000,
            issued_at_ns=NOW - 1_000,
            expires_at_ns=NOW + 100_000,
        )
        controller = DirectiveAuthorityController(kernel)
        activation = signed_envelope(
            kernel,
            controller.authority_intent(controller.ACTIVATE, directive, operator_principal=OPERATOR),
            verifier,
            now_ns=NOW - 10,
            approval_id="approval-v91-activate",
            nonce="nonce-v91-activate",
        )
        self.assertEqual(
            "allow",
            controller.activate(directive, activation, operator_principal=OPERATOR).outcome,
        )
        decision = GovernedDirectiveProjection(kernel).evaluate(intent, directive)
        self.assertEqual("allow", decision.outcome)
        self.assertIsNotNone(decision.permit)

        def revoke_between_consume_and_purchase():
            revocation = signed_envelope(
                kernel,
                controller.authority_intent(controller.REVOKE, directive, operator_principal=OPERATOR),
                verifier,
                now_ns=NOW - 10,
                approval_id="approval-v91-revoke",
                nonce="nonce-v91-revoke",
            )
            self.assertEqual(
                "allow",
                controller.revoke(directive, revocation, operator_principal=OPERATOR).outcome,
            )

        budget = HookedBudget(BudgetAccount(), revoke_between_consume_and_purchase)
        reservation = budget.reserve(order, now_ns=NOW)
        registrar = FakeRegistrar(
            RegistrarResult("payment-1", 2_000, "a" * 64, "registration-1", order.domain, order.registrar)
        )
        with self.assertRaisesRegex(CommerceViolation, "directive_revoked"):
            DomainCommerceExecutor().execute(
                kernel, order, decision.permit, registrar, budget,
                reservation.reservation_id, now_ns=NOW,
            )
        # Refused before any transmission: the provider was never called.
        self.assertEqual(0, registrar.calls)
        refusals = audit_events(kernel, "purchase_revalidation_failed")
        self.assertEqual(1, len(refusals))
        self.assertEqual("directive_revoked", refusals[0]["payload"]["reason"])
        self.assertEqual(order.order_hash, refusals[0]["payload"]["order_hash"])
        self.assertTrue(kernel.verify_audit())

    def test_pre_purchase_revalidation_refuses_expired_permit(self):
        order = self.order()
        clock = [NOW]
        kernel, permit = self.kernel_with(
            order, clock=lambda: clock[0], permit_ttl_ns=100,
        )
        # The permit expires at NOW + 100. Advance the trusted clock between
        # consume (inside execute) and the provider call.
        budget = HookedBudget(BudgetAccount(), lambda: clock.__setitem__(0, NOW + 1_000))
        reservation = budget.reserve(order, now_ns=NOW)
        registrar = FakeRegistrar(
            RegistrarResult("payment-1", 2_000, "a" * 64, "registration-1", order.domain, order.registrar)
        )
        with self.assertRaisesRegex(CommerceViolation, "permit_expired"):
            DomainCommerceExecutor().execute(
                kernel, order, permit, registrar, budget,
                reservation.reservation_id, now_ns=NOW + 1_000,
            )
        self.assertEqual(0, registrar.calls)
        refusals = audit_events(kernel, "purchase_revalidation_failed")
        self.assertEqual(1, len(refusals))
        self.assertEqual("permit_expired", refusals[0]["payload"]["reason"])

    def test_pre_purchase_revalidation_refuses_policy_hash_change(self):
        order = self.order()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "kernel.sqlite3"
            state = SQLiteKernelState(path)
            self.addCleanup(state.close)
            kernel, permit = self.kernel_with(order, state=state)
            holder = {}

            def tamper_policy_hash():
                connection = sqlite3.connect(path)
                try:
                    connection.execute(
                        "UPDATE permits SET policy_hash = ? WHERE permit = ?",
                        ("0" * 64, permit),
                    )
                    connection.commit()
                finally:
                    connection.close()
                holder["tampered"] = True

            budget = HookedBudget(SQLiteBudgetAccount(path), tamper_policy_hash)
            reservation = budget.reserve(order, now_ns=NOW)
            registrar = FakeRegistrar(
                RegistrarResult("payment-1", 2_000, "a" * 64, "registration-1", order.domain, order.registrar)
            )
            with self.assertRaisesRegex(CommerceViolation, "permit_policy_mismatch"):
                DomainCommerceExecutor().execute(
                    kernel, order, permit, registrar, budget,
                    reservation.reservation_id, now_ns=NOW,
                )
            self.assertTrue(holder.get("tampered"))
            self.assertEqual(0, registrar.calls)
            refusals = audit_events(kernel, "purchase_revalidation_failed")
            self.assertEqual(1, len(refusals))
            self.assertEqual("permit_policy_mismatch", refusals[0]["payload"]["reason"])
            self.assertTrue(kernel.verify_audit())

    def test_revalidation_accepts_null_expiry_as_no_expiry(self):
        # NULL expires_at_ns is load-bearing fork semantics ("no expiry").
        # The re-check must not re-impose a stricter expiry invariant.
        order = self.order()
        state = InMemoryKernelState()
        kernel = GovernanceKernel(
            Policy(frozenset({"purchase_domain"}), 3_000),
            clock=lambda: NOW,
            state=state,
        )
        intent = purchase_intent(order)
        digest = kernel.intent_hash(intent)
        state.issue_permit(
            "permit-null-expiry", digest, "allow", NOW,
            policy_hash=kernel.policy_hash, issuer_hash=None, expires_at_ns=None,
        )
        self.assertTrue(state.consume_permit("permit-null-expiry", digest, NOW))
        self.assertEqual("valid", kernel.revalidate_consumed_permit("permit-null-expiry", intent))

    # (c) Happy path unchanged.
    def test_happy_path_unchanged(self):
        order = self.order()
        kernel, permit = self.kernel_with(order)
        budget = BudgetAccount()
        reservation = budget.reserve(order, now_ns=NOW)
        registrar = FakeRegistrar(
            RegistrarResult("payment-1", 2_000, "a" * 64, "registration-1", order.domain, order.registrar)
        )
        outcome = DomainCommerceExecutor().execute(
            kernel, order, permit, registrar, budget,
            reservation.reservation_id, now_ns=NOW,
        )
        self.assertTrue(outcome.authorized)
        self.assertTrue(outcome.capability_revoked)
        self.assertEqual("payment-1", outcome.payment.payment_id)
        self.assertEqual(2_000, outcome.payment.charged_cents)
        self.assertEqual("registration-1", outcome.delivery.registration_id)
        self.assertEqual(1, registrar.calls)
        self.assertEqual([], audit_events(kernel, "purchase_consequence_unknown"))
        self.assertEqual([], audit_events(kernel, "purchase_revalidation_failed"))
        self.assertTrue(kernel.verify_audit())

    # (d) Retry after an uncertain outcome is blocked, not silently retried.
    def test_retry_after_uncertain_outcome_is_blocked(self):
        order = self.order()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "commerce.sqlite3"
            kernel, permit = self.kernel_with(order)
            budget = SQLiteBudgetAccount(path)
            reservation = budget.reserve(order, now_ns=NOW)
            uncertain = UncertainRegistrar()
            executor = DomainCommerceExecutor()

            with self.assertRaisesRegex(ConnectionError, "unknown"):
                executor.execute(
                    kernel, order, permit, uncertain, budget,
                    reservation.reservation_id, now_ns=NOW,
                )

            # Same executor: the in-memory attempt set blocks the retry.
            should_not_run = FakeRegistrar(
                RegistrarResult("payment-1", 2_000, "a" * 64, "registration-1", order.domain, order.registrar)
            )
            with self.assertRaisesRegex(CommerceViolation, "duplicate_purchase_attempt"):
                executor.execute(
                    kernel, order, permit, should_not_run, budget,
                    reservation.reservation_id, now_ns=NOW,
                )
            self.assertEqual(0, should_not_run.calls)

            # Fresh executor after restart: the durable budget blocks it.
            restarted = SQLiteBudgetAccount(path)
            retry_kernel, retry_permit = self.kernel_with(order)
            with self.assertRaisesRegex(CommerceViolation, "already_attempted"):
                DomainCommerceExecutor().execute(
                    retry_kernel, order, retry_permit, should_not_run, restarted,
                    reservation.reservation_id, now_ns=NOW,
                )
            self.assertEqual(0, should_not_run.calls)
            self.assertEqual(1, len(audit_events(kernel, "purchase_consequence_unknown")))

    # Coordinator route.
    def custody_stack(self, path):
        custody = SQLiteGovernanceCustody(
            path,
            signing_secret=b"v91-custody-live-purchase",
            clock=lambda: NOW,
        )
        budget = SQLiteBudgetAccount(path)
        state = SQLiteKernelState(path)
        kernel = GovernanceKernel(
            Policy(frozenset({"purchase_domain"}), 3_000),
            secret=b"test-secret",
            clock=lambda: NOW,
            state=state,
        )
        coordinator = GovernedDomainAttemptCoordinator(kernel, custody, budget)
        self.addCleanup(state.close)
        return kernel, custody, budget, coordinator

    def test_coordinator_route_happy_path(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "custody.sqlite3"
            kernel, custody, budget, coordinator = self.custody_stack(path)
            order = self.order()
            intent = purchase_intent(order)
            target = kernel.lock_target("domain-v91", intent)
            decision = kernel.evaluate(intent)
            self.assertEqual("allow", decision.outcome)
            reservation = coordinator.reserve(order)
            registrar = FakeRegistrar(
                RegistrarResult("payment-1", 2_000, "a" * 64, "registration-1", order.domain, order.registrar)
            )
            outcome = DomainCommerceExecutor(coordinator=coordinator).execute(
                kernel, order, decision.permit, registrar, budget,
                reservation.reservation_id, now_ns=NOW,
                target_id=target.target_id, expected_target_hash=target.target_hash,
            )
            self.assertTrue(outcome.authorized)
            self.assertEqual(1, registrar.calls)
            self.assertEqual([], audit_events(kernel, "purchase_consequence_unknown"))
            self.assertEqual([], audit_events(kernel, "purchase_revalidation_failed"))
            self.assertEqual("permit_consumed", kernel.audit[-1]["event"])
            self.assertTrue(kernel.verify_audit())

    def test_coordinator_route_records_unknown_outcome_with_attempt_id(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "custody.sqlite3"
            kernel, custody, budget, coordinator = self.custody_stack(path)
            order = self.order()
            intent = purchase_intent(order)
            target = kernel.lock_target("domain-v91", intent)
            decision = kernel.evaluate(intent)
            reservation = coordinator.reserve(order)
            uncertain = UncertainRegistrar()

            with self.assertRaisesRegex(ConnectionError, "unknown"):
                DomainCommerceExecutor(coordinator=coordinator).execute(
                    kernel, order, decision.permit, uncertain, budget,
                    reservation.reservation_id, now_ns=NOW,
                    target_id=target.target_id, expected_target_hash=target.target_hash,
                )
            self.assertEqual(1, uncertain.calls)
            unknown = audit_events(kernel, "purchase_consequence_unknown")
            self.assertEqual(1, len(unknown))
            attempt_id = unknown[0]["payload"]["custody_attempt_id"]
            self.assertIsNotNone(attempt_id)
            # No attempt_authorized -> reconciliation_required edge exists in
            # the custody state machine, so the custody attempt stays
            # authorized and the canonical audit event is the
            # reconciliation-required record for the live path.
            self.assertEqual("attempt_authorized", custody.attempt(attempt_id).state)
            self.assertTrue(kernel.verify_audit())

    def test_coordinator_route_requires_target_and_matching_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "custody.sqlite3"
            kernel, _, budget, coordinator = self.custody_stack(path)
            order = self.order()
            decision = kernel.evaluate(purchase_intent(order))
            reservation = coordinator.reserve(order)
            registrar = FakeRegistrar(
                RegistrarResult("payment-1", 2_000, "a" * 64, "registration-1", order.domain, order.registrar)
            )
            with self.assertRaisesRegex(CommerceViolation, "custody_target_required"):
                DomainCommerceExecutor(coordinator=coordinator).execute(
                    kernel, order, decision.permit, registrar, budget,
                    reservation.reservation_id, now_ns=NOW,
                )
            self.assertEqual(0, registrar.calls)

            other_budget = SQLiteBudgetAccount(path)
            target = kernel.lock_target("domain-v91", purchase_intent(order))
            with self.assertRaisesRegex(CommerceViolation, "custody_budget_mismatch"):
                DomainCommerceExecutor(coordinator=coordinator).execute(
                    kernel, order, decision.permit, registrar, other_budget,
                    reservation.reservation_id, now_ns=NOW,
                    target_id=target.target_id, expected_target_hash=target.target_hash,
                )
            self.assertEqual(0, registrar.calls)


if __name__ == "__main__":
    unittest.main()
