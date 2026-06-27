from __future__ import annotations

import argparse
import json
import re
import shlex
from pathlib import Path

from terminal.financial_rigor import (
    build_valuation_snapshot,
    build_valuation_snapshots,
    render_financial_rigor_markdown,
    render_report_audit_json,
    render_report_audit_markdown,
    render_valuation_check_markdown,
)


AUDIT_USAGE = """## NSE Report Data Audit

Usage: `/audit-report reports/latest/investment_checklist.md`

Examples:
- `/audit-report reports/latest/investment_checklist.md`
- `/audit-report reports/latest/top_picks.md --ratio 0.2 --seed 42`
- `/audit-report reports/latest/investment_checklist.md --json`

Research only. Not investment advice."""


FINANCIAL_RIGOR_USAGE = """## NSE Financial Rigor

Usage: `/financial-rigor INFY`

Examples:
- `/financial-rigor INFY`
- `/financial-rigor INFY --json`

Research only. Not investment advice."""


VALUATION_USAGE = """## NSE Valuation Check

Usage: `/valuation-check INFY TCS HDFCBANK`

Examples:
- `/valuation-check INFY TCS HDFCBANK`
- `/valuation-check INFY TCS --json`

Research only. Not investment advice."""


def handle_audit_report_command(text: str) -> str:
    args = _parse_audit_args(text)
    if args is None:
        return AUDIT_USAGE
    report_path = Path(args.report).expanduser()
    if not report_path.exists():
        return f"## NSE Report Data Audit\n\nReport not found: `{report_path}`\n\n{AUDIT_USAGE}"
    if args.json:
        return render_report_audit_json(report_path, ratio=args.ratio, seed=args.seed)
    return render_report_audit_markdown(report_path, ratio=args.ratio, seed=args.seed)


def handle_financial_rigor_command(text: str) -> str:
    args = _parse_financial_rigor_args(text)
    if args is None:
        return FINANCIAL_RIGOR_USAGE
    snapshot = build_valuation_snapshot(args.symbol.upper())
    if args.json:
        return json.dumps(snapshot.to_dict(), indent=2, sort_keys=True)
    return render_financial_rigor_markdown(snapshot)


def handle_valuation_check_command(text: str) -> str:
    args = _parse_valuation_args(text)
    if args is None:
        return VALUATION_USAGE
    symbols = [symbol.upper() for symbol in args.symbols]
    snapshots = build_valuation_snapshots(symbols)
    if args.json:
        return json.dumps([snapshot.to_dict() for snapshot in snapshots], indent=2, sort_keys=True)
    return render_valuation_check_markdown(snapshots)


def _parse_audit_args(text: str) -> argparse.Namespace | None:
    raw = re.sub(r"^\s*/audit-report\b", "", text or "", flags=re.IGNORECASE).strip()
    try:
        tokens = shlex.split(raw)
    except ValueError:
        return None
    if not tokens:
        return None
    parser = argparse.ArgumentParser(prog="/audit-report", add_help=False)
    parser.add_argument("report")
    parser.add_argument("--ratio", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("-h", "--help", action="store_true")
    return _safe_parse(parser, tokens)


def _parse_financial_rigor_args(text: str) -> argparse.Namespace | None:
    raw = re.sub(r"^\s*/financial-rigor\b", "", text or "", flags=re.IGNORECASE).strip()
    try:
        tokens = shlex.split(raw)
    except ValueError:
        return None
    if not tokens or not any(not token.startswith("-") for token in tokens):
        return None
    parser = argparse.ArgumentParser(prog="/financial-rigor", add_help=False)
    parser.add_argument("symbol")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("-h", "--help", action="store_true")
    return _safe_parse(parser, tokens)


def _parse_valuation_args(text: str) -> argparse.Namespace | None:
    raw = re.sub(r"^\s*/valuation-check\b", "", text or "", flags=re.IGNORECASE).strip()
    try:
        tokens = shlex.split(raw)
    except ValueError:
        return None
    if not tokens or not any(not token.startswith("-") for token in tokens):
        return None
    parser = argparse.ArgumentParser(prog="/valuation-check", add_help=False)
    parser.add_argument("symbols", nargs="+")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("-h", "--help", action="store_true")
    return _safe_parse(parser, tokens)


def _safe_parse(parser: argparse.ArgumentParser, tokens: list[str]) -> argparse.Namespace | None:
    try:
        args = parser.parse_args(tokens)
    except SystemExit:
        return None
    if getattr(args, "help", False):
        return None
    return args
