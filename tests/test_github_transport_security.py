"""Token-safe metadata reads: bounded fake responses and local TLS only."""
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from pulpo.github_execution_context import GitHubRESTMetadataReader, GitHubContextAttestationError
import pulpo.github_execution_context as github


class Response(io.BytesIO):
    status=200


class GitHubMetadataAdmissionTests(unittest.TestCase):
    def test_exact_response_bound_accepts_and_closes(self):
        payload=b'{"id":1}'+b' '*(1_048_576-8)
        self.assertEqual(1_048_576,len(payload))
        response=Response(payload)
        reader=GitHubRESTMetadataReader('synthetic',opener=lambda *a,**k:response)
        self.assertEqual({'id':1},reader.fetch_authenticated_user())
        self.assertTrue(response.closed)

    def test_oversized_response_rejects_after_bounded_read_and_closes(self):
        class RecordingResponse(Response):
            def read(self,size=-1):
                self.size=size
                return super().read(size)
        response=RecordingResponse(b'{"padding":"'+b'x'*(2*1024*1024)+b'"}')
        with self.assertRaisesRegex(GitHubContextAttestationError,'too large'):
            GitHubRESTMetadataReader('synthetic',opener=lambda *a,**k:response).fetch_authenticated_user()
        self.assertEqual(1_048_577,response.size)
        self.assertTrue(response.closed)

    def test_rejected_status_does_not_read_and_closes(self):
        response=Response(b'not-used');response.status=403
        with self.assertRaisesRegex(GitHubContextAttestationError,'HTTP 403'):
            GitHubRESTMetadataReader('synthetic',opener=lambda *a,**k:response).fetch_authenticated_user()
        self.assertTrue(response.closed)

    def test_body_read_failure_closes_and_sanitizes_transport_error(self):
        class Broken(Response):
            def read(self,size=-1):raise OSError('synthetic-sensitive-provider-material')
        response=Broken()
        with self.assertRaises(GitHubContextAttestationError) as error:
            GitHubRESTMetadataReader('synthetic',opener=lambda *a,**k:response).fetch_authenticated_user()
        self.assertTrue(response.closed)
        self.assertEqual('GitHub context read failed',str(error.exception))
        self.assertTrue(error.exception.__suppress_context__)

    @unittest.skipUnless(sys.platform.startswith('linux') and shutil.which('openssl'),'Ubuntu TLS fixture needs openssl')
    def test_default_reader_rejects_cross_origin_redirect_before_token_release(self):
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        import os,secrets,ssl,threading
        received=[];token=secrets.token_hex(32)
        class Sink(BaseHTTPRequestHandler):
            def do_GET(self):
                received.append(self.headers.get('Authorization')=='Bearer '+token)
                body=b'{"login":"synthetic","id":1}'
                self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
            def log_message(self,*args):pass
        class Origin(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302);self.send_header('Location',f'https://localhost:{sink.server_port}/capture');self.send_header('Content-Length','0');self.end_headers()
            def log_message(self,*args):pass
        with tempfile.TemporaryDirectory(prefix='pulpo-github-tls-') as folder:
            cert,key=Path(folder)/'cert.pem',Path(folder)/'key.pem'
            subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-keyout',str(key),'-out',str(cert),'-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost,IP:127.0.0.1','-addext','basicConstraints=critical,CA:TRUE'],check=True,capture_output=True)
            servers=[]
            try:
                for handler in (Sink,Origin):
                    server=ThreadingHTTPServer(('127.0.0.1',0),handler)
                    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(cert,key)
                    server.socket=context.wrap_socket(server.socket,server_side=True)
                    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();servers.append((server,thread))
                    if handler is Sink:sink=server
                    else:origin=server
                env={k:v for k,v in os.environ.items() if k.lower() not in ('http_proxy','https_proxy','all_proxy','ssl_cert_file','ssl_cert_dir','requests_ca_bundle','curl_ca_bundle')}
                env.update(SSL_CERT_FILE=str(cert),PULPO_CA_BUNDLE=str(cert))
                with patch.dict(os.environ,env,clear=True):
                    with patch.object(github,'_GITHUB_API_ORIGIN',f'https://127.0.0.1:{sink.server_port}'):
                        self.assertEqual('synthetic',GitHubRESTMetadataReader(token).fetch_authenticated_user()['login'])
                    self.assertEqual([True],received);received.clear()
                    with patch.object(github,'_GITHUB_API_ORIGIN',f'https://127.0.0.1:{origin.server_port}'):
                        with self.assertRaises(GitHubContextAttestationError):GitHubRESTMetadataReader(token).fetch_authenticated_user()
                    self.assertEqual([],received)
            finally:
                for server,thread in reversed(servers):server.shutdown();server.server_close();thread.join(3)

if __name__=='__main__':unittest.main()
