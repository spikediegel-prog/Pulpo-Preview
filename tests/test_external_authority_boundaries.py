"""Synthetic containment characterizations, not production isolation proofs.

No remote providers, real credentials, or host command execution adapters.
Passing means the stated external-control limitation was reproduced.
"""
import json
import os
import secrets
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from pulpo import GovernanceKernel, Intent, Policy
from pulpo.directives import GovernedDirectiveProjection
from pulpo.state import SQLiteKernelState
from tests import test_directives as directives


class ExternalAuthorityBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.token = secrets.token_hex(32)  # disposable simulated provider token
        self.accepted = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                valid = secrets.compare_digest(
                    self.headers.get('Authorization', ''), 'Bearer ' + owner.token
                )
                if valid:
                    owner.accepted.append(self.path)
                self.send_response(200 if valid else 403)
                self.end_headers()
                self.wfile.write(b'accepted' if valid else b'denied')

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.url = f'http://127.0.0.1:{self.server.server_port}/synthetic-effect'

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.assertFalse(self.thread.is_alive())

    def post(self, token):
        request = Request(self.url, data=b'', headers={'Authorization': 'Bearer ' + token})
        with build_opener(ProxyHandler({})).open(request, timeout=3) as response:
            self.assertEqual(b'accepted', response.read())

    def reject_missing_credential(self):
        with self.assertRaises(HTTPError) as denied:
            self.post('')
        self.assertEqual(403, denied.exception.code)
        denied.exception.close()
        self.assertEqual([], self.accepted)

    def test_child_process_with_ambient_route_is_not_intercepted_by_kernel_denial(self):
        kernel = GovernanceKernel(Policy(frozenset({'inspect'}), 0))
        denied = kernel.evaluate(Intent('agent:fixture', 'provider_write', 'synthetic:provider'))
        self.assertEqual(('deny', None), (denied.outcome, denied.permit))
        self.reject_missing_credential()
        audit_before = list(kernel._state.audit)
        code = (
            'import json,sys; from urllib.request import Request,build_opener,ProxyHandler; '
            'd=json.load(sys.stdin); '
            'r=Request(d["url"],data=b"",headers={"Authorization":"Bearer "+d["token"]}); '
            'response=build_opener(ProxyHandler({})).open(r,timeout=3); '
            'assert response.read()==b"accepted"; response.close()'
        )
        # An isolated standard-library child receives only this synthetic token
        # through stdin. No shell, ambient credential variables, or real endpoint.
        env = {k: os.environ[k] for k in ('SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP') if k in os.environ}
        child = subprocess.run(
            [sys.executable, '-I', '-S', '-B', '-c', code],
            input=json.dumps({'url': self.url, 'token': self.token}),
            text=True, capture_output=True, timeout=10, env=env,
        )
        self.assertEqual(0, child.returncode, child.stderr)
        self.assertEqual(['/synthetic-effect'], self.accepted)
        self.assertEqual(audit_before, kernel._state.audit)
        self.assertTrue(kernel.verify_audit())

    def test_provider_token_survives_directive_revocation_and_kernel_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'kernel.sqlite'
            state = SQLiteKernelState(path)
            self.addCleanup(state.close)
            fixture = directives.DirectiveProofTests()
            directive = directives.directive()
            kernel, verifier, controller = fixture.activate(state, directive)
            intent = Intent('agent:builder', 'write', 'repo:file', 1)
            decision = GovernedDirectiveProjection(kernel).evaluate(intent, directive)
            self.assertEqual('allow', decision.outcome)
            self.assertIsNotNone(decision.permit)
            self.reject_missing_credential()
            self.post(self.token)  # provider's positive control before revocation
            envelope = fixture.approve(kernel, verifier, controller.REVOKE, directive,
                                       'revoke-external-test', 'revoke-external-nonce')
            self.assertEqual('allow', controller.revoke(
                directive, envelope, operator_principal=directives.OPERATOR).outcome)
            self.assertFalse(kernel.consume(decision.permit, intent))
            self.assertTrue(kernel.verify_audit())
            state.close()
            restarted = SQLiteKernelState(path)
            try:
                kernel, _ = fixture.governed(restarted)
                self.assertFalse(kernel.consume(decision.permit, intent))
                audit_before = list(restarted.audit)
                self.post(self.token)
                self.assertEqual(['/synthetic-effect'] * 2, self.accepted)
                self.assertEqual(audit_before, restarted.audit)
                self.assertTrue(kernel.verify_audit())
            finally:
                restarted.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
