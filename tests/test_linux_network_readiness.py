import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from scripts import check_linux_network_readiness as diagnostic
from pulpo.transport import TransportConfigurationError, _ssl_context, sanitized_transport_environment


class NetworkInventoryTests(unittest.TestCase):
    def test_key_logging_rejects_before_context_creation_or_destination_access(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "secret-canary.log"
            with patch.dict(os.environ, {"SSLKEYLOGFILE": str(path)}, clear=True), \
                    patch("pulpo.transport.ssl.create_default_context") as create, \
                    patch("socket.getaddrinfo") as resolve:
                with self.assertRaisesRegex(TransportConfigurationError, "key_logging_not_permitted"):
                    _ssl_context()
                report = diagnostic.trust_observation()
                self.assertEqual("error", report["state"])
                self.assertNotIn("secret-canary", json.dumps(report))
                self.assertIn("SSLKEYLOGFILE", report["override_variables_present"])
                self.assertEqual("trust_configuration_rejected", diagnostic.probe_https("https://example.invalid/")["state"])
                create.assert_not_called()
                resolve.assert_not_called()
            self.assertFalse(path.exists())

    def test_transport_sanitizer_removes_tls_secret_logging(self):
        self.assertEqual({"SAFE": "kept"}, sanitized_transport_environment(
            {"SSLKEYLOGFILE": "/private-secret-canary.log", "SAFE": "kept"}))

    def test_interface_addresses_and_link_kind_are_observations(self):
        result = diagnostic.interfaces([{"ifname": "vlan17", "mtu": 1500, "operstate": "UP",
            "linkinfo": {"info_kind": "vlan"}, "addr_info": [
                {"family": "inet", "local": "192.0.2.3", "prefixlen": 24, "scope": "global"},
                {"family": "inet6", "local": "fe80::1", "prefixlen": 64, "scope": "link"}]}])
        self.assertEqual("vlan", result[0]["kind"])
        self.assertEqual("link", result[0]["addresses"][1]["scope"])

    def test_malformed_and_mixed_output_never_becomes_empty_success(self):
        for value in ({}, [None], [{"ifname": "eth0", "mtu": True, "operstate": "UP", "addr_info": []}]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                diagnostic.interfaces(value)
        with patch.object(diagnostic.shutil, "which", return_value="/usr/sbin/ip"), \
                patch.object(diagnostic.subprocess, "run") as run:
            run.return_value.stdout = '[{"dst":"default","gateway":"not-an-ip"}]'
            self.assertEqual("error", diagnostic.collect_ip([], lambda v: diagnostic.routes(v, 4))["state"])

    def test_main_route_family_and_complex_route_presence(self):
        self.assertEqual([], diagnostic.routes([], 6))
        result = diagnostic.routes([{"dst": "default", "nexthops": [{"dev": "tun0"}]}], 4)
        self.assertTrue(result[0]["multipath_present"])
        with self.assertRaises(ValueError):
            diagnostic.routes([{"dst": "default", "gateway": "::1"}], 4)

    def test_missing_command_and_timeout_remain_errors(self):
        with patch.object(diagnostic.shutil, "which", return_value=None):
            self.assertEqual("error", diagnostic.collect_ip([], diagnostic.interfaces)["state"])
        with patch.object(diagnostic.shutil, "which", return_value="/usr/sbin/ip"), \
                patch.object(diagnostic.subprocess, "run", side_effect=subprocess.TimeoutExpired("ip", 5)):
            self.assertEqual("error", diagnostic.collect_ip([], diagnostic.interfaces)["state"])

    def test_dns_configuration_is_not_dns_reachability_and_search_names_are_redacted(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "resolv.conf"
            path.write_text("nameserver 127.0.0.53\nsearch private-customer.invalid\n")
            report = diagnostic.resolver_observation(path)
            self.assertEqual("not_tested", report["reachability"])
            self.assertEqual("not_assessed", report["upstream_resolvers"])
            self.assertNotIn("private-customer", json.dumps(report))
            path.write_text("nameserver invalid\n")
            self.assertEqual("error", diagnostic.resolver_observation(path)["state"])

    def test_proxy_credentials_and_ca_paths_never_enter_inventory(self):
        with patch.dict(os.environ, {"HTTPS_PROXY": "http://private-user:secret-canary@proxy.invalid:8080",
                                    "SSL_CERT_FILE": "/secret-canary/private.pem"}, clear=True), \
                patch.object(diagnostic, "collect_ip", return_value={"state": "observed", "items": []}), \
                patch.object(diagnostic, "resolver_observation", return_value={"state": "observed"}):
            report = diagnostic.collect()
        self.assertNotIn("secret-canary", json.dumps(report))
        self.assertNotIn("private-user", json.dumps(report))
        self.assertEqual("error", report["checks"]["tls_trust"]["state"])
        self.assertIn("HTTPS_PROXY", report["checks"]["proxy"]["variables_present"])
        self.assertEqual("not_assessed", report["enforcement"])

    def test_default_cli_never_probes_and_preserves_existing_report(self):
        fixture = {"checks": {"inventory": {"state": "observed"}}, "probes": []}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "previous.json"
            path.write_text("retain")
            with patch.object(diagnostic, "collect", return_value=fixture), \
                    patch.object(diagnostic, "bounded_probe") as probe, \
                    contextlib.redirect_stdout(io.StringIO()) as stdout, \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(2, diagnostic.main(["--evidence", str(path)]))
                probe.assert_not_called()
            self.assertEqual("retain", path.read_text())
            self.assertEqual("", stdout.getvalue())

    def test_invalid_origins_are_rejected_before_collection(self):
        for origin in ("http://example.com/", "https://u:p@example.com/", "https://example.com/?token=x",
                       "https://example.com/private", "https://example.com/#x", "https://example.com/\n"):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                diagnostic.validate_origin(origin)

    def test_worker_timeout_and_inconsistent_success_are_not_success(self):
        with patch.object(diagnostic.subprocess, "run", side_effect=subprocess.TimeoutExpired("probe", 8)):
            self.assertEqual("timed_out", diagnostic.bounded_probe("https://example.invalid/")["state"])
        for payload in ({"origin": "https://example.invalid/", "state": "https_ok", "tls_verified": False},
                        {"origin": "https://other.invalid/", "state": "https_ok", "tls_verified": True, "http_status": 200}):
            with patch.object(diagnostic.subprocess, "run") as run:
                run.return_value.stdout = json.dumps(payload)
                self.assertEqual("probe_result_unavailable", diagnostic.bounded_probe("https://example.invalid/")["state"])


@unittest.skipUnless(shutil.which("openssl"), "openssl needed for disposable TLS server fixture")
class LocalHttpsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(prefix="pulpo-tls-fixture-")
        cls.cert = Path(cls.folder.name) / "localhost.pem"
        key = Path(cls.folder.name) / "server.key"
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-sha256", "-days", "1", "-nodes",
            "-keyout", str(key), "-out", str(cls.cert), "-subj", "/CN=localhost",
            "-addext", "subjectAltName=DNS:localhost"], check=True, capture_output=True, timeout=15)
        cls.calls = 0
        class Handler(BaseHTTPRequestHandler):
            def do_HEAD(self):
                cls.calls += 1
                self.send_response(302 if cls.redirect else 200)
                if cls.redirect:
                    self.send_header("Location", "https://must-not-be-contacted.invalid/")
                self.end_headers()
            def log_message(self, *_args):
                pass
        cls.redirect = False
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cls.cert, key)
        cls.server.socket = context.wrap_socket(cls.server.socket, server_side=True)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.origin = f"https://localhost:{cls.server.server_port}/"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.folder.cleanup()

    def setUp(self):
        type(self).redirect = False

    def test_untrusted_certificate_rejected_without_http_request(self):
        before = self.calls
        with patch.dict(os.environ, {}, clear=True):
            report = diagnostic.probe_https(self.origin)
        self.assertEqual("certificate_rejected", report["state"])
        self.assertFalse(report["tls_verified"])
        self.assertEqual(before, self.calls)

    def test_explicit_public_test_ca_succeeds_and_wrong_hostname_rejects(self):
        with patch.dict(os.environ, {"PULPO_CA_BUNDLE": str(self.cert)}, clear=True):
            self.assertEqual("https_ok", diagnostic.probe_https(self.origin)["state"])
            wrong = diagnostic.probe_https(self.origin.replace("localhost", "127.0.0.1"))
        self.assertEqual("certificate_rejected", wrong["state"])
        self.assertFalse(wrong["tls_verified"])

    def test_real_bounded_child_uses_existing_tls_policy(self):
        with patch.dict(os.environ, {"PULPO_CA_BUNDLE": str(self.cert)}, clear=True):
            self.assertEqual("https_ok", diagnostic.bounded_probe(self.origin)["state"])
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual("certificate_rejected", diagnostic.bounded_probe(self.origin)["state"])

    def test_ipv6_loopback_https_with_hostname_validation(self):
        class IPv6Server(ThreadingHTTPServer):
            address_family = socket.AF_INET6
        try:
            server = IPv6Server(("::1", 0), self.server.RequestHandlerClass)
        except OSError as exc:
            self.skipTest("IPv6 loopback unavailable: " + type(exc).__name__)
        server.socket = self.server.socket.context.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        original = socket.getaddrinfo
        def resolve(host, port, *_args, **_kwargs):
            self.assertEqual("localhost", host)
            return original("::1", port, socket.AF_INET6, socket.SOCK_STREAM)
        try:
            with patch.dict(os.environ, {"PULPO_CA_BUNDLE": str(self.cert)}, clear=True), \
                    patch("socket.getaddrinfo", side_effect=resolve):
                report = diagnostic.probe_https(f"https://localhost:{server.server_port}/")
            self.assertEqual("https_ok", report["state"])
            self.assertTrue(report["tls_verified"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_redirect_is_rejected_without_second_destination(self):
        type(self).redirect = True
        before = self.calls
        original = socket.getaddrinfo
        def resolve(host, *args, **kwargs):
            self.assertEqual("localhost", host)
            return original(host, *args, **kwargs)
        with patch.dict(os.environ, {"PULPO_CA_BUNDLE": str(self.cert)}, clear=True), \
                patch("socket.getaddrinfo", side_effect=resolve):
            report = diagnostic.probe_https(self.origin)
        self.assertEqual("redirect_rejected", report["state"])
        self.assertEqual(before + 1, self.calls)

    def test_dns_failure_is_reported_through_real_transport(self):
        with patch.dict(os.environ, {}, clear=True), \
                patch("socket.getaddrinfo", side_effect=socket.gaierror(socket.EAI_AGAIN, "fixture DNS unavailable")):
            report = diagnostic.probe_https(self.origin)
        self.assertEqual("dns_unavailable", report["state"])

    def test_unreachable_loopback_port_is_not_a_tls_success(self):
        with socket.socket() as reserved:
            reserved.bind(("127.0.0.1", 0))
            origin = f"https://127.0.0.1:{reserved.getsockname()[1]}/"
            with patch.dict(os.environ, {}, clear=True):
                report = diagnostic.probe_https(origin)
        self.assertEqual("connection_refused", report["state"])
        self.assertFalse(report["tls_verified"])
