"""`pulpo incidents` CLI: list / show / summary over a frozen incident report.

Read-only, except for `report`: list/show/summary load a frozen
`pulpo.incident-report.v3` snapshot (produced by `export_incident_report`)
and never open a database, never append to the audit, and offer no
lifecycle transition. `report` files a human incident report into the
canonical audit (see `pulpo incidents report --help`).
"""
import argparse
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from pulpo import GovernanceKernel, Policy, PulpoOrchestrator, SQLiteKernelState
from pulpo.cli import (
    _incidents_list_command,
    _incidents_show_command,
    _incidents_summary_command,
    build_parser,
    main,
)
from pulpo.incident_channel import export_incident_report


def _namespace(**kwargs):
    values = {
        "report": None, "kind": None, "resolution": None, "lifecycle": None,
        "since": None, "until": None, "record_id": None,
    }
    values.update(kwargs)
    return argparse.Namespace(**values)


class IncidentsCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "state.sqlite"
        self.backend = SQLiteKernelState(self.db)
        self.addCleanup(self.backend.close)
        self.kernel = GovernanceKernel(Policy(frozenset({"read"}), 0), secret=b"test-only", state=self.backend)
        self.owner = PulpoOrchestrator(self.kernel)
        # One unresolved incident (first seen 1s after the epoch) and one
        # near-miss (first seen 2s after the epoch).
        self.backend.append("purchase_consequence_unknown",
                            {"order_hash": "a" * 64, "intent_hash": "b" * 64,
                             "permit_hash": "c" * 64, "reservation_id": "res-1",
                             "reason": "external_consequence_not_yet_verified"}, 1_000_000_000)
        self.backend.append("permit_rejected",
                            {"permit": "d" * 64, "reason": "permit_expired"}, 2_000_000_000)
        self.report_path = Path(self.temp.name) / "incident_report.json"
        export_incident_report(self.owner, self.report_path)
        self.incident_id, self.near_miss_id = self._record_ids()

    def _record_ids(self):
        from pulpo.incident_channel import load_incident_report
        report = load_incident_report(self.report_path)
        incident = next(record for record in report.records if record.kind == "incident")
        near_miss = next(record for record in report.records if record.kind == "near_miss")
        return incident.record_id, near_miss.record_id

    def _run(self, func, args):
        output = io.StringIO()
        with redirect_stdout(output):
            code = func(args)
        return code, output.getvalue()

    def test_list_all(self):
        code, output = self._run(_incidents_list_command, _namespace(report=str(self.report_path)))
        self.assertEqual(0, code)
        self.assertIn("Matching .................. 2", output)
        self.assertIn(self.incident_id, output)
        self.assertIn(self.near_miss_id, output)
        self.assertIn("incident · unresolved · open", output)
        self.assertIn("near_miss · not_applicable · not_applicable", output)

    def test_list_kind_filter(self):
        code, output = self._run(
            _incidents_list_command, _namespace(report=str(self.report_path), kind="incident"))
        self.assertEqual(0, code)
        self.assertIn("Matching .................. 1", output)
        self.assertIn(self.incident_id, output)
        self.assertNotIn(self.near_miss_id, output)

    def test_list_resolution_filter(self):
        code, output = self._run(
            _incidents_list_command,
            _namespace(report=str(self.report_path), resolution="not_applicable"))
        self.assertIn("Matching .................. 1", output)
        self.assertIn(self.near_miss_id, output)
        self.assertNotIn(self.incident_id, output)

    def test_list_lifecycle_filter(self):
        code, output = self._run(
            _incidents_list_command, _namespace(report=str(self.report_path), lifecycle="open"))
        self.assertIn("Matching .................. 1", output)
        self.assertIn(self.incident_id, output)

    def test_list_time_window(self):
        code, output = self._run(
            _incidents_list_command,
            _namespace(report=str(self.report_path), since="1970-01-01T00:00:01.500Z"))
        self.assertIn("Matching .................. 1", output)
        self.assertIn(self.near_miss_id, output)
        self.assertNotIn(self.incident_id, output)
        code, output = self._run(
            _incidents_list_command,
            _namespace(report=str(self.report_path), until="1970-01-01T00:00:01.500Z"))
        self.assertIn("Matching .................. 1", output)
        self.assertIn(self.incident_id, output)
        self.assertNotIn(self.near_miss_id, output)

    def test_list_empty_match(self):
        code, output = self._run(
            _incidents_list_command,
            _namespace(report=str(self.report_path), since="2026-01-01T00:00:00Z"))
        self.assertEqual(0, code)
        self.assertIn("No incidents match.", output)

    def test_list_reversed_window_rejected(self):
        with self.assertRaises(ValueError):
            self._run(_incidents_list_command, _namespace(
                report=str(self.report_path), since="2026-01-02T00:00:00Z",
                until="2026-01-01T00:00:00Z"))

    def test_list_bad_timestamp_rejected(self):
        with self.assertRaises(ValueError):
            self._run(_incidents_list_command, _namespace(
                report=str(self.report_path), since="not-a-date"))

    def test_show_record(self):
        code, output = self._run(
            _incidents_show_command,
            _namespace(report=str(self.report_path), record_id=self.incident_id))
        self.assertEqual(0, code)
        self.assertIn(self.incident_id, output)
        self.assertIn("Kind ...................... incident", output)
        self.assertIn("Resolution ................ unresolved", output)
        self.assertIn("Lifecycle ................. open", output)
        self.assertIn("Reason .................... external_consequence_not_yet_verified", output)

    def test_show_unknown_id_rejected(self):
        with self.assertRaises(ValueError):
            self._run(_incidents_show_command, _namespace(
                report=str(self.report_path), record_id="incident:" + "f" * 64))

    def test_summary_counts(self):
        code, output = self._run(_incidents_summary_command, _namespace(report=str(self.report_path)))
        self.assertEqual(0, code)
        self.assertIn("Incidents ................. 1", output)
        self.assertIn("Near-misses ............... 1", output)
        self.assertIn("Unresolved ................ 1", output)
        self.assertIn("Resolved cleanly .......... 0", output)
        self.assertIn("Confirmed wrong ........... 0", output)
        self.assertIn("Audit valid ............... yes", output)

    def test_missing_report_rejected(self):
        missing = Path(self.temp.name) / "no-such-report.json"
        with self.assertRaises(ValueError):
            self._run(_incidents_list_command, _namespace(report=str(missing)))

    def test_parser_wiring(self):
        parser = build_parser()
        args = parser.parse_args(["incidents", "list", "--report", str(self.report_path),
                                  "--kind", "incident"])
        self.assertIs(args.func, _incidents_list_command)
        args = parser.parse_args(["incidents", "show", "--report", str(self.report_path),
                                  self.incident_id])
        self.assertIs(args.func, _incidents_show_command)
        args = parser.parse_args(["incidents", "summary", "--report", str(self.report_path)])
        self.assertIs(args.func, _incidents_summary_command)

    def test_main_end_to_end(self):
        output = io.StringIO()
        with redirect_stdout(output), patch.object(
                sys, "argv", ["pulpo", "incidents", "list", "--report", str(self.report_path)]):
            self.assertEqual(0, main())
        self.assertIn(self.incident_id, output.getvalue())


if __name__ == "__main__":
    unittest.main()
