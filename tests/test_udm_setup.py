from dataclasses import asdict, replace
import io
import json
from pathlib import Path
import shlex
import tempfile
import time
import unittest
from unittest.mock import patch

from pulpo import connection_collector as collector
from pulpo.connection_observation import ConnectionObservation
from pulpo.udm_setup import UdmSetup, UdmSites, collector_command, discovery_source, load_setup, load_sites
from pulpo.mcp_boundary import _publish_snapshot
from tests.test_connections import SITE, page


class UdmSetupTests(unittest.TestCase):
    def test_private_handoff_roundtrip_rejects_credentials_and_bad_targets(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/"setup.json"
            setup = UdmSetup("https://192.168.1.1", "sites", str(Path(temporary)/"sites.json"))
            _publish_snapshot(setup, path)
            self.assertEqual(setup, load_setup(path))
            for change in ({"origin":"http://192.168.1.1"}, {"origin":"https://169.254.169.254"},
                    {"origin":"https://key@192.168.1.1"}, {"origin":"https://192.168.\n1.1"},
                    {"output":"relative.json"}, {"mode":"execute"}, {"mode":"collect"}):
                with self.assertRaises(ValueError): replace(setup, **change)
            value=asdict(setup);value["api_key"]="PRIVATE"
            path.write_text(json.dumps(value));path.chmod(0o600)
            with self.assertRaises(ValueError):load_setup(path)

    def test_site_discovery_fixed_route_and_sanitized_failures(self):
        response=page([{"id":SITE,"name":"PRIVATE"}])
        with patch.object(collector,"_request",return_value=response) as request:
            result=collector.discover_sites("https://192.168.1.1","fixture-key")
        self.assertEqual((SITE,),result.site_ids)
        self.assertTrue(result.more_available)
        self.assertNotIn("PRIVATE",json.dumps(asdict(result)))
        self.assertNotIn("fixture-key",json.dumps(asdict(result)))
        self.assertEqual("/proxy/network/integration/v1/sites?offset=0&limit=100",request.call_args.args[1])
        for reason in ("tls","authentication","permission","timeout"):
            with patch.object(collector,"_request",side_effect=collector.CollectionError(reason, reason in ("authentication","permission"))):
                failure=collector.discover_sites("https://192.168.1.1","fixture-key")
                self.assertIsInstance(failure,ConnectionObservation)
                self.assertEqual(reason,failure.reason)
                self.assertIsNone(failure.devices_seen)
        with patch.object(collector,"_request",return_value=page([{"id":"bad"}])):
            self.assertEqual("response",collector.discover_sites("https://192.168.1.1","fixture-key").reason)

    def test_site_report_bounds_time_and_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/"sites.json"
            sites=UdmSites(time.time_ns(),discovery_source("https://192.168.1.1"),(SITE,),False)
            _publish_snapshot(sites,path)
            self.assertEqual(sites,load_sites(path))
            for ids in ((SITE,SITE),("bad",),tuple(SITE for _ in range(101))):
                with self.assertRaises(ValueError):replace(sites,site_ids=ids)
            _publish_snapshot(replace(sites,observed_at_ns=time.time_ns()-901_000_000_000),path)
            with self.assertRaises(ValueError):load_sites(path)

    def test_cli_profile_no_credential_fields_no_option_substitution(self):
        with tempfile.TemporaryDirectory() as temporary:
            profile=Path(temporary)/"profile.json";output=Path(temporary)/"sites.json"
            _publish_snapshot(UdmSetup("https://192.168.1.1","sites",str(output)),profile)
            result=UdmSites(time.time_ns(),discovery_source("https://192.168.1.1"),(SITE,),False)
            with patch.dict(collector.os.environ,{"PULPO_UNIFI_API_KEY":"fixture-only"}), patch.object(collector,"discover_sites",return_value=result) as discover, patch("sys.stdout",new_callable=io.StringIO):
                self.assertEqual(0,collector.main(["unifi","--setup-profile",str(profile)]))
                self.assertEqual(result,load_sites(output))
                discover.assert_called_once_with("https://192.168.1.1","fixture-only",None)
            with patch.object(collector,"collect") as collect, patch("sys.stderr",new_callable=io.StringIO):
                with self.assertRaises(SystemExit): collector.main(["unifi","--setup-profile",str(profile),"--origin","https://192.168.1.2"])
                collect.assert_not_called()
            _publish_snapshot(UdmSetup("https://192.168.1.1","sites",str(profile)),profile)
            with patch.object(collector,"discover_sites") as discover, patch("sys.stderr",new_callable=io.StringIO):
                with self.assertRaises(SystemExit): collector.main(["unifi","--setup-profile",str(profile)])
                discover.assert_not_called()

    def test_command_quotes_paths_without_expanding_shell_text(self):
        path="/tmp/owner's $(command) `literal`; setup.json"
        self.assertEqual(path,shlex.split(collector_command(path))[-1])
        self.assertIn("owner''s",collector_command(path,windows=True))
        for bad in ("/tmp/bad\ncommand", "/tmp/bad’quote.json"):
            with self.assertRaises(ValueError):collector_command(bad,windows=True)


if __name__ == "__main__":unittest.main()
