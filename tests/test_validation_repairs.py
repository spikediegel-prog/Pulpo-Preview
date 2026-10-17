"""Local adversarial probes. Synthetic SQLite and fake provider only."""
import json
import hmac
from hashlib import sha256
import random
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from pulpo import GovernanceKernel, Policy, SQLiteKernelState, StateIntegrityError
from pulpo.audit_parallel import AuditVerificationEngine
from pulpo.custody import CustodyViolation, SQLiteGovernanceCustody
from pulpo.custody_executor import TrustedDomainExecutor, ExternalConsequenceUnknown
from pulpo.custody_evidence import SQLiteCustodyEvidenceConvergence
from pulpo.state import ApprovalUse
from tests import test_custody_executor as executor_fixtures
from tests.test_custody_executor import FakeCustodyRegistrar
from tests import test_custody_evidence as evidence_fixtures

OBSERVATIONS = []

def observe(name, **values):
    OBSERVATIONS.append(dict(name=name, **values))

def accepted(call):
    try:
        return bool(call()), None
    except Exception as exc:
        return False, type(exc).__name__ + ': ' + str(exc)

class VerifierTests(unittest.TestCase):
    def exercise(self, mutation, workers, cache):
        with tempfile.TemporaryDirectory() as directory, closing(SQLiteKernelState(Path(directory) / 'synthetic.sqlite3')) as state:
            for i in range(3):
                state.append('sample', {'i': i}, i + 1)
            kernel = GovernanceKernel(Policy(frozenset(), 0), state=state, secret=b'test-only')
            engine = AuditVerificationEngine(workers=workers, cache_size=cache, parallel_threshold=1, batch_size=2)
            self.addCleanup(engine.close)
            self.assertTrue(engine.verify_rows(state.audit_verification_rows()))
            self.assertTrue(engine.verify_rows(state.audit_verification_rows()))
            if mutation == 'fractional_timestamp':
                sql = 'UPDATE audit SET timestamp_ns = 1.5 WHERE sequence = 1'
            elif mutation == 'malformed_json':
                sql = "UPDATE audit SET payload_json = '{bad' WHERE sequence = 1"
            elif mutation == 'changed_payload':
                sql = "UPDATE audit SET payload_json = '{}' WHERE sequence = 1"
            elif mutation == 'deep_json':
                sql = None
            else:
                sql = None
            with state._connection:
                if sql:
                    state._connection.execute(sql)
                elif mutation == 'deep_json':
                    state._connection.execute('UPDATE audit SET payload_json=? WHERE sequence=1', ('[' * 1500 + '0' + ']' * 1500,))
            normal, normal_error = accepted(kernel.verify_audit)
            accelerated, accelerated_error = accepted(lambda: engine.verify_rows(state.audit_verification_rows()))
            boots = {}
            for label, accelerator in [('normal', None), ('accelerated', engine)]:
                try:
                    GovernanceKernel(Policy(frozenset(), 0), state=state, secret=b'test-only', audit_verification_engine=accelerator)
                    boots[label] = True
                except StateIntegrityError:
                    boots[label] = False
            after_acceleration, after_error = accepted(lambda: GovernanceKernel(
                Policy(frozenset(), 0), state=state, secret=b'test-only') is not None)
            observe(self.id(), mutation=mutation, workers=workers, cache=cache, normal=normal,
                    accelerated=accelerated, normal_error=normal_error, accelerated_error=accelerated_error,
                    bootstrap_accepted=boots, pool_used=engine._executor is not None,
                    normal_bootstrap_after_accelerated=after_acceleration, after_error=after_error)
            expected = mutation == 'valid'
            self.assertEqual((expected, expected), (normal, accelerated))
            self.assertEqual({'normal': expected, 'accelerated': expected}, boots)

def verifier_case(mutation, workers, cache):
    return lambda self: self.exercise(mutation, workers, cache)

for _mutation in ['valid', 'fractional_timestamp', 'malformed_json', 'changed_payload', 'deep_json']:
    for _workers, _cache in [(0, 0), (0, 16), (2, 0)]:
        setattr(VerifierTests, f'test_{_mutation}_workers{_workers}_cache{_cache}', verifier_case(_mutation, _workers, _cache))

class HandleTests(unittest.TestCase):
    def exercise(self, field):
        fixture = executor_fixtures.CustodyExecutorTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        custody, budget, governed, order = fixture.governed_attempt()
        head = custody.snapshot()
        custody.claim_attempt(expected_epoch=head.epoch, expected_state_root=head.state_root,
            attempt_id=governed.attempt_id, executor_id='executor:test')
        evidence = SQLiteCustodyEvidenceConvergence(custody)
        # Real pending obligation from a synthetic, unrelated attempt. An invalid
        # input must not use the executor callback to flush canonical evidence.
        head = custody.snapshot()
        custody.authorize_attempt(expected_epoch=head.epoch, expected_state_root=head.state_root,
            object_hash='1'*64, target_hash='2'*64, permit_hash='3'*64, authorization_hash='4'*64)
        self.assertEqual(1, evidence.pending_count())
        if field == 'custody':
            modified = replace(governed, custody=replace(governed.custody, attempt_id='f'*64))
        elif field in ['reserved_cents', 'budget_ceiling_cents']:
            modified = replace(governed, **{field: 1})
        elif field == 'valid':
            modified = governed
        else:
            modified = replace(governed, **{field: 'f'*64})
        before = custody.snapshot()
        adapter = FakeCustodyRegistrar()
        error = None
        claim = None
        try:
            claim = TrustedDomainExecutor(custody, executor_id='executor:test',
                evidence_projector=evidence.project_all).execute(modified, order, adapter)
        except Exception as exc:
            error = type(exc).__name__ + ': ' + str(exc)
        after = custody.snapshot()
        observe(self.id(), field=field, error=error, claim_returned=claim is not None,
            preflight_calls=adapter.preflight_calls, provider_calls=adapter.calls,
            epoch_before=before.epoch, epoch_after=after.epoch,
            pending_after=evidence.pending_count(), budget_available=budget.available_cents)
        # Pending unrelated evidence blocks an otherwise valid attempt too.
        self.assertEqual((0, 0, before, 1),
            (adapter.preflight_calls, adapter.calls, after, evidence.pending_count()))
        self.assertIsNotNone(error)

for _field in ['attempt_id', 'order_hash', 'target_hash', 'intent_hash', 'policy_hash',
               'reservation_id', 'reserved_cents', 'budget_ceiling_cents', 'canonical_audit_tip', 'custody']:
    setattr(HandleTests, 'test_substitute_' + _field, lambda self, field=_field: self.exercise(field))

class StatefulTests(unittest.TestCase):
    def test_old_authenticated_malformed_checkpoint_is_rejected_without_republication(self):
        from pulpo.state import _canonical
        with tempfile.TemporaryDirectory() as directory, closing(SQLiteKernelState(Path(directory)/'old-cache.sqlite3')) as state:
            state.append('sample', {}, 1)
            with state._connection:
                state._connection.execute('UPDATE audit SET timestamp_ns=1.5')
                rows = state._connection.execute('SELECT * FROM audit ORDER BY sequence').fetchall()
                # Exactly the cache the old coercing verifier could publish.
                body = {'schema':'pulpo.audit-checkpoint.v1','sequence':rows[-1][0],
                        'head':rows[-1][-1], 'prefix_digest':sha256(_canonical(rows)).hexdigest()}
                value = _canonical({**body,'mac':hmac.new(b'old-cache-test-only',
                    b'pulpo.audit-checkpoint.v1\0'+_canonical(body),sha256).hexdigest()}).decode()
                state._connection.execute('INSERT INTO audit_verification_checkpoint VALUES(1,?)',(value,))
            with self.assertRaises(StateIntegrityError):
                GovernanceKernel(Policy(frozenset(),0),state=state,secret=b'old-cache-test-only')
            self.assertEqual(value,state._connection.execute('SELECT checkpoint_json FROM audit_verification_checkpoint').fetchone()[0])

    def test_cache_numeric_type_aliases_and_malformed_row_shapes_rejected(self):
        from tests.test_parallel_performance import audit_row
        row=audit_row('0'*64,'sample',{},1)
        for workers in [0,2]:
            with AuditVerificationEngine(workers=workers,cache_size=16,parallel_threshold=1) as engine:
                self.assertTrue(engine.verify_rows([row]))
                for timestamp in [1.0, True, '1', None]:
                    self.assertFalse(engine.verify_rows([(*row[:3],timestamp,row[4])]))
                for malformed in [None,(),row[:-1],(*row,1),([], *row[1:]),(b'sample',*row[1:])]:
                    self.assertFalse(engine.verify_rows([malformed]))

    def test_receipt_substitution_and_numeric_handle_aliases_have_zero_side_effects(self):
        fixture=executor_fixtures.CustodyExecutorTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        custody,_,governed,order=fixture.governed_attempt()
        receipt=governed.custody.receipt
        variants=[replace(governed,reserved_cents=float(governed.reserved_cents)),
                  replace(governed,budget_ceiling_cents=float(governed.budget_ceiling_cents)),
                  replace(governed,custody=None)]
        for field,value in [('epoch',float(receipt.epoch)),('object_hash','f'*64),
                            ('state_root','f'*64),('previous_root','f'*64),
                            ('transition_hash','f'*64),('transition_type','request_transmitted'),
                            ('custody_time_ns',receipt.custody_time_ns+1),('signature','0'*64),
                            ('schema','unknown')]:
            variants.append(replace(governed,custody=replace(governed.custody,receipt=replace(receipt,**{field:value}))))
        before=custody.snapshot()
        adapter=FakeCustodyRegistrar()
        executor=TrustedDomainExecutor(custody,executor_id='executor:test',
            evidence_projector=lambda: self.fail('invalid handle projected evidence'))
        for variant in variants:
            with self.subTest(variant=variant), self.assertRaises(CustodyViolation):
                executor.execute(variant,order,adapter)
            self.assertEqual(before,custody.snapshot())
        self.assertEqual((0,0),(adapter.preflight_calls,adapter.calls))

    def test_fractional_timestamp_cannot_publish_a_trusted_checkpoint_across_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'checkpoint.sqlite3'
            state = SQLiteKernelState(path)
            try:
                state.append('sample', {}, 1)
                with state._connection:
                    state._connection.execute('UPDATE audit SET timestamp_ns=1.5')
                with AuditVerificationEngine(workers=0) as engine:
                    accelerated, error = accepted(lambda: GovernanceKernel(Policy(frozenset(),0),
                        state=state,secret=b'checkpoint-test-only',audit_verification_engine=engine) is not None)
            finally:
                state.close()
            restarted = SQLiteKernelState(path)
            try:
                cached, cached_error = accepted(lambda: GovernanceKernel(Policy(frozenset(),0),
                    state=restarted,secret=b'checkpoint-test-only') is not None)
                restarted._connection.execute('DELETE FROM audit_verification_checkpoint')
                restarted._connection.commit()
                cold, cold_error = accepted(lambda: GovernanceKernel(Policy(frozenset(),0),
                    state=restarted,secret=b'checkpoint-test-only') is not None)
                observe(self.id(), accelerated_bootstrap=accelerated, restarted_cached_bootstrap=cached,
                    restarted_cold_bootstrap=cold, error=error, cached_error=cached_error, cold_error=cold_error)
                self.assertEqual((False,False,False),(accelerated,cached,cold))
            finally:
                restarted.close()

    def test_boss_lost_response_restart_wrong_identity_substitution_and_replay(self):
        fixture = executor_fixtures.CustodyExecutorTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        custody, budget, governed, order = fixture.governed_attempt()
        adapter = FakeCustodyRegistrar(fail=True)
        with self.assertRaises(ExternalConsequenceUnknown):
            TrustedDomainExecutor(custody,executor_id='executor:test').execute(governed,order,adapter)
        restarted = SQLiteGovernanceCustody(fixture.path, signing_secret=b'trusted-executor-custody',clock=lambda:11_000_000)
        for identity in ['executor:wrong','executor:test']:
            with self.assertRaises(CustodyViolation):
                TrustedDomainExecutor(restarted,executor_id=identity).execute(governed,order,adapter)
            with self.assertRaises(CustodyViolation):
                TrustedDomainExecutor(restarted,executor_id=identity).execute(replace(governed,order_hash='f'*64),order,adapter)
        self.assertEqual(1,adapter.calls)
        self.assertEqual(1000,budget.available_cents)
        self.assertEqual(restarted.RECONCILIATION_REQUIRED,restarted.attempt(governed.attempt_id).state)
        observe(self.id(), provider_calls=adapter.calls, budget_available=budget.available_cents,
            post_restart_state=restarted.attempt(governed.attempt_id).state, replay_attempts=4)

    def test_seeded_permit_model_with_restarts_and_wrong_bindings(self):
        count = 0
        for seed in [17, 302, 312, 20261017]:
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'model.sqlite3'
                state = SQLiteKernelState(path)
                model = {}
                rng = random.Random(seed)
                try:
                    for step in range(200):
                        action = rng.choice(['issue', 'consume', 'wrong_binding', 'restart'])
                        number = rng.randrange(20)
                        permit, digest = f'p{number}', f'h{number}'
                        if action == 'issue' and permit not in model:
                            self.assertIsNone(state.issue_permit(permit, digest, 'synthetic', step))
                            model[permit] = False
                        elif action in ['consume', 'wrong_binding']:
                            supplied = digest if action == 'consume' else 'wrong'
                            expected = permit in model and not model[permit] and supplied == digest
                            self.assertEqual(expected, state.consume_permit(permit, supplied, step))
                            if expected:
                                model[permit] = True
                        elif action == 'restart':
                            state.close()
                            state = SQLiteKernelState(path)
                            self.assertTrue(GovernanceKernel(Policy(frozenset(), 0), state=state, secret=b'model-only').verify_audit())
                        count += 1
                    stored = dict(state._connection.execute('SELECT permit, spent FROM permits'))
                    self.assertEqual({k:int(v) for k,v in model.items()}, stored)
                    self.assertEqual('ok', state._connection.execute('PRAGMA integrity_check').fetchone()[0])
                finally:
                    state.close()
        observe(self.id(), seeds=[17,302,312,20261017], transitions=count)

    def test_issuance_fault_matrix_rolls_back_then_exact_retry_succeeds(self):
        cases = [('approvals','INSERT'), ('permits','INSERT'), ('audit','INSERT'), ('audit_head','UPDATE')]
        for table, operation in cases:
            with self.subTest(table=table), tempfile.TemporaryDirectory() as directory:
                state = SQLiteKernelState(Path(directory) / 'fault.sqlite3')
                try:
                    before = {t:list(state._connection.execute('SELECT * FROM ' + t)) for t,_ in cases}
                    state._connection.execute(f"CREATE TRIGGER injected_failure BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT, 'round3 fault'); END")
                    approval = ApprovalUse('approval-test', 'nonce-test', {'test':True})
                    with self.assertRaisesRegex(sqlite3.IntegrityError, 'round3 fault'):
                        state.issue_permit('p', 'h', 'test', 1, approval)
                    self.assertFalse(state._connection.in_transaction)
                    self.assertEqual(before, {t:list(state._connection.execute('SELECT * FROM ' + t)) for t,_ in cases})
                    state._connection.execute('DROP TRIGGER injected_failure')
                    self.assertIsNone(state.issue_permit('p', 'h', 'test', 1, approval))
                    self.assertEqual('approval_id_replayed', state.issue_permit('p2','h','test',2,approval))
                    self.assertTrue(state.consume_permit('p','h',3))
                    self.assertFalse(state.consume_permit('p','h',4))
                finally:
                    state.close()
        observe(self.id(), injection_points=cases)

    def test_projection_faults_at_both_hooks_preserve_pending_then_retry_once(self):
        for point in ['after_audit_insert', 'before_projection_commit']:
            fixture = evidence_fixtures.CustodyEvidenceConvergenceTests()
            fixture.setUp()
            try:
                auth = fixture.authorize()
                def fault(current):
                    if current == point:
                        raise RuntimeError('round3 fault')
                faulty = SQLiteCustodyEvidenceConvergence(fixture.custody, fault_hook=fault)
                with self.assertRaises(Exception):
                    faulty.project_one()
                self.assertEqual(1, fixture.evidence.pending_count())
                self.assertEqual(0, fixture.evidence.canonical_event_count(auth.receipt.transition_hash))
                self.assertEqual(1,len(fixture.evidence.project_all()))
                self.assertEqual(0,len(fixture.evidence.project_all()))
                self.assertEqual(1, fixture.evidence.canonical_event_count(auth.receipt.transition_hash))
            finally:
                fixture.doCleanups()
        observe(self.id(), injection_points=['after_audit_insert','before_projection_commit'])

    def test_bounded_history_large_payload_cache_and_worker_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            state = SQLiteKernelState(Path(directory) / 'load.sqlite3')
            try:
                start = time.monotonic()
                for i in range(1000):
                    state.append('sample', {'i':i, 'text':'x' * (262144 if i == 0 else 8)}, i)
                rows = state.audit_verification_rows()
                with AuditVerificationEngine(workers=0, cache_size=16) as engine:
                    self.assertTrue(engine.verify_rows(rows))
                    self.assertLessEqual(len(engine.cache),16)
                    self.assertTrue(engine.verify_rows(rows))
                with AuditVerificationEngine(workers=2, cache_size=0, parallel_threshold=1, batch_size=32) as engine:
                    self.assertTrue(engine.verify_rows(rows))
                    with patch.object(engine, '_executor_for_work', side_effect=RuntimeError('synthetic worker unavailable')):
                        result, error = accepted(lambda: engine.verify_rows(rows))
                    self.assertFalse(result)
                    self.assertIn('worker unavailable', error)
                observe(self.id(), rows=1000, first_payload_bytes=262144, cache_limit=16,
                    seconds=round(time.monotonic()-start,3), worker_failure_accepted=result)
            finally:
                state.close()

# Runner selects the three probe classes explicitly; imported fixtures are helpers.
