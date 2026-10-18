from dataclasses import asdict
from pathlib import Path
import tempfile
import unittest
from fastapi.testclient import TestClient
import test_service
from pulpo_authority_service.api import create_app
from pulpo_authority_service.restart_adapters import SQLiteRestartState


class WorkerRequestOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_service.AuthorityServiceTests(methodName='test_one_exact_verified_ceremony_produces_one_kernel_usable_envelope')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_second_authenticated_worker_cannot_poll_signed_envelope(self):
        class Auth:
            def authenticate(self,request):
                header=request.headers.get('authorization')
                if header=='Bearer synthetic-a':return 'worker:a'
                if header=='Bearer synthetic-b':return 'worker:b'
                raise PermissionError('synthetic identity required')
        f=self.fixture
        with TestClient(create_app(f.service,worker_authenticator=Auth())) as client:
            response=client.post('/v1/approval-requests',json=asdict(f.request),headers={'Authorization':'Bearer synthetic-a'})
            self.assertEqual(200,response.status_code)
            request_id=response.json()['request_id']
            f.service.approve(request_id,f.primary.credential_id,'raw-assertion-json')
            path='/v1/approval-requests/'+request_id
            self.assertEqual(401,client.get(path).status_code)
            self.assertEqual(404,client.get(path,headers={'Authorization':'Bearer synthetic-b'}).status_code)
            own=client.get(path,headers={'Authorization':'Bearer synthetic-a'})
            self.assertEqual(200,own.status_code)
            self.assertIn('envelope',own.json())

    def test_legacy_ownerless_request_cannot_be_claimed_by_worker(self):
        f=self.fixture
        request_id,_=f.service.request_approval(f.request)
        with self.assertRaises(PermissionError):f.service.poll(request_id,worker_identity='worker:a')

    def test_request_owner_survives_sqlite_adapter_restart(self):
        f=self.fixture
        request_id,_=f.service.request_approval(f.request,worker_identity='worker:a')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'authority.sqlite'
            state=SQLiteRestartState(path,(f.primary,))
            state.requests[request_id]=f.service.state.requests[request_id]
            restarted=SQLiteRestartState(path,())
            self.assertEqual('worker:a',restarted.requests[request_id].worker_identity)
