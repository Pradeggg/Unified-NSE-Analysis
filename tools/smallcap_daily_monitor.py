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
BUILDER = ROOT / "mutual_funds" / "working" / "build_smallcap_research_update.py"


def _display_date(run_date: str) -> str:
    return f"{run_date[:4]}-{run_date[4:6]}-{run_date[6:]}"


def default_run_date() -> str:
    return datetime.now().strftime("%Y%m%d")


def artifact_paths(run_date: str | None = None) -> dict[str, Path]:
    dated = run_date or default_run_date()
    display = _display_date(dated)
    return {
        "csv": ROOT / "Mutual Funds" / "extracted" / f"agent_adda_smallcap_research_update_{dated}.csv",
        "md": ROOT / "docs" / "fund_policies" / "research_updates" / f"{display}-smallcap-portfolio-research-update.md",
        "html": ROOT / "Mutual Funds" / "reports" / f"agent_adda_smallcap_research_update_{dated}.html",
    }


def _float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return 0.0


def parse_rows(csv_text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(csv_text.splitlines()))


def load_rows(path: Path) -> list[dict[str, str]]:
    return parse_rows(path.read_text(encoding="utf-8"))


def _symbols(rows: Iterable[dict[str, str]], predicate: Any) -> list[str]:
    return [row["symbol"] for row in rows if predicate(row)]


def build_monitor_summary(rows: list[dict[str, str]]) -> dict[str, Any]:
    trigger_review = _symbols(rows, lambda r: r.get("trigger_state") == "TRIGGER_READY_REVIEW")
    blocked_triggers = _symbols(rows, lambda r: "TRIGGER_TOUCHED_BUT_BLOCKED" in r.get("trigger_state", ""))
    refresh_first = _symbols(
        rows,
        lambda r: r.get("action_bucket") == "Refresh first"
        and "NEAR_BREAKOUT" in r.get("trigger_state", ""),
    )
    retest_only = _symbols(rows, lambda r: r.get("action_bucket") == "Retest only")
    governance_review = _symbols(rows, lambda r: "governance" in r.get("action_bucket", "").lower())
    top_readiness = [
        row["symbol"]
        for row in sorted(
            rows,
            key=lambda r: (_float(r.get("readiness_overlay_100")), _float(r.get("policy_score_100"))),
            reverse=True,
        )
    ]
    paper_order_allowed = bool(trigger_review) and not blocked_triggers

    return {
        "total_symbols": len(rows),
        "paper_order_allowed": paper_order_allowed,
        "trigger_review_symbols": trigger_review,
        "blocked_trigger_symbols": blocked_triggers,
        "refresh_first_symbols": refresh_first,
        "retest_only_symbols": retest_only,
        "governance_review_symbols": governance_review,
        "top_readiness_symbols": top_readiness,
    }


def run_builder(run_date: str) -> None:
    subprocess.run([sys.executable, str(BUILDER), "--run-date", run_date], cwd=ROOT, check=True)


def render_summary(summary: dict[str, Any], rows: list[dict[str, str]], paths: dict[str, Path]) -> str:
    top = summary["top_readiness_symbols"][:5]
    lines = [
        "Agent Adda Smallcap Daily Monitor",
        f"Symbols monitored: {summary['total_symbols']}",
        f"Paper order allowed: {'YES - review required' if summary['paper_order_allowed'] else 'NO'}",
        f"Top readiness: {', '.join(top) if top else 'NA'}",
        f"Blocked triggers: {', '.join(summary['blocked_trigger_symbols']) or 'none'}",
        f"Trigger review: {', '.join(summary['trigger_review_symbols']) or 'none'}",
        f"Refresh first: {', '.join(summary['refresh_first_symbols']) or 'none'}",
        f"Retest only: {', '.join(summary['retest_only_symbols']) or 'none'}",
        f"Governance review: {', '.join(summary['governance_review_symbols']) or 'none'}",
        "",
        "Artifacts:",
        f"- CSV: {paths['csv'].relative_to(ROOT)}",
        f"- Markdown: {paths['md'].relative_to(ROOT)}",
        f"- HTML: {paths['html'].relative_to(ROOT)}",
    ]
    for row in rows[:5]:
        lines.append(
            f"- {row.get('symbol')}: readiness {row.get('readiness_overlay_100')}, "
            f"{row.get('trigger_state')}, {row.get('action_bucket')}"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Agent Adda smallcap daily monitor.")
    parser.add_argument(
        "--skip-run",
        action="store_true",
        help="Read the existing monitor CSV without regenerating quotes/reports.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the monitor summary as JSON.",
    )
    parser.add_argument(
        "--run-date",
        default=default_run_date(),
        help="Run date in YYYYMMDD format. Defaults to today.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = artifact_paths(args.run_date)
    if not args.skip_run:
        run_builder(args.run_date)
    rows = load_rows(paths["csv"])
    summary = build_monitor_summary(rows)
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(render_summary(summary, rows, paths))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
