import unittest

from pulpo.decision_explorer import record_details, record_time
from pulpo.evidence_observation import EvidenceEvent, MAX_COUNTER


class DecisionProjectionTests(unittest.TestCase):
    def event(self, name, outcome="recorded"):
        return EvidenceEvent(1_000_000_001, name, outcome, "a" * 64)

    def test_decision_is_not_execution_or_approval(self):
        for outcome in ("allowed", "denied", "approval_required", "blocked_by_policy", "recorded"):
            detail = record_details(self.event("decision", outcome))
            self.assertIn("Source-reported outcome: " + outcome.replace("_", " "), detail)
            self.assertIn("Approval\nUnknown", detail)
            self.assertIn("Permit\nUnknown", detail)
            self.assertIn("Execution and consequence\nUnknown", detail)
            self.assertIn("Decision reason and policy binding are not exported", detail)

    def test_permit_and_approval_records_cannot_fill_other_stages(self):
        for name in ("approval_verified", "approval_rejected", "permit_consumed", "permit_rejected"):
            detail = record_details(self.event(name))
            stage = "Approval" if name.startswith("approval") else "Permit"
            self.assertIn(stage + "\nRecorded", detail)
            self.assertIn("Policy decision\nUnknown", detail)
            self.assertIn("Execution and consequence\nUnknown", detail)
            self.assertIn("Request and target\nUnknown", detail)

    def test_directives_and_other_are_not_decisions(self):
        for name in ("directive_activated", "directive_revoked", "other"):
            self.assertEqual(5, record_details(self.event(name)).count("Unknown"))

    def test_times_preserve_nanoseconds_and_contract_bounds(self):
        self.assertEqual("1970-01-01 00:00:01.000000001 UTC", record_time(1_000_000_001))
        self.assertEqual("1970-01-01 00:00:00.000000000 UTC", record_time(0))
        self.assertEqual("2262-04-11 23:47:16.854775807 UTC", record_time(MAX_COUNTER))


if __name__ == "__main__":
    unittest.main()
