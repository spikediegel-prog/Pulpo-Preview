"""Pulpo command-line entry point."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import replace
from pathlib import Path

from .setup import run_setup


def _verify_command(args: argparse.Namespace) -> int:
    from .verifier import run_verification
    from .verifier.evidence import write_report
    from .verifier.external_integrity import check_external_integrity
    from .verifier.report import build_report

    report = run_verification()
    integrity_options = (
        args.integrity_manifest_url,
        args.integrity_public_key,
        args.integrity_key_sha256,
    )
    if any(integrity_options) and not all(integrity_options):
        raise ValueError(
            "--integrity-manifest-url, --integrity-public-key, and --integrity-key-sha256 must be used together"
        )
    if all(integrity_options):
        check = check_external_integrity(
            manifest_url=args.integrity_manifest_url,
            public_key_path=args.integrity_public_key,
            pinned_key_sha256=args.integrity_key_sha256,
            max_age_seconds=args.integrity_max_age_seconds,
        )
        report = build_report((*report.checks, check))
        report = replace(
            report,
            scope={
                **report.scope,
                "external_integrity": (
                    "challenge-bound HTTPS manifest signature and verifier file digests checked "
                    "against an independently provisioned key pin"
                ),
                "external_integrity_boundary": (
                    "does not attest the running process, loaded memory, host, or independence of the "
                    "local trust-pin provisioning"
                ),
            },
        )
    destination = write_report(report, args.report)
    print("PULPO VERIFIER")
    print()
    for check in report.checks:
        print(f"{check.status.value:13} {check.check_id}: {check.summary}")
    counts = report.check_counts
    score = report.governance_score
    print()
    print(f'Governance score .......... {score["passed"]}/{score["total"]} ({score["percentage"]}%)')
    print(
        f'Checks .................... {counts["pass"]} PASS, {counts["fail"]} FAIL, '
        f'{counts["unverifiable"]} UNVERIFIABLE'
    )
    print(f"Report .................... {destination}")
    print(f"Overall ................... {report.status.value}")
    return 0 if report.status.value == "PASS" else 1


def _setup_command(args: argparse.Namespace) -> int:
    evidence_settings = None
    if args.evidence_install is not None:
        from .evidence_tuning import EvidenceSettings, recommended
        if args.evidence_install == "custom":
            if args.evidence_workers is None:
                raise ValueError("Custom evidence setup requires --evidence-workers")
            evidence_settings = EvidenceSettings(args.evidence_workers).validate()
        else:
            if args.evidence_workers is not None:
                raise ValueError("--evidence-workers requires --evidence-install custom")
            evidence_settings = recommended()
    elif args.evidence_workers is not None or args.evidence_profile is not None:
        raise ValueError("Evidence options require --evidence-install recommended or custom")
    report = run_setup(
        profile_path=args.profile,
        benchmark_path=args.benchmark,
        calibrate_if_needed=not args.no_calibrate,
        calibration_sizes=tuple(args.calibration_sizes),
        calibration_batches=tuple(args.batch_sizes),
        calibration_repeats=args.repeats,
    )
    if evidence_settings is not None:
        from .evidence_tuning import save_settings
        if not report["ready_for_test_use"]:
            raise ValueError("Setup verification failed; evidence settings were not applied")
        destination = save_settings(evidence_settings, args.evidence_profile)
        report["evidence_performance"] = {"mode": "serial" if evidence_settings.workers <= 1 else "threads", "workers": evidence_settings.workers,
            "profile_path": str(destination), "correctness": "PASS", "authority_effect": "none"}

    if args.json_report:
        destination = Path(args.json_report)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    env = report["environment"]
    profile = report["profile"]
    verification = report["audit_verification"]

    print("PULPO SETUP")
    print()
    print(f'Environment .............. {env["status"]}')
    print(f'Performance profile ...... {profile["status"]}')
    print(f'Audit verification ....... {verification["status"]}')
    print("Authority changes ........ NONE")
    if "evidence_performance" in report:
        print(f'Evidence threads ......... {report["evidence_performance"]["workers"]}')
    print()
    fingerprint = env["fingerprint"]
    print(f'Platform ................. {fingerprint["platform"]}')
    print(f'Python ................... {fingerprint["python"]}')
    print(f'Logical CPUs ............. {fingerprint["cpu_count"]}')
    print()
    for item in profile["profiles"]:
        print(
            f'<= {item["max_records"]:7d} records  '
            f'workers={item["workers"]}  batch={item["batch_size"]}  '
            f'source={item["source"]}'
        )
    print()
    if report["ready_for_test_use"]:
        print("PULPO READY FOR TEST USE")
        print("This setup report does not claim production readiness.")
        return 0
    print("PULPO SETUP FAILED")
    return 1


def _tune_command(args: argparse.Namespace) -> int:
    from .evidence_tuning import EvidenceSettings, default_profile_path, load_settings, recommended, save_settings, refresh_settings
    if args.show:
        path = Path(args.profile) if args.profile else default_profile_path()
        resolved = load_settings(path)
        print(json.dumps({"mode": "serial" if resolved.workers <= 1 else "threads", "workers": resolved.workers,
                          "profile_path": str(path),
                          "authority_effect": "none", "process_runtime_enabled": False}, indent=2))
    elif args.refresh:
        print(f"Revalidated upgrade settings: {refresh_settings(args.profile)}")
    elif args.gui_check:
        from .tuning_app import check_gui
        check_gui()
        print("PASS bundled Tkinter window construction")
    elif args.recommended or args.workers is not None:
        settings = recommended() if args.recommended else EvidenceSettings(args.workers).validate()
        destination = save_settings(settings, args.profile)
        print(f"Saved {settings.workers} evidence workers after fresh correctness checks: {destination}")
    else:
        from .tuning_app import launch
        launch(args.profile)
    return 0


DEFAULT_INCIDENT_REPORT = "evidence/incident_report.json"


def _parse_incident_instant(value, flag):
    """Parse an ISO 8601 datetime flag into nanoseconds since the epoch."""
    if value is None:
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        from datetime import datetime, timezone
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise ValueError(
            f"{flag} must be an ISO 8601 datetime, e.g. 2026-11-11T00:00:00Z"
        ) from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp()) * 1_000_000_000 + parsed.microsecond * 1000


def _format_incident_time(timestamp_ns):
    return time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime(timestamp_ns / 1e9))


def _load_incident_report(report):
    """Load a frozen incident report; the path is resolved against the cwd."""
    from .incident_channel import load_incident_report
    destination = Path(report).expanduser().resolve()
    try:
        return load_incident_report(destination)
    except (ValueError, OSError) as exc:
        raise ValueError(f"incident report unavailable or invalid: {destination}") from exc


def _filter_incident_records(report, args):
    """Apply the CLI filters; the time window applies to first_seen_ns."""
    since_ns = _parse_incident_instant(args.since, "--since")
    until_ns = _parse_incident_instant(args.until, "--until")
    if since_ns is not None and until_ns is not None and since_ns > until_ns:
        raise ValueError("--since must not be after --until")
    source = getattr(args, "source", None)
    return tuple(
        record for record in report.records
        if (args.kind is None or record.kind == args.kind)
        and (args.resolution is None or record.resolution == args.resolution)
        and (args.lifecycle is None or record.lifecycle == args.lifecycle)
        and (source is None or record.source == source)
        and (since_ns is None or record.first_seen_ns >= since_ns)
        and (until_ns is None or record.first_seen_ns <= until_ns)
    )


def _incidents_list_command(args):
    report = _load_incident_report(args.report)
    records = _filter_incident_records(report, args)
    print("PULPO INCIDENTS")
    print()
    print(f"Report .................... {Path(args.report).expanduser().resolve()}")
    print(f"Incidents ................. {report.incidents} · Near-misses: {report.near_misses} "
          f"· Unresolved: {report.unresolved}")
    print(f"Matching .................. {len(records)}")
    print()
    if not records:
        print("No incidents match.")
        return 0
    for record in records:
        print(f"{record.record_id} · {record.kind} · {record.resolution} · {record.lifecycle} · "
              f"{_format_incident_time(record.first_seen_ns)}")
    return 0


def _incidents_show_command(args):
    report = _load_incident_report(args.report)
    record = next((item for item in report.records if item.record_id == args.record_id), None)
    if record is None:
        raise ValueError(f"incident_record_not_found: {args.record_id}")
    print("PULPO INCIDENT")
    print()
    print(f"Record .................... {record.record_id}")
    print(f"Kind ...................... {record.kind}")
    print(f"Source .................... {record.source} · {record.source_detail}")
    if record.source == "human_report":
        print(f"Reporter .................. {record.reporter}")
        print(f"Claimed ................... {_format_incident_time(record.claimed_at_ns)} (as reported, not verified)")
    print(f"Reason .................... {record.reason}")
    print(f"Resolution ................ {record.resolution}")
    print(f"Lifecycle ................. {record.lifecycle} · "
          f"{_format_incident_time(record.lifecycle_at_ns)} · {record.lifecycle_actor or '—'}")
    print(f"First seen ................ {_format_incident_time(record.first_seen_ns)}")
    print(f"Last seen ................. {_format_incident_time(record.last_seen_ns)}")
    print(f"Anchor hash ............... {record.anchor_hash}")
    print("Anchors ...................")
    for name, value in record.anchors:
        print(f"  {name}: {value}")
    return 0


def _incidents_summary_command(args):
    report = _load_incident_report(args.report)
    print("PULPO INCIDENT SUMMARY")
    print()
    print(f"Report .................... {Path(args.report).expanduser().resolve()}")
    print(f"Observed ................... {_format_incident_time(report.observed_at_ns)}")
    print(f"Audit valid ............... {'yes' if report.audit_valid else 'no'}")
    print(f"Audit records ............. {report.audit_records}")
    print(f"Incidents ................. {report.incidents}")
    print(f"Near-misses ............... {report.near_misses}")
    print(f"Unresolved ................ {report.unresolved}")
    print(f"Resolved cleanly .......... {report.resolved_cleanly}")
    print(f"Confirmed wrong ........... {report.confirmed_wrong}")
    return 0


def _incidents_report_command(args):
    """File a human incident report into the canonical audit.

    This is the channel's first write surface: unlike list/show/summary,
    it opens the state file the operator points at and appends a
    `human_incident_report` audit event. The state path has no default --
    there is no canonical deployment layout to guess at -- and a missing
    file is refused, never created. The kernel is constructed with the
    same throwaway read-only policy the tests use: filing appends through
    the direct state seam (as `transition_incident` does), not through a
    governed action, so the policy is not consulted; the audit chain hash
    is unkeyed SHA-256, so the constructed kernel appends validly. The
    reporter is recorded as given, not authenticated.
    """
    from . import GovernanceKernel, Policy, PulpoOrchestrator, SQLiteKernelState
    from .incident_channel import file_human_incident_report
    state_path = Path(args.state).expanduser().resolve()
    if not state_path.is_file():
        raise ValueError(f"incident state file not found: {state_path}")
    if not _state_file_has_audit(state_path):
        raise ValueError(f"incident state file is not a Pulpo kernel state: {state_path}")
    claimed_at_ns = _parse_incident_instant(args.claimed_at, "--claimed-at")
    if claimed_at_ns is None or claimed_at_ns <= 0:
        raise ValueError("--claimed-at must be an ISO 8601 datetime")
    backend = SQLiteKernelState(state_path)
    try:
        kernel = GovernanceKernel(Policy(frozenset({"read"}), 0), state=backend)
        owner = PulpoOrchestrator(kernel)
        record = file_human_incident_report(
            owner,
            kind=args.kind,
            reporter=args.reporter,
            description=args.description,
            claimed_at_ns=claimed_at_ns,
            related_record_ids=tuple(args.related or ()),
        )
    finally:
        backend.close()
    print("PULPO INCIDENT FILED")
    print()
    print(f"Record .................... {record.record_id}")
    print(f"Kind ...................... {record.kind}")
    print(f"Reporter .................. {record.reporter}")
    print(f"Lifecycle ................. {record.lifecycle}")
    print(f"State ..................... {state_path}")
    return 0


def _state_file_has_audit(state_path):
    """True when the file is a Pulpo kernel state: it has an audit table.

    Opening a non-state file with SQLiteKernelState would create the
    tables in it, so the CLI checks first and refuses instead.
    """
    import sqlite3
    try:
        connection = sqlite3.connect(state_path.as_uri() + "?mode=ro", uri=True)
    except sqlite3.Error:
        return False
    try:
        row = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'audit'"
        ).fetchone()
        return row is not None
    except sqlite3.Error:
        return False
    finally:
        connection.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pulpo")
    subparsers = parser.add_subparsers(dest="command", required=True)

    verify = subparsers.add_parser(
        "verify",
        help="run isolated governance probes and write a scoped verification report",
    )
    verify.add_argument(
        "--report",
        default="evidence/verifier_report.json",
        help="verifier report path (default: evidence/verifier_report.json)",
    )
    verify.add_argument(
        "--integrity-manifest-url",
        help="optional HTTPS endpoint for a fresh signed verifier-integrity manifest",
    )
    verify.add_argument(
        "--integrity-public-key",
        help="path to the independently provisioned Ed25519 public key (raw 32 bytes or PEM)",
    )
    verify.add_argument(
        "--integrity-key-sha256",
        help="out-of-band pinned SHA-256 fingerprint of the raw Ed25519 public key",
    )
    verify.add_argument(
        "--integrity-max-age-seconds",
        type=int,
        default=300,
        help="maximum signed-manifest age (1-604800 seconds; default: 300)",
    )
    verify.set_defaults(func=_verify_command)

    setup = subparsers.add_parser(
        "setup",
        help="detect the machine, resolve a bounded performance profile, and self-test audit verification",
    )
    setup.add_argument(
        "--profile",
        default=".pulpo/audit-performance-profile.json",
        help="machine-bound performance profile path",
    )
    setup.add_argument("--benchmark", help="existing v2 memory-scaling benchmark JSON")
    setup.add_argument(
        "--no-calibrate",
        action="store_true",
        help="use conservative fallback instead of calibrating when no valid profile is available",
    )
    setup.add_argument(
        "--calibration-sizes",
        nargs="+",
        type=int,
        default=[10000, 50000, 100000],
    )
    setup.add_argument(
        "--batch-sizes",
        nargs="+",
        type=int,
        default=[256, 1024, 4096],
    )
    setup.add_argument("--repeats", type=int, default=1)
    setup.add_argument("--json-report", help="optional setup report JSON path")
    setup.add_argument("--evidence-install", choices=["recommended", "custom"],
                       help="opt in to bounded evidence thread settings")
    setup.add_argument("--evidence-workers", type=int, help="custom thread count; 0/1=serial")
    setup.add_argument("--evidence-profile", help="optional evidence performance profile path")
    setup.set_defaults(func=_setup_command)
    tune = subparsers.add_parser("tune", help="open the performance tuning window")
    tune.add_argument("--profile", help="optional evidence performance profile path")
    actions = tune.add_mutually_exclusive_group()
    actions.add_argument("--show", action="store_true", help="show resolved settings")
    actions.add_argument("--recommended", action="store_true", help="check and save recommended threads")
    actions.add_argument("--workers", type=int, help="check and save custom thread count")
    actions.add_argument("--refresh", action="store_true", help="revalidate saved settings after an upgrade")
    actions.add_argument("--gui-check", action="store_true", help=argparse.SUPPRESS)
    tune.set_defaults(func=_tune_command)
    incidents = subparsers.add_parser(
        "incidents",
        help="incident reports: list/show/summary read a frozen report; report files a human claim",
    )
    incidents_sub = incidents.add_subparsers(dest="incidents_command", required=True)
    incidents_list = incidents_sub.add_parser("list", help="list incidents in a frozen report")
    incidents_list.add_argument(
        "--report",
        default=DEFAULT_INCIDENT_REPORT,
        help="frozen incident report path (default: evidence/incident_report.json)",
    )
    incidents_list.add_argument("--kind", choices=["incident", "near_miss"])
    incidents_list.add_argument(
        "--resolution",
        choices=["unresolved", "resolved_cleanly", "confirmed_wrong", "not_applicable"],
    )
    incidents_list.add_argument(
        "--lifecycle",
        choices=["open", "acknowledged", "resolved", "closed", "not_applicable"],
    )
    incidents_list.add_argument(
        "--source",
        choices=["canonical_audit", "custody_store", "human_report"],
        help="only records from this feed",
    )
    incidents_list.add_argument(
        "--since", help="ISO 8601 lower bound on first seen, e.g. 2026-11-11T00:00:00Z"
    )
    incidents_list.add_argument("--until", help="ISO 8601 upper bound on first seen")
    incidents_list.set_defaults(func=_incidents_list_command)
    incidents_show = incidents_sub.add_parser("show", help="show one incident record")
    incidents_show.add_argument(
        "--report",
        default=DEFAULT_INCIDENT_REPORT,
        help="frozen incident report path (default: evidence/incident_report.json)",
    )
    incidents_show.add_argument("record_id", help="incident or near-miss record id")
    incidents_show.set_defaults(func=_incidents_show_command)
    incidents_summary = incidents_sub.add_parser(
        "summary", help="counts from a frozen incident report"
    )
    incidents_summary.add_argument(
        "--report",
        default=DEFAULT_INCIDENT_REPORT,
        help="frozen incident report path (default: evidence/incident_report.json)",
    )
    incidents_summary.set_defaults(func=_incidents_summary_command)
    incidents_report = incidents_sub.add_parser(
        "report", help="file a human incident report into the canonical audit"
    )
    incidents_report.add_argument(
        "--state",
        required=True,
        help="canonical kernel state file to file into (must already exist)",
    )
    incidents_report.add_argument("--kind", choices=["incident", "near_miss"], required=True)
    incidents_report.add_argument(
        "--reporter", required=True,
        help="reporter identity, recorded as given, e.g. operator:alice",
    )
    incidents_report.add_argument(
        "--description", required=True,
        help="what happened, in the reporter's words",
    )
    incidents_report.add_argument(
        "--claimed-at", required=True,
        help="ISO 8601 time the reporter says it happened, e.g. 2026-11-10T14:30:00Z",
    )
    incidents_report.add_argument(
        "--related", nargs="*", default=[],
        help="record ids this report relates to",
    )
    incidents_report.set_defaults(func=_incidents_report_command)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except (ValueError, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
