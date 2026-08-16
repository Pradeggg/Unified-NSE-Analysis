"""Daily command views for Agent Adda model portfolios."""

from __future__ import annotations

import argparse
import csv
import json
import shlex
import subprocess
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parent.parent

SMALLCAP_POLICY = ROOT / "docs" / "fund_policies" / "2026-08-06-smallcap-super-performers-fund-policy.md"
MIDCAP_POLICY = ROOT / "docs" / "fund_policies" / "2026-08-08-midcap-leaders-portfolio-policy.md"


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        text = str(value).replace(",", "").replace("Rs.", "").strip()
        if not text:
            return None
        return float(text)
    except ValueError:
        return None


def _fmt_num(value: Any, digits: int = 2) -> str:
    number = _float(value)
    if number is None:
        return "NA"
    if digits == 0:
        return f"{number:,.0f}"
    return f"{number:,.{digits}f}"


def _display_symbol_list(symbols: list[str], limit: int = 8) -> str:
    clean = [str(s).strip().upper() for s in symbols if str(s).strip()]
    if not clean:
        return "none"
    suffix = "" if len(clean) <= limit else f" (+{len(clean) - limit} more)"
    return ", ".join(clean[:limit]) + suffix


def _row_map(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {str(row.get("symbol") or "").upper(): row for row in rows if row.get("symbol")}


def _stop_hits(rows: list[dict[str, str]]) -> list[str]:
    hits: list[str] = []
    for row in rows:
        price = _float(row.get("latest_price"))
        stop = _float(row.get("initial_stop"))
        if price is None or stop is None:
            continue
        if price <= stop:
            hits.append(f"{row.get('symbol')} <= stop {_fmt_num(stop, 0)}; price Rs. {_fmt_num(price)}")
    return hits


def _target_hits(rows: list[dict[str, str]]) -> list[str]:
    hits: list[str] = []
    for row in rows:
        price = _float(row.get("latest_price"))
        target = _float(row.get("target_2r"))
        if price is None or target is None:
            continue
        if price >= target:
            hits.append(f"{row.get('symbol')}: {_fmt_num(price)} >= 2R target {_fmt_num(target, 0)}")
    return hits


def _smallcap_buy_review(summary: dict[str, Any], rows_by_symbol: dict[str, dict[str, str]]) -> list[str]:
    out: list[str] = []
    for symbol in summary.get("trigger_review_symbols") or []:
        row = rows_by_symbol.get(str(symbol).upper(), {})
        qty = row.get("paper_quantity") or "NA"
        value = _fmt_num(row.get("paper_position_value"), 0)
        stop = _fmt_num(row.get("initial_stop"), 0)
        target = _fmt_num(row.get("target_2r"), 0)
        out.append(
            f"{symbol}: trigger-ready paper-order review only; qty {qty}, "
            f"value Rs. {value}, stop Rs. {stop}, 2R target Rs. {target}."
        )
    return out


def _smallcap_position_map(rows: list[dict[str, str]], limit: int = 8) -> list[str]:
    out: list[str] = []
    for row in rows[:limit]:
        out.append(
            f"{row.get('symbol')}: price Rs. {_fmt_num(row.get('latest_price'))}; "
            f"breakout Rs. {_fmt_num(row.get('breakout_level'), 0)}; "
            f"retest Rs. {_fmt_num(row.get('retest_level'), 0)}; "
            f"stop Rs. {_fmt_num(row.get('initial_stop'), 0)}; "
            f"2R target Rs. {_fmt_num(row.get('target_2r'), 0)}; "
            f"paper qty {row.get('paper_quantity') or 'NA'}; "
            f"value Rs. {_fmt_num(row.get('paper_position_value'), 0)}; "
            f"risk Rs. {_fmt_num(row.get('paper_risk_to_stop'), 0)}."
        )
    return out


def _smallcap_news(rows: list[dict[str, str]], limit: int = 8) -> list[str]:
    out: list[str] = []
    for row in rows[:limit]:
        status = row.get("result_status") or row.get("financial_freshness") or "NA"
        action = row.get("research_action") or row.get("external_note") or "No new note."
        out.append(f"{row.get('symbol')}: {status}. {action}")
    return out


def _midcap_buy_review(summary: dict[str, Any], rows_by_symbol: dict[str, dict[str, str]]) -> list[str]:
    trigger_symbols = [str(s).upper() for s in summary.get("trigger_review_symbols") or []]
    core_symbols = [str(s).upper() for s in summary.get("core_candidates") or []]
    symbols = trigger_symbols or core_symbols
    out: list[str] = []
    for symbol in symbols:
        row = rows_by_symbol.get(symbol, {})
        bucket = row.get("decision_bucket") or "candidate"
        score = row.get("overall_score_100") or "NA"
        stage = row.get("stage") or "NA"
        if symbol in trigger_symbols:
            out.append(f"{symbol}: trigger-ready paper-order review; score {score}, {bucket}, stage {stage}.")
        else:
            out.append(f"{symbol}: {bucket} pre-order review only; score {score}, stage {stage}; trigger not confirmed.")
    return out


def _midcap_news(rows: list[dict[str, str]], limit: int = 10) -> list[str]:
    out: list[str] = []
    for row in rows[:limit]:
        freshness = row.get("freshness_gate") or "NA"
        blockers = row.get("blockers") or "none"
        source_date = row.get("source_score_date") or "NA"
        out.append(
            f"{row.get('symbol')}: freshness {freshness}; source {source_date}; blockers {blockers}."
        )
    return out


def _append_section(lines: list[str], title: str, items: list[str] | str) -> None:
    lines.append("")
    lines.append(f"## {title}")
    if isinstance(items, str):
        lines.append(items)
        return
    if not items:
        lines.append("- none")
        return
    for item in items:
        lines.append(f"- {item}")


def build_fund_action_view(
    fund_type: str,
    rows: list[dict[str, str]],
    summary: dict[str, Any],
    paths: dict[str, Path],
    *,
    run_date: str,
) -> str:
    """Render the daily portfolio/fund command answer from monitor rows."""
    fund = fund_type.strip().lower().replace("-", "")
    rows_by_symbol = _row_map(rows)
    paper_allowed = bool(summary.get("paper_order_allowed"))
    paper_text = "YES - review required" if paper_allowed else "NO"
    date_display = f"{run_date[:4]}-{run_date[4:6]}-{run_date[6:]}" if len(run_date) == 8 else run_date

    if fund == "smallcap":
        title = "Agent Adda Small Cap Portfolio Daily Command"
        policy_path = SMALLCAP_POLICY
        top_symbols = summary.get("top_readiness_symbols") or []
        lines = [
            f"# {title}",
            f"Date: {date_display}",
            "Policy: Smallcap Super Performers Portfolio policy.",
            f"Policy file: `{policy_path.relative_to(ROOT)}`",
            f"Symbols monitored: {summary.get('total_symbols', len(rows))}",
            f"Paper order allowed: {paper_text}",
            f"Top readiness: {_display_symbol_list(list(top_symbols))}",
            f"Blocked triggers: {_display_symbol_list(list(summary.get('blocked_trigger_symbols') or []))}",
            "",
            "Research-only. No live order instruction.",
        ]
        _append_section(lines, "Buy / New Paper Order Review", _smallcap_buy_review(summary, rows_by_symbol))
        _append_section(lines, "Sell / Exit Review", _stop_hits(rows))
        _append_section(
            lines,
            "Increase / Add Review",
            "No add/increase instruction until an active paper position exists and the add trigger clears policy, governance, freshness, and risk gates.",
        )
        _append_section(lines, "Decrease / Trim Review", _target_hits(rows))
        _append_section(lines, "Position Size / Stop / Target Map", _smallcap_position_map(rows))
        _append_section(lines, "News / Result Watch", _smallcap_news(rows))
    elif fund == "midcap":
        title = "Agent Adda Mid Cap Portfolio Daily Command"
        policy_path = MIDCAP_POLICY
        top_symbols = summary.get("top_score_symbols") or []
        lines = [
            f"# {title}",
            f"Date: {date_display}",
            "Policy: Midcap Leaders Portfolio policy.",
            f"Policy file: `{policy_path.relative_to(ROOT)}`",
            f"Symbols monitored: {summary.get('total_symbols', len(rows))}",
            f"Paper order allowed: {paper_text}",
            f"Top score: {_display_symbol_list(list(top_symbols))}",
            f"Core candidates: {_display_symbol_list(list(summary.get('core_candidates') or []))}",
            f"Refresh first: {_display_symbol_list(list(summary.get('refresh_first_symbols') or []))}",
            f"Retest only: {_display_symbol_list(list(summary.get('retest_only_symbols') or []))}",
            "",
            "Research-only. No live order instruction.",
        ]
        _append_section(lines, "Buy / New Paper Order Review", _midcap_buy_review(summary, rows_by_symbol))
        _append_section(
            lines,
            "Sell / Exit Review",
            "No sell/exit instruction because no active midcap paper positions are connected to this command yet.",
        )
        _append_section(
            lines,
            "Increase / Add Review",
            "No add/increase instruction until active paper positions and add triggers are integrated.",
        )
        _append_section(
            lines,
            "Decrease / Trim Review",
            "No trim/decrease instruction until active paper positions and target levels are integrated.",
        )
        _append_section(
            lines,
            "Position Size / Stop / Target Map",
            "Position sizing is policy guidance only: initial slot Rs. 20,000-25,000, validated slot up to Rs. 45,000-50,000, single-entry risk 0.50%-0.75% of NAV, total open risk cap 6%. Stop/target map is pending a midcap trigger-risk layer.",
        )
        _append_section(lines, "News / Result Watch", _midcap_news(rows))
    else:
        raise ValueError(f"Unknown fund type: {fund_type}")

    lines.extend(
        [
            "",
            "## Artifacts",
            f"- CSV: `{paths['csv'].relative_to(ROOT) if paths['csv'].is_absolute() else paths['csv']}`",
            f"- Markdown: `{paths['md'].relative_to(ROOT) if paths['md'].is_absolute() else paths['md']}`",
            f"- Report: `{paths['html'].relative_to(ROOT) if paths['html'].is_absolute() else paths['html']}`",
            f"Report: {paths['html']}",
        ]
    )
    return "\n".join(lines)


def _build_parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog, add_help=False)
    parser.add_argument("--run-date", default="")
    parser.add_argument("--skip-run", action="store_true")
    parser.add_argument("--skip-history", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--open", action="store_true")
    parser.add_argument("-h", "--help", action="store_true")
    return parser


def _load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _open_path(path: Path, opener: Callable[[Path], None] | None = None) -> None:
    if opener is not None:
        opener(path)
        return
    subprocess.Popen(["open", str(path)])


def _usage() -> str:
    return "\n".join(
        [
            "Usage:",
            "- /agent-adda-small-cap-fund [--skip-run] [--json] [--open] [--run-date YYYYMMDD]",
            "- /agent-adda-mid-cap-fund [--skip-run] [--skip-history] [--json] [--open] [--run-date YYYYMMDD]",
            "",
            "Default behavior runs the daily monitor, rebuilds artifacts, and prints the daily action view.",
        ]
    )


def handle_agent_adda_fund_command(
    text: str,
    *,
    opener: Callable[[Path], None] | None = None,
) -> str:
    """Run the requested Agent Adda fund monitor and return a Markdown action view."""
    try:
        parts = shlex.split(text)
    except ValueError as exc:
        return f"Invalid fund command arguments: {exc}\n\n{_usage()}"
    if not parts:
        return _usage()

    root = parts[0].lower().strip()
    if root == "/agent-adda-small-cap-fund":
        fund_type = "smallcap"
        from tools import smallcap_daily_monitor as monitor
    elif root == "/agent-adda-mid-cap-fund":
        fund_type = "midcap"
        from tools import midcap_daily_monitor as monitor
    else:
        return _usage()

    parser = _build_parser(root)
    try:
        args = parser.parse_args(parts[1:])
    except SystemExit:
        return _usage()
    if args.help:
        return _usage()

    run_date = args.run_date or monitor.default_run_date()
    paths = monitor.artifact_paths(run_date)
    if not args.skip_run:
        if fund_type == "midcap":
            monitor.run_builder(run_date, skip_history=args.skip_history)
        else:
            monitor.run_builder(run_date)

    if not paths["csv"].exists():
        return (
            f"Missing monitor CSV: `{paths['csv']}`\n\n"
            "Run the command without `--skip-run`, or generate the monitor artifact first."
        )

    rows = _load_rows(paths["csv"])
    summary = monitor.build_monitor_summary(rows)
    if args.json:
        payload = {
            "fund_type": fund_type,
            "run_date": run_date,
            "summary": summary,
            "artifacts": {key: str(value) for key, value in paths.items()},
            "research_only": True,
            "paper_order_allowed": bool(summary.get("paper_order_allowed")),
        }
        return json.dumps(payload, indent=2, sort_keys=True)

    output = build_fund_action_view(fund_type, rows, summary, paths, run_date=run_date)
    if args.open and paths["html"].exists():
        _open_path(paths["html"], opener=opener)
        output += f"\n\nOpened report: `{paths['html']}`"
    return output
