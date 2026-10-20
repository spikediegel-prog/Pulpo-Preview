from dataclasses import replace
import json
import unittest

from pulpo.evidence_observation import EvidenceObservation
from pulpo.governance_observer import GovernanceObservation
from pulpo.source_health_model import SourceRead, source_health
from pulpo.troubleshooting import findings, support_report


class TroubleshootingTests(unittest.TestCase):
    def sources(self, *, evidence=None, reads=None, error=None):
        return source_health(governance_selected=False, governance=GovernanceObservation(),
            evidence_selected=evidence is not None or error is not None, evidence=evidence, evidence_error=error,
            connections_selected={}, connections={}, connection_errors={}, reads=reads or {}, now_ns=100_000_000_000)

    def test_missing_sources_and_service_status_are_unknown_not_offline(self):
        rows = findings(self.sources())
        self.assertEqual(9, len(rows))
        self.assertTrue(all(row.state == "Unknown" for row in rows))
        self.assertTrue(all(row.checked_at_ns is None for row in rows))
        self.assertIn("No live service-health", rows[1].cause)
        self.assertEqual("Recorded", findings(self.sources(), local_checked_at_ns=1)[0].state)
        self.assertEqual("Needs attention", findings(self.sources(), cleanup_blocked=True)[-1].state)

    def test_capacity_thresholds_missing_metrics_and_stale_results_are_scoped(self):
        for free, expected in ((0, "Needs attention"), (9, "Needs attention"), (10, "Recorded"), (90, "Recorded")):
            evidence = EvidenceObservation("a" * 32, 99_000_000_000, True, 0, volume_total=100, volume_free=free)
            rows = findings(self.sources(evidence=evidence, reads={"Evidence": SourceRead(100_000_000_000, True)}), evidence)
            storage = next(row for row in rows if row.key == "storage")
            self.assertEqual(expected, storage.state)
            self.assertIn(f"{free} of 100 bytes", storage.cause)
            self.assertEqual(99_000_000_000, storage.source_at_ns)
        stale = replace(evidence, observed_at_ns=1)
        row = next(row for row in findings(self.sources(evidence=stale, reads={"Evidence": SourceRead(100, True)}), stale) if row.key == "storage")
        self.assertEqual("Needs attention", row.state)
        self.assertIn("stale", row.cause)
        missing = replace(evidence, volume_total=None, volume_free=None)
        row = next(row for row in findings(self.sources(evidence=missing, reads={"Evidence": SourceRead(100, True)}), missing) if row.key == "storage")
        self.assertEqual("Unknown", row.state)

    def test_failed_read_suppresses_cached_capacity_and_never_exports_secrets(self):
        secret = "PRIVATE /home/operator/key.pem https://secret-host/api?token=private"
        evidence = EvidenceObservation("b" * 32, 99_000_000_000, True, 0, volume_total=100, volume_free=2)
        sources = self.sources(evidence=evidence, error=secret, reads={"Evidence": SourceRead(100_000_000_000, False)})
        # Unknown/raw display fields cannot enter the support report.
        sources = tuple(replace(row, source_id=secret, coverage=secret, next_step=secret, issues=(secret,)) for row in sources)
        rows = findings(sources, evidence)
        storage = next(row for row in rows if row.key == "storage")
        self.assertIsNone(storage.source_at_ns)
        self.assertNotIn("2 of 100", storage.cause)
        report = support_report(rows, 101_000_000_000)
        self.assertNotIn(secret, report)
        self.assertNotIn("b" * 32, report)
        parsed = json.loads(report)
        self.assertEqual("Unknown", parsed["enforcement"])
        self.assertEqual("none", parsed["authority_effect"])
        self.assertEqual("1970-01-01 00:01:40.000000000 UTC", next(row for row in parsed["findings"] if row["check"] == "Evidence export")["local_check_at"])

    def test_failed_health_and_future_source_cannot_become_all_clear(self):
        evidence = EvidenceObservation("a" * 32, 110_000_000_000, False, 0, health="failed")
        rows = findings(self.sources(evidence=evidence, reads={"Evidence": SourceRead(100, True)}), evidence)
        self.assertEqual("Needs attention", next(row for row in rows if row.key == "Evidence").state)
        self.assertEqual("Unknown", next(row for row in rows if row.key == "storage").state)


if __name__ == "__main__":
    unittest.main()
