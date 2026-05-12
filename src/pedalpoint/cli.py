"""CLI entry point for pedalpoint."""

from __future__ import annotations

import argparse
import sys

from pedalpoint.config import get_config
from pedalpoint.doctor import format_report, run_all


def _cmd_doctor(_args: argparse.Namespace) -> int:
    cfg = get_config()
    results = run_all(cfg)
    text, exit_code = format_report(results)
    print(text)
    return exit_code


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pedalpoint",
        description="pedalpoint — MCP server for local LLM routing",
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser(
        "doctor",
        help="Run health checks and print PASS/FAIL for each",
    )

    args = parser.parse_args()

    if args.command == "doctor":
        sys.exit(_cmd_doctor(args))
    else:
        parser.print_help()
        sys.exit(0)
