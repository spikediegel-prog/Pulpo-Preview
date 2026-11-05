import json
from pathlib import Path
import tempfile
import unittest

from scripts.security.audit_dependencies import profiles, public_requirements, validate_report
from scripts.security.check_dependency_admission import admitted


class DependencyScanningTests(unittest.TestCase):
    def inventory(self):
        return [{"name": name, "version": "0.1.0"} for name in
                ["pulpo", "pulpo-independent-authority", "pulpo-hostile-worker-custody"]] + [
                    {"name": "pip", "version": "26.2.2"}, {"name": "cloud_extra", "version": "1.0"}]

    def test_optional_cloud_and_tooling_are_not_silently_excluded(self):
        self.assertEqual({"cloud-extra": "1.0", "pip": "26.2.2"}, public_requirements(self.inventory()))

    def test_duplicate_missing_local_and_requirement_injection_fail_closed(self):
        for packages in [self.inventory() + [{"name": "PIP", "version": "26.2.2"}],
                         self.inventory()[1:], self.inventory() + [{"name": "bad", "version": "1\n--index-url evil"}]]:
            with self.subTest(packages=packages), self.assertRaises(ValueError):
                public_requirements(packages)

    def test_report_must_cover_exact_versions_without_skips(self):
        expected = {"pip": "26.2.2"}
        for dependencies in [[], [{"name": "pip", "version": "25.1.1", "vulns": []}],
                             [{"name": "pip", "skip_reason": "unsupported"}],
                             [{"name": "pip", "version": "26.2.2"}],
                             [{"name": "pip", "version": "26.2.2", "vulns": []}] * 2]:
            with self.subTest(dependencies=dependencies), self.assertRaises(ValueError):
                validate_report({"dependencies": dependencies}, expected)

    def test_findings_remain_findings_even_if_scanner_returns_success(self):
        self.assertEqual(1, validate_report({"dependencies": [{"name": "pip", "version": "26.2.2", "vulns": [{"id": "test"}]}]}, {"pip": "26.2.2"}))

    def test_new_extras_automatically_enter_install_profiles(self):
        root = Path(__file__).resolve().parents[1]
        selected = profiles(root)
        self.assertIn('.[authority,mcp]', selected)
        self.assertTrue(any('gcp-cloud-sql' in p and 'postgres-test' in p for p in selected))
        with tempfile.TemporaryDirectory() as directory:
            copy = Path(directory)
            for path in [".", "authority-service", "custody-service"]:
                (copy / path).mkdir(parents=True, exist_ok=True)
                text = (root / path / 'pyproject.toml').read_text()
                if path == '.':
                    text = text.replace('[project.optional-dependencies]', '[project.optional-dependencies]\nfuture = ["future-package"]')
                (copy / path / 'pyproject.toml').write_text(text)
            self.assertIn('.[authority,future,mcp]', profiles(copy))

    def test_skipped_failed_cancelled_or_missing_matrix_denies_admission(self):
        for result in ['failure', 'skipped', 'cancelled', None]:
            for job in ['python-dependencies', 'container-dependencies']:
                needs = {name: {'result': 'success'} for name in ['python-dependencies', 'container-dependencies']}
                needs[job] = {'result': result}
                self.assertFalse(admitted(needs))
        self.assertFalse(admitted({}))
        self.assertFalse(admitted(None))
        self.assertTrue(admitted({'python-dependencies': {'result': 'success'}, 'container-dependencies': {'result': 'success'}}))


if __name__ == '__main__':
    unittest.main()
