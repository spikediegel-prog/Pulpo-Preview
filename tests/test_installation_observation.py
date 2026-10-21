"""Isolated installation fixtures; no system package or production owner touched."""
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import tempfile
import unittest
from unittest.mock import patch

from pulpo import installation_observation as app
from pulpo.kernel import GovernanceKernel, Policy
from pulpo.mcp_plugin import load_mcp_snapshot
from pulpo.evidence_observation import load_observation


@unittest.skipUnless(platform.system() == "Linux", "requires Linux descriptor-relative file semantics")
class InstallationObservationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="pulpo-installation-fixture-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.system = self.root / "system"
        self.system.mkdir(mode=0o755)
        self.name = "usr/lib/pulpo-control-center/pulpo_control_center/cli.py"
        self.target = self.system / self.name
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(b"# public installed application fixture\n")
        self.target.chmod(0o644)
        self.document = {"schema": 1, "package": "pulpo-control-center", "version": "0.1.0~test.1",
            "source_revision": "a" * 40, "files": {self.name: hashlib.sha256(self.target.read_bytes()).hexdigest()}}
        self.manifest = self.system / app.MANIFEST
        self.manifest.parent.mkdir(parents=True)
        self.save_manifest()
        for attribute, value in (("SYSTEM_ROOT", self.system), ("SYSTEM_UID", os.getuid())):
            context = patch.object(app, attribute, value)
            context.start()
            self.addCleanup(context.stop)

    def save_manifest(self):
        self.manifest.write_text(json.dumps(self.document), encoding="utf-8")
        self.manifest.chmod(0o644)

    def test_actual_package_reads_and_exports_remain_private_and_state_is_removed(self):
        before = self.target.read_bytes(), self.manifest.read_bytes()
        output = io.StringIO()
        with patch.object(app.tempfile, "tempdir", str(self.root)), patch.object(app.time, "sleep"), redirect_stdout(output):
            folder, status = app.run(cycles=2, interval=1)
        self.assertEqual(status, 0)
        self.assertEqual(before, (self.target.read_bytes(), self.manifest.read_bytes()))
        governance = load_mcp_snapshot(folder / "LOCAL-VALIDATION-governance.json")
        evidence = load_observation(folder / "LOCAL-VALIDATION-evidence.json")
        self.assertTrue(governance.audit_valid)
        self.assertEqual(evidence.allowed, 2)
        self.assertEqual(evidence.permit_consumed, 2)
        self.assertEqual(evidence.denied, 0)  # No synthetic denial/replay inflation.
        self.assertEqual(evidence.permit_rejected, 0)
        self.assertEqual(evidence.health, "ok")
        self.assertEqual(list(folder.glob("private-state-*")), [])
        for path in folder.glob("*.json"):
            self.assertEqual(path.stat().st_mode & 0o077, 0)
        records = [json.loads(line) for line in output.getvalue().splitlines() if line.startswith("{")]
        self.assertEqual([record["files"] for record in records], [{"match": 1}, {"match": 1}])
        self.assertEqual(records[0]["bytes_read"], len(before[0]))

    def test_denial_and_failed_consumption_never_read_target(self):
        kernel = GovernanceKernel(Policy(frozenset({"other.action"}), 0))
        with patch.object(app, "_read_system_file", side_effect=AssertionError("read before permit")):
            self.assertEqual(app.inspect_file(kernel, "a" * 64, self.name, "b" * 64, "test"), ("denied", 0))
        kernel = GovernanceKernel(Policy(frozenset({app.ACTION}), 0))
        with patch.object(kernel, "consume", return_value=False), \
                patch.object(app, "_read_system_file", side_effect=AssertionError("read before consume")):
            self.assertEqual(app.inspect_file(kernel, "a" * 64, self.name, "b" * 64, "test"), ("rejected", 0))

    def test_real_mismatch_and_missing_file_are_reported_without_repair(self):
        kernel = GovernanceKernel(Policy(frozenset({app.ACTION}), 0))
        original = self.target.read_bytes()
        self.assertEqual(app.inspect_file(kernel, "a" * 64, self.name, "0" * 64, "test")[0], "mismatch")
        self.assertEqual(self.target.read_bytes(), original)
        self.target.unlink()
        self.assertEqual(app.inspect_file(kernel, "a" * 64, self.name, "0" * 64, "test"), ("unavailable", 0))

    def test_private_state_and_exports_are_not_allocated_without_installed_manifest(self):
        self.manifest.unlink()
        with patch.object(app.tempfile, "mkdtemp", side_effect=AssertionError("unexpected state creation")), self.assertRaises(OSError):
            app.run(cycles=1)

    def test_rejects_links_fifo_hardlinks_writable_and_oversized_targets(self):
        actual = self.target.with_name("actual.py")
        self.target.rename(actual)
        self.target.symlink_to(actual)
        with self.assertRaises(OSError):
            app._read_system_file(self.name)
        self.target.unlink()
        os.link(actual, self.target)
        with self.assertRaises(ValueError):
            app._read_system_file(self.name)
        self.target.unlink()
        os.mkfifo(self.target)
        with self.assertRaises(ValueError):
            app._read_system_file(self.name)
        self.target.unlink()
        actual.rename(self.target)
        self.target.chmod(0o666)
        with self.assertRaises(ValueError):
            app._read_system_file(self.name)
        self.target.chmod(0o644)
        with self.assertRaises(ValueError):
            app._read_system_file(self.name, 2)
        self.target.parent.chmod(0o777)
        with self.assertRaises(ValueError):
            app._read_system_file(self.name)

    def test_rejects_manifest_escape_unknown_fields_duplicates_and_non_package_files(self):
        for name in ("../../secret", "/etc/shadow", "usr/lib/pulpo-control-center/../../key.pem", "usr/bin/other",
                     "usr/lib/pulpo-control-center/pulpo_control_center/state.db"):
            with self.subTest(name=name):
                self.document["files"] = {name: "a" * 64}
                self.save_manifest()
                with self.assertRaises(ValueError):
                    app.load_inventory()
        self.document["files"] = {self.name: "a" * 64}
        self.document["unknown"] = "field"
        self.save_manifest()
        with self.assertRaises(ValueError):
            app.load_inventory()
        self.manifest.write_text('{"schema":1,"schema":1}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            app.load_inventory()

    def test_changed_manifest_stops_without_new_export(self):
        original = app.load_inventory
        calls = 0
        def changed():
            nonlocal calls
            calls += 1
            document, digest = original()
            return document, ("f" * 64 if calls == 3 else digest)
        with patch.object(app.tempfile, "tempdir", str(self.root)), patch.object(app, "load_inventory", side_effect=changed), \
                patch.object(app, "export_mcp_snapshot", side_effect=AssertionError("published changed scope")), \
                redirect_stdout(io.StringIO()), self.assertRaisesRegex(ValueError, "changed during scan"):
            app.run(cycles=1)
        folder = next(self.root.glob("pulpo-LOCAL-VALIDATION-*"))
        self.assertEqual(list(folder.glob("*.json")), [])
        self.assertEqual(list(folder.glob("private-state-*")), [])

    def test_rejects_root_and_invalid_bounds_before_reading_manifest(self):
        with patch.object(app, "load_inventory", side_effect=AssertionError("unexpected bootstrap read")):
            with patch.object(app.os, "geteuid", return_value=0), self.assertRaises(ValueError):
                app.run()
            for cycles, interval in ((0, 1), (61, 1), (True, 1), (1, 0), (1, 11)):
                with self.subTest(cycles=cycles, interval=interval), self.assertRaises(ValueError):
                    app.run(cycles=cycles, interval=interval)


if __name__ == "__main__":
    unittest.main()
