import tempfile
import json
import sqlite3
import unittest
from contextlib import closing
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from pulpo.commerce import (
    DomainPurchaseRequest,
    DomainQuote,
    RegistrarResult,
    SQLiteBudgetAccount,
    assess_quote,
    purchase_intent,
)
from pulpo.custody import SQLiteGovernanceCustody
from pulpo.custody_reconcile import IndependentDomainObservation
from pulpo.kernel import GovernanceKernel, Policy
from pulpo.state import SQLiteKernelState
from tests.authority_support import HmacTestVerifier, signed_envelope, trust_for

from pulpo_custody_service.api import create_app
from pulpo_custody_service.core import AttemptHandle, DomainCustodyService, ServiceRejected


NOW = 31_000_000


class FakeRegistrar:
    def __init__(self):
        self.preflight_calls = 0
        self.purchase_calls = 0

    def preflight(self, order):
        self.preflight_calls += 1
        return "b" * 64

    def purchase(self, order, *, max_charge_cents, idempotency_key):
        self.purchase_calls += 1
        return RegistrarResult(
            payment_id="fake-order:1",
            charged_cents=order.purchase_price_cents,
            receipt_hash="c" * 64,
            registration_id="fake-registration:1",
            domain=order.domain,
            registrar=order.registrar,
        )


class FakeObserver:
    def __init__(self, custody):
        self.custody = custody
        self.calls = 0

    def observe(self, governed, order):
        self.calls += 1
        attempt = self.custody.attempt(governed.attempt_id)
        return IndependentDomainObservation(
            observation_id=f"fake-observer:{self.calls}",
            provider_request_id=attempt.provider_request_id,
            provider_request_status="succeeded",
            domain=order.domain,
            registrar=order.registrar,
            owner_ref=order.owner_ref,
            registered=True,
            payment_id="fake-order:1",
            charged_cents=order.purchase_price_cents,
            receipt_hash="d" * 64,
            privacy_enabled=True,
            dns_state="registered",
                   auto_renew_enabled=False,
        )


class CustodyServiceApiTests(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".sqlite3")
        self.path = Path(handle.name)
        handle.close()
        self.addCleanup(lambda: self.path.unlink(missing_ok=True))
        self.addCleanup(lambda: Path(str(self.path) + "-wal").unlink(missing_ok=True))
        self.addCleanup(lambda: Path(str(self.path) + "-shm").unlink(missing_ok=True))

    def order(self, suffix="v0"):
        request = DomainPurchaseRequest(
            request_id=f"service-{suffix}",
            principal="agent:hostile-worker",
            acceptable_domains=(f"pulpo-service-{suffix}.example",),
            max_purchase_cents=3_000,
            max_renewal_cents=2_500,
            approved_registrar="name.com",
            owner_ref="owner://iron-ember",
            privacy_required=True,
            prohibited_upsells=("hosting",),
            expires_at_ns=NOW + 100_000,
        )
        quote = DomainQuote(
            quote_id=f"service-quote-{suffix}",
            domain=f"pulpo-service-{suffix}.example",
            registrar="name.com",
            purchase_price_cents=2_000,
            renewal_price_cents=2_400,
            owner_ref="owner://iron-ember",
            privacy_enabled=True,
            upsells=(),
            expires_at_ns=NOW + 50_000,
        )
        result = assess_quote(
            request,
            quote,
            credential_ref="credential://service/namecom",
            now_ns=NOW,
        )
        self.assertIsNotNone(result.order)
        return result.order

    def build(self, *, require_approval=False):
        custody = SQLiteGovernanceCustody(
            self.path,
            signing_secret=b"service-custody-secret",
            clock=lambda: NOW,
        )
        budget = SQLiteBudgetAccount(self.path)
        verifier = HmacTestVerifier() if require_approval else None
        policy = (
            Policy(
                frozenset({"purchase_domain"}),
                3_000,
                frozenset({"purchase_domain"}),
                authority_trust=trust_for(verifier),
            )
            if verifier
            else Policy(frozenset({"purchase_domain"}), 3_000)
        )

        def kernel_factory():
            state = SQLiteKernelState(self.path)
            try:
                return GovernanceKernel(
                    policy,
                    secret=b"service-kernel-secret",
                    approval_verifier=verifier,
                    clock=lambda: NOW,
                    state=state,
                )
            except Exception:
                state.close()
                raise

        registrar = FakeRegistrar()
        observer = FakeObserver(custody)
        service = DomainCustodyService(
            kernel_factory=kernel_factory,
            custody=custody,
            budget=budget,
            registrar=registrar,
            observer=observer,
            observer_id="observer:service-v0",
            executor_id="executor:service-v0",
        )
        signing_kernel = GovernanceKernel(
            policy,
            secret=b"service-kernel-secret",
            approval_verifier=verifier,
            clock=lambda: NOW,
        )
        return TestClient(create_app(service)), service, registrar, observer, signing_kernel, verifier

    def commit(self, service, order):
        return service.proposals.create(
            order,
            availability_hash="a" * 64,
            created_at_ns=NOW - 100,
            expires_at_ns=order.expires_at_ns,
        )

    def test_changed_handle_cannot_flush_pending_evidence_or_reach_adapters(self):
        client, service, registrar, observer, _, _ = self.build()
        commitment = self.commit(service, self.order())
        handle = service.authorize_commitment(commitment.commitment_id)
        head = service.custody.snapshot()
        service.custody.authorize_attempt(expected_epoch=head.epoch, expected_state_root=head.state_root,
            object_hash="1"*64,target_hash="2"*64,permit_hash="3"*64,authorization_hash="4"*64)
        before = service.custody.snapshot()
        with service._kernel_session() as kernel:
            audit = kernel.audit
        for field, value in [("attempt_id","f"*64),("order_hash","f"*64),("target_hash","f"*64),
                             ("reservation_id","substitute"),("reserved_cents",1),
                             ("state","request_transmitted"),("schema","unknown")]:
            for operation in ["execute","reconcile"]:
                with self.subTest(field=field, operation=operation):
                    response = client.post(f"/v1/domain-attempts/{handle.attempt_id}/{operation}",
                        json={"handle":asdict(replace(handle,**{field:value}))})
                    self.assertEqual(400 if field == "attempt_id" else 409,response.status_code,response.text)
                    self.assertEqual(before,service.custody.snapshot())
                    self.assertEqual(1,service.evidence.pending_count())
                    self.assertEqual(1000,service.budget.available_cents)
        with service._kernel_session() as kernel:
            self.assertEqual(audit,kernel.audit)
        self.assertEqual((0,0,0),(registrar.preflight_calls,registrar.purchase_calls,observer.calls))

    def test_complete_reference_survives_service_restart_and_replay_remains_denied(self):
        _, first, original_registrar, _, _, _ = self.build()
        commitment = self.commit(first,self.order())
        handle = first.authorize_commitment(commitment.commitment_id)
        client, second, registrar, _, _, _ = self.build()
        operation = {"handle":asdict(handle)}
        response = client.post(f"/v1/domain-attempts/{handle.attempt_id}/execute",json=operation)
        self.assertEqual(200,response.status_code,response.text)
        client, third, third_registrar, observer, _, _ = self.build()
        self.assertEqual(409,client.post(f"/v1/domain-attempts/{handle.attempt_id}/execute",json=operation).status_code)
        response = client.post(f"/v1/domain-attempts/{handle.attempt_id}/reconcile",json=operation)
        self.assertEqual(200,response.status_code,response.text)
        self.assertEqual("success",response.json()["outcome"])
        self.assertEqual((0,1,0),(original_registrar.purchase_calls,registrar.purchase_calls,third_registrar.purchase_calls))
        self.assertEqual(1,observer.calls)
        self.assertEqual(0,third.evidence.pending_count())

    def _alter_authorization_append(self, service, alter):
        original = service._kernel_factory
        def factory():
            kernel = original()
            append = kernel._append
            def intercept(event,payload):
                if event == "custody_domain_authorization":
                    payload = json.loads(json.dumps(payload))
                    alter(payload)
                return append(event,payload)
            kernel._append = intercept
            return kernel
        return patch.object(service,"_kernel_factory",factory)

    def test_missing_authorization_after_append_failure_cannot_be_recreated_from_worker(self):
        _, service, registrar, _, _, _ = self.build()
        order = self.order()
        commitment = self.commit(service,order)
        def fail(payload):
            raise RuntimeError("synthetic authorization append failure")
        with self._alter_authorization_append(service,fail):
            with self.assertRaises(ServiceRejected):
                service.authorize_commitment(commitment.commitment_id)
        with closing(sqlite3.connect(self.path)) as connection:
            attempt = connection.execute("SELECT attempt_id,target_hash FROM custody_attempts WHERE object_hash=?",(order.order_hash,)).fetchone()
            reservation = connection.execute("SELECT reservation_id FROM commerce_reservations").fetchone()
        self.assertIsNotNone(attempt)
        handle = AttemptHandle(attempt[0],order.order_hash,attempt[1],reservation[0],2000,service.custody.ATTEMPT_AUTHORIZED)
        before = service.custody.snapshot()
        self.assertEqual(1,service.evidence.pending_count())
        with self.assertRaises(ServiceRejected):
            service.execute(handle)
        self.assertEqual(before,service.custody.snapshot())
        self.assertEqual(1,service.evidence.pending_count())
        self.assertEqual(0,registrar.purchase_calls)
        with self.assertRaises(ServiceRejected):
            service.authorize_commitment(commitment.commitment_id)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual((1,1),connection.execute("SELECT COUNT(*),SUM(spent) FROM permits").fetchone())

    def test_duplicate_authorization_preimages_fail_closed(self):
        _, service, registrar, _, _, _ = self.build()
        handle = service.authorize_commitment(self.commit(service,self.order()).commitment_id)
        with service._kernel_session() as kernel:
            payload = next(row["payload"] for row in kernel.audit if row["event"]=="custody_domain_authorization")
            kernel._append("custody_domain_authorization",payload)
        before = service.custody.snapshot()
        with self.assertRaises(ServiceRejected):
            service.execute(handle)
        self.assertEqual(before,service.custody.snapshot())
        self.assertEqual((0,0),(registrar.preflight_calls,registrar.purchase_calls))

    def test_valid_audit_cannot_ratify_changed_commitment_or_receipt(self):
        alterations = [lambda p:p.update(policy_hash="f"*64),
                       lambda p:p["custody"]["receipt"].update(signature="0"*64),
                       lambda p:p["custody"].update(extra="untrusted")]
        for number, alter in enumerate(alterations):
            with self.subTest(number=number), tempfile.TemporaryDirectory() as directory:
                previous_path = self.path
                self.path = Path(directory)/"synthetic.sqlite3"
                try:
                    _,service,registrar,observer,_,_ = self.build()
                    with self._alter_authorization_append(service,alter):
                        handle = service.authorize_commitment(self.commit(service,self.order()).commitment_id)
                    with service._kernel_session() as kernel:
                        self.assertTrue(kernel.verify_audit())
                    before = service.custody.snapshot()
                    with self.assertRaises(ServiceRejected):
                        service.execute(handle)
                    with self.assertRaises(ServiceRejected):
                        service.reconcile(handle)
                    self.assertEqual(before,service.custody.snapshot())
                    self.assertEqual((0,0),(registrar.preflight_calls,registrar.purchase_calls))
                    self.assertEqual(0,observer.calls)
                finally:
                    self.path = previous_path

    def test_valid_handle_can_project_pending_evidence_before_one_transmission(self):
        _,service,registrar,_,_,_ = self.build()
        handle = service.authorize_commitment(self.commit(service,self.order()).commitment_id)
        head = service.custody.snapshot()
        service.custody.authorize_attempt(expected_epoch=head.epoch,expected_state_root=head.state_root,
            object_hash="1"*64,target_hash="2"*64,permit_hash="3"*64,authorization_hash="4"*64)
        claim = service.execute(handle)
        self.assertIsNotNone(claim)
        self.assertEqual(1,registrar.purchase_calls)
        self.assertEqual(0,service.evidence.pending_count())

    def test_worker_uses_proposal_reference_then_handle_only(self):
        client, service, registrar, observer, _, _ = self.build()
        order = self.order()
        commitment = self.commit(service, order)

        authorized = client.post(
            "/v1/domain-attempts",
            json={"proposal_commitment_id": commitment.commitment_id},
        )
        self.assertEqual(200, authorized.status_code, authorized.text)
        handle = authorized.json()
        self.assertNotIn("permit", handle)
        self.assertNotIn("secret", handle)
        self.assertNotIn("now_ns", handle)
        self.assertEqual("attempt_authorized", handle["state"])
        self.assertEqual(0, service.evidence.pending_count())

        operation = {"handle": handle}
        executed = client.post(
            f"/v1/domain-attempts/{handle['attempt_id']}/execute",
            json=operation,
        )
        self.assertEqual(200, executed.status_code, executed.text)
        self.assertEqual("provider_claim_recorded", executed.json()["status"])
        self.assertEqual(1, registrar.preflight_calls)
        self.assertEqual(1, registrar.purchase_calls)
        self.assertEqual(0, service.evidence.pending_count())

        replay = client.post(
            f"/v1/domain-attempts/{handle['attempt_id']}/execute",
            json=operation,
        )
        self.assertEqual(409, replay.status_code)
        self.assertEqual(1, registrar.purchase_calls)

        reconciled = client.post(
            f"/v1/domain-attempts/{handle['attempt_id']}/reconcile",
            json=operation,
        )
        self.assertEqual(200, reconciled.status_code, reconciled.text)
        self.assertEqual("success", reconciled.json()["outcome"])
        self.assertEqual(1, observer.calls)
        self.assertEqual("reconciled_success", service.status(handle["attempt_id"])["state"])
        self.assertEqual(0, service.evidence.pending_count())

    def test_byte_identical_external_order_has_no_authority_without_commitment(self):
        client, service, _, _, _, _ = self.build()
        order = self.order()
        external_order = asdict(order)
        external_order["prohibited_upsells"] = list(external_order["prohibited_upsells"])

        response = client.post(
            "/v1/domain-attempts",
            json={"order": external_order},
        )
        self.assertEqual(422, response.status_code)
        self.assertEqual(0, service.budget.reserved_cents)
        self.assertEqual(0, service.custody.snapshot().epoch)

        # The former direct approval-challenge route is not part of the hostile
        # worker surface either.
        challenge = client.post(
            "/v1/domain-approval-challenges",
            json={"order": external_order},
        )
        self.assertEqual(404, challenge.status_code)

    def test_worker_cannot_inject_order_time_budget_or_provider_fields(self):
        client, service, _, _, _, _ = self.build()
        commitment = self.commit(service, self.order())
        for field, value in (
            ("order", {"domain": "attacker.example"}),
            ("now_ns", 1),
            ("budget_available_cents", 3_000),
            ("custody_epoch", 0),
            ("permit", "worker-forged"),
            ("provider_token", "worker-secret"),
        ):
            response = client.post(
                "/v1/domain-attempts",
                json={"proposal_commitment_id": commitment.commitment_id, field: value},
            )
            self.assertEqual(422, response.status_code, field)
        self.assertEqual(0, service.budget.reserved_cents)
        self.assertEqual(0, service.custody.snapshot().epoch)

    def test_copied_handle_cannot_execute_twice_or_substitute_order_hash(self):
        client, service, registrar, _, _, _ = self.build()
        order = self.order()
        commitment = self.commit(service, order)
        handle = client.post(
            "/v1/domain-attempts",
            json={"proposal_commitment_id": commitment.commitment_id},
        ).json()
        operation = {"handle": handle}
        self.assertEqual(
            200,
            client.post(
                f"/v1/domain-attempts/{handle['attempt_id']}/execute",
                json=operation,
            ).status_code,
        )

        forged = dict(handle)
        forged["order_hash"] = "0" * 64
        response = client.post(
            f"/v1/domain-attempts/{handle['attempt_id']}/execute",
            json={"handle": forged},
        )
        self.assertEqual(409, response.status_code)
        self.assertEqual(1, registrar.purchase_calls)

        full_order_smuggle = client.post(
            f"/v1/domain-attempts/{handle['attempt_id']}/execute",
            json={"handle": handle, "order": asdict(order)},
        )
        self.assertEqual(422, full_order_smuggle.status_code)

    def test_approval_required_policy_binds_signature_to_committed_order(self):
        client, service, _, _, signing_kernel, verifier = self.build(require_approval=True)

        missing_order = self.order("missing")
        missing_commitment = self.commit(service, missing_order)
        missing = client.post(
            "/v1/domain-attempts",
            json={"proposal_commitment_id": missing_commitment.commitment_id},
        )
        self.assertEqual(403, missing.status_code)

        approved_order = self.order("approved")
        approved_commitment = self.commit(service, approved_order)
        envelope = signed_envelope(
            signing_kernel,
            purchase_intent(approved_order),
            verifier,
            now_ns=NOW - 10,
            approval_id="service-approval-v0",
            nonce="service-nonce-v0",
        )
        approved = client.post(
            "/v1/domain-attempts",
            json={
                "proposal_commitment_id": approved_commitment.commitment_id,
                "approval": asdict(envelope),
            },
        )
        self.assertEqual(200, approved.status_code, approved.text)
        self.assertEqual("attempt_authorized", approved.json()["state"])

        forged_order = self.order("forged")
        forged_commitment = self.commit(service, forged_order)
        bad = asdict(
            signed_envelope(
                signing_kernel,
                purchase_intent(forged_order),
                verifier,
                now_ns=NOW - 10,
                approval_id="service-approval-forged",
                nonce="service-nonce-forged",
            )
        )
        bad["signature"] = "0" * len(bad["signature"])
        rejected = client.post(
            "/v1/domain-attempts",
            json={
                "proposal_commitment_id": forged_commitment.commitment_id,
                "approval": bad,
            },
        )
        self.assertEqual(403, rejected.status_code)


if __name__ == "__main__":
    unittest.main()
