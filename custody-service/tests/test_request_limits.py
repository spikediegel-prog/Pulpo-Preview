"""Bounded admission regressions: no database, credentials, sockets or providers."""
import asyncio
import unittest

from pulpo_custody_service.api import create_app


class CustodyAdmissionTests(unittest.TestCase):
    def request(self, body=b'', *, path='/v1/domain-proposals', headers=(), method='POST'):
        class Service:
            calls = 0
            def prepare_proposal(self, domain):
                self.calls += 1
                raise ValueError('isolated proposal stub')
        service = Service()
        app = create_app(service)
        consumed = 0
        messages = []
        async def receive():
            nonlocal consumed
            if consumed == len(body):
                return {'type':'http.request','body':b'','more_body':False}
            chunk = body[consumed:consumed+16384]
            consumed += len(chunk)
            return {'type':'http.request','body':chunk,'more_body':consumed < len(body)}
        async def send(message):
            messages.append(message)
        async def run():
            await app({'type':'http','asgi':{'version':'3.0'},'http_version':'1.1',
                'method':method,'scheme':'http','path':path,'raw_path':path.encode(),
                'query_string':b'','root_path':'','client':('127.0.0.1',1),
                'server':('isolated',80),'headers':[(b'content-type',b'application/json'),*headers]},receive,send)
        asyncio.run(run())
        return next(m['status'] for m in messages if m['type']=='http.response.start'),consumed,service.calls

    def test_declared_oversize_rejected_before_read_or_service(self):
        body = b' '*(512*1024)+b'{"domain":"example.test"}'
        self.assertEqual((413,0,0),self.request(body,headers=[(b'content-length',str(len(body)).encode())]))

    def test_streamed_oversize_stops_before_complete_body(self):
        body = b' '*(512*1024)+b'{"domain":"example.test"}'
        status,consumed,calls = self.request(body)
        self.assertEqual(413,status)
        self.assertLess(consumed,len(body))
        self.assertLessEqual(consumed,262144+16384)
        self.assertEqual(0,calls)

    def test_small_valid_proposal_reaches_existing_service(self):
        body = b'{"domain":"example.test"}'
        self.assertEqual((403,len(body),1),self.request(body))

    def test_invalid_content_length_rejected_before_service(self):
        self.assertEqual((400,0,0),self.request(b'{}',headers=[(b'content-length',b'bad')]))

    def test_negative_content_length_rejected_before_service(self):
        self.assertEqual((400,0,0),self.request(b'{}',headers=[(b'content-length',b'-1')]))

    def test_health_route_remains_available(self):
        self.assertEqual((200,0,0),self.request(path='/health',method='GET'))

    def test_oversize_target_rejected_before_service(self):
        self.assertEqual((414,0,0),self.request(b'{}',path='/'+'x'*8192))

    def test_oversize_header_rejected_before_service(self):
        self.assertEqual((431,0,0),self.request(b'{}',headers=[(b'x-test',b'x'*32768)]))
