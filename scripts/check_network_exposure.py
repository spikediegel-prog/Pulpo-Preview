#!/usr/bin/env python3
"""Deployment-time Pulpo inbound-listener proof."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile

from pulpo.network_exposure import (
    NetworkExposureError,
    audit_network_exposure,
    parse_allowlist,
)


def publish_report(destination: Path, payload: str) -> None:
    """Publish a private, complete diagnostic without replacing any old file.

    Use an operator-owned directory. Hard-link publication fails closed on
    filesystems without this primitive. A post-link sync failure is unknown
    durability; the report is retained and the CLI returns an error.
    """
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent,
            prefix=".pulpo-network-", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(payload + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink()
    if sys.platform == "linux":
        directory = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail if the host has any listener not explicitly allowlisted."
    )
    parser.add_argument(
        "--allow",
        action="append",
        default=[],
        metavar="PROTO:ADDRESS:PORT",
        help="Exact allowed listener. Repeat as needed. Default: none.",
    )
    parser.add_argument(
        "--evidence",
        type=Path,
        help="New report path in an operator-owned directory; existing files are never replaced.",
    )
    args = parser.parse_args(argv)

    try:
        report = audit_network_exposure(allowed=parse_allowlist(args.allow))
    except NetworkExposureError as exc:
        print(f"pulpo_network_exposure_error:{exc}", file=sys.stderr)
        return 2

    payload = report.to_json()
    if args.evidence is not None:
        try:
            publish_report(args.evidence, payload)
        except OSError as exc:
            print(f"pulpo_network_evidence_error:{exc}; publication durability unknown", file=sys.stderr)
            return 2
    print(payload)

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
