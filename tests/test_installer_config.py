"""Installer config validation: the example passes, bad configs fail.

The validator mirrors the Control Center Guided Setup rules
(PR #55, ``system_config.py``). These tests use ``unittest`` so the
repo's CI (``python -m unittest discover -s tests``) runs them;
pytest is not installed in this repo and no workflow runs it.
"""

import copy
import hashlib
import importlib.util
import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = REPO_ROOT / "installer"


def _load_validator():
    path = INSTALLER / "validate_config.py"
    spec = importlib.util.spec_from_file_location("installer_validate_config", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validate_config = _load_validator()


def _example():
    return json.loads(
        (INSTALLER / "pulpo-preview-config.example.json").read_text(encoding="utf-8")
    )


def _mutated(**overrides):
    doc = copy.deepcopy(_example())
    for key, value in overrides.items():
        doc[key] = value
    return doc


class InstallerConfigTests(unittest.TestCase):
    def test_example_config_passes(self):
        self.assertEqual(validate_config.validate(_example()), [])

    def test_bad_timezone_fails(self):
        doc = _mutated(display_timezone="Mars/Olympus")
        errors = validate_config.validate(doc)
        self.assertTrue(any("timezone" in error for error in errors), errors)

    def test_duplicate_ntp_servers_fail(self):
        doc = _example()
        doc["time"]["secondary"] = doc["time"]["primary"]
        errors = validate_config.validate(doc)
        self.assertTrue(any("must differ" in error for error in errors), errors)

    def test_gateway_off_subnet_fails(self):
        doc = _example()
        doc["network"] = {
            "mode": "static",
            "address": "192.168.1.10/24",
            "gateway": "10.0.0.1",
            "dns": [],
        }
        errors = validate_config.validate(doc)
        self.assertTrue(
            any("not on the static subnet" in error for error in errors), errors
        )

    def test_four_dns_servers_fail(self):
        doc = _example()
        doc["network"] = {
            "mode": "static",
            "address": "192.168.1.10/24",
            "gateway": "192.168.1.1",
            "dns": ["8.8.8.8", "1.1.1.1", "9.9.9.9", "4.4.4.4"],
        }
        errors = validate_config.validate(doc)
        self.assertTrue(any("at most 3" in error for error in errors), errors)

    def test_retention_over_24h_fails(self):
        doc = _example()
        doc["storage"]["retention_hours"] = 48
        errors = validate_config.validate(doc)
        self.assertTrue(any("24h" in error for error in errors), errors)

    def test_missing_storage_acknowledgement_fails(self):
        doc = _example()
        doc["storage"]["acknowledged"] = False
        errors = validate_config.validate(doc)
        self.assertTrue(any("acknowledged" in error for error in errors), errors)


class InstallerManifestTests(unittest.TestCase):
    def test_manifest_assets_exist_and_match_sha256(self):
        manifest = json.loads(
            (INSTALLER / "installer-manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["version"], "0.1.0-preview.4")
        for image in manifest["images"]:
            path = REPO_ROOT / image["file"]
            self.assertTrue(path.is_file(), f"missing manifest asset: {image['file']}")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(digest, image["sha256"], image["file"])
            self.assertEqual(path.stat().st_size, image["bytes"], image["file"])

    def test_no_forbidden_version_strings_in_installer_docs(self):
        forbidden = ("1.0.0-preview", "24.10 Preview")
        for name in ("README.md", "grub.cfg", "installer-manifest.json"):
            text = (INSTALLER / name).read_text(encoding="utf-8")
            for needle in forbidden:
                self.assertNotIn(needle, text, f"{needle} in {name}")


if __name__ == "__main__":
    unittest.main()
