"""Exercise a built WSL package using temporary application and HOME directories."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def check(package, output):
    package = package.resolve()
    records = []
    with tempfile.TemporaryDirectory(prefix="pulpo-wsl-package-smoke-") as folder:
        base = Path(folder)
        home, root = base / "home", base / "pulpo-control-center"
        home.mkdir()
        environment = dict(os.environ, HOME=str(home), PYTHONPATH="/nonexistent")
        canaries = [home / ".config/PulpoPreview/evidence-performance.json",
                    home / ".config/PulpoPreview/control-center-session.json", base / "evidence/audit.db",
                    base / "checkout/local-change.txt"]
        for path in canaries:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"TEST ONLY - preserve unchanged")

        def run(label, action, expected=0, installed_package=False):
            executable = root / "Pulpo-Setup.pyz" if installed_package else package
            result = subprocess.run([sys.executable, "-I", "-B", str(executable), action,
                                     "--root", str(root), *(["--yes"] if action == "uninstall" else [])],
                                    cwd=base, env=environment, text=True, capture_output=True, timeout=45)
            if result.returncode != expected:
                raise RuntimeError(f"{label}: exit {result.returncode}: {result.stdout}\n{result.stderr}")
            for path in canaries:
                if path.read_bytes() != b"TEST ONLY - preserve unchanged":
                    raise RuntimeError("User-data preservation check failed")
            records.append({"case": label, "returncode": result.returncode,
                            "stdout": result.stdout, "stderr": result.stderr})

        run("check-before-install", "check")
        run("fresh-install", "install")
        run("packaged-gui-construction", "gui-check")
        run("check-installed", "check")
        missing = root / "app/pulpo/evidence_page.py"
        missing.unlink()
        (root / "app/pulpo/control_center.py").write_bytes(b"TEST ONLY damaged application")
        run("check-damaged", "check")
        if "files differing from package: 2" not in records[-1]["stdout"]:
            raise RuntimeError("Corruption diagnostic did not identify both damaged files")
        run("repair-damaged", "repair")
        run("repair-from-independent-installed-setup", "repair", installed_package=True)
        run("packaged-gui-after-repair", "gui-check")
        run("remove", "uninstall")
        run("remove-again", "uninstall")
        run("reinstall-after-removal", "repair")
        run("final-remove", "uninstall")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"package_sha256": hashlib.sha256(package.read_bytes()).hexdigest(),
        "scope": "Isolated WSL package lifecycle, GUI construction and synthetic data preservation; not visual approval, publisher authentication or enforcement proof",
        "cases": records}, indent=2) + "\n", encoding="utf-8")
    print(f"PASS {len(records)} isolated packaged cases; settings/evidence/checkout canaries unchanged")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    check(args.package, args.output)
