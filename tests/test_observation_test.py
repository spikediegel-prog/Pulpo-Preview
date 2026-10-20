from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pulpo import observation_test
from pulpo.evidence_observation import load_observation
from pulpo.mcp_plugin import load_mcp_snapshot


@unittest.skipUnless(os.name == "posix", "Ubuntu test workload")
class ObservationTestTests(unittest.TestCase):
    def test_real_decisions_export_without_private_state_or_invented_ai(self):
        with tempfile.TemporaryDirectory() as parent:
            with patch.object(tempfile, "tempdir", parent), \
                    patch.object(observation_test.time, "sleep"), redirect_stdout(io.StringIO()):
                result = observation_test.run(cycles=2, interval=1)
            folder = result
            self.assertEqual(0o700, folder.stat().st_mode & 0o777)
            self.assertEqual({"TEST-ONLY.txt", "TEST-ONLY-governance.json", "TEST-ONLY-evidence.json"},
                             {p.name for p in folder.iterdir()})
            sample = load_observation(folder / "TEST-ONLY-evidence.json")
            governance = load_mcp_snapshot(folder / "TEST-ONLY-governance.json")
            self.assertEqual((2, 2, 2, 2), (sample.allowed, sample.denied, sample.permit_consumed, sample.permit_rejected))
            self.assertTrue(sample.audit_valid)
            self.assertEqual("ok", sample.health)
            self.assertGreater(sample.writes, 0)
            self.assertGreater(sample.commits, 0)
            self.assertIsNone(sample.ai.input_tokens)
            self.assertIsNone(sample.ai.cost_microusd)
            self.assertEqual(governance.audit_records, sample.audit_records)
            self.assertEqual(0o600, (folder / "TEST-ONLY-evidence.json").stat().st_mode & 0o777)

    def test_invalid_bounds_create_nothing(self):
        for options in ({"cycles": 0}, {"cycles": 61}, {"cycles": True}, {"interval": 0}, {"interval": 11}):
            with patch.object(observation_test.tempfile, "mkdtemp") as create:
                with self.assertRaises(ValueError):
                    observation_test.run(**options)
                create.assert_not_called()

    def test_interruption_closes_and_removes_private_state(self):
        with tempfile.TemporaryDirectory() as parent:
            with patch.object(tempfile, "tempdir", parent), \
                    patch.object(observation_test.time, "sleep", side_effect=KeyboardInterrupt), \
                    redirect_stdout(io.StringIO()):
                with self.assertRaises(KeyboardInterrupt):
                    observation_test.run(cycles=2)
            folder = next(Path(parent).glob("pulpo-TEST-ONLY-*"))
            self.assertFalse(any(folder.glob("private-state-*")))
            self.assertEqual(1, load_observation(folder / "TEST-ONLY-evidence.json").allowed)

    def test_publication_failure_stops_without_retry_and_cleans_state(self):
        with tempfile.TemporaryDirectory() as parent:
            with patch.object(tempfile, "tempdir", parent), \
                    patch.object(observation_test, "export_mcp_snapshot", side_effect=OSError("test failure")) as publish, \
                    patch.object(observation_test, "export_evidence_observation") as evidence, \
                    redirect_stdout(io.StringIO()):
                with self.assertRaises(OSError):
                    observation_test.run(cycles=2)
            publish.assert_called_once()
            evidence.assert_not_called()
            folder = next(Path(parent).glob("pulpo-TEST-ONLY-*"))
            self.assertEqual(["TEST-ONLY.txt"], [p.name for p in folder.iterdir()])
