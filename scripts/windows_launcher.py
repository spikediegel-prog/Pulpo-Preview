"""Frozen Windows entry point for the unofficial Pulpo Preview CLI."""
from __future__ import annotations

import multiprocessing
import os
from pathlib import Path
import sys


def main() -> int:
    from pulpo.cli import main as cli_main

    quick_start = len(sys.argv) == 1
    if quick_start:
        report_root = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "PulpoPreview"
        print("Pulpo Preview - The Mad Lads Playground")
        print("Unofficial preview: checking this PC with conservative settings.\n")
        sys.argv.extend([
            "setup", "--no-calibrate",
            "--profile", str(report_root / "audit-performance-profile.json"),
            "--json-report", str(report_root / "setup-report.json"),
        ])
    result = cli_main()
    if quick_start:
        print(f"\nReport: {report_root / 'setup-report.json'}")
        if sys.stdin is not None and sys.stdin.isatty():
            input("Press Enter to close.")
    return result


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
