"""Negative transport controls retained when extracting #242's parser bounds."""
import json
from io import BytesIO
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from pulpo.authority_client import AuthorityClient
from pulpo.namecom_core import (
    NameComCoreClient, NameComCoreConfig, NameComResponse, NameComViolation,
    UrllibNameComTransport,
)


class Response(BytesIO):
    status = 200
    headers = {}

    def geturl(self):
        return 'https://authority.example.com/v1/approval-requests/request%3A1'


def nested(depth):
    return b'{"extra":' * depth + b'0' + b'}' * depth


class ExternalResponseBoundsTests(unittest.TestCase):
    def test_authority_rejects_depth_items_and_parser_recursion(self):
        for body in (b'{"status":"pending","extra":' + nested(30) + b'}',
                     json.dumps({'status': 'pending', 'extra': list(range(4097))}).encode(),
                     b'{"status":"pending","extra":' + b'[' * 2000 + b'0' + b']' * 2000 + b'}'):
            with self.subTest(length=len(body)):
                client = AuthorityClient('https://authority.example.com')
                with patch.object(client._opener, 'open', return_value=Response(body)):
                    with self.assertRaisesRegex(RuntimeError, 'resource limits'):
                        client.poll_approval('request:1')

    def test_namecom_rejects_oversized_valid_json_and_deep_response(self):
        for body in (b'{}' + b' ' * 1_048_576, nested(30)):
            with self.subTest(length=len(body)):
                transport = unittest.mock.Mock()
                transport.request.return_value = NameComResponse(200, {}, body)
                client = NameComCoreClient(NameComCoreConfig('tester-test', 'synthetic'), transport=transport)
                with self.assertRaises(NameComViolation):
                    client.check_availability('example.com')
                self.assertEqual(1, transport.request.call_count)

    def test_namecom_bounds_success_and_http_error_reads_and_closes_both(self):
        transport = UrllibNameComTransport()
        response = Response(b'{}' + b' ' * 1_048_600)
        with patch.object(transport._opener, 'open', return_value=response):
            result = transport.request('GET', 'https://api.dev.name.com/core/v1/domains', {}, None)
        self.assertEqual(1_048_577, len(result.body))
        self.assertTrue(response.closed)
        body = Response(b' ' * 1_048_600)
        error = HTTPError('https://api.dev.name.com/core/v1/domains', 500, 'synthetic', {}, body)
        with patch.object(transport._opener, 'open', side_effect=error):
            result = transport.request('GET', error.url, {}, None)
        self.assertEqual(1_048_577, len(result.body))
        self.assertTrue(body.closed)
