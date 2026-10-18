"""Regression coverage for canonical permit, budget and execution boundaries.

These bounded software fixtures make no production exploit claim.
All credentials, costs, clocks, providers and state are disposable fixtures.
"""
import inspect,json,pathlib,sys,tempfile,threading,unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pulpo import GovernanceKernel,Intent,Policy
from pulpo.state import InMemoryKernelState,SQLiteKernelState
from tests.authority_support import HmacTestVerifier,signed_envelope,trust_for
from tests import test_custody_executor as executor_fixture

NOW=1_000_000
OBSERVATIONS=[]
def observe(case,**values):OBSERVATIONS.append(dict(case=case,**values))

class GovernanceSecurityRegressions(unittest.TestCase):
    def test_non_finite_cost_must_not_obtain_permit(self):
        k=GovernanceKernel(Policy(frozenset({'write'}),10),clock=lambda:NOW)
        self.assertEqual('deny',k.evaluate(Intent('agent:test','write','repo:test',11)).outcome)
        d=k.evaluate(Intent('agent:test','write','repo:test',float('nan')))
        observe('nan_cost',outcome=d.outcome,permit_issued=d.permit is not None)
        self.assertEqual('deny',d.outcome)

    def test_expired_approval_must_not_leave_indefinite_execution_permit(self):
        results=[]
        with tempfile.TemporaryDirectory() as folder:
            for label,state in [('memory',InMemoryKernelState()),('sqlite',SQLiteKernelState(pathlib.Path(folder)/'expiry.sqlite'))]:
                now=[NOW];verifier=HmacTestVerifier()
                k=GovernanceKernel(Policy(frozenset({'write'}),10,frozenset({'write'}),authority_trust=trust_for(verifier)),approval_verifier=verifier,clock=lambda:now[0],state=state)
                intent=Intent('agent:test','write','repo:test',1,'session:test')
                envelope=signed_envelope(k,intent,verifier,now_ns=NOW)
                decision=k.evaluate_with_approval(intent,envelope)
                self.assertEqual('allow',decision.outcome)
                now[0]=envelope.expires_at_ns+100_000
                accepted=k.consume(decision.permit,intent)
                results.append(accepted);observe('approval_expiry',backend=label,accepted_after_expiry=accepted)
                if hasattr(state,'close'):state.close()
        self.assertEqual([False,False],results)

    def test_policy_narrowing_must_invalidate_old_permit(self):
        results=[]
        with tempfile.TemporaryDirectory() as folder:
            for label,state in [('memory',InMemoryKernelState()),('sqlite',SQLiteKernelState(pathlib.Path(folder)/'policy.sqlite'))]:
                intent=Intent('agent:test','write','repo:test',1)
                old=GovernanceKernel(Policy(frozenset({'write'}),10),state=state,clock=lambda:NOW,secret=b'old-fixture-key')
                permit=old.evaluate(intent).permit
                new=GovernanceKernel(Policy(frozenset({'inspect'}),0),state=state,clock=lambda:NOW+1,secret=b'rotated-fixture-key')
                denied=new.evaluate(intent)
                self.assertEqual('deny',denied.outcome)
                accepted=new.consume(permit,intent)
                observe('policy_narrowing',backend=label,fresh_evaluation=denied.outcome,old_permit_accepted=accepted)
                results.append(accepted)
                if hasattr(state,'close'):state.close()
        self.assertEqual([False,False],results)

    def test_inmemory_permit_consumption_must_be_atomic(self):
        k=GovernanceKernel(Policy(frozenset({'write'}),10),clock=lambda:NOW)
        intent=Intent('agent:test','write','repo:test',1);permit=k.evaluate(intent).permit
        source,start=inspect.getsourcelines(InMemoryKernelState.consume_permit)
        line=start+next(i for i,text in enumerate(source) if 'if valid: self._spent.add(permit)' in text)
        barrier=threading.Barrier(2)
        second_valid=threading.Event()
        schedule_lock=threading.Lock()
        reached=[0]
        def worker():
            def trace(frame,event,arg):
                if event=='line' and frame.f_code is InMemoryKernelState.consume_permit.__code__ and frame.f_lineno==line and frame.f_locals.get('valid') is True:
                    with schedule_lock:
                        reached[0]+=1
                        first=reached[0]==1
                    if first:
                        second_valid.wait(timeout=0.2)
                    else:
                        second_valid.set()
                return trace
            barrier.wait(timeout=5)
            sys.settrace(trace)
            try:return k.consume(permit,intent)
            finally:sys.settrace(None)
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:worker(),range(2)))
        observe('memory_replay_race',accepted_count=sum(results),audit_valid=k.verify_audit(),method='trace barrier schedules two consumers after validity check, before spent-set write; no validation result is changed')
        self.assertEqual(1,sum(results))

    def test_sqlite_permit_consumption_is_atomic_control(self):
        with tempfile.TemporaryDirectory() as folder:
            path=pathlib.Path(folder)/'race.sqlite';s=SQLiteKernelState(path)
            k=GovernanceKernel(Policy(frozenset({'write'}),10),state=s,clock=lambda:NOW)
            intent=Intent('agent:test','write','repo:test',1);permit=k.evaluate(intent).permit;s.close()
            barrier=threading.Barrier(2)
            def worker(_):
                state=SQLiteKernelState(path)
                try:
                    kernel=GovernanceKernel(Policy(frozenset({'write'}),10),state=state,clock=lambda:NOW)
                    barrier.wait(timeout=5);return kernel.consume(permit,intent)
                finally:state.close()
            with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(worker,range(2)))
            observe('sqlite_replay_control',accepted_count=sum(results))
            self.assertEqual(1,sum(results))

    def test_expired_custody_order_must_not_reach_provider(self):
        f=executor_fixture.CustodyExecutorTests();f.setUp()
        try:
            custody,budget,governed,order=f.governed_attempt()
            custody._clock=lambda:order.expires_at_ns+1
            adapter=executor_fixture.FakeCustodyRegistrar()
            try:executor_fixture.TrustedDomainExecutor(custody,executor_id='executor:audit').execute(governed,order,adapter)
            except executor_fixture.CustodyViolation as error:self.assertEqual('order_expired',str(error))
            observe('expired_order',preflight_calls=adapter.preflight_calls,provider_calls=adapter.calls,now=order.expires_at_ns+1,expiry=order.expires_at_ns)
            self.assertEqual(0,adapter.calls)
        finally:f.doCleanups()

    def test_expiry_during_preflight_must_not_reach_provider(self):
        f=executor_fixture.CustodyExecutorTests();f.setUp()
        try:
            custody,budget,governed,order=f.governed_attempt()
            class SlowPreflight(executor_fixture.FakeCustodyRegistrar):
                def preflight(self,order):
                    value=super().preflight(order)
                    custody._clock=lambda:order.expires_at_ns+1
                    return value
            adapter=SlowPreflight()
            try:executor_fixture.TrustedDomainExecutor(custody,executor_id='executor:audit').execute(governed,order,adapter)
            except executor_fixture.CustodyViolation as error:self.assertEqual('order_expired',str(error))
            observe('expiry_during_preflight',provider_calls=adapter.calls)
            self.assertEqual(0,adapter.calls)
        finally:f.doCleanups()

    def test_legacy_unbound_permit_is_not_retroactively_authorized(self):
        with tempfile.TemporaryDirectory() as folder:
            path=pathlib.Path(folder)/'legacy.sqlite'
            state=SQLiteKernelState(path)
            intent=Intent('agent:test','write','repo:test',1)
            state.issue_permit('legacy-permit',GovernanceKernel.intent_hash(intent),'fixture',NOW)
            state.close()
            state=SQLiteKernelState(path)
            try:
                kernel=GovernanceKernel(Policy(frozenset({'write'}),10),state=state,clock=lambda:NOW+1)
                self.assertFalse(kernel.consume('legacy-permit',intent))
                self.assertTrue(kernel.verify_audit())
            finally:state.close()

    def test_approval_deadline_and_policy_binding_survive_sqlite_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            path=pathlib.Path(folder)/'restart.sqlite'
            state=SQLiteKernelState(path);verifier=HmacTestVerifier()
            policy=Policy(frozenset({'write'}),10,frozenset({'write'}),authority_trust=trust_for(verifier))
            kernel=GovernanceKernel(policy,state=state,approval_verifier=verifier,clock=lambda:NOW)
            intent=Intent('agent:test','write','repo:test',1)
            envelope=signed_envelope(kernel,intent,verifier,now_ns=NOW)
            permit=kernel.evaluate_with_approval(intent,envelope).permit
            state.close();state=SQLiteKernelState(path)
            try:
                kernel=GovernanceKernel(policy,state=state,approval_verifier=verifier,clock=lambda:envelope.expires_at_ns)
                self.assertFalse(kernel.consume(permit,intent))
                self.assertTrue(kernel.verify_audit())
            finally:state.close()

    def test_bool_fractional_and_nonfinite_costs_are_denied(self):
        kernel=GovernanceKernel(Policy(frozenset({'write'}),10),clock=lambda:NOW)
        for cost in (True,False,1.5,float('nan'),float('inf'),float('-inf')):
            with self.subTest(cost=repr(cost)):
                decision=kernel.evaluate(Intent('agent:test','write','repo:test',cost))
                self.assertEqual(('deny',None),(decision.outcome,decision.permit))


    def test_expiry_during_transmission_evidence_projection_blocks_purchase(self):
        f=executor_fixture.CustodyExecutorTests();f.setUp()
        try:
            custody,budget,governed,order=f.governed_attempt()
            adapter=executor_fixture.FakeCustodyRegistrar()
            executor=executor_fixture.TrustedDomainExecutor(custody,executor_id='executor:audit')
            original=executor._project_evidence
            def project():
                original()
                if custody.attempt(governed.attempt_id).state==custody.REQUEST_TRANSMITTED:
                    custody._clock=lambda:order.expires_at_ns+1
            executor._project_evidence=project
            with self.assertRaisesRegex(executor_fixture.CustodyViolation,'order_expired'):
                executor.execute(governed,order,adapter)
            self.assertEqual(0,adapter.calls)
            self.assertEqual(custody.REQUEST_TRANSMITTED,custody.attempt(governed.attempt_id).state)
            with self.assertRaises(executor_fixture.CustodyViolation):
                executor.execute(governed,order,adapter)
            self.assertEqual(0,adapter.calls)
        finally:f.doCleanups()

    def test_deadline_is_checked_inside_transmission_transaction(self):
        f=executor_fixture.CustodyExecutorTests();f.setUp()
        try:
            custody,budget,governed,order=f.governed_attempt()
            head=custody.snapshot()
            custody.claim_attempt(expected_epoch=head.epoch,expected_state_root=head.state_root,
                attempt_id=governed.attempt_id,executor_id='executor:audit')
            head=custody.snapshot()
            custody._clock=lambda:order.expires_at_ns
            with self.assertRaisesRegex(executor_fixture.CustodyViolation,'order_expired'):
                custody.authorize_transmission(expected_epoch=head.epoch,expected_state_root=head.state_root,
                    attempt_id=governed.attempt_id,expires_at_ns=order.expires_at_ns)
            self.assertEqual(head,custody.snapshot())
            self.assertEqual(custody.ATTEMPT_CLAIMED,custody.attempt(governed.attempt_id).state)
        finally:f.doCleanups()

    def test_explicit_kernel_key_rotation_rejects_old_issuer_permit(self):
        with tempfile.TemporaryDirectory() as folder:
            for state in (InMemoryKernelState(),SQLiteKernelState(pathlib.Path(folder)/'issuer.sqlite')):
                try:
                    policy=Policy(frozenset({'write'}),10)
                    intent=Intent('agent:test','write','repo:test',1)
                    old=GovernanceKernel(policy,state=state,secret=b'old-fixture-key',clock=lambda:NOW)
                    permit=old.evaluate(intent).permit
                    rotated=GovernanceKernel(policy,state=state,secret=b'new-fixture-key',clock=lambda:NOW+1)
                    self.assertFalse(rotated.consume(permit,intent))
                    self.assertTrue(old.consume(permit,intent))
                finally:
                    if hasattr(state,'close'):state.close()

if __name__=='__main__':unittest.main(verbosity=2)
