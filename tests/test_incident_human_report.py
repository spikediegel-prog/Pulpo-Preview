"""Incident channel slice (e): the human report path.

A human files a report of their own -- a claim, in their words, about an
effect they say happened. These tests pin the slice's rules: the claim
enters the channel as a `human_incident_report` audit event and derives
into an IncidentRecord with source `human_report`, in the same lifecycle
and audit trail as machine records; it never alters, reclassifies, or
overwrites a machine-derived record; the claimed time is recorded as
claimed (first_seen_ns is the filing time); the reporter is recorded as
given, not authenticated; and v2 snapshots still load.
"""
import argparse
import io
import json
import os
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from pulpo import GovernanceKernel, Policy, PulpoOrchestrator, SQLiteKernelState
from pulpo.cli import (
    _incidents_list_command,
    _incidents_report_command,
    _incidents_show_command,
    build_parser,
)
from pulpo.custody import SQLiteGovernanceCustody
from pulpo.incident_channel import (
    HUMAN_REPORT_EVENT,
    HUMAN_REPORT_SCHEMA,
    INCIDENT_SCHEMA,
    REPORT_SCHEMA,
    IncidentRecord,
    export_incident_report,
    file_human_incident_report,
    freeze_incident_report,
    list_incidents,
    load_incident_report,
    transition_incident,
)

NOW = 8_000_000
OPERATOR = "operator:owner"
REPORTER = "operator:alice"
DESCRIPTION = "The payment went through twice, I think."
CLAIMED = 1_700_000_000_000_000_000  # 2023-11-14T22:13:20Z, long before filing
_TEST_SECRET = "test-only".encode("utf-8")


def _owner(directory):
    db = Path(directory) / "state.sqlite"
    backend = SQLiteKernelState(db)
    kernel = GovernanceKernel(Policy(frozenset({"read"}), 0), secret=_TEST_SECRET, state=backend)
    return PulpoOrchestrator(kernel), backend, kernel


def _machine_events(backend):
    # One unresolved machine incident and one near-miss, as in the CLI tests.
    backend.append("purchase_consequence_unknown",
                   {"order_hash": "a" * 64, "intent_hash": "b" * 64,
                    "permit_hash": "c" * 64, "reservation_id": "res-1",
                    "reason": "external_consequence_not_yet_verified"}, 1_000_000_000)
    backend.append("permit_rejected",
                   {"permit": "d" * 64, "reason": "permit_expired"}, 2_000_000_000)


def _custody(directory):
    path = Path(directory) / "custody.sqlite3"
    return SQLiteGovernanceCustody(path, signing_secret=_TEST_SECRET,
                                   clock=lambda: NOW)


class HumanReportFilingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.owner, self.backend, self.kernel = _owner(self.temp.name)
        self.addCleanup(self.backend.close)
        _machine_events(self.backend)
        report = freeze_incident_report(self.owner)
        self.machine_incident = next(
            record for record in report.records if record.kind == "incident")
        self.machine_near_miss = next(
            record for record in report.records if record.kind == "near_miss")

    def test_file_incident(self):
        before_ns = time.time_ns()
        record = file_human_incident_report(
            self.owner, kind="incident", reporter=REPORTER,
            description=DESCRIPTION, claimed_at_ns=CLAIMED)
        self.assertEqual("incident", record.kind)
        self.assertEqual("human_report", record.source)
        self.assertEqual(HUMAN_REPORT_EVENT, record.source_detail)
        self.assertEqual(DESCRIPTION, record.reason)
        self.assertEqual(REPORTER, record.reporter)
        self.assertEqual(CLAIMED, record.claimed_at_ns)
        self.assertEqual("unresolved", record.resolution)
        self.assertEqual("open", record.lifecycle)
        self.assertTrue(record.record_id.startswith("incident:"))
        self.assertEqual(record.anchor_hash, record.anchors[0][1])
        self.assertEqual(("audit_record", record.anchor_hash), record.anchors[0])
        self.assertGreaterEqual(record.first_seen_ns, before_ns)
        self.assertEqual(record.first_seen_ns, record.last_seen_ns)
        event = [item for item in self.kernel.audit
                 if item["event"] == HUMAN_REPORT_EVENT]
        self.assertEqual(1, len(event))
        self.assertEqual(HUMAN_REPORT_SCHEMA, event[0]["payload"]["schema"])
        self.assertEqual(REPORTER, event[0]["payload"]["reporter"])
        self.assertEqual(CLAIMED, event[0]["payload"]["claimed_at_ns"])
        self.assertEqual([], event[0]["payload"]["related_record_ids"])

    def test_file_near_miss(self):
        record = file_human_incident_report(
            self.owner, kind="near_miss", reporter=REPORTER,
            description="Almost charged the wrong account.", claimed_at_ns=CLAIMED)
        self.assertEqual("near_miss", record.kind)
        self.assertTrue(record.record_id.startswith("near-miss:"))
        self.assertEqual("not_applicable", record.resolution)
        self.assertEqual("not_applicable", record.lifecycle)
        self.assertEqual(REPORTER, record.reporter)
        self.assertEqual(CLAIMED, record.claimed_at_ns)

    def test_claimed_time_is_recorded_as_claimed_not_as_seen(self):
        record = file_human_incident_report(
            self.owner, kind="incident", reporter=REPORTER,
            description=DESCRIPTION, claimed_at_ns=CLAIMED)
        self.assertEqual(CLAIMED, record.claimed_at_ns)
        # First seen is the filing time, never the claimed time.
        self.assertNotEqual(CLAIMED, record.first_seen_ns)
        self.assertGreater(record.first_seen_ns, CLAIMED)

    def test_future_claimed_time_is_recorded_as_given(self):
        future = time.time_ns() + 10 ** 12
        record = file_human_incident_report(
            self.owner, kind="incident", reporter=REPORTER,
            description=DESCRIPTION, claimed_at_ns=future)
        self.assertEqual(future, record.claimed_at_ns)

    def test_related_record_anchor_and_machine_record_unchanged(self):
        machine_hash = self.machine_incident.record_id.split(":", 1)[1]
        record = file_human_incident_report(
            self.owner, kind="incident", reporter=REPORTER,
            description=DESCRIPTION, claimed_at_ns=CLAIMED,
            related_record_ids=(self.machine_incident.record_id,))
        self.assertIn(("related_record", machine_hash), record.anchors)
        updated = freeze_incident_report(self.owner)
        machine = next(item for item in updated.records
                       if item.record_id == self.machine_incident.record_id)
        self.assertEqual(self.machine_incident, machine)

    def test_related_human_record(self):
        first = file_human_incident_report(
            self.owner, kind="incident", reporter=REPORTER,
            description="First report.", claimed_at_ns=CLAIMED)
        second = file_human_incident_report(
            self.owner, kind="incident", reporter=REPORTER,
            description="Follow-up to the first.", claimed_at_ns=CLAIMED,
            related_record_ids=(first.record_id,))
        first_hash = first.record_id.split(":", 1)[1]
        self.assertIn(("related_record", first_hash), second.anchors)

    def test_related_custody_record(self):
        store = _custody(self.temp.name)
        epoch, root = store.snapshot().epoch, store.snapshot().state_root
        authorization = store.authorize_attempt(
            expected_epoch=epoch, expected_state_root=root,
            object_hash="a" * 64, target_hash="b" * 64,
            permit_hash="c" * 64, authorization_hash="d" * 64)
        custody_id = f"incident:custody:{authorization.attempt_id}"
        record = file_human_incident_report(
            self.owner, kind="incident", reporter=REPORTER,
            description=DESCRIPTION, claimed_at_ns=CLAIMED,
            related_record_ids=(custody_id,), custody=store)
        self.assertIn(("related_record", authorization.attempt_id), record.anchors)

    def test_human_report_never_reclassifies_machine_record(self):
        # A human near-miss about a machine incident, then a human incident
        # that goes through the lifecycle: the machine incident is untouched.
        file_human_incident_report(
            self.owner, kind="near_miss", reporter=REPORTER,
            description="Thought this was wrong; it was fine.", claimed_at_ns=CLAIMED,
            related_record_ids=(self.machine_incident.record_id,))
        human = file_human_incident_report(
            self.owner, kind="incident", reporter=REPORTER,
            description=DESCRIPTION, claimed_at_ns=CLAIMED,
            related_record_ids=(self.machine_incident.record_id,))
        transition_incident(self.owner, human.record_id, "acknowledge", actor=OPERATOR)
        updated = freeze_incident_report(self.owner)
        machine = next(item for item in updated.records
                       if item.record_id == self.machine_incident.record_id)
        self.assertEqual(self.machine_incident, machine)

    def test_lifecycle_on_human_incident(self):
        record = file_human_incident_report(
            self.owner, kind="incident", reporter=REPORTER,
            description=DESCRIPTION, claimed_at_ns=CLAIMED)
        record = transition_incident(
            self.owner, record.record_id, "acknowledge", actor=OPERATOR)
        self.assertEqual("acknowledged", record.lifecycle)
        self.assertEqual(OPERATOR, record.lifecycle_actor)
        record = transition_incident(
            self.owner, record.record_id, "resolve", actor=OPERATOR)
        self.assertEqual("resolved", record.lifecycle)
        with self.assertRaises(ValueError):
            transition_incident(
                self.owner, record.record_id, "close", actor=OPERATOR)
        record = transition_incident(
            self.owner, record.record_id, "close", actor=OPERATOR,
            reason="Outcome will stay unknown; closing as decided.")
        self.assertEqual("closed", record.lifecycle)
        event = [item for item in self.kernel.audit
                 if item["event"] == "incident_lifecycle"
                 and item["payload"].get("transition") == "close"]
        self.assertTrue(event[-1]["payload"]["override"])
        record = transition_incident(
            self.owner, record.record_id, "reopen", actor=OPERATOR)
        self.assertEqual("open", record.lifecycle)

    def test_human_near_miss_rejects_transitions(self):
        record = file_human_incident_report(
            self.owner, kind="near_miss", reporter=REPORTER,
            description="Caught in time.", claimed_at_ns=CLAIMED)
        with self.assertRaises(ValueError):
            transition_incident(
                self.owner, record.record_id, "acknowledge", actor=OPERATOR)

    def test_validation_errors(self):
        cases = [
            {"kind": "bogus"},
            {"reporter": ""},
            {"reporter": 7},
            {"description": ""},
            {"description": "   "},
            {"description": 7},
            {"claimed_at_ns": 0},
            {"claimed_at_ns": -5},
            {"claimed_at_ns": "yesterday"},
            {"related_record_ids": "incident:abc"},
            {"related_record_ids": [7]},
            {"related_record_ids": ("incident:" + "f" * 64,)},
        ]
        for overrides in cases:
            kwargs = {"kind": "incident", "reporter": REPORTER,
                      "description": DESCRIPTION, "claimed_at_ns": CLAIMED}
            kwargs.update(overrides)
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):
                    file_human_incident_report(self.owner, **kwargs)

    def test_malformed_human_event_is_not_projected(self):
        self.backend.append(HUMAN_REPORT_EVENT,
                            {"schema": "pulpo.incident-human-report.v999",
                             "kind": "incident", "reporter": REPORTER,
                             "description": DESCRIPTION,
                             "claimed_at_ns": CLAIMED,
                             "related_record_ids": []}, 3_000_000_000)
        self.backend.append(HUMAN_REPORT_EVENT,
                            {"schema": HUMAN_REPORT_SCHEMA,
                             "kind": "incident", "reporter": REPORTER,
                             "description": DESCRIPTION,
                             "claimed_at_ns": 0,
                             "related_record_ids": []}, 3_000_000_001)
        report = freeze_incident_report(self.owner)
        self.assertEqual(
            [], [record for record in report.records if record.source == "human_report"])
        # The machine records are unaffected, and the claims stay in the audit.
        self.assertEqual(2, len(report.records))
        self.assertEqual(2, len([item for item in self.kernel.audit
                                 if item["event"] == HUMAN_REPORT_EVENT]))

    def test_v2_snapshot_loads(self):
        with tempfile.TemporaryDirectory() as directory:
            owner, backend, _kernel = _owner(directory)
            self.addCleanup(backend.close)
            _machine_events(backend)
            path = Path(directory) / "report.json"
            export_incident_report(owner, path)
            value = json.loads(path.read_text(encoding="utf-8"))
            value["schema"] = "pulpo.incident-report.v2"
            for record in value["records"]:
                record["schema"] = "pulpo.incident-record.v2"
                record.pop("claimed_at_ns", None)
                record.pop("reporter", None)
            v2_path = Path(directory) / "report-v2.json"
            v2_path.write_text(json.dumps(value), encoding="utf-8")
            os.chmod(v2_path, 0o600)
            loaded = load_incident_report(v2_path)
            self.assertEqual(REPORT_SCHEMA, loaded.schema)
            self.assertEqual(2, len(loaded.records))
            for record in loaded.records:
                self.assertEqual(0, record.claimed_at_ns)
                self.assertEqual("", record.reporter)
                self.assertEqual(INCIDENT_SCHEMA, record.schema)

    def test_v2_record_with_human_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            owner, backend, _kernel = _owner(directory)
            self.addCleanup(backend.close)
            _machine_events(backend)
            path = Path(directory) / "report.json"
            export_incident_report(owner, path)
            value = json.loads(path.read_text(encoding="utf-8"))
            value["schema"] = "pulpo.incident-report.v2"
            for record in value["records"]:
                record["schema"] = "pulpo.incident-record.v2"
                record.pop("claimed_at_ns", None)
                record.pop("reporter", None)
            # A v2 snapshot cannot contain a human record: v2 predates them.
            value["records"][0]["source"] = "human_report"
            v2_path = Path(directory) / "report-v2.json"
            v2_path.write_text(json.dumps(value), encoding="utf-8")
            os.chmod(v2_path, 0o600)
            with self.assertRaises(ValueError):
                load_incident_report(v2_path)

    def test_v3_round_trip_with_human(self):
        record = file_human_incident_report(
            self.owner, kind="incident", reporter=REPORTER,
            description=DESCRIPTION, claimed_at_ns=CLAIMED,
            related_record_ids=(self.machine_incident.record_id,))
        path = Path(self.temp.name) / "report.json"
        export_incident_report(self.owner, path)
        loaded = load_incident_report(path)
        self.assertEqual(REPORT_SCHEMA, loaded.schema)
        found = next(item for item in loaded.records
                     if item.record_id == record.record_id)
        self.assertEqual(record, found)

    def test_list_source_filter(self):
        file_human_incident_report(
            self.owner, kind="incident", reporter=REPORTER,
            description=DESCRIPTION, claimed_at_ns=CLAIMED)
        human = list_incidents(self.owner, source="human_report")
        self.assertEqual(1, len(human))
        self.assertEqual("human_report", human[0].source)
        machine = list_incidents(self.owner, source="canonical_audit")
        self.assertEqual(2, len(machine))
        self.assertTrue(all(item.source == "canonical_audit" for item in machine))
        with self.assertRaises(ValueError):
            list_incidents(self.owner, source="rumour")

    def test_record_validation_for_human_fields(self):
        base = {
            "record_id": "incident:" + "a" * 64,
            "kind": "incident",
            "source": "human_report",
            "source_detail": HUMAN_REPORT_EVENT,
            "first_seen_ns": 100,
            "last_seen_ns": 100,
            "anchors": (("audit_record", "a" * 64),),
            "reason": DESCRIPTION,
            "resolution": "unresolved",
            "anchor_hash": "a" * 64,
            "lifecycle": "open",
            "lifecycle_at_ns": 100,
            "lifecycle_actor": "",
        }
        with self.assertRaises(ValueError):
            IncidentRecord(**base)
        with self.assertRaises(ValueError):
            IncidentRecord(**{**base, "claimed_at_ns": CLAIMED})
        with self.assertRaises(ValueError):
            IncidentRecord(**{**base, "reporter": REPORTER})
        record = IncidentRecord(**{**base, "claimed_at_ns": CLAIMED,
                                   "reporter": REPORTER})
        self.assertEqual(CLAIMED, record.claimed_at_ns)
        with self.assertRaises(ValueError):
            IncidentRecord(**{**base, "source": "canonical_audit",
                              "claimed_at_ns": CLAIMED, "reporter": REPORTER})
        self.assertEqual(INCIDENT_SCHEMA, record.schema)
        self.assertEqual(REPORT_SCHEMA, freeze_incident_report(self.owner).schema)


class HumanReportCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.owner, self.backend, self.kernel = _owner(self.temp.name)
        self.addCleanup(self.backend.close)
        _machine_events(self.backend)
        self.db = Path(self.temp.name) / "state.sqlite"
        self.report_path = Path(self.temp.name) / "incident_report.json"
        export_incident_report(self.owner, self.report_path)
        report = freeze_incident_report(self.owner)
        self.machine_incident = next(
            record for record in report.records if record.kind == "incident")

    def _namespace(self, **kwargs):
        values = {
            "state": None, "kind": None, "reporter": None, "description": None,
            "claimed_at": None, "related": [], "report": None, "record_id": None,
            "resolution": None, "lifecycle": None, "source": None,
            "since": None, "until": None,
        }
        values.update(kwargs)
        return argparse.Namespace(**values)

    def _run(self, func, args):
        output = io.StringIO()
        with redirect_stdout(output):
            code = func(args)
        return code, output.getvalue()

    def test_report_files(self):
        code, output = self._run(_incidents_report_command, self._namespace(
            state=str(self.db), kind="incident", reporter=REPORTER,
            description=DESCRIPTION, claimed_at="2023-11-14T22:13:20Z"))
        self.assertEqual(0, code)
        self.assertIn("PULPO INCIDENT FILED", output)
        self.assertIn("incident:", output)
        self.assertIn(REPORTER, output)
        report = freeze_incident_report(self.owner)
        human = [record for record in report.records
                 if record.source == "human_report"]
        self.assertEqual(1, len(human))
        self.assertEqual(CLAIMED, human[0].claimed_at_ns)
        self.assertEqual(DESCRIPTION, human[0].reason)

    def test_report_with_related(self):
        code, output = self._run(_incidents_report_command, self._namespace(
            state=str(self.db), kind="near_miss", reporter=REPORTER,
            description="Almost charged twice.", claimed_at="2023-11-14T22:13:20Z",
            related=[self.machine_incident.record_id]))
        self.assertEqual(0, code)
        machine_hash = self.machine_incident.record_id.split(":", 1)[1]
        report = freeze_incident_report(self.owner)
        human = next(record for record in report.records
                     if record.source == "human_report")
        self.assertIn(("related_record", machine_hash), human.anchors)

    def test_report_missing_state(self):
        with self.assertRaises(ValueError):
            self._run(_incidents_report_command, self._namespace(
                state=str(Path(self.temp.name) / "nope.sqlite"),
                kind="incident", reporter=REPORTER,
                description=DESCRIPTION, claimed_at="2023-11-14T22:13:20Z"))

    def test_report_not_a_state_file(self):
        other = Path(self.temp.name) / "notes.txt"
        other.write_text("not a Pulpo state file\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            self._run(_incidents_report_command, self._namespace(
                state=str(other), kind="incident", reporter=REPORTER,
                description=DESCRIPTION, claimed_at="2023-11-14T22:13:20Z"))
        # The file was not turned into a state file.
        self.assertEqual("not a Pulpo state file\n", other.read_text(encoding="utf-8"))

    def test_report_bad_claimed_at(self):
        with self.assertRaises(ValueError):
            self._run(_incidents_report_command, self._namespace(
                state=str(self.db), kind="incident", reporter=REPORTER,
                description=DESCRIPTION, claimed_at="yesterday"))

    def test_report_unknown_related(self):
        with self.assertRaises(ValueError):
            self._run(_incidents_report_command, self._namespace(
                state=str(self.db), kind="incident", reporter=REPORTER,
                description=DESCRIPTION, claimed_at="2023-11-14T22:13:20Z",
                related=["incident:" + "f" * 64]))

    def test_report_via_parser(self):
        args = build_parser().parse_args([
            "incidents", "report", "--state", str(self.db),
            "--kind", "near_miss", "--reporter", REPORTER,
            "--description", "Almost charged twice.",
            "--claimed-at", "2026-11-10T14:30:00Z"])
        self.assertIs(args.func, _incidents_report_command)
        self.assertEqual("near_miss", args.kind)
        self.assertEqual([], args.related)

    def test_list_source_filter(self):
        file_human_incident_report(
            self.owner, kind="incident", reporter=REPORTER,
            description=DESCRIPTION, claimed_at_ns=CLAIMED)
        export_incident_report(self.owner, self.report_path)
        code, output = self._run(_incidents_list_command, self._namespace(
            report=str(self.report_path), source="human_report"))
        self.assertEqual(0, code)
        self.assertIn("Matching .................. 1", output)
        self.assertNotIn(self.machine_incident.record_id, output)

    def test_show_human_record(self):
        record = file_human_incident_report(
            self.owner, kind="incident", reporter=REPORTER,
            description=DESCRIPTION, claimed_at_ns=CLAIMED)
        export_incident_report(self.owner, self.report_path)
        code, output = self._run(_incidents_show_command, self._namespace(
            report=str(self.report_path), record_id=record.record_id))
        self.assertEqual(0, code)
        self.assertIn(f"Reporter .................. {REPORTER}", output)
        self.assertIn("(as reported, not verified)", output)
        self.assertIn(DESCRIPTION, output)


if __name__ == "__main__":
    unittest.main()
