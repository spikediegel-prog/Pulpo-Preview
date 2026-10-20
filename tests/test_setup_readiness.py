import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pulpo.connection_observation import ConnectionObservation, PROVIDERS
from pulpo.evidence_observation import EvidenceObservation
from pulpo.governance_observer import GovernanceObservation
from pulpo.setup_readiness import is_wsl, readiness_items, reviewed_udm_setup
from pulpo.source_health_model import SourceRead, source_health
from pulpo.udm_setup import UdmSetup


class SetupReadinessTests(unittest.TestCase):
    now = 100_000_000_000

    def sources(self, **changes):
        values = dict(governance_selected=False, governance=GovernanceObservation(), evidence_selected=False,
            evidence=None, evidence_error=None, connections_selected={}, connections={}, connection_errors={}, reads={}, now_ns=self.now)
        values.update(changes)
        return source_health(**values)

    def test_only_linux_with_wsl_kernel_is_enabled(self):
        for system, release, expected in (("Linux", "6.6.87.2-microsoft-standard-WSL2", True),
                ("Linux", "4.4.0-Microsoft", True), ("Windows", "microsoft", False),
                ("Linux", "6.8.0-generic", False), ("Darwin", "microsoft", False)):
            with patch("pulpo.setup_readiness.platform.system", return_value=system), \
                 patch("pulpo.setup_readiness.platform.release", return_value=release):
                self.assertEqual(expected, is_wsl())

    def test_first_run_core_gaps_optional_connectors_and_unknown_assurance(self):
        rows = {row.key: row for row in readiness_items(self.sources())}
        self.assertEqual(9, len(rows))
        self.assertEqual("Needs setup", rows["Governance"].state)
        self.assertEqual("Needs setup", rows["Evidence"].state)
        for key in PROVIDERS:
            self.assertEqual("Optional", rows[key].state)
        for key in ("udm_trust", "udm_site", "assurance"):
            self.assertEqual("Unknown", rows[key].state)

    def test_recorded_setup_never_becomes_verified_enforcement_or_trust(self):
        connections = {provider: ConnectionObservation(provider, self.now, "Responded", "Accepted", "ok") for provider in PROVIDERS}
        sources = self.sources(governance_selected=True, governance=GovernanceObservation(policy="Recorded · fixture"),
            evidence_selected=True, evidence=EvidenceObservation("a" * 32, self.now, True, 0),
            connections_selected=dict.fromkeys(PROVIDERS, True), connections=connections,
            reads={key: SourceRead(self.now, True) for key in ("Governance", "Evidence", *PROVIDERS)})
        rows = {row.key: row for row in readiness_items(sources, udm_reviewed=True)}
        for key in ("Governance", "Evidence", *PROVIDERS, "udm_site"):
            self.assertEqual("Recorded", rows[key].state)
        self.assertIn("freshness stays Unknown", rows["Governance"].detail)
        self.assertEqual("Unknown", rows["assurance"].state)
        self.assertEqual("Unknown", rows["udm_trust"].state)
        self.assertIn("not proof of discovery", rows["udm_site"].detail)

    def test_failed_stale_and_future_sources_need_attention(self):
        for stamp in (self.now - 16_000_000_000, self.now + 6_000_000_000):
            source = self.sources(evidence_selected=True, evidence=EvidenceObservation("a" * 32, stamp, True, 0),
                reads={"Evidence": SourceRead(self.now, True)})
            row = next(row for row in readiness_items(source) if row.key == "Evidence")
            self.assertEqual("Needs attention", row.state)
        sources = self.sources(evidence_selected=True, evidence=EvidenceObservation("a" * 32, self.now, True, 0),
            evidence_error="PRIVATE credential /path", reads={"Evidence": SourceRead(self.now, False)})
        row = next(row for row in readiness_items(sources) if row.key == "Evidence")
        self.assertEqual("Needs attention", row.state)
        self.assertNotIn("PRIVATE", row.detail)

    def test_tls_report_is_a_blocker_not_live_probe_or_site_proof(self):
        sources = self.sources(connections_selected={"UniFi UDM": True},
            connections={"UniFi UDM": ConnectionObservation("UniFi UDM", self.now - 70_000_000_000, reason="tls")})
        rows = {row.key: row for row in readiness_items(sources)}
        self.assertEqual("Needs attention", rows["udm_trust"].state)
        self.assertIn("source time is Stale", rows["udm_trust"].detail)
        self.assertEqual("Unknown", rows["udm_site"].state)
        self.assertIn("cannot fill this gap", rows["udm_site"].detail)

    def test_readable_unknown_collection_result_is_still_unknown(self):
        sources = self.sources(connections_selected={"NinjaOne": True},
            connections={"NinjaOne": ConnectionObservation("NinjaOne", self.now)},
            reads={"NinjaOne": SourceRead(self.now, True)})
        row = next(row for row in readiness_items(sources) if row.key == "NinjaOne")
        self.assertEqual("Unknown", row.state)

    def guide(self):
        values = dict(origin="https://192.168.1.1", inventory_output="/tmp/fixture-observation.json",
                      ca="/tmp/public-ca.pem", site="11111111-2222-3333-4444-555555555555")
        setup = UdmSetup(values["origin"], "collect", values["inventory_output"], values["ca"], values["site"])
        return SimpleNamespace(window=object(), saved={"collect": (setup, "/tmp/fixture-setup.json")},
            fields={key: Mock(get=Mock(return_value=value)) for key, value in values.items()},
            config=Mock(side_effect=AssertionError("No file probes")))

    def test_reviewed_site_uses_matching_non_secret_form_without_path_probes(self):
        guide = self.guide()
        with patch("pathlib.Path.is_file", side_effect=AssertionError("No certificate read")), \
             patch("pathlib.Path.is_dir", side_effect=AssertionError("No path probes")):
            self.assertTrue(reviewed_udm_setup(guide))
            guide.config.assert_not_called()
            for key in guide.fields:
                field = guide.fields[key]
                original = field.get.return_value
                field.get.return_value = "changed PRIVATE"
                self.assertFalse(reviewed_udm_setup(guide))
                field.get.return_value = original
        guide.window = None
        self.assertFalse(reviewed_udm_setup(guide))
        self.assertFalse(reviewed_udm_setup(None))

    def test_missing_or_malformed_handoff_cannot_supply_site_observation(self):
        guide = self.guide()
        for saved in ({}, {"sites": (object(), "untrusted")}, {"collect": (object(), "untrusted")}, {"collect": ()}):
            guide.saved = saved
            self.assertFalse(reviewed_udm_setup(guide))


if __name__ == "__main__":
    unittest.main()
