from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit

from pulpo import __version__
from pulpo.verifier.external_integrity import (
    VERIFIED_FILES,
    check_external_integrity,
)
from pulpo.verifier.report import CheckStatus


RFC8032_PUBLIC_KEY = bytes.fromhex(
    "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
)
RFC8032_EMPTY_MESSAGE_SIGNATURE = bytes.fromhex(
    "e5564300c360ac729086e2cc806e828a"
    "84877f1eb8e5d974d873e06522490155"
    "5fb8821590a33bacc61e39701cf9b46b"
    "d25bf5f0595bbe24655141438e7a100b"
)
NOW = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
CHALLENGE = "a" * 64


class ExternalIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "checkout"
        self.root.mkdir()
        for relative_path in VERIFIED_FILES:
            path = self.root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"fixture:{relative_path}\n", encoding="utf-8")
        self.key_path = Path(self.temporary.name) / "trusted-public-key.bin"
        self.key_path.write_bytes(RFC8032_PUBLIC_KEY)
        self.pin = hashlib.sha256(RFC8032_PUBLIC_KEY).hexdigest()

    def tearDown(self):
        self.temporary.cleanup()

    def manifest(self, *, nonce=CHALLENGE, generated_at=None, files=None):
        return {
            "schema": "pulpo.integrity-manifest.v1",
            "version": __version__,
            "nonce": nonce,
            "generated_at": (generated_at or NOW).isoformat(),
            "files": files or {
                relative_path: hashlib.sha256(
                    (self.root / relative_path).read_bytes()
                ).hexdigest()
                for relative_path in VERIFIED_FILES
            },
        }

    def invoke(self, manifest, *, transport=None, signature_verifier=None):
        body = json.dumps(
            {"manifest": manifest, "signature": "00" * 64},
            separators=(",", ":"),
        ).encode()
        requested = []

        def opener(url, timeout):
            requested.append((url, timeout))
            if transport is not None:
                return transport(url, timeout)
            return body

        check = check_external_integrity(
            manifest_url="https://integrity.example.test/v1/manifest?channel=stable",
            public_key_path=self.key_path,
            pinned_key_sha256=self.pin,
            root=self.root,
            now=NOW,
            challenge=CHALLENGE,
            opener=opener,
            signature_verifier=signature_verifier or (lambda message, signature, key: True),
        )
        return check, requested

    def test_external_manifest_challenge_signature_freshness_and_file_hashes_pass(self):
        check, requested = self.invoke(self.manifest())

        self.assertEqual(CheckStatus.PASS, check.status)
        self.assertIn("challenge_matched=true", check.evidence)
        self.assertEqual(1, len(requested))
        parsed = urlsplit(requested[0][0])
        self.assertEqual("https", parsed.scheme)
        self.assertEqual(CHALLENGE, parse_qs(parsed.query)["nonce"][0])

    def test_bad_challenge_and_file_digest_fail_closed(self):
        challenge_check, _ = self.invoke(self.manifest(nonce="b" * 64))
        mismatched_files = self.manifest()
        mismatched_files["files"][VERIFIED_FILES[0]] = "0" * 64
        digest_check, _ = self.invoke(mismatched_files)

        self.assertEqual(CheckStatus.FAIL, challenge_check.status)
        self.assertIn("challenge mismatch", challenge_check.summary)
        self.assertEqual(CheckStatus.FAIL, digest_check.status)
        self.assertIn("differ from", digest_check.summary)

    def test_kernel_and_audit_sources_are_part_of_integrity_scope(self):
        self.assertIn("pulpo/kernel.py", VERIFIED_FILES)
        self.assertIn("pulpo/state.py", VERIFIED_FILES)
        self.assertIn("pulpo/audit_parallel.py", VERIFIED_FILES)
        manifest = self.manifest()
        manifest["files"]["pulpo/kernel.py"] = "0" * 64

        check, _ = self.invoke(manifest)

        self.assertEqual(CheckStatus.FAIL, check.status)
        self.assertIn("pulpo/kernel.py", check.evidence[-1])

    def test_stale_manifest_and_wrong_pin_fail_closed(self):
        stale = self.manifest(
            generated_at=datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
        )
        stale_check, _ = self.invoke(stale)
        wrong_pin_check = check_external_integrity(
            manifest_url="https://integrity.example.test/manifest",
            public_key_path=self.key_path,
            pinned_key_sha256="0" * 64,
            root=self.root,
            now=NOW,
            challenge=CHALLENGE,
            opener=lambda url, timeout: self.fail("source fetched with a wrong key pin"),
        )

        self.assertEqual(CheckStatus.FAIL, stale_check.status)
        self.assertIn("stale", stale_check.summary)
        self.assertEqual(CheckStatus.FAIL, wrong_pin_check.status)
        self.assertIn("fingerprint mismatch", wrong_pin_check.summary)

    def test_unavailable_source_is_unknown_not_pass(self):
        check, _ = self.invoke(
            self.manifest(),
            transport=lambda url, timeout: (_ for _ in ()).throw(URLError("offline")),
        )
        self.assertEqual(CheckStatus.UNVERIFIABLE, check.status)
        self.assertIn("unavailable", check.summary)

    def test_manifest_url_must_use_https(self):
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            check_external_integrity(
                manifest_url="http://integrity.example.test/manifest",
                public_key_path=self.key_path,
                pinned_key_sha256=self.pin,
                challenge=CHALLENGE,
            )

    @unittest.skipUnless(
        importlib.util.find_spec("cryptography"),
        "cryptography extra is required for the Ed25519 verification vector",
    )
    def test_ed25519_verifier_matches_public_rfc8032_test_vector(self):
        from pulpo.verifier.external_integrity import _verify_ed25519

        self.assertTrue(
            _verify_ed25519(
                b"",
                RFC8032_EMPTY_MESSAGE_SIGNATURE,
                RFC8032_PUBLIC_KEY,
            )
        )
        self.assertFalse(
            _verify_ed25519(
                b"changed",
                RFC8032_EMPTY_MESSAGE_SIGNATURE,
                RFC8032_PUBLIC_KEY,
            )
        )


if __name__ == "__main__":
    unittest.main()
