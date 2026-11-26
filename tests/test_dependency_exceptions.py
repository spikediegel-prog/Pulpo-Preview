import copy
import datetime
import json
from pathlib import Path
import unittest

from scripts.security.check_dependency_exceptions import (
    evaluate, grype_blocking, load_exceptions, pip_audit_blocking)

ROOT = Path(__file__).resolve().parents[1]
EXCEPTIONS = ROOT / "docs/security/dependency-exceptions.json"
TODAY = datetime.date(2026, 11, 26)


def finding(id, package="libssl3t64", version="3.5.9-1~deb13u1", scanner="grype"):
    return {"id": id, "scanner": scanner, "package": package,
            "version": version, "severity": "High"}


class DependencyExceptionTests(unittest.TestCase):
    def test_exception_record_is_bounded_and_exact(self):
        record = load_exceptions(EXCEPTIONS)
        self.assertEqual("2026-12-25", record["expires"])
        entries = record["exceptions"]
        self.assertEqual(24, len(entries))
        self.assertEqual(24, len({e["id"] for e in entries}))
        for entry in entries:
            self.assertEqual("grype", entry["scanner"])
            self.assertFalse(entry["fix_available"])
            self.assertEqual("2026-12-25", entry["expires"])
            self.assertTrue(entry["packages"])
            self.assertTrue(entry["exposure"])
            self.assertTrue(entry["evidence"])
            self.assertTrue(entry["accepted_by"])

    def test_every_listed_package_is_admitted(self):
        record = load_exceptions(EXCEPTIONS)
        findings = []
        for entry in record["exceptions"]:
            for package in entry["packages"]:
                findings.append(finding(entry["id"], package["name"], package["version"]))
        result = evaluate(findings, record, TODAY)
        self.assertEqual([], result["unadmitted"])
        self.assertEqual([], result["expired"])
        self.assertEqual([], result["unused"])
        self.assertEqual(len(findings), len(result["admitted"]))

    def test_new_id_version_change_and_expiry_fail_closed(self):
        record = load_exceptions(EXCEPTIONS)
        base = finding("CVE-2026-107493")
        self.assertEqual([], evaluate([base], record, TODAY)["unadmitted"])
        # A finding the record never named is not admitted.
        self.assertEqual(1, len(evaluate(
            [finding("CVE-2099-00001")], record, TODAY)["unadmitted"]))
        # A package version the record does not cover is not admitted.
        changed = evaluate(
            [finding("CVE-2026-107493", version="3.5.10-1~deb13u1")], record, TODAY)
        self.assertEqual(1, len(changed["unadmitted"]))
        self.assertIn("version mismatch", changed["unadmitted"][0]["reason"])
        # An expired entry admits nothing.
        expired = evaluate([base], record, datetime.date(2026, 12, 26))
        self.assertEqual(1, len(expired["expired"]))
        self.assertEqual([], expired["admitted"])

    def test_unused_entry_warns_but_admits_nothing_new(self):
        record = load_exceptions(EXCEPTIONS)
        result = evaluate([], record, TODAY)
        self.assertEqual(24, len(result["unused"]))
        self.assertEqual([], result["unadmitted"])
        self.assertEqual([], result["expired"])

    def test_malformed_record_fails_closed(self):
        record = load_exceptions(EXCEPTIONS)
        for mutate in [
                lambda r: r.update(schema="other"),
                lambda r: r["exceptions"][0].update(fix_available=True),
                lambda r: r["exceptions"][0].update(expires="25-12-2026"),
                lambda r: r["exceptions"].append(copy.deepcopy(r["exceptions"][0])),
                lambda r: r["exceptions"][0].pop("exposure"),
                lambda r: r["exceptions"][0].update(packages=[])]:
            broken = copy.deepcopy(record)
            mutate(broken)
            with self.subTest(mutate=mutate):
                # load_exceptions reads a file; write the broken record out.
                import tempfile
                with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
                    json.dump(broken, handle)
                    path = Path(handle.name)
                try:
                    with self.assertRaises(ValueError):
                        load_exceptions(path)
                finally:
                    path.unlink()

    def test_grype_and_pip_audit_reports_extract_blocking_findings(self):
        grype = {"matches": [
            {"vulnerability": {"id": "CVE-2026-107493", "severity": "High"},
             "artifact": {"name": "libssl3t64", "version": "3.5.9-1~deb13u1"}},
            {"vulnerability": {"id": "CVE-2026-00001", "severity": "Medium"},
             "artifact": {"name": "other", "version": "1.0"}}]}
        self.assertEqual([finding("CVE-2026-107493")], grype_blocking(grype))
        audit = {"dependencies": [
            {"name": "dnspython", "version": "2.9.0",
             "vulns": [{"id": "CVE-2026-128089"}]},
            {"name": "pip", "version": "26.2.2", "vulns": []}]}
        self.assertEqual(
            [{"id": "CVE-2026-128089", "scanner": "pip-audit",
              "package": "dnspython", "version": "2.9.0", "severity": "High"}],
            pip_audit_blocking(audit))
        with self.assertRaises(ValueError):
            grype_blocking({"matches": [{"vulnerability": {"id": "x"}}]})
        with self.assertRaises(ValueError):
            pip_audit_blocking({"dependencies": [{"name": "pip", "skip_reason": "x"}]})


if __name__ == "__main__":
    unittest.main()
