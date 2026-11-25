from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pulpo.state import _audit_record
from scripts import prototype_evidence_archive as archive


class SyntheticArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="pulpo-archive-test-")
        self.addCleanup(self.temporary.cleanup)
        self.store = Path(self.temporary.name)
        self.payload, self.pin = archive.build_fixture(8)

    def test_canonical_fixture_and_frozen_pin(self):
        self.assertTrue(archive.verify_package(self.payload, self.pin))
        with self.assertRaises(FrozenInstanceError):
            self.pin.records = 1
        for count in (True, 0, 257):
            with self.subTest(count=count), self.assertRaises(archive.PrototypeError):
                archive.build_fixture(count)

    def test_create_only_private_copy_and_duplicate_retry(self):
        first = archive.publish_fixture(self.store, self.payload, self.pin)
        self.assertTrue(first["created"])
        target = self.store / (self.pin.digest + ".archive.json")
        before = target.stat()
        self.assertEqual(0o600, before.st_mode & 0o777)
        self.assertEqual(self.payload, target.read_bytes())
        self.assertFalse(archive.publish_fixture(self.store, self.payload, self.pin)["created"])
        self.assertEqual(before.st_ino, target.stat().st_ino)
        self.assertEqual([target], list(self.store.iterdir()))
        observed = archive.check_local_receipt(self.store, first["receipt"], self.pin)
        self.assertTrue(observed["local_copy_observed"])
        self.assertFalse(observed["pruning_authorized"])

    def test_corruption_truncation_and_valid_shorter_prefix_reject(self):
        shorter, _pin = archive.build_fixture(4)
        for candidate in (self.payload[:-1], self.payload[:-1] + b"X", shorter):
            with self.subTest(size=len(candidate)), self.assertRaises(archive.PrototypeError):
                archive.verify_package(candidate, self.pin)

    def test_valid_nonfixture_canonical_event_is_not_an_export_route(self):
        body = json.loads(self.payload)
        record = _audit_record("0" * 64, "decision", {"synthetic_canary": "never-live-data"}, 1)
        body["rows"] = [[record["event"], json.dumps(record["payload"], sort_keys=True, separators=(",", ":")),
                         record["previous_hash"], record["timestamp_ns"], record["hash"]]]
        body["last_sequence"] = 1
        body["tip_hash"] = record["hash"]
        payload = archive.canonical(body)
        pin = archive.FixturePin(1, len(payload), sha256(payload).hexdigest(), record["hash"], self.pin.producer_commit)
        with self.assertRaisesRegex(archive.PrototypeError, "nonfixture"):
            archive.verify_package(payload, pin)

    def test_duplicate_keys_reject_even_with_matching_envelope_hash(self):
        payload = self.payload.replace(b'"fixture_only":true', b'"fixture_only":false,"fixture_only":true')
        pin = replace(self.pin, size=len(payload), digest=sha256(payload).hexdigest())
        with self.assertRaisesRegex(archive.PrototypeError, "duplicate_json_key"):
            archive.verify_package(payload, pin)

    def test_wrong_pin_count_and_manifest_reject(self):
        for pin in (replace(self.pin, records=4), replace(self.pin, tip="f" * 64),
                    replace(self.pin, producer_commit="a" * 40)):
            with self.subTest(pin=pin), self.assertRaises(archive.PrototypeError):
                archive.verify_package(self.payload, pin)

    def test_receipts_do_not_self_authenticate_or_grant_pruning(self):
        receipt = archive.publish_fixture(self.store, self.payload, self.pin)["receipt"]
        for candidate in (None, {}, dict(receipt, pruning_authorized=True),
                          dict(receipt, archive_bytes=float(self.pin.size)), dict(receipt, records=4),
                          dict(receipt, archive_sha256="f" * 64), dict(receipt, extra="not-accepted")):
            with self.subTest(candidate=candidate), self.assertRaises(archive.PrototypeError):
                archive.check_local_receipt(self.store, candidate, self.pin)

    def test_wrong_store_receipt_rejects(self):
        receipt = archive.publish_fixture(self.store, self.payload, self.pin)["receipt"]
        other = self.store / "other"
        other.mkdir(mode=0o700)
        archive.publish_fixture(other, self.payload, self.pin)
        with self.assertRaises(archive.PrototypeError):
            archive.check_local_receipt(other, receipt, self.pin)

    def test_corrupt_object_and_old_ack_are_preserved_but_not_accepted(self):
        receipt = archive.publish_fixture(self.store, self.payload, self.pin)["receipt"]
        target = self.store / (self.pin.digest + ".archive.json")
        target.write_bytes(b"corrupt synthetic fixture")
        with self.assertRaises(archive.PrototypeError):
            archive.check_local_receipt(self.store, receipt, self.pin)
        with self.assertRaises(archive.PrototypeError):
            archive.publish_fixture(self.store, self.payload, self.pin)
        self.assertEqual(b"corrupt synthetic fixture", target.read_bytes())

    def test_directory_sync_uncertainty_retains_object_and_retry_reverifies(self):
        with patch.object(archive, "sync_directory", side_effect=OSError("fixture sync")):
            with self.assertRaises(archive.PrototypeError):
                archive.publish_fixture(self.store, self.payload, self.pin)
        target = self.store / (self.pin.digest + ".archive.json")
        self.assertEqual(self.payload, target.read_bytes())
        retry = archive.publish_fixture(self.store, self.payload, self.pin)
        self.assertFalse(retry["created"])
        self.assertTrue(archive.check_local_receipt(self.store, retry["receipt"], self.pin)["local_copy_observed"])

    def test_disk_full_before_publication_leaves_no_final_artifact(self):
        with patch.object(archive, "write_all", side_effect=OSError(28, "fixture full")):
            with self.assertRaises(archive.PrototypeError):
                archive.publish_fixture(self.store, self.payload, self.pin)
        self.assertEqual([], list(self.store.iterdir()))

    def test_shared_directory_and_symlinks_reject(self):
        self.store.chmod(0o755)
        with self.assertRaises(archive.PrototypeError):
            archive.publish_fixture(self.store, self.payload, self.pin)
        self.store.chmod(0o700)
        alias = self.store / "alias"
        private = self.store / "private"
        private.mkdir(mode=0o700)
        alias.symlink_to(private, target_is_directory=True)
        with self.assertRaises(OSError):
            archive.publish_fixture(alias, self.payload, self.pin)

    def test_existing_object_symlink_and_fifo_are_not_followed(self):
        target = self.store / (self.pin.digest + ".archive.json")
        outside = self.store / "untouched"
        outside.write_text("keep")
        target.symlink_to(outside)
        with self.assertRaises(archive.PrototypeError):
            archive.publish_fixture(self.store, self.payload, self.pin)
        self.assertEqual("keep", outside.read_text())
        target.unlink()
        os.mkfifo(target, mode=0o600)
        with self.assertRaises(archive.PrototypeError):
            archive.publish_fixture(self.store, self.payload, self.pin)
        self.assertTrue(target.exists())

    def test_fixture_builder_never_opens_live_state_or_uses_a_signer(self):
        with patch("sqlite3.connect", side_effect=AssertionError("no database")), \
                patch("pulpo.kernel.GovernanceKernel", side_effect=AssertionError("no governor")):
            payload, pin = archive.build_fixture(3)
            self.assertTrue(archive.verify_package(payload, pin))

    def test_complete_disposable_failure_protocol(self):
        report = archive.run_prototype()
        self.assertTrue(report["passed"])
        self.assertTrue(all(value is True for value in report["checks"].values()))
        self.assertEqual("unavailable", report["canonical_pruning"])
        self.assertTrue(report["checks"]["disposable_fixture_cleanup"])
