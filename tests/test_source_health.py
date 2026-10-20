import unittest

from pulpo.connection_observation import ConnectionObservation, PROVIDERS
from pulpo.evidence_observation import EvidenceObservation
from pulpo.governance_observer import GovernanceObservation
from pulpo.source_health_model import SOURCE_KEYS, SourceRead, source_age, source_health


class SourceHealthTests(unittest.TestCase):
    now = 100_000_000_000

    def project(self, **changes):
        values = dict(governance_selected=False, governance=GovernanceObservation(),
            evidence_selected=False, evidence=None, evidence_error=None,
            connections_selected={}, connections={}, connection_errors={}, reads={}, now_ns=self.now)
        values.update(changes)
        return {row.key: row for row in source_health(**values)}

    def test_first_run_is_five_unknown_sources_not_offline(self):
        rows = self.project()
        self.assertEqual(SOURCE_KEYS, tuple(rows))
        for row in rows.values():
            self.assertFalse(row.cached)
            self.assertEqual("Not selected", row.read_status)
            self.assertEqual("Age unknown", source_age(row, self.now))
            self.assertIn("does not mean offline", row.next_step)

    def test_local_read_is_distinct_from_source_time_and_reported_failure(self):
        observation = EvidenceObservation("a" * 32, self.now - 20_000_000_000, False, 0, health="failed")
        row = self.project(evidence_selected=True, evidence=observation,
            reads={"Evidence": SourceRead(self.now, True)})["Evidence"]
        self.assertEqual("Read OK", row.read_status)
        self.assertEqual("Stale", row.freshness)
        self.assertEqual("20s old", source_age(row, self.now))
        self.assertEqual(2, len(row.issues))
        self.assertIn("unchanged file does not refresh", row.next_step)
        self.assertIn("not zero", row.unknowns)

    def test_governance_read_success_never_supplies_missing_export_time(self):
        observation = GovernanceObservation(policy="Recorded · fingerprint", state="Attention")
        row = self.project(governance_selected=True, governance=observation,
            reads={"Governance": SourceRead(self.now, True)})["Governance"]
        self.assertTrue(row.cached)
        self.assertEqual("Read OK", row.read_status)
        self.assertIsNone(row.observed_at_ns)
        self.assertEqual("Unknown", row.source_id)
        self.assertEqual("Time unknown", row.freshness)
        self.assertTrue(row.issues)
        self.assertIn("Re-reading cannot establish freshness", row.next_step)

    def test_missing_database_checks_are_gaps_not_failed_checks(self):
        for health in ("not_checked", "unavailable", "failed", "ok"):
            observation = EvidenceObservation("a" * 32, self.now, True, 0, health=health)
            row = self.project(evidence_selected=True, evidence=observation)["Evidence"]
            self.assertEqual(health == "failed", row.problem)
            self.assertEqual(health != "ok", bool(row.issues))

    def test_failed_reads_override_cached_good_data_without_echoing_errors(self):
        good = EvidenceObservation("a" * 32, self.now, True, 0)
        connection = ConnectionObservation("UniFi UDM", self.now, "Responded", "Accepted", "ok", "b" * 32)
        rows = self.project(evidence_selected=True, evidence=good, evidence_error="PRIVATE secret /path",
            connections_selected={"UniFi UDM": "/private"}, connections={"UniFi UDM": connection},
            connection_errors={"UniFi UDM": "PRIVATE secret"})
        for key in ("Evidence", "UniFi UDM"):
            self.assertFalse(rows[key].cached)
            self.assertIsNone(rows[key].observed_at_ns)
            self.assertEqual("Unknown", rows[key].source_id)
            self.assertNotIn("PRIVATE", str(rows[key]))
            self.assertNotIn("/private", str(rows[key]))
        row = self.project(connections_selected={"UniFi UDM": True}, connections={"UniFi UDM": connection},
            reads={"UniFi UDM": SourceRead(self.now, False)})["UniFi UDM"]
        self.assertEqual("Read failed", row.read_status)
        self.assertFalse(row.cached)
        self.assertNotIn("Read collection completed", row.coverage)

    def test_provider_file_read_ok_can_report_tls_or_permission_failure(self):
        for provider in PROVIDERS:
            observation = ConnectionObservation(provider, self.now, reason="tls" if provider == "UniFi UDM" else "permission")
            row = self.project(connections_selected={provider: True}, connections={provider: observation},
                reads={provider: SourceRead(self.now, True)})[provider]
            self.assertEqual("Read OK", row.read_status)
            self.assertEqual("Recent", row.freshness)
            self.assertTrue(row.issues)
            self.assertIn("Unknown", row.unknowns)
            if provider == "UniFi UDM":
                self.assertIn("Do not bypass TLS", row.next_step)

    def test_freshness_boundaries_future_clocks_and_repeated_bounded_projection(self):
        for age, expected in ((15, "Recent"), (16, "Stale"), (-5, "Recent"), (-6, "Clock mismatch")):
            value = EvidenceObservation("a" * 32, self.now - age * 1_000_000_000, True, 0)
            row = self.project(evidence_selected=True, evidence=value)["Evidence"]
            self.assertEqual(expected, row.freshness)
            if age < 0:
                self.assertIn("ahead", source_age(row, self.now))
        for age, expected in ((60, "Recent"), (61, "Stale")):
            value = ConnectionObservation("NinjaOne", self.now - age * 1_000_000_000)
            row = self.project(connections_selected={"NinjaOne": True}, connections={"NinjaOne": value})["NinjaOne"]
            self.assertEqual(expected, row.freshness)
        rows = self.project(reads={"unrecognized source": SourceRead(self.now, True)})
        for _ in range(20):
            self.assertEqual(rows, self.project())
        self.assertEqual(5, len(rows))

    def test_clearing_selection_ignores_old_cache_and_read_metadata(self):
        value = EvidenceObservation("a" * 32, self.now, True, 0)
        row = self.project(evidence=value, reads={"Evidence": SourceRead(self.now, True)})["Evidence"]
        self.assertFalse(row.selected)
        self.assertFalse(row.cached)
        self.assertIsNone(row.read)
        self.assertIsNone(row.observed_at_ns)


if __name__ == "__main__":
    unittest.main()
