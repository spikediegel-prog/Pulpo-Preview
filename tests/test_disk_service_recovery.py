"""Disk-backed synthetic state, fresh processes, and bounded fixture cleanup."""
import json
import hashlib
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
import unittest

from scripts.prove_linux_service_sandbox import ROOT, disk_mount_observation, remove_disk_fixture


class DiskRecoveryTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("PULPO_E1_USER_SERVICE_PROOF") == "1", "explicit live user-service fixture proof")
    def test_full_user_service_exit_and_fresh_service_reopen_disk_fixture(self):
        evidence = {"classification": "Recorded", "passed": False, "runs": [], "units": [],
                    "boundary": "Synthetic canonical-kernel fixture in transient user services; not the hardened custody system service."}
        with tempfile.TemporaryDirectory(prefix="e1-disk-service-", dir=ROOT.parent) as folder:
            state = Path(folder)
            evidence["mount"] = disk_mount_observation(state)
            secret = state / "secret.hex"
            secret.write_text(secrets.token_hex(32))
            secret.chmod(0o600)
            runner = state / "worker.py"
            runner.write_text(
                "import json,os,sys\nfrom pathlib import Path\n"
                "sys.path.insert(0,sys.argv[2])\n"
                "from scripts.prove_linux_service_sandbox import exercise_restart_fixture\n"
                "state=Path(sys.argv[1])\n"
                "r=exercise_restart_fixture(state,bytes.fromhex((state/'secret.hex').read_text()))\n"
                "r['pid']=os.getpid()\nprint(json.dumps(r),flush=True)\n"
            )
            suffix = secrets.token_hex(5)
            for phase in ("initial", "fresh"):
                unit = "pulpo-e1-disk-" + suffix + "-" + phase + ".service"
                evidence["units"].append(unit)
                command = ["systemd-run", "--user", "--wait", "--pipe", "--collect", "--service-type=oneshot",
                    "--unit=" + unit, "--property=NoNewPrivileges=yes", "--property=UMask=0077",
                    "--property=RestrictAddressFamilies=AF_UNIX", "--property=KillMode=control-group",
                    sys.executable, str(runner), str(state), str(ROOT)]
                try:
                    completed = subprocess.run(command, capture_output=True, text=True, timeout=20)
                    self.assertEqual(0, completed.returncode, completed.stderr)
                    report = json.loads(completed.stdout)
                    self.assertTrue(all(report["checks"].values()))
                    evidence["runs"].append(report)
                    active = subprocess.run(["systemctl", "--user", "is-active", unit],
                        capture_output=True, text=True, timeout=10)
                    self.assertIn(active.stdout.strip(), ("unknown", "inactive"))
                    self.assertTrue((state / "restart-fixture.sqlite3").is_file())
                    if phase == "initial":
                        evidence["stopped_interval"] = {"first_service_exited": True,
                            "state_retained": True,
                            "database_bytes": (state / "restart-fixture.sqlite3").stat().st_size}
                finally:
                    subprocess.run(["systemctl", "--user", "stop", unit], capture_output=True, timeout=15)
            initial, recovered = evidence["runs"]
            self.assertEqual("initial", initial["phase"])
            self.assertEqual("restart", recovered["phase"])
            self.assertNotEqual(initial["pid"], recovered["pid"])
            self.assertEqual(initial["audit_after_sha256"], recovered["audit_before_sha256"])
            self.assertEqual(initial["audit_rows"], recovered["audit_rows_before"])
            self.assertTrue(recovered["checks"]["spent_permit_replay_denied"])
            evidence["exact_prior_audit_preserved"] = True
            evidence["passed"] = True
        evidence["fixture_files_removed"] = not state.exists()
        self.assertTrue(evidence["fixture_files_removed"])
        output_dir = Path(os.environ.get("PULPO_E1_EVIDENCE_DIR", str(ROOT.parent / "e1-disk-evidence")))
        output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        output = output_dir / ("disk-user-service-" + str(time.time_ns()) + ".json")
        evidence["tested_commit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        evidence["source_sha256"] = hashlib.sha256(
            (ROOT / "scripts/prove_linux_service_sandbox.py").read_bytes()).hexdigest()
        evidence["test_source_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        with output.open("x") as stream:
            json.dump(evidence, stream, indent=2)
        output.chmod(0o600)
        print("Disk user-service proof: " + str(output), flush=True)

    def test_saved_state_survives_two_fresh_processes_with_exact_audit_prefix(self):
        with tempfile.TemporaryDirectory(prefix="e1-disk-fixture-", dir=ROOT.parent) as folder:
            mount = disk_mount_observation(Path(folder))
            self.assertNotIn(mount["fstype"], {"tmpfs", "ramfs", "devtmpfs"})
            environment = {**os.environ, "E1_FIXTURE_SECRET": secrets.token_hex(32)}
            code = (
                "import json,os,sys; from pathlib import Path; "
                "from scripts.prove_linux_service_sandbox import exercise_restart_fixture; "
                "r=exercise_restart_fixture(Path(sys.argv[1]),bytes.fromhex(os.environ['E1_FIXTURE_SECRET'])); "
                "r['pid']=os.getpid(); print(json.dumps(r))"
            )
            def fresh():
                result = subprocess.run([sys.executable, "-c", code, folder], cwd=ROOT, env=environment,
                                        capture_output=True, text=True, timeout=15)
                self.assertEqual(0, result.returncode, result.stderr)
                return json.loads(result.stdout)

            initial = fresh()
            self.assertEqual("initial", initial["phase"])
            self.assertTrue(all(initial["checks"].values()))
            self.assertGreater((Path(folder) / "restart-fixture.sqlite3").stat().st_size, 0)
            recovered = fresh()
            self.assertEqual("restart", recovered["phase"])
            self.assertNotEqual(initial["pid"], recovered["pid"])
            self.assertTrue(recovered["checks"]["spent_permit_replay_denied"])
            self.assertTrue(all(recovered["checks"].values()))
            self.assertEqual(initial["audit_rows"], recovered["audit_rows_before"])
            self.assertEqual(initial["audit_after_sha256"], recovered["audit_before_sha256"])

    def test_cleanup_removes_only_expected_generated_private_fixture(self):
        with tempfile.TemporaryDirectory() as folder:
            parent = Path(folder)
            name = "pulpo-e1-0123456789"
            target = parent / "private" / name
            target.mkdir(parents=True)
            (target / "synthetic.sqlite3").write_text("fixture only")
            (parent / name).symlink_to("private/" + name)
            unrelated = parent / "unrelated"
            unrelated.write_text("preserve")
            self.assertTrue(remove_disk_fixture(parent, name))
            self.assertFalse(os.path.lexists(parent / name))
            self.assertFalse(target.exists())
            self.assertEqual("preserve", unrelated.read_text())

    def test_cleanup_refuses_wrong_target_and_preserves_live_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            parent = Path(folder)
            unrelated = parent / "unrelated"
            unrelated.mkdir()
            name = "pulpo-e1-0123456789"
            (parent / name).symlink_to(unrelated)
            with self.assertRaises(RuntimeError):
                remove_disk_fixture(parent, name)
            self.assertTrue(unrelated.is_dir())
            self.assertTrue((parent / name).is_symlink())
            with self.assertRaises(RuntimeError):
                remove_disk_fixture(parent, "../unrelated")

    def test_cleanup_refuses_orphan_private_fixture_without_marker(self):
        with tempfile.TemporaryDirectory() as folder:
            parent = Path(folder)
            name = "pulpo-e1-0123456789"
            private = parent / "private" / name
            private.mkdir(parents=True)
            with self.assertRaises(RuntimeError):
                remove_disk_fixture(parent, name)
            self.assertTrue(private.is_dir())
