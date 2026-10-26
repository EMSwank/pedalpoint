"""CLI entry point for pedalpoint."""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version

from pedalpoint import handoff_log, stats, transcripts
from pedalpoint.config import get_config
from pedalpoint.doctor import format_report, run_all


def _cmd_doctor(_args: argparse.Namespace) -> int:
    cfg = get_config()
    results = run_all(cfg)
    text, exit_code = format_report(results)
    print(text)
    return exit_code


def _cmd_stats(args: argparse.Namespace) -> int:
    handoffs = stats.join_records(handoff_log.read_all())
    costs = transcripts.handoff_costs({h.handoff_id for h in handoffs})
    rows = stats.summarize(handoffs, costs, datetime.now(UTC), args.days)
    print(stats.format_rows(rows, args.days))
    return 0


def _version() -> str:
    try:
        return version("pedalpoint")
    except PackageNotFoundError:  # pragma: no cover - only when run from source
        return "unknown"


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pedalpoint",
        description="pedalpoint — MCP server for local LLM routing",
    )
    parser.add_argument(
        "--version", action="version", version=f"pedalpoint {_version()}"
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser(
        "doctor",
        help="Run health checks and print PASS/FAIL for each",
    )

    stats_parser = subparsers.add_parser(
        "stats",
        help="Show net Claude tokens saved by local handoffs",
    )
    stats_parser.add_argument("--days", type=int, default=7)

    args = parser.parse_args()

    if args.command == "doctor":
        sys.exit(_cmd_doctor(args))
    elif args.command == "stats":
        sys.exit(_cmd_stats(args))
    else:
        parser.print_help()
        sys.exit(0)
