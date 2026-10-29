"""Regressions from the actual restrictive system-service proof failure."""
import os
from pathlib import Path
import tempfile
import unittest

from scripts.prove_linux_service_sandbox import network_interfaces, remove_runtime_marker


HEADER = "Inter-| Receive | Transmit\n face |bytes packets |bytes packets\n"


class ServiceProofTests(unittest.TestCase):
    def test_loopback_and_external_interfaces_are_distinguished(self):
        self.assertEqual({"lo"}, network_interfaces(HEADER + " lo: 10 2 10 2\n"))
        self.assertEqual({"lo", "eth0"}, network_interfaces(
            HEADER + " lo: 10 2 10 2\n eth0: 100 5 100 5\n"))

    def test_unrecognized_observations_are_not_treated_as_loopback_only(self):
        for text in ("", HEADER, "unknown\nformat\n lo: 0\n", HEADER + "malformed"):
            with self.subTest(text=text), self.assertRaises(RuntimeError):
                network_interfaces(text)

    def test_only_expected_dangling_marker_is_removed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "pulpo-e1-0123456789"
            path.symlink_to("private/" + path.name)
            self.assertTrue(path.is_symlink())
            self.assertTrue(remove_runtime_marker(path))
            self.assertFalse(os.path.lexists(path))

    def test_live_target_wrong_link_and_regular_file_are_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "pulpo-e1-0123456789"
            target = Path(folder) / "private" / path.name
            target.mkdir(parents=True)
            path.symlink_to("private/" + path.name)
            with self.assertRaises(RuntimeError):
                remove_runtime_marker(path)
            self.assertTrue(target.is_dir())
            path.unlink()
            path.symlink_to("unrelated")
            with self.assertRaises(RuntimeError):
                remove_runtime_marker(path)
            self.assertTrue(path.is_symlink())
            path.unlink()
            path.write_text("preserve")
            self.assertFalse(remove_runtime_marker(path))
            self.assertEqual("preserve", path.read_text())

    def test_arbitrary_marker_names_are_rejected(self):
        with self.assertRaises(RuntimeError):
            remove_runtime_marker(Path("/run/unrelated-service"))
