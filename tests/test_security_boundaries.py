"""Synthetic boundary characterizations. No real credentials or remote services.

Passing characterization tests may demonstrate a missing external control;
test names and assertions deliberately distinguish this from a permit bypass.
"""
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import secrets
import threading
import unittest
from urllib.request import ProxyHandler, Request, build_opener
from urllib.error import HTTPError

from pulpo import GovernanceKernel, Policy
from pulpo.kernel import AgentGrant
from pulpo.telegram import GovernedTelegramSender, TelegramOutboundMessage, TelegramSendRejected
from tests.test_telegram_capability_activation_prep import TelegramCapabilityActivationPrepTests, BOT_ID, CHAT_ID, PRINCIPAL, SESSION, ProbeTransport


class ExactMessageCases(unittest.TestCase):
    def setUp(self):
        self.fixture = TelegramCapabilityActivationPrepTests()
        self.fixture.setUp()

    def test_plain_and_encoded_secret_cannot_replace_approved_text(self):
        for text in ('synthetic-private-canary', base64.b64encode(b'synthetic-private-canary').decode()):
            with self.subTest(text=text):
                self.setUp()
                f = self.fixture
                activation = f._approve_activation()
                permit = f._approve_message()
                changed = TelegramOutboundMessage(BOT_ID, CHAT_ID, text)
                with self.assertRaisesRegex(TelegramSendRejected, 'message permit rejected'):
                    f.sender.execute(changed, activation_permit=activation.permit, message_permit=permit.permit, principal=PRINCIPAL, session_id=SESSION)
                self.assertEqual(0, f.transport.provider_calls)

    def test_exactly_approved_sensitive_text_has_no_independent_content_filter(self):
        f = self.fixture
        message = TelegramOutboundMessage(BOT_ID, CHAT_ID, 'synthetic-private-canary')
        captured = []
        original_send = f.transport.send_message
        def capture(sent):
            captured.append(sent.text)
            return original_send(sent)
        f.transport.send_message = capture
        activation = f._approve_activation(message)
        permit = f._approve_message(message)
        f.sender.execute(message, activation_permit=activation.permit, message_permit=permit.permit, principal=PRINCIPAL, session_id=SESSION)
        self.assertEqual(1, f.transport.provider_calls)
        self.assertEqual(['synthetic-private-canary'], captured)


class BroadPolicyCases(unittest.TestCase):
    def test_destination_scoped_grant_does_not_define_a_data_scope(self):
        message = TelegramOutboundMessage(BOT_ID, CHAT_ID, 'synthetic-private-canary')
        actions = frozenset({'activate_capability', 'telegram_send_message'})
        grant = AgentGrant(PRINCIPAL, actions, (f'telegram:bot:{BOT_ID}:chat:{CHAT_ID}:',), 0)
        kernel = GovernanceKernel(Policy(actions, 0, agent_grants=(grant,)))
        transport = ProbeTransport()
        sender = GovernedTelegramSender(kernel, transport)
        activation = sender.evaluate_activation(message, principal=PRINCIPAL, session_id=SESSION)
        permit = sender.evaluate(message, principal=PRINCIPAL, session_id=SESSION)
        self.assertEqual(('allow', 'allow'), (activation.outcome, permit.outcome))
        sender.execute(message, activation_permit=activation.permit, message_permit=permit.permit, principal=PRINCIPAL, session_id=SESSION)
        self.assertEqual(1, transport.provider_calls)
        self.assertTrue(kernel.verify_audit())

    def test_exact_resource_grant_rejects_changed_content_before_permit_issue(self):
        approved = TelegramOutboundMessage(BOT_ID, CHAT_ID, 'public summary')
        changed = TelegramOutboundMessage(BOT_ID, CHAT_ID, 'synthetic-private-canary')
        actions = frozenset({'activate_capability', 'telegram_send_message'})
        grant = AgentGrant(PRINCIPAL, actions, (approved.activation_resource, approved.resource), 0)
        kernel = GovernanceKernel(Policy(actions, 0, agent_grants=(grant,)))
        transport = ProbeTransport()
        sender = GovernedTelegramSender(kernel, transport)
        self.assertEqual('allow', sender.evaluate(approved, principal=PRINCIPAL, session_id=SESSION).outcome)
        denied = sender.evaluate(changed, principal=PRINCIPAL, session_id=SESSION)
        self.assertEqual('deny', denied.outcome)
        self.assertIsNone(denied.permit)
        self.assertEqual(0, transport.provider_calls)


class AmbientNetworkCase(unittest.TestCase):
    def test_denied_kernel_action_does_not_intercept_direct_loopback_io(self):
        token = secrets.token_hex(32)
        received = []
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                valid = secrets.compare_digest(self.headers.get('Authorization', ''), 'Bearer '+token)
                received.append(valid)
                self.send_response(200 if valid else 403)
                self.end_headers()
                self.wfile.write(b'synthetic-provider-accepted' if valid else b'denied')
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            from pulpo import Intent
            kernel = GovernanceKernel(Policy(frozenset({'inspect'}), 0))
            decision = kernel.evaluate(Intent('agent:fixture', 'provider_read', 'synthetic:provider'))
            self.assertEqual('deny', decision.outcome)
            self.assertIsNone(decision.permit)
            opener = build_opener(ProxyHandler({}))
            url = f'http://127.0.0.1:{server.server_port}/synthetic'
            with self.assertRaises(HTTPError) as denial:
                opener.open(url, timeout=2)
            self.assertEqual(403, denial.exception.code)
            denial.exception.close()
            with opener.open(Request(url, headers={'Authorization':'Bearer '+token}), timeout=2) as response:
                self.assertEqual(b'synthetic-provider-accepted', response.read())
            self.assertEqual([False, True], received)
            self.assertTrue(kernel.verify_audit())
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


def load_tests(loader, tests, pattern):
    # Importing an existing fixture must not duplicate its own tests here.
    return unittest.TestSuite(loader.loadTestsFromTestCase(cls) for cls in (ExactMessageCases, BroadPolicyCases, AmbientNetworkCase))

if __name__ == '__main__':
    unittest.main(verbosity=2)
