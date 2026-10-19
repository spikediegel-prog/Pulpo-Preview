"""Exercise the test gate in fresh processes with disposable fixtures."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class UnitTestCleanupGateTests(unittest.TestCase):
    def gate(self, body):
        with tempfile.TemporaryDirectory(prefix="pulpo-cleanup-gate-") as directory:
            source = "import unittest, sqlite3\nclass Fixture(unittest.TestCase):\n    def test_fixture(self):\n"
            source += "\n".join("        " + line for line in body.splitlines()) + "\n"
            (Path(directory) / "test_fixture.py").write_text(source)
            return subprocess.run(
                [sys.executable, "-B", "-W", "error", str(Path(__file__).resolve().parents[1] /
                 "scripts/run_unit_tests.py"), "-s", directory],
                capture_output=True, text=True, timeout=20)

    def test_closed_database_passes(self):
        result = self.gate("connection = sqlite3.connect(':memory:')\nconnection.close()")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertNotIn("FAILED cleanup", result.stderr)

    @unittest.skipUnless(sys.version_info >= (3, 13), "SQLite finalizer warning requires Python 3.13+")
    def test_unclosed_database_fails_even_when_unittest_is_ok(self):
        result = self.gate("connection = sqlite3.connect(':memory:')")
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("OK", result.stderr)
        self.assertIn("FAILED cleanup", result.stderr)
        self.assertIn("ResourceWarning", result.stderr)

    def test_unraisable_destructor_failure_fails(self):
        result = self.gate("class Broken:\n    def __del__(self):\n        raise RuntimeError('synthetic destructor failure')\nBroken()")
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("FAILED cleanup", result.stderr)
