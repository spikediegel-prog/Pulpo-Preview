from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pulpo.effect_reconcile import EffectReconciliationError, SurfaceSpec, capture_surface


class SnapshotResourceBoundsTests(unittest.TestCase):
    def test_oversized_file_is_rejected_before_open(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'oversized'
            with path.open('wb') as handle:
                handle.truncate(64 * 1024 * 1024 + 1)
            with patch.object(Path, 'open', side_effect=AssertionError('must reject before hashing')):
                with self.assertRaisesRegex(EffectReconciliationError, 'file_size_limit'):
                    capture_surface(SurfaceSpec(directory, 'protected'))

    def test_depth_and_entry_exhaustion_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'one' / 'two' / 'three').mkdir(parents=True)
            with patch('pulpo.effect_reconcile.MAX_SNAPSHOT_DEPTH', 2):
                with self.assertRaisesRegex(EffectReconciliationError, 'depth_limit'):
                    capture_surface(SurfaceSpec(directory, 'protected'))
            with patch('pulpo.effect_reconcile.MAX_SNAPSHOT_ENTRIES', 2):
                with self.assertRaisesRegex(EffectReconciliationError, 'entry_limit'):
                    capture_surface(SurfaceSpec(directory, 'protected'))

    def test_excluded_oversized_file_does_not_block_bounded_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'excluded'
            with path.open('wb') as handle:
                handle.truncate(64 * 1024 * 1024 + 1)
            result = capture_surface(SurfaceSpec(directory, 'protected', exclude=('excluded',)))
            self.assertEqual(['.'], [entry.relative_path for entry in result.entries])
