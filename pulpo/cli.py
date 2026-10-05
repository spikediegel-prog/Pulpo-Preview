"""Pulpo command-line entry point."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .setup import run_setup


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
        report["evidence_performance"] = {"mode": "threads", "workers": evidence_settings.workers,
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
        print(json.dumps({"mode": "threads", "workers": load_settings(path).workers if path.is_file() else 0,
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pulpo")
    subparsers = parser.add_subparsers(dest="command", required=True)

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
