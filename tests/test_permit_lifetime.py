"""Expiry supplements policy/issuer binding and canonical one-use state."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from pulpo import GovernanceKernel, Intent, Policy
from pulpo.state import InMemoryKernelState, SQLiteKernelState, DirectivePermitBinding

class PermitLifetimeTests(unittest.TestCase):
    def states(self, directory):
        yield InMemoryKernelState()
        state=SQLiteKernelState(Path(directory)/'state.sqlite3')
        self.addCleanup(state.close)
        yield state

    def test_default_ordinary_permit_cannot_be_used_after_24_hours(self):
        with TemporaryDirectory() as directory:
            for state in self.states(directory):
                now=[1_000_000_000]
                kernel=GovernanceKernel(Policy(frozenset({'read'}),0),secret=b'synthetic',state=state,clock=lambda:now[0])
                intent=Intent('agent','read','evidence:synthetic')
                permit=kernel.evaluate(intent).permit
                now[0]+=86_400_000_000_000
                self.assertFalse(kernel.consume(permit,intent))

    def test_exact_expiry_boundary_and_replay(self):
        with TemporaryDirectory() as directory:
            for state in self.states(directory):
                now=[100]
                kernel=GovernanceKernel(Policy(frozenset({'read'}),0,permit_ttl_ns=10),state=state,clock=lambda:now[0])
                intent=Intent('agent','read','evidence:synthetic')
                expired=kernel.evaluate(intent).permit
                valid=kernel.evaluate(intent).permit
                now[0]=109
                self.assertTrue(kernel.consume(valid,intent))
                self.assertFalse(kernel.consume(valid,intent))
                now[0]=110
                self.assertFalse(kernel.consume(expired,intent))

    def test_sqlite_expiry_survives_restart(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'state.sqlite3';state=SQLiteKernelState(path)
            policy=Policy(frozenset({'read'}),0,permit_ttl_ns=10)
            kernel=GovernanceKernel(policy,secret=b'synthetic',state=state,clock=lambda:100)
            intent=Intent('agent','read','evidence:synthetic');permit=kernel.evaluate(intent).permit
            state.close();state=SQLiteKernelState(path);self.addCleanup(state.close)
            restarted=GovernanceKernel(policy,secret=b'synthetic',state=state,clock=lambda:110)
            self.assertFalse(restarted.consume(permit,intent))

    def test_missing_expiry_cannot_gain_context_bound_authority(self):
        with TemporaryDirectory() as directory:
            for state in self.states(directory):
                kernel=GovernanceKernel(Policy(frozenset({'read'}),0),secret=b'synthetic',state=state,clock=lambda:100)
                intent=Intent('agent','read','evidence:synthetic')
                permit=kernel.evaluate(intent).permit
                if isinstance(state, InMemoryKernelState):
                    context=state._permit_context[permit];state._permit_context[permit]=(context[0],context[1],None,context[3])
                else:
                    state._connection.execute('UPDATE permits SET expires_at_ns=NULL');state._connection.commit()
                self.assertFalse(kernel.consume(permit,intent))

    def test_expired_permit_rejects_before_directive_binding(self):
        with TemporaryDirectory() as directory:
            for state in self.states(directory):
                kernel=GovernanceKernel(Policy(frozenset({'read'}),0,permit_ttl_ns=10),state=state,clock=lambda:100)
                intent=Intent('agent','read','evidence:synthetic');permit=kernel.evaluate(intent).permit
                with self.assertRaisesRegex(ValueError,'permit unavailable'):
                    state.bind_permit_to_directive(permit,kernel.intent_hash(intent),None,110)

    def test_ttl_is_strict_and_part_of_policy_identity(self):
        for value in (True,False,0,-1,1.5,'10',None):
            with self.subTest(value=value),self.assertRaises(ValueError):
                Policy(frozenset({'read'}),0,permit_ttl_ns=value)
        hashes=[GovernanceKernel(Policy(frozenset({'read'}),0,permit_ttl_ns=n)).policy_hash for n in (10,11)]
        self.assertNotEqual(*hashes)
