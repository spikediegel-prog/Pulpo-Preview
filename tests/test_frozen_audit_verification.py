"""Bundled executables must never be used as Python worker interpreters."""
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from pulpo.audit_parallel import AuditVerificationEngine
from pulpo.setup import run_setup, synthetic_audit_rows


class FrozenAuditVerificationTests(unittest.TestCase):
    def test_bundled_runtime_checks_every_hash_without_launching_a_worker(self):
        rows=synthetic_audit_rows(4)
        with patch.object(sys, 'frozen', True, create=True), patch(
            'pulpo.audit_parallel.DigestWorkerPool',
            side_effect=AssertionError('bundled executable cannot interpret worker code'),
        ) as factory:
            for cache_size in (0, 16):
                with self.subTest(cache_size=cache_size), AuditVerificationEngine(
                    workers=2, cache_size=cache_size, parallel_threshold=1,
                ) as engine:
                    self.assertTrue(engine.verify_rows(rows))
                    self.assertTrue(engine.verify_rows(rows))
                    changed=list(rows);row=list(changed[-1]);row[4]='f'*64;changed[-1]=tuple(row)
                    self.assertFalse(engine.verify_rows(changed))
                    malformed=list(rows);row=list(malformed[0]);row[3]=True;malformed[0]=tuple(row)
                    self.assertFalse(engine.verify_rows(malformed))
            factory.assert_not_called()

    def test_bundled_calibration_completes_without_worker_subprocesses(self):
        with TemporaryDirectory() as directory, patch.object(sys, 'frozen', True, create=True), patch(
            'pulpo.audit_parallel.DigestWorkerPool',
            side_effect=AssertionError('bundled executable cannot interpret worker code'),
        ) as factory:
            report=run_setup(profile_path=Path(directory)/'profile.json',
                calibration_sizes=(512,), calibration_batches=(256,), calibration_repeats=1)
            self.assertEqual('CALIBRATED', report['profile']['status'])
            self.assertTrue(report['ready_for_test_use'])
            self.assertTrue(all(profile['workers'] == 1 for profile in report['profile']['profiles']))
            factory.assert_not_called()
