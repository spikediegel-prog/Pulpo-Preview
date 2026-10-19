"""Preview-specific synthetic controls; no daemon or provider required."""
from dataclasses import asdict, replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pulpo import AgentGrant, GovernanceKernel, Intent, Policy, PulpoOrchestrator, SQLiteKernelState
from pulpo.mcp_boundary import freeze_mcp_snapshot
from pulpo.ollama_proposal import LocalModel, LocalProposalError, project_local_proposal, request_local_proposal

GOOD = '{"action":"read","resource":"repo:synthetic","cost":0}'


class OllamaPreviewBoundaryTests(unittest.TestCase):
    def policy(self, ttl=10):
        return Policy(frozenset({'read'}), 0, agent_grants=(
            AgentGrant('agent:fixture',frozenset({'read'}),('repo:',),0),),permit_ttl_ns=ttl)

    def proposal(self, kernel):
        snapshot=freeze_mcp_snapshot(PulpoOrchestrator(kernel))
        return project_local_proposal(GOOD,snapshot,principal='agent:fixture',session_id='fixture',target_id='fixture')

    def test_proposed_intent_still_obeys_preview_exact_permit_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            state=SQLiteKernelState(Path(directory)/'synthetic.sqlite3')
            try:
                now=[100]
                kernel=GovernanceKernel(self.policy(),state=state,secret=b'fixture-only',clock=lambda:now[0])
                intent=Intent(**self.proposal(kernel)['intent'])
                self.assertEqual([],kernel.audit)
                permit=kernel.evaluate(intent).permit
                self.assertIsNotNone(permit)
                now[0]=110
                self.assertFalse(kernel.consume(permit,intent))
                self.assertTrue(kernel.verify_audit())
            finally:
                state.close()

    def test_proposal_cannot_change_issuer_policy_binding_across_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'synthetic.sqlite3'
            first=SQLiteKernelState(path)
            try:
                kernel=GovernanceKernel(self.policy(),state=first,secret=b'issuer-one',clock=lambda:100)
                intent=Intent(**self.proposal(kernel)['intent'])
                permit=kernel.evaluate(intent).permit
                self.assertIsNotNone(permit)
            finally:
                first.close()
            second=SQLiteKernelState(path)
            try:
                new_issuer=GovernanceKernel(self.policy(),state=second,secret=b'issuer-two',clock=lambda:101)
                self.assertFalse(new_issuer.consume(permit,intent))
                new_policy=GovernanceKernel(self.policy(ttl=20),state=second,secret=b'issuer-one',clock=lambda:101)
                self.assertFalse(new_policy.consume(permit,intent))
                original=GovernanceKernel(self.policy(),state=second,secret=b'issuer-one',clock=lambda:101)
                self.assertTrue(original.consume(permit,intent))
                self.assertFalse(original.consume(permit,intent))
            finally:
                second.close()

    def test_model_cannot_supply_preview_execution_context(self):
        kernel=GovernanceKernel(self.policy(),secret=b'fixture-only',clock=lambda:100)
        snapshot=freeze_mcp_snapshot(PulpoOrchestrator(kernel))
        for field in ['permit_ttl_ns','expires_at_ns','issuer_hash','budget_ceiling_cents','custody','approval']:
            with self.subTest(field=field), self.assertRaises(LocalProposalError):
                project_local_proposal(json.dumps({**json.loads(GOOD),field:'forged'}),snapshot,
                    principal='agent:fixture',session_id='fixture',target_id='fixture')
        self.assertEqual([],kernel.audit)

    def test_frozen_proposal_does_not_renew_or_reauthorize_expired_permit(self):
        now=[100]
        kernel=GovernanceKernel(self.policy(),secret=b'fixture-only',clock=lambda:now[0])
        snapshot=freeze_mcp_snapshot(PulpoOrchestrator(kernel))
        kwargs=dict(principal='agent:fixture',session_id='fixture',target_id='fixture')
        intent=Intent(**project_local_proposal(GOOD,snapshot,**kwargs)['intent'])
        permit=kernel.evaluate(intent).permit
        now[0]=110
        before=list(kernel.audit)
        for _ in range(20):
            self.assertEqual(asdict(intent),project_local_proposal(GOOD,snapshot,**kwargs)['intent'])
        self.assertEqual(before,kernel.audit)
        self.assertFalse(kernel.consume(permit,intent))

    def test_failed_inference_does_not_publish_canonical_evidence(self):
        kernel=GovernanceKernel(self.policy(),secret=b'fixture-only',clock=lambda:100)
        before=list(kernel.audit)
        with patch('pulpo.ollama_proposal._request',side_effect=LocalProposalError('synthetic-unavailable')) as request:
            with self.assertRaises(LocalProposalError):
                request_local_proposal('Synthetic permitted context only',LocalModel('synthetic:fixture','f'*64))
        request.assert_called_once()
        self.assertEqual(before,kernel.audit)


if __name__=='__main__':
    unittest.main()
