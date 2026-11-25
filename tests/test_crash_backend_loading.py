"""The actual crash harness launches baseline children with warnings as errors."""
import subprocess
import sys
import unittest


class CrashBackendLoadingTests(unittest.TestCase):
    def test_exact_head_backend_loads_in_strict_child(self):
        result = subprocess.run(
            [sys.executable, "-W", "error", "-c",
             "from scripts.test_crash_recovery import backend; "
             "module, state = backend('baseline', 'HEAD'); "
             "assert module.__package__ == 'pulpo'; "
             "assert state.__module__ == 'pulpo._crash_baseline'"],
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stderr)
