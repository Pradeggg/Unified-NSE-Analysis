"""Backend runner for the /company-xray command."""

from __future__ import annotations

import argparse
import shlex
from pathlib import Path
from typing import Callable

from company_intelligence import DEFAULT_DB_PATH, DEFAULT_REPORT_DIR, run_company_xray


def parse_company_xray_args(command_args: str | list[str]) -> argparse.Namespace:
    tokens = shlex.split(command_args) if isinstance(command_args, str) else list(command_args)
    parser = argparse.ArgumentParser(prog="/company-xray", add_help=False)
    parser.add_argument("symbol", nargs="?")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--format", choices=["html", "md"], default="html")
    parser.add_argument("--no-indexed-evidence", dest="include_indexed_evidence", action="store_false")
    parser.set_defaults(include_indexed_evidence=True)
    args = parser.parse_args(tokens)
    if args.symbol:
        args.symbol = args.symbol.strip().upper()
    return args


def run_company_xray_from_args(
    command_args: str | list[str],
    db_path: str | Path = DEFAULT_DB_PATH,
    output_dir: str | Path = DEFAULT_REPORT_DIR,
    runner: Callable[..., dict] = run_company_xray,
) -> dict:
    args = parse_company_xray_args(command_args)
    if not args.symbol:
        raise ValueError("symbol is required")

    result = runner(
        args.symbol,
        strict=args.strict,
        refresh=args.refresh,
        db_path=db_path,
        output_dir=output_dir,
        include_indexed_evidence=args.include_indexed_evidence,
    )
    return {
        **result,
        "format": args.format,
        "coverage_summary": _coverage_summary(result.get("coverage", {})),
        "disclaimer": "Research-only output. Verify against official filings before investment decisions.",
    }


def _coverage_summary(coverage: dict) -> dict:
    return {
        key: value
        for key, value in coverage.items()
        if key != "known_gaps"
    }
