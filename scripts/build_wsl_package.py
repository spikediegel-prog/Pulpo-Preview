"""Build the WSL-only offline Control Center maintenance zipapp."""
import argparse
import hashlib
import json
import io
from pathlib import Path
import re
import subprocess
import zipapp
import zipfile


def build(repo, output, version):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", version):
        raise ValueError("Use a bounded version identifier")
    files = {"app/" + p.relative_to(repo).as_posix(): p.read_bytes()
             for p in sorted((repo / "pulpo").rglob("*"))
             if p.is_file() and not p.is_symlink()
             and (p.suffix == ".py" or p.parent == repo / "pulpo/assets" and p.suffix == ".png")}
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    manifest = {"schema": 1, "version": version, "source_revision": revision,
                "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
    output.parent.mkdir(parents=True, exist_ok=True)
    # A zipapp is executable code. Its internal hashes detect damage, not publisher identity.
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("__main__.py", (repo / "scripts/wsl_package_manager.py").read_bytes())
        archive.writestr("package.json", json.dumps(manifest, sort_keys=True))
        for name, data in files.items():
            archive.writestr(name, data)
    zipapp.create_archive(io.BytesIO(output.read_bytes()), output, interpreter="/usr/bin/env python3")
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix + ".sha256").write_text(f"{digest}  {output.name}\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, default=Path("dist/Pulpo-Control-Center-WSL.pyz"))
    args = parser.parse_args()
    result = build(Path(__file__).resolve().parents[1], args.output, args.version)
    print(f"Built {args.output}: {result['version']} ({len(result['files'])} files)")
