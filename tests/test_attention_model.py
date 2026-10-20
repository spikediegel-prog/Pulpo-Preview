from dataclasses import replace
import unittest

from pulpo.attention_model import age_text, attention_items
from pulpo.connection_observation import ConnectionObservation, PROVIDERS
from pulpo.evidence_observation import EvidenceObservation
from pulpo.governance_observer import GovernanceObservation
from pulpo.local_resources import Metric, ResourceSample


NOW = 1_790_000_000_000_000_000


def project(**changes):
    inputs = dict(connections={}, connection_errors={}, evidence=None, evidence_error=False,
                  governance=GovernanceObservation(), governance_selected=False, resources=None, now_ns=NOW)
    inputs.update(changes)
    return {item.key: item for item in attention_items(**inputs)}


def evidence(**changes):
    return replace(EvidenceObservation("a" * 32, NOW, True, 0, health="ok", volume_total=1000, volume_free=500), **changes)


class AttentionModelTests(unittest.TestCase):
    def test_first_run_gaps_are_not_problems(self):
        items = project()
        self.assertEqual({"connections:missing", "evidence:missing", "governance:coverage"}, set(items))
        self.assertTrue(all(item.kind == "Information gap" for item in items.values()))
        self.assertTrue(all(item.observed_at_ns is None for item in items.values()))
        self.assertIn("unresolved consequences remain unknown", items["governance:coverage"].impact)

    def test_provider_failures_stale_success_and_fixed_actions(self):
        reports = {provider: ConnectionObservation(provider, NOW, reason="tls") for provider in PROVIDERS}
        items = project(connections=reports)
        self.assertTrue(items["connection:UniFi UDM:failure"].udm_setup)
        self.assertFalse(items["connection:CrowdStrike:failure"].udm_setup)
        self.assertIn("identity unverified", items["connection:UniFi UDM:failure"].source)
        reports["UniFi UDM"] = ConnectionObservation("UniFi UDM", NOW-61_000_000_000, "Responded", "Accepted", "ok", devices_seen=2)
        items = project(connections=reports)
        self.assertNotIn("connection:UniFi UDM:failure", items)
        self.assertEqual("Information gap", items["connection:UniFi UDM:age"].kind)
        self.assertTrue(all(item.page in ("Connections", "Evidence", "Governance", "System") for item in items.values()))

    def test_evidence_conditions_keep_workflow_totals_out_of_incidents(self):
        healthy = evidence(denied=25, approval_required=15, permit_rejected=5, approval_rejected=3, errors=20)
        self.assertFalse(any(item.kind == "Problem" for item in project(evidence=healthy).values()))
        failed = replace(healthy, audit_valid=False, health="failed", volume_free=40,
                         database_bytes=1024, wal_bytes=70*1024**2, observed_at_ns=NOW-20_000_000_000)
        items = project(evidence=failed)
        self.assertEqual("Problem", items["evidence:audit"].kind)
        self.assertEqual("Problem", items["evidence:health"].kind)
        self.assertEqual("Information gap", items["evidence:age"].kind)
        self.assertEqual("Resource hint", items["evidence:capacity"].kind)
        self.assertEqual("Resource hint", items["evidence:wal"].kind)
        self.assertIn("cannot independently verify", items["evidence:audit"].impact)
        missing = project(evidence=evidence(health="not_checked", volume_total=None, volume_free=None))
        self.assertEqual("Information gap", missing["evidence:health"].kind)
        self.assertEqual("Information gap", missing["evidence:capacity"].kind)

    def test_invalid_sources_override_previous_samples_without_echo(self):
        private = "PRIVATE credential body /private/export.json https://private.example"
        reports = {"UniFi UDM": ConnectionObservation("UniFi UDM", NOW, reason="tls")}
        items = project(connections=reports, connection_errors={"UniFi UDM": private}, evidence=evidence(audit_valid=False), evidence_error=private,
                        governance=GovernanceObservation(state="Attention", source=private, summary=private), governance_selected=True)
        self.assertIn("connection:UniFi UDM:invalid", items)
        self.assertNotIn("connection:UniFi UDM:failure", items)
        self.assertIn("evidence:invalid", items)
        self.assertNotIn("evidence:audit", items)
        self.assertNotIn("PRIVATE", repr(items))
        self.assertTrue(all(item.observed_at_ns is None for item in items.values()))

    def test_governance_unknown_time_resource_hints_and_bound(self):
        resources = ResourceSample(NOW/1e9, 0, "PRIVATE source", "PRIVATE volume", Metric(95), Metric(80), Metric(None))
        failed = GovernanceObservation(state="Attention", policy="Recorded fingerprint")
        items = project(governance=failed, governance_selected=True, resources=resources)
        self.assertIsNone(items["governance:problem"].observed_at_ns)
        self.assertIn("failed audit check", items["governance:problem"].title)
        self.assertEqual("Resource hint", items["resource:cpu"].kind)
        self.assertEqual("Resource hint", items["resource:memory"].kind)
        self.assertEqual("Information gap", items["resources:missing"].kind)
        self.assertNotIn("PRIVATE", repr(items))
        aged = project(resources=replace(resources, observed_at=NOW/1e9-11))
        self.assertIn("resources:age", aged)
        maximal = project(connections={p: ConnectionObservation(p, NOW-61_000_000_000, reason="tls") for p in PROVIDERS},
                          governance=failed, governance_selected=True, resources=replace(resources, observed_at=NOW/1e9-11),
                          evidence=evidence(audit_valid=False, health="failed", observed_at_ns=NOW-20_000_000_000,
                                            volume_free=1, database_bytes=0, wal_bytes=70*1024**2))
        self.assertLessEqual(len(maximal), 24)
        self.assertEqual(maximal, project(connections={p: ConnectionObservation(p, NOW-61_000_000_000, reason="tls") for p in PROVIDERS},
                          governance=failed, governance_selected=True, resources=replace(resources, observed_at=NOW/1e9-11),
                          evidence=evidence(audit_valid=False, health="failed", observed_at_ns=NOW-20_000_000_000,
                                            volume_free=1, database_bytes=0, wal_bytes=70*1024**2)))

    def test_age_and_clock_mismatch_never_appear_fresh_or_zero(self):
        self.assertEqual("Age unknown", age_text(None, NOW))
        self.assertEqual("1m old", age_text(NOW-61_000_000_000, NOW))
        self.assertIn("ahead", age_text(NOW+10_000_000_000, NOW))
        items = project(evidence=evidence(observed_at_ns=NOW+10_000_000_000))
        self.assertIn("clock mismatch", items["evidence:age"].title)


if __name__ == "__main__":
    unittest.main()
