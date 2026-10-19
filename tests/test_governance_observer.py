from dataclasses import asdict
import json
import os
from pathlib import Path
import tempfile
import unittest

from pulpo import GovernanceKernel, Intent, Policy, PulpoOrchestrator
from pulpo.governance_observer import GovernanceObservation, observe_snapshot
from pulpo.mcp_boundary import MCPReadSnapshot, export_mcp_snapshot


class GovernanceObserverTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "snapshot.json"
        self.document = asdict(MCPReadSnapshot("a" * 64, True, 3, "b" * 64))

    def write(self, document):
        self.path.write_text(json.dumps(document), encoding="utf-8")
        self.path.chmod(0o600)

    def test_valid_report_is_recorded_and_never_enforcement_verified(self):
        self.write(self.document)
        result = observe_snapshot(self.path)
        self.assertEqual("Unknown", result.state)
        self.assertIn("a" * 64, result.policy)
        self.assertIn("3", result.integrity)
        self.assertIn("not decision counts", result.integrity)
        self.assertIn("export time and source authenticity: Unknown", result.source)
        self.assertIn("Unknown", result.decisions)
        self.assertNotIn("Verified", str(result))

    def test_source_failure_is_attention_not_an_independent_verification(self):
        self.document["audit_valid"] = False
        self.write(self.document)
        result = observe_snapshot(self.path)
        self.assertEqual("Attention", result.state)
        self.assertIn("Source reports", result.summary)
        self.assertIn("FAILED", result.integrity)

    def test_empty_audit_is_not_activity_or_readiness(self):
        self.document.update(audit_records=0, audit_tip=None)
        self.write(self.document)
        result = observe_snapshot(self.path)
        self.assertEqual("Unknown", result.state)
        self.assertIn("empty audit", result.integrity)
        self.assertEqual(GovernanceObservation().decisions, result.decisions)

    def test_malformed_injected_and_inconsistent_snapshots_clear_values_without_echo(self):
        good = json.dumps(self.document)
        candidates = ["{", "null", "[1]", "x" * 17000, "[" * 2000,
                      good[:-1] + ', "audit_valid":false}',
                      json.dumps(dict(self.document, permit="secret-bearer")),
                      json.dumps(dict(self.document, audit_records=True)),
                      json.dumps(dict(self.document, audit_records=0)),
                      json.dumps(dict(self.document, audit_tip=None)),
                      json.dumps(dict(self.document, source_schema="future.v1"))]
        for raw in candidates:
            with self.subTest(raw=raw[:40]):
                self.path.write_text(raw, encoding="utf-8")
                self.path.chmod(0o600)
                result = observe_snapshot(self.path)
                self.assertEqual("Attention", result.state)
                self.assertEqual(GovernanceObservation().policy, result.policy)
                self.assertNotIn("secret-bearer", str(result))
                self.assertEqual(raw, self.path.read_text(encoding="utf-8"))

    def test_missing_relative_directory_and_fifo_fail_without_creation(self):
        for path in (self.path, Path("snapshot.json"), self.path.parent):
            self.assertEqual("Attention", observe_snapshot(path).state)
        self.assertFalse(self.path.exists())
        if hasattr(os, "mkfifo"):
            os.mkfifo(self.path)
            self.assertEqual("Attention", observe_snapshot(self.path).state)

    def test_canonical_export_repeated_replayed_and_substituted_reads_do_not_mutate(self):
        kernel = GovernanceKernel(Policy(frozenset({"read"}), 0), secret=b"test-only")
        kernel.evaluate(Intent("agent:test", "read", "fixture", 0))
        export_mcp_snapshot(PulpoOrchestrator(kernel), self.path)
        before_audit, before_export = list(kernel.audit), self.path.read_bytes()
        for _ in range(10):
            result = observe_snapshot(self.path)
            self.assertEqual("Unknown", result.state)
            self.assertEqual(before_audit, list(kernel.audit))
            self.assertEqual(before_export, self.path.read_bytes())
        # A structurally valid substituted report is still unauthenticated.
        self.write(self.document)
        self.assertEqual("Unknown", observe_snapshot(self.path).state)
        self.path.write_text("{}")
        self.assertEqual("Attention", observe_snapshot(self.path).state)
        self.assertEqual(before_audit, list(kernel.audit))


if __name__ == "__main__":
    unittest.main()
