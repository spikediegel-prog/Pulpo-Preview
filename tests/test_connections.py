from dataclasses import asdict, replace
import json
from pathlib import Path
import ssl
import tempfile
import time
import unittest
from unittest.mock import patch

from pulpo import connection_collector as collector
from pulpo.connection_observation import ConnectionObservation, load_connection_observation


SITE = "12345678-1234-1234-1234-123456789abc"


def page(rows):
    return {"data": rows, "count": len(rows), "offset": 0, "limit": 100, "totalCount": 150}


class ConnectorTests(unittest.TestCase):
    def test_udm_fixed_reads_bounded_counts_and_no_sensitive_export(self):
        replies = [page([{"state": "ONLINE", "name": "PRIVATE", "ipAddress": "PRIVATE"}, {"state": "OFFLINE"}]), page([{"macAddress": "PRIVATE"}])]
        with patch.object(collector, "_request", side_effect=replies) as request:
            result = collector.collect("UniFi UDM", "https://192.168.1.1", api_key="fixture-key", site_id=SITE)
        self.assertEqual((2, 1, 1), (result.devices_seen, result.online_seen, result.clients_seen))
        self.assertEqual("Accepted", result.authentication)
        self.assertEqual(2, request.call_count)
        self.assertTrue(all(call.args[1].startswith(f"/proxy/network/integration/v1/sites/{SITE}/") for call in request.call_args_list))
        self.assertNotIn("PRIVATE", json.dumps(asdict(result)))
        self.assertNotIn("fixture-key", json.dumps(asdict(result)))
        self.assertNotIn("192.168", json.dumps(asdict(result)))

    def test_cloud_collectors_scope_and_partial_failure_clear_metrics(self):
        token = {"access_token": "fixture-access", "token_type": "Bearer"}
        for provider, origin, replies in (("NinjaOne", "https://app.ninjarmm.com", [token, [{}], [{}, {}]]),
                ("CrowdStrike", "https://api.crowdstrike.com", [token, {"resources": ["a"]}, {"resources": ["b", "c"]}])):
            with self.subTest(provider=provider), patch.object(collector, "_request", side_effect=replies) as request:
                result = collector.collect(provider, origin, client_id="fixture-id", client_secret="fixture-secret")
                self.assertEqual("ok", result.reason)
                self.assertEqual((1, 2), (result.devices_seen, result.alerts_seen))
                if provider == "NinjaOne": self.assertEqual("monitoring", request.call_args_list[0].kwargs["form"]["scope"])
                self.assertNotIn("fixture", json.dumps(asdict(result)))
            with patch.object(collector, "_request", side_effect=[token, replies[1], collector.CollectionError("permission", True)]):
                result = collector.collect(provider, origin, client_id="fixture-id", client_secret="fixture-secret")
                self.assertEqual("permission", result.reason)
                self.assertIsNone(result.devices_seen)
                self.assertIsNone(result.alerts_seen)
                self.assertEqual("Unknown", result.authentication)

    def test_bad_configuration_malformed_results_and_auth_failures(self):
        with patch.object(collector, "_request") as request:
            for origin in ("http://192.168.1.1", "https://127.0.0.1", "https://169.254.169.254", "https://8.8.8.8", "https://user:pass@192.168.1.1", "https://192.168.1.1/path"):
                self.assertEqual("configuration", collector.collect("UniFi UDM", origin, site_id=SITE, api_key="fixture").reason)
            self.assertEqual("configuration", collector.collect("UniFi UDM", "https://192.168.1.1", site_id="../escape", api_key="fixture").reason)
            self.assertEqual("configuration", collector.collect("CrowdStrike", "https://example.com", client_id="a", client_secret="b").reason)
            request.assert_not_called()
        for token in ({"token_type": 123}, {"token_type": "bearer", "access_token": "bad\nheader"}, {"token_type": "bearer"}):
            with patch.object(collector, "_request", return_value=token):
                self.assertNotEqual("ok", collector.collect("CrowdStrike", "https://api.crowdstrike.com", client_id="fixture", client_secret="fixture").reason)
        with patch.object(collector, "_request", side_effect=collector.CollectionError("authentication", True)):
            result = collector.collect("UniFi UDM", "https://192.168.1.1", site_id=SITE, api_key="fixture")
            self.assertEqual(("Responded", "Rejected"), (result.reachability, result.authentication))
        for bad in (page([{"state": "NEW_UNKNOWN_STATE"}]), {"data": [], "count": True, "offset": 0, "totalCount": 0}, page([{}] * 101)):
            with patch.object(collector, "_request", side_effect=[bad, page([])]):
                result = collector.collect("UniFi UDM", "https://192.168.1.1", site_id=SITE, api_key="fixture")
                self.assertEqual("response", result.reason)
                self.assertIsNone(result.devices_seen)

    def test_transport_blocks_redirect_compression_bad_json_and_write_route(self):
        class Response:
            def __init__(self, status=200, body=b'{}', headers=None):
                self.status, self.body, self.headers = status, body, headers or {"Content-Type": "application/json"}
            def getheader(self, key, default=None): return self.headers.get(key, default)
            def read1(self, limit):
                block, self.body = self.body[:limit], self.body[limit:]
                return block
        class Connection:
            sock = None
            def __init__(self, response): self.response, self.closed, self.calls = response, False, []
            def request(self, *args, **kwargs): self.calls.append((args, kwargs))
            def getresponse(self): return self.response
            def close(self): self.closed = True
        for response in (Response(302), Response(429), Response(body=b'{"x":1,"x":2}'), Response(body=b'{"x":NaN}'),
                Response(body=b'x' * (collector.MAX_BYTES + 1)), Response(headers={"Content-Encoding": "gzip"})):
            connection = Connection(response)
            with patch.object(collector.http.client, "HTTPSConnection", return_value=connection) as constructor:
                with self.assertRaises(collector.CollectionError):
                    collector._request("api.crowdstrike.com", "/devices/queries/devices/v1?limit=100&offset=0", ssl.create_default_context(), token="fixture", deadline=time.monotonic() + 20)
                constructor.assert_called_once()
                self.assertEqual("GET", connection.calls[0][0][0])
                self.assertTrue(connection.closed)
        with patch.object(collector.http.client, "HTTPSConnection") as constructor:
            with self.assertRaises(collector.CollectionError):
                collector._request("api.crowdstrike.com", "/devices/entities/devices-actions/v2", None, token="fixture", deadline=time.monotonic()+20)
            constructor.assert_not_called()

    def test_strict_private_observation_and_publication_without_kernel(self):
        from pulpo.mcp_boundary import _publish_snapshot
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "observation.json"
            sample = ConnectionObservation("NinjaOne", time.time_ns())
            _publish_snapshot(sample, path)
            self.assertEqual(sample, load_connection_observation(path))
            self.assertEqual("Stale", replace(sample, observed_at_ns=time.time_ns()-61_000_000_000).freshness())
            for changes in ({"schema": "fake"}, {"reachability": "Governed"}, {"devices_seen": True}, {"reason": "unavailable", "devices_seen": 0}, {"source_id": "PRIVATE"}):
                with self.assertRaises(ValueError): replace(sample, **changes)
            value = asdict(sample)
            value["api_key"] = "PRIVATE"
            path.write_text(json.dumps(value))
            path.chmod(0o600)
            with self.assertRaises(ValueError): load_connection_observation(path)
            _publish_snapshot(replace(sample, observed_at_ns=time.time_ns()+60_000_000_000), path)
            with self.assertRaises(ValueError): load_connection_observation(path)


if __name__ == "__main__":
    unittest.main()
