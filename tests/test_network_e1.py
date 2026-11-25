"""Linux diagnostic boundaries; all storage targets are disposable fixtures."""
import contextlib
import errno
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from pulpo.network_exposure import NetworkExposureError, parse_linux_ss, evaluate_listeners
from scripts import check_network_exposure as cli


class LinuxListenerValidationTests(unittest.TestCase):
    def test_malformed_local_endpoints_states_and_queues_reject(self):
        rows = [
            "tcp LISTEN 0 128 127.0.0.1:80",  # Missing peer.
            "tcp ESTAB 0 128 127.0.0.1:80 0.0.0.0:*",
            "udp LISTEN 0 0 127.0.0.1:80 0.0.0.0:*",
            "tcp LISTEN -1 128 127.0.0.1:80 0.0.0.0:*",
            "tcp LISTEN 0 NaN 127.0.0.1:80 0.0.0.0:*",
        ]
        for endpoint in ("localhost:80", "garbage:80", "127.0.0.1:*",
                         "127.0.0.1:0", "127.0.0.1:65536", "127.0.0.1:-1"):
            rows.append(f"tcp LISTEN 0 128 {endpoint} 0.0.0.0:*")
        for row in rows:
            with self.subTest(row=row), self.assertRaises(NetworkExposureError):
                parse_linux_ss(row)

    def test_numeric_ipv6_scopes_and_wildcards_remain_visible(self):
        observed = parse_linux_ss(
            "tcp LISTEN 0 128 [::1]:8080 [::]:*\n"
            "udp UNCONN 0 0 [fe80::1%eth0]:5353 [::]:*\n"
            "tcp LISTEN 0 128 *:9000 *:*\n"
        )
        self.assertEqual(3, len(observed))
        self.assertEqual(2, sum(x.externally_reachable_binding for x in observed))


@unittest.skipUnless(os.name == "posix", "POSIX evidence permissions and symlinks")
class DiagnosticPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.path = self.folder / "report.json"
        self.payload = evaluate_listeners([], system="linux").to_json()

    def test_complete_private_report(self):
        cli.publish_report(self.path, self.payload)
        self.assertTrue(json.loads(self.path.read_text())["passed"])
        self.assertEqual(0o600, stat.S_IMODE(self.path.stat().st_mode))
        self.assertEqual([self.path], list(self.folder.iterdir()))

    def test_existing_regular_file_symlink_and_dangling_link_are_preserved(self):
        target = self.folder / "original"
        target.write_text("old evidence")
        for kind in ("regular", "symlink", "dangling"):
            with self.subTest(kind=kind):
                if kind == "regular":
                    self.path.write_text("old report")
                else:
                    self.path.symlink_to(target if kind == "symlink" else self.folder / "missing")
                with self.assertRaises(FileExistsError):
                    cli.publish_report(self.path, self.payload)
                self.assertEqual("old evidence", target.read_text())
                if kind == "regular":
                    self.assertEqual("old report", self.path.read_text())
                else:
                    self.assertTrue(self.path.is_symlink())
                self.path.unlink()
        self.assertFalse((self.folder / "missing").exists())
        self.assertFalse(list(self.folder.glob(".pulpo-network-*")))

    def test_file_sync_failure_never_publishes_partial_report(self):
        with patch.object(cli.os, "fsync", side_effect=OSError(errno.ENOSPC, "fixture full")):
            with self.assertRaises(OSError):
                cli.publish_report(self.path, self.payload)
        self.assertFalse(self.path.exists())
        self.assertEqual([], list(self.folder.iterdir()))

    def test_link_failure_preserves_existing_reports(self):
        old = self.folder / "previous.json"
        old.write_text(self.payload)
        with patch.object(cli.os, "link", side_effect=OSError(errno.EOPNOTSUPP, "fixture unsupported")):
            with self.assertRaises(OSError):
                cli.publish_report(self.path, self.payload)
        self.assertEqual(self.payload, old.read_text())
        self.assertFalse(self.path.exists())

    def test_directory_sync_failure_keeps_report_but_cli_returns_error(self):
        with patch.object(cli, "audit_network_exposure", return_value=evaluate_listeners([])), \
                patch.object(cli.os, "fsync", side_effect=[None, OSError(errno.EIO, "fixture sync")]), \
                contextlib.redirect_stdout(io.StringIO()) as stdout, \
                contextlib.redirect_stderr(io.StringIO()) as stderr:
            self.assertEqual(2, cli.main(["--evidence", str(self.path)]))
        self.assertEqual("", stdout.getvalue())
        self.assertIn("durability unknown", stderr.getvalue())
        self.assertTrue(self.path.exists())

    def test_cli_collision_has_no_success_stdout(self):
        self.path.write_text("retain")
        with patch.object(cli, "audit_network_exposure", return_value=evaluate_listeners([])), \
                contextlib.redirect_stdout(io.StringIO()) as stdout, \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(2, cli.main(["--evidence", str(self.path)]))
        self.assertEqual("", stdout.getvalue())
        self.assertEqual("retain", self.path.read_text())
