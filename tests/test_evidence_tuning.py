import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pulpo import evidence_tuning as tuning
from pulpo.effect_reconcile import SurfaceSpec, capture_surface, capture_envelope_surfaces
from types import SimpleNamespace


class EvidenceTuningTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.profile = self.root / "performance.json"
        self.cpu = patch.object(tuning.os, "cpu_count", return_value=8)
        self.cpu.start()
        self.addCleanup(self.cpu.stop)

    def rewrite(self, change):
        tuning.save_settings(tuning.EvidenceSettings(4), self.profile)
        document = json.loads(self.profile.read_text())
        change(document)
        self.profile.write_text(json.dumps(document))

    def test_save_and_load_valid_setting(self):
        tuning.save_settings(tuning.EvidenceSettings(4), self.profile)
        self.assertEqual(4, tuning.load_settings(self.profile).workers)

    def test_absent_profile_recommends_complete_collection(self):
        self.assertEqual(2, tuning.load_settings(self.profile).workers)

    def test_invalid_types_and_ranges_rejected(self):
        for value in (True, False, "2", 2.5, None, -1, 9, 100000):
            with self.subTest(value=value), self.assertRaises(ValueError):
                tuning.EvidenceSettings(value).validate()

    def test_single_cpu_recommendation(self):
        with patch.object(tuning.os, "cpu_count", return_value=1):
            self.assertEqual(1, tuning.recommended().workers)

    def test_hardware_limit_is_capped(self):
        with patch.object(tuning.os, "cpu_count", return_value=128):
            self.assertEqual(16, tuning.thread_limit())

    def test_corrupt_digest_falls_back(self):
        self.rewrite(lambda document: document.update(digest="0" * 64))
        self.assertEqual(2, tuning.load_settings(self.profile).workers)

    def test_stale_machine_falls_back(self):
        self.rewrite(lambda document: document["machine"].update(logical_cpus=99))
        self.assertEqual(2, tuning.load_settings(self.profile).workers)

    def test_changed_code_falls_back(self):
        self.rewrite(lambda document: document.update(source_sha256="stale"))
        self.assertEqual(2, tuning.load_settings(self.profile).workers)

    def stale_profile(self):
        tuning.save_settings(tuning.EvidenceSettings(4), self.profile)
        tuning.save_settings(tuning.EvidenceSettings(2), self.profile)
        document = json.loads(self.profile.read_text())
        document["source_sha256"] = "0" * 64
        payload = {key: value for key, value in document.items() if key != "digest"}
        document["digest"] = tuning.sha256(tuning._canonical(payload)).hexdigest()
        self.profile.write_text(json.dumps(document))

    def test_upgrade_revalidates_choice_and_preserves_undo(self):
        self.stale_profile()
        tuning.refresh_settings(self.profile)
        self.assertEqual(2, tuning.load_settings(self.profile).workers)
        tuning.restore_previous(self.profile)
        self.assertEqual(4, tuning.load_settings(self.profile).workers)

    def test_upgrade_failed_check_preserves_original_file(self):
        self.stale_profile()
        original = self.profile.read_bytes()
        with patch.object(tuning, "check_settings", side_effect=ValueError("failed")):
            with self.assertRaises(ValueError):
                tuning.refresh_settings(self.profile)
        self.assertEqual(original, self.profile.read_bytes())

    def test_upgrade_rejects_corrupted_digest(self):
        self.rewrite(lambda document: document.update(digest="corrupt"))
        with self.assertRaises(ValueError):
            tuning.refresh_settings(self.profile)

    def test_upgrade_rejects_out_of_bounds_hardware_change(self):
        self.stale_profile()
        with patch.object(tuning.os, "cpu_count", return_value=1):
            with self.assertRaises(ValueError):
                tuning.refresh_settings(self.profile)

    def test_unknown_controls_rejected_even_with_recomputed_digest(self):
        def modify(document):
            document["settings"]["skip_audit"] = True
            payload = {key: value for key, value in document.items() if key != "digest"}
            document["digest"] = tuning.sha256(tuning._canonical(payload)).hexdigest()
        self.rewrite(modify)
        self.assertEqual(2, tuning.load_settings(self.profile).workers)

    def test_process_mode_cannot_be_enabled_by_profile(self):
        def modify(document):
            document["settings"]["mode"] = "processes"
            payload = {key: value for key, value in document.items() if key != "digest"}
            document["digest"] = tuning.sha256(tuning._canonical(payload)).hexdigest()
        self.rewrite(modify)
        self.assertEqual(2, tuning.load_settings(self.profile).workers)

    def test_malformed_json_falls_back(self):
        for value in ('[1,2]', 'null', '{"workers":2}', '{', '{"schema":1,"schema":2}'):
            with self.subTest(value=value):
                self.profile.write_text(value)
                self.assertEqual(2, tuning.load_settings(self.profile).workers)

    def test_oversized_profile_falls_back(self):
        self.profile.write_text(" " * 17000)
        self.assertEqual(2, tuning.load_settings(self.profile).workers)

    def test_failed_check_does_not_replace_saved_setting(self):
        tuning.save_settings(tuning.EvidenceSettings(4), self.profile)
        old = self.profile.read_bytes()
        with patch.object(tuning, "check_settings", side_effect=ValueError("bad collector")):
            with self.assertRaises(ValueError):
                tuning.save_settings(tuning.EvidenceSettings(2), self.profile)
        self.assertEqual(old, self.profile.read_bytes())

    def test_atomic_save_failure_preserves_old_profile(self):
        tuning.save_settings(tuning.EvidenceSettings(4), self.profile)
        old = self.profile.read_bytes()
        with patch.object(tuning.os, "replace", side_effect=OSError("disk error")):
            with self.assertRaises(OSError):
                tuning.save_settings(tuning.EvidenceSettings(2), self.profile)
        self.assertEqual(old, self.profile.read_bytes())
        self.assertFalse(list(self.root.glob(".evidence-*.tmp")))

    def test_rollback_rechecks_and_restores_previous_setting(self):
        tuning.save_settings(tuning.EvidenceSettings(4), self.profile)
        tuning.save_settings(tuning.EvidenceSettings(2), self.profile)
        tuning.restore_previous(self.profile)
        self.assertEqual(4, tuning.load_settings(self.profile).workers)

    def test_corrupt_profile_cannot_authorize_rollback(self):
        self.rewrite(lambda document: document.update(digest="corrupt"))
        old = self.profile.read_bytes()
        with self.assertRaises(ValueError):
            tuning.restore_previous(self.profile)
        self.assertEqual(old, self.profile.read_bytes())

    def test_fresh_fixture_checks_each_allowed_count(self):
        for count in (0, 1, 2, 4, 8):
            with self.subTest(count=count):
                tuning.check_settings(tuning.EvidenceSettings(count))

    def test_runtime_auto_profile_preserves_complete_serial_snapshot(self):
        root = self.root / "surface"
        root.mkdir()
        (root / "file.bin").write_bytes(b"original")
        surfaces = (SurfaceSpec(str(root), "evidence"),)
        envelope = SimpleNamespace(surfaces=surfaces)
        tuning.save_settings(tuning.EvidenceSettings(4), self.profile)
        with patch.object(tuning, "default_profile_path", return_value=self.profile):
            self.assertEqual(tuple(capture_surface(s) for s in surfaces), capture_envelope_surfaces(envelope))
            (root / "file.bin").write_bytes(b"modified")
            self.assertEqual(tuple(capture_surface(s) for s in surfaces), capture_envelope_surfaces(envelope))

    def test_absent_runtime_profile_preserves_serial_behavior(self):
        from pulpo.effect_reconcile import ParallelEvidenceCollector
        with patch.object(tuning, "default_profile_path", return_value=self.profile), \
             patch.object(ParallelEvidenceCollector, "capture", side_effect=AssertionError("unexpected collector")):
            self.assertEqual((), capture_envelope_surfaces(SimpleNamespace(surfaces=())))

    def test_runtime_profile_cannot_suppress_capture_errors(self):
        tuning.save_settings(tuning.EvidenceSettings(4), self.profile)
        with patch.object(tuning, "default_profile_path", return_value=self.profile):
            with self.assertRaises(AttributeError):
                capture_envelope_surfaces(SimpleNamespace(surfaces=(object(),)))

    def test_cli_custom_count_requires_custom_mode(self):
        from pulpo.cli import build_parser, _setup_command
        args = build_parser().parse_args(["setup", "--no-calibrate", "--evidence-workers", "4"])
        with self.assertRaises(ValueError):
            _setup_command(args)

    def test_cli_forbids_conflicting_actions(self):
        from pulpo.cli import build_parser
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["tune", "--recommended", "--workers", "4"])

    def test_setup_does_not_save_evidence_profile_on_verification_failure(self):
        from pulpo.cli import build_parser, _setup_command
        args = build_parser().parse_args(["setup", "--evidence-install", "recommended",
                                          "--evidence-profile", str(self.profile)])
        with patch("pulpo.cli.run_setup", return_value={"ready_for_test_use": False}):
            with self.assertRaises(ValueError):
                _setup_command(args)
        self.assertFalse(self.profile.exists())


if __name__ == "__main__":
    unittest.main()
