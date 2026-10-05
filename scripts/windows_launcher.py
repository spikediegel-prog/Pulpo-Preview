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
        if not (report_root / "evidence-performance.json").is_file():
            sys.argv.extend(["--evidence-install", "recommended"])
        else:
            from pulpo.evidence_tuning import refresh_settings
            try:
                refresh_settings(report_root / "evidence-performance.json")
            except (OSError, ValueError, TypeError) as exc:
                print(f"Saved evidence setting could not be revalidated: {exc}")
                print("Complete collection will use conservative settings; saved profile is retained.")
    result = cli_main()
    if quick_start:
        print(f"\nReport: {report_root / 'setup-report.json'}")
        print("Open the tuning window later with: pulpo-preview.exe tune")
        if sys.stdin is not None and sys.stdin.isatty():
            input("Press Enter to close.")
    return result


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
