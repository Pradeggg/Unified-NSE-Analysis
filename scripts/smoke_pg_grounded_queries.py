#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:
    pass

from terminal.financials_cache import read_financials
from terminal.skills.fundamental_driver import diagnose_fundamental_driver
from terminal.tools import get_market_breadth, get_symbol_snapshot, get_technical_setup


DSN = (
    os.environ.get("AGENT_ADDA_PG_DSN")
    or os.environ.get("PG_DSN")
    or "dbname=nse_market user=nse_admin host=/tmp"
)


@dataclass
class SmokeCase:
    category: str
    user_input: str
    status: str
    pg_grounded: bool
    pg_sources: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    final_output: str = ""
    output_file: str | None = None
    failures: list[str] = field(default_factory=list)


def _json_default(value: Any) -> str:
    return str(value)


def _connect():
    return psycopg2.connect(DSN)


def _fetchone(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any]:
    with _connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return dict(row or {})


def _count(table: str, where_sql: str = "", params: tuple[Any, ...] = ()) -> int:
    sql = f"select count(*) as n from {table} {where_sql}"
    return int((_fetchone(sql, params).get("n") or 0))


def _status_from(failures: list[str]) -> str:
    return "fail" if failures else "pass"


def _case(
    *,
    category: str,
    user_input: str,
    pg_sources: list[str],
    evidence: dict[str, Any],
    final_output: str,
    failures: list[str],
) -> SmokeCase:
    return SmokeCase(
        category=category,
        user_input=user_input,
        status=_status_from(failures),
        pg_grounded=not failures,
        pg_sources=pg_sources,
        evidence=evidence,
        final_output=final_output,
        failures=failures,
    )


def technicals_case(symbol: str = "RELIANCE") -> SmokeCase:
    user_input = f"{symbol} technical setup with RSI MACD and moving averages"
    snap = get_symbol_snapshot(symbol)
    tech = get_technical_setup(symbol)
    failures: list[str] = []
    if snap.get("error"):
        failures.append(f"snapshot_error={snap.get('error')}")
    if tech.get("error"):
        failures.append(f"technical_error={tech.get('error')}")
    if snap.get("data_source") != "PostgreSQL scores.stage_snapshots":
        failures.append(f"snapshot_not_pg={snap.get('data_source')}")
    if "PostgreSQL" not in str(tech.get("data_source")):
        failures.append(f"technical_not_pg={tech.get('data_source')}")
    for key in ("rsi", "macd", "sma20", "sma50", "sma200"):
        if tech.get(key) in (None, ""):
            failures.append(f"missing_{key}")
    final = (
        f"{symbol} technical read: close {tech.get('current_price')}, "
        f"RSI {tech.get('rsi')}, MACD {tech.get('macd')}, "
        f"SMA20/50/200 {tech.get('sma20')}/{tech.get('sma50')}/{tech.get('sma200')}. "
        f"Snapshot signal {snap.get('trading_signal')} on {snap.get('snapshot_date')}."
    )
    return _case(
        category="technicals",
        user_input=user_input,
        pg_sources=["scores.stage_snapshots", "market.equity_eod"],
        evidence={
            "symbol_snapshot": {
                "snapshot_date": snap.get("snapshot_date"),
                "stage": snap.get("stage"),
                "trading_signal": snap.get("trading_signal"),
                "data_source": snap.get("data_source"),
            },
            "technical_setup": {
                "as_of": tech.get("as_of"),
                "rsi": tech.get("rsi"),
                "macd": tech.get("macd"),
                "sma20": tech.get("sma20"),
                "sma50": tech.get("sma50"),
                "sma200": tech.get("sma200"),
                "data_source": tech.get("data_source"),
            },
        },
        final_output=final,
        failures=failures,
    )


def market_analysis_case() -> SmokeCase:
    user_input = "market breadth and stage distribution using latest EOD data"
    breadth = get_market_breadth()
    latest = _fetchone("select max(snapshot_date)::text as snapshot_date from scores.stage_snapshots")
    row_count = _count("scores.stage_snapshots", "where snapshot_date=%s", (latest["snapshot_date"],))
    failures: list[str] = []
    if breadth.get("error"):
        failures.append(f"breadth_error={breadth.get('error')}")
    if breadth.get("data_source") != "PostgreSQL scores.stage_snapshots":
        failures.append(f"breadth_not_pg={breadth.get('data_source')}")
    if row_count <= 0:
        failures.append("no_latest_stage_snapshot_rows")
    if int(breadth.get("total_stocks") or 0) <= 0:
        failures.append("no_breadth_universe")
    final = (
        f"Market breadth as of {breadth.get('snapshot_date')}: "
        f"{breadth.get('advances')} advances, {breadth.get('declines')} declines, "
        f"A/D {breadth.get('ad_ratio')}, stage distribution {breadth.get('stage_distribution')}."
    )
    return _case(
        category="market_analysis",
        user_input=user_input,
        pg_sources=["scores.stage_snapshots"],
        evidence={"breadth": breadth, "latest_snapshot_rows": row_count},
        final_output=final,
        failures=failures,
    )


def stock_analysis_case(symbol: str = "TCS") -> SmokeCase:
    user_input = f"{symbol} stock analysis with price trend, stage, score, sector and risk read"
    snap = get_symbol_snapshot(symbol)
    tech = get_technical_setup(symbol)
    latest_rows = _count("scores.stage_snapshots", "where symbol=%s", (symbol,))
    eod_rows = _count("market.equity_eod", "where symbol=%s", (symbol,))
    failures: list[str] = []
    if snap.get("error"):
        failures.append(f"snapshot_error={snap.get('error')}")
    if tech.get("error"):
        failures.append(f"technical_error={tech.get('error')}")
    if latest_rows <= 0:
        failures.append("no_stage_snapshot_rows")
    if eod_rows <= 0:
        failures.append("no_eod_rows")
    final = (
        f"{symbol} stock read: {snap.get('company_name') or symbol}, sector {snap.get('sector')}, "
        f"stage {snap.get('stage')}, technical score {snap.get('technical_score')}, "
        f"investment score {snap.get('investment_score')}, RSI {tech.get('rsi')}, "
        f"trend {snap.get('trend_signal')}."
    )
    return _case(
        category="stock_analysis",
        user_input=user_input,
        pg_sources=["scores.stage_snapshots", "market.equity_eod"],
        evidence={
            "stage_snapshot_rows": latest_rows,
            "eod_rows": eod_rows,
            "symbol_snapshot": {
                "snapshot_date": snap.get("snapshot_date"),
                "company_name": snap.get("company_name"),
                "sector": snap.get("sector"),
                "stage": snap.get("stage"),
                "technical_score": snap.get("technical_score"),
                "investment_score": snap.get("investment_score"),
            },
            "technical_setup": {
                "as_of": tech.get("as_of"),
                "current_price": tech.get("current_price"),
                "rsi": tech.get("rsi"),
                "data_source": tech.get("data_source"),
            },
        },
        final_output=final,
        failures=failures,
    )


def index_analysis_case(index_symbol: str = "NIFTY 50") -> SmokeCase:
    user_input = f"{index_symbol} index trend and breadth from PostgreSQL"
    latest = _fetchone(
        """
        select trade_date::text as trade_date, index_symbol, close, change_pct,
               technical_score, rsi, momentum_50d, trend_signal, trading_signal
        from market.index_eod
        where upper(index_symbol) = upper(%s)
        order by trade_date desc
        limit 1
        """,
        (index_symbol,),
    )
    row_count = _count("market.index_eod", "where upper(index_symbol)=upper(%s)", (index_symbol,))
    breadth = get_market_breadth()
    failures: list[str] = []
    if not latest:
        failures.append(f"no_index_row={index_symbol}")
    if row_count <= 20:
        failures.append(f"too_few_index_rows={row_count}")
    if breadth.get("data_source") != "PostgreSQL scores.stage_snapshots":
        failures.append(f"breadth_not_pg={breadth.get('data_source')}")
    final = (
        f"{index_symbol} index read as of {latest.get('trade_date')}: close {latest.get('close')}, "
        f"change {latest.get('change_pct')}%, RSI {latest.get('rsi')}, "
        f"technical score {latest.get('technical_score')}, trend {latest.get('trend_signal')}; "
        f"market breadth A/D {breadth.get('ad_ratio')}."
    )
    return _case(
        category="index_analysis",
        user_input=user_input,
        pg_sources=["market.index_eod", "scores.stage_snapshots"],
        evidence={"latest_index_row": latest, "index_rows": row_count, "breadth": breadth},
        final_output=final,
        failures=failures,
    )


def deep_fundamental_case(symbol: str = "DMART") -> SmokeCase:
    user_input = (
        f"Use LLM reasoning for PostgreSQL grounded deep fundamental analysis of {symbol} using cached PostgreSQL "
        "financial statements with quarterly sales PAT EPS annual ROCE balance sheet and cash flow"
    )
    financials = read_financials(symbol, dsn=DSN)
    section_counts = {name: len(rows or []) for name, rows in financials.items()}
    eps = diagnose_fundamental_driver(symbol, "eps", financials=financials, max_age_days=0)
    roce = diagnose_fundamental_driver(symbol, "roce", financials=financials, max_age_days=0)
    cashflow = diagnose_fundamental_driver(symbol, "cashflow", financials=financials, max_age_days=0)
    failures: list[str] = []
    for section, count in section_counts.items():
        if count <= 0:
            failures.append(f"missing_financial_section={section}")
    if not eps.success:
        failures.append(f"eps_driver_failed={eps.short_answer}")
    if not roce.success:
        failures.append(f"roce_driver_failed={roce.short_answer}")
    if not cashflow.success:
        failures.append(f"cashflow_driver_failed={cashflow.short_answer}")
    latest_q = (financials.get("quarterly") or [{}])[0]
    final = (
        f"{symbol} fundamental read: latest quarter {latest_q.get('period_label')} "
        f"revenue {latest_q.get('revenue')}, PAT {latest_q.get('pat')}, EPS {latest_q.get('eps')}. "
        f"{eps.short_answer} {roce.short_answer} {cashflow.short_answer}"
    )
    return _case(
        category="deep_fundamental_analysis",
        user_input=user_input,
        pg_sources=[
            "scores.quarterly_results",
            "scores.annual_results",
            "scores.balance_sheet",
            "scores.cash_flow",
        ],
        evidence={
            "section_counts": section_counts,
            "latest_quarter": latest_q,
            "eps_driver": asdict(eps),
            "roce_driver": asdict(roce),
            "cashflow_driver": asdict(cashflow),
        },
        final_output=final,
        failures=failures,
    )


def run_quick_cases() -> list[SmokeCase]:
    return [
        technicals_case(),
        market_analysis_case(),
        stock_analysis_case(),
        index_analysis_case(),
        deep_fundamental_case(),
    ]


def run_agent_cases(output_dir: Path, timeout: int) -> list[SmokeCase]:
    cases = run_quick_cases()
    env = os.environ.copy()
    env.setdefault("AGENT_ADDA_SKIP_READINESS", "1")
    for case in cases:
        log_path = output_dir / f"agent_{case.category}.txt"
        cmd = [
            sys.executable,
            "nse_agent.py",
            "--no-briefing",
            "--skip-readiness",
            "-q",
            case.user_input,
            "--trace",
        ]
        result = subprocess.run(
            cmd,
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        output = result.stdout + result.stderr
        log_path.write_text(output)
        case.output_file = str(log_path)
        case.final_output = output
        if result.returncode != 0:
            case.failures.append(f"agent_exit_code={result.returncode}")
        lower = output.lower()
        if "source trail" not in lower and "tool trace" not in lower:
            case.failures.append("missing_agent_source_trail")
        if "required tool validation failed" in lower:
            case.failures.append("agent_required_tool_validation_failed")
        if case.category == "deep_fundamental_analysis" and not (
            "get_cached_financials" in lower
            or "postgresql financial statement cache" in lower
            or "scores.quarterly_results" in lower
        ):
            case.failures.append("missing_pg_cached_financials_in_agent_output")
        case.status = _status_from(case.failures)
        case.pg_grounded = not case.failures
    return cases


def write_reports(cases: list[SmokeCase], output_dir: Path, *, mode: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for case in cases:
        case_path = output_dir / f"{case.category}.txt"
        case_path.write_text(case.final_output)
        if not case.output_file:
            case.output_file = str(case_path)

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": mode,
        "dsn": DSN,
        "cases": [asdict(case) for case in cases],
        "overall_status": "pass" if all(case.status == "pass" for case in cases) else "fail",
    }
    (output_dir / "pg_grounded_query_report.json").write_text(
        json.dumps(payload, indent=2, default=_json_default)
    )

    lines = [
        "# PG Grounded Query Smoke Report",
        "",
        f"- Generated: {payload['generated_at']}",
        f"- Mode: `{mode}`",
        f"- Overall: `{payload['overall_status']}`",
        "",
        "| Category | Status | PG grounded | PG sources | Output |",
        "|---|---:|---:|---|---|",
    ]
    for case in cases:
        sources = ", ".join(f"`{source}`" for source in case.pg_sources)
        output_name = Path(case.output_file or "").name
        lines.append(
            f"| {case.category} | `{case.status}` | `{case.pg_grounded}` | "
            f"{sources} | `{output_name}` |"
        )
    lines.extend(["", "## Failures", ""])
    for case in cases:
        if case.failures:
            lines.append(f"- `{case.category}`: {', '.join(case.failures)}")
    if not any(case.failures for case in cases):
        lines.append("- None")
    lines.append("")
    (output_dir / "pg_grounded_query_report.md").write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test PG-grounded Agent Adda query paths.")
    parser.add_argument("--quick", action="store_true", help="Run deterministic local tools only.")
    parser.add_argument("--agent", action="store_true", help="Also run nse_agent.py final-answer prompts.")
    parser.add_argument("--output-dir", default=str(ROOT / "reports" / "pg_grounded_queries"))
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    mode = "agent" if args.agent else "quick"
    cases = run_agent_cases(output_dir, args.timeout) if args.agent else run_quick_cases()
    write_reports(cases, output_dir, mode=mode)
    print(f"PG_GROUNDED_QUERY_REPORT={output_dir / 'pg_grounded_query_report.md'}")
    return 0 if all(case.status == "pass" for case in cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
