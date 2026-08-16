from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "Mutual Funds" / "working" / "build_midcap_leaders.py"


def _display_date(run_date: str) -> str:
    return f"{run_date[:4]}-{run_date[4:6]}-{run_date[6:]}"


def default_run_date() -> str:
    return datetime.now().strftime("%Y%m%d")


def artifact_paths(run_date: str | None = None) -> dict[str, Path]:
    dated = run_date or default_run_date()
    display = _display_date(dated)
    return {
        "csv": ROOT / "Mutual Funds" / "extracted" / f"agent_adda_midcap_leaders_preselection_{dated}.csv",
        "md": ROOT / "docs" / "fund_policies" / "research_updates" / f"{display}-midcap-leaders-portfolio-research-update.md",
        "html": ROOT / "Mutual Funds" / "reports" / f"agent_adda_midcap_leaders_report_{dated}.html",
    }


def parse_rows(csv_text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(csv_text.splitlines()))


def load_rows(path: Path) -> list[dict[str, str]]:
    return parse_rows(path.read_text(encoding="utf-8"))


def _symbols(rows: Iterable[dict[str, str]], predicate: Any) -> list[str]:
    return [row["symbol"] for row in rows if row.get("symbol") and predicate(row)]


def _float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return 0.0


def build_monitor_summary(rows: list[dict[str, str]]) -> dict[str, Any]:
    core_candidates = _symbols(rows, lambda r: r.get("decision_bucket") == "CORE CANDIDATE")
    refresh_first = _symbols(rows, lambda r: r.get("decision_bucket") == "REFRESH FIRST")
    retest_only = _symbols(rows, lambda r: r.get("decision_bucket") == "RETEST ONLY")
    stage2_pass = _symbols(rows, lambda r: r.get("stage2_gate") == "PASS")
    growth_pass = _symbols(rows, lambda r: r.get("growth_gate") == "PASS")
    high_eps_pass = _symbols(rows, lambda r: r.get("high_eps_gate") == "PASS")
    yoy_sales_pass = _symbols(rows, lambda r: r.get("yoy_sales_gate") == "PASS")
    government_aligned = _symbols(rows, lambda r: r.get("government_investment_gate") == "PASS")
    trigger_review = _symbols(rows, lambda r: r.get("trigger_state") == "TRIGGER_READY_REVIEW")
    blocked = _symbols(rows, lambda r: "BLOCKED" in r.get("trigger_state", ""))
    top = [
        row["symbol"]
        for row in sorted(
            rows,
            key=lambda r: _float(r.get("overall_score_100")),
            reverse=True,
        )
        if row.get("symbol")
    ]
    paper_order_allowed = bool(trigger_review) and not blocked
    return {
        "total_symbols": len(rows),
        "paper_order_allowed": paper_order_allowed,
        "core_candidates": core_candidates,
        "refresh_first_symbols": refresh_first,
        "retest_only_symbols": retest_only,
        "stage2_pass_symbols": stage2_pass,
        "growth_pass_symbols": growth_pass,
        "high_eps_pass_symbols": high_eps_pass,
        "yoy_sales_pass_symbols": yoy_sales_pass,
        "government_aligned_symbols": government_aligned,
        "trigger_review_symbols": trigger_review,
        "blocked_trigger_symbols": blocked,
        "top_score_symbols": top,
    }


def run_builder(run_date: str, skip_history: bool = False) -> None:
    cmd = [sys.executable, str(BUILDER), "--run-date", run_date]
    if skip_history:
        cmd.append("--skip-history")
    subprocess.run(cmd, cwd=ROOT, check=True)


def render_summary(summary: dict[str, Any], rows: list[dict[str, str]], paths: dict[str, Path]) -> str:
    lines = [
        "Agent Adda Midcap Leaders Daily Monitor",
        f"Symbols monitored: {summary['total_symbols']}",
        f"Paper order allowed: {'YES - review required' if summary['paper_order_allowed'] else 'NO'}",
        f"Top score: {', '.join(summary['top_score_symbols'][:8]) or 'NA'}",
        f"Core candidates: {', '.join(summary['core_candidates']) or 'none'}",
        f"Refresh first: {', '.join(summary['refresh_first_symbols']) or 'none'}",
        f"Retest only: {', '.join(summary['retest_only_symbols']) or 'none'}",
        f"Stage 2 pass: {len(summary['stage2_pass_symbols'])}",
        f"Growth pass: {len(summary['growth_pass_symbols'])}",
        f"High EPS pass: {len(summary['high_eps_pass_symbols'])}",
        f"YoY sales pass: {len(summary['yoy_sales_pass_symbols'])}",
        f"Government aligned: {len(summary['government_aligned_symbols'])}",
        f"Trigger review: {', '.join(summary['trigger_review_symbols']) or 'none'}",
        f"Blocked triggers: {', '.join(summary['blocked_trigger_symbols']) or 'none'}",
        "",
        "Artifacts:",
        f"- CSV: {paths['csv'].relative_to(ROOT)}",
        f"- Markdown: {paths['md'].relative_to(ROOT)}",
        f"- HTML: {paths['html'].relative_to(ROOT)}",
    ]
    for row in rows[:8]:
        lines.append(
            f"- {row.get('symbol')}: score {row.get('overall_score_100')}, "
            f"{row.get('decision_bucket')}, {row.get('stage2_gate')}/"
            f"{row.get('growth_gate')}/{row.get('high_eps_gate')}/"
            f"{row.get('government_investment_gate')}"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Agent Adda midcap leaders daily monitor.")
    parser.add_argument("--skip-run", action="store_true", help="Read the existing CSV without regenerating.")
    parser.add_argument("--skip-history", action="store_true", help="Ask the builder to avoid live history refresh.")
    parser.add_argument("--json", action="store_true", help="Print JSON summary.")
    parser.add_argument("--run-date", default=default_run_date(), help="Run date in YYYYMMDD format.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = artifact_paths(args.run_date)
    if not args.skip_run:
        run_builder(args.run_date, skip_history=args.skip_history)
    rows = load_rows(paths["csv"])
    summary = build_monitor_summary(rows)
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(render_summary(summary, rows, paths))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
