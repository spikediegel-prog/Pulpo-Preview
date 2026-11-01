"""Persistence for verifier reports."""

from __future__ import annotations

import json
from pathlib import Path

from .report import VerificationReport


def write_report(report: VerificationReport, destination: str | Path) -> Path:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path
