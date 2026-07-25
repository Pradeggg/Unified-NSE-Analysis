"""Terminal helpers for the EOD Strategy Lab."""

from __future__ import annotations

import csv
import json
import shlex
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from backtesting.data import inspect_backtest_data
from backtesting.engine import BacktestConfig, run_backtest
from backtesting.storage import load_latest_backtest_report, persist_backtest_result
from backtesting.strategy_registry import list_strategies
from terminal.reports import generate_preset_report
from terminal.intraday_indicator_study import StudyConfig, run_intraday_indicator_study
from terminal.intraday_editorial_report import run_editorial_report
from terminal.edge_knowledge import generate_edge_memory_report


def _strategy_ids() -> set[str]:
    return {s.id for s in list_strategies()}


_UNIVERSE_ALIASES = {
    "nifty50": "NIFTY 50",
    "nifty100": "NIFTY 100",
    "nifty200": "NIFTY 200",
    "nifty500": "NIFTY 500",
    "niftymidcap50": "NIFTY MIDCAP 50",
    "niftymidcap100": "NIFTY MIDCAP 100",
    "niftymidcap150": "NIFTY MIDCAP 150",
    "niftysmallcap100": "NIFTY SMALLCAP 100",
    "niftysmallcap250": "NIFTY SMALLCAP 250",
    "niftymicrocap250": "NIFTY MICROCAP 250",
    "niftylargemidcap250": "NIFTY LARGEMIDCAP 250",
}


def _resolve_universe(name: str, project_root: Path) -> tuple[str, list[str]]:
    """Return (display_label, symbols[]) for a universe alias."""
    key = name.lower().replace(" ", "").replace("_", "").replace("-", "")
    label = _UNIVERSE_ALIASES.get(key)
    if not label:
        raise ValueError(
            f"Unknown universe '{name}'. Try: " + ", ".join(sorted(_UNIVERSE_ALIASES))
        )
    mapping = project_root / "data" / "index_stock_mapping.csv"
    if not mapping.exists():
        raise ValueError(f"index_stock_mapping.csv not found at {mapping}")
    syms: list[str] = []
    with mapping.open() as f:
        for row in csv.DictReader(f):
            if (row.get("INDEX_NAME") or "").strip().upper() == label.upper():
                s = (row.get("STOCK_SYMBOL") or "").strip().upper()
                if s:
                    syms.append(s)
    return label, sorted(set(syms))


def _usage_block() -> str:
    examples = (
        "Usage:\n"
        "  /backtest list                            — show available strategies\n"
        "  /strategy-lab validate                    — check EOD data readiness\n"
        "  /strategy-lab run                         — replay portfolio strategies + HTML report\n"
        "  /intraday-indicator-study                  — rank intraday F&O indicator setups\n"
        "  /edge-knowledge-report                     — build Edge Memory dashboard\n"
        "  /intraday-editorial-report                 — build editorial quant F&O research note\n"
        "  /backtest run <strategy> [options]        — execute a backtest\n"
        "  /backtest <strategy> <SYMBOL>             — shorthand for last 2y on one symbol\n"
        "  /backtest report latest                   — show last persisted run\n"
        "\n"
        "Run options:\n"
        "  --symbol <SYM>            single symbol (NSE ticker)\n"
        "  --universe <name>         nifty500 | nifty50 | niftysmallcap250 | …\n"
        "  --max-symbols <N>         cap universe to first N tickers\n"
        "  --from YYYY-MM-DD         start date (default: 2 years before today)\n"
        "  --to YYYY-MM-DD           end date (default: today)\n"
        "  --capital <amount>        initial capital (default 100000)\n"
        "  --persist                 store run + trades in PostgreSQL\n"
        "  --persist-edges           store intraday findings as Edge Knowledge Nodes\n"
        "  --data <path>             override CSV (default data/nse_sec_full_data.csv)\n"
        "\n"
        "Examples:\n"
        "  /backtest stage2 DMART\n"
        "  /backtest run vcp --symbol RELIANCE --from 2024-01-01\n"
        "  /backtest run canslim --universe nifty500 --from 2024-01-01 --persist\n"
        "  /strategy-lab run --top-n 200\n"
        "  /intraday-indicator-study --universe fno --timeframes 5m,15m --lookback-days 30 --persist-edges\n"
        "  /edge-knowledge-report --output-dir reports/latest"
    )
    return examples


def _render_strategy_list() -> str:
    lines = ["Strategy Lab — EOD strategies", ""]
    lines.append("| ID | Family | Status | Description |")
    lines.append("|---|---|---|---|")
    for strategy in list_strategies():
        lines.append(
            f"| {strategy.id} | {strategy.family} | {strategy.status} | {strategy.description} |"
        )
    return "\n".join(lines)


def _render_validation(project_root: Path | None = None) -> str:
    status = inspect_backtest_data(project_root)
    state = "OK" if status.ok_to_backtest else "BLOCKED"
    lines = [
        f"Strategy Lab EOD validation: {state}",
        f"EOD latest date: {status.latest_eod_date or 'not found'}",
        f"Symbols: {status.symbol_count}",
        f"Modes: {', '.join(status.modes) if status.modes else 'none'}",
    ]
    if status.blockers:
        lines.append(f"Blockers: {', '.join(status.blockers)}")
    if status.warnings:
        lines.append(f"Warnings: {', '.join(status.warnings)}")
    return "\n".join(lines)


def handle_backtest_command(text: str, *, project_root: Path | None = None) -> str:
    raw = text.strip()
    lower = raw.lower()

    if lower in ("/backtest", "/backtest list", "/strategy-lab list"):
        return _render_strategy_list()

    if lower == "/strategy-lab validate":
        return _render_validation(project_root)

    if lower == "/backtest report latest":
        return _render_latest_report()

    parts = shlex.split(raw)
    if len(parts) >= 2 and parts[0].lower() == "/strategy-lab" and parts[1].lower() == "run":
        return _run_portfolio_strategy_lab_command(parts[2:], project_root=project_root)

    if parts and parts[0].lower() in {"/intraday-indicator-study", "/intraday-indicators"}:
        return _run_intraday_indicator_study_command(parts[1:], project_root=project_root)

    if parts and parts[0].lower() in {"/intraday-editorial-report", "/intraday-fno-editorial"}:
        return _run_intraday_editorial_report_command(parts[1:], project_root=project_root)

    if parts and parts[0].lower() in {"/edge-knowledge-report", "/edge-memory", "/edge-memory-report"}:
        return _run_edge_memory_report_command(parts[1:], project_root=project_root)

    if len(parts) >= 3 and parts[0].lower() == "/backtest" and parts[1].lower() == "run":
        return _run_backtest_command(parts[2:], project_root=project_root)

    # Shorthand: /backtest <strategy> <SYMBOL>
    if (
        len(parts) >= 3
        and parts[0].lower() == "/backtest"
        and parts[1].lower().replace("-", "_") in _strategy_ids()
    ):
        strategy = parts[1].lower().replace("-", "_")
        symbol = parts[2].upper()
        default_from = (date.today() - timedelta(days=730)).isoformat()
        return _run_backtest_command(
            [strategy, "--symbol", symbol, "--from", default_from],
            project_root=project_root,
        )

    head = parts[0] if parts else raw
    hint = ""
    if " /" in raw:
        hint = (
            "\n\nNote: it looks like two slash-commands were joined on one line "
            f"('{raw[:80]}…'). Run them one at a time."
        )
    elif len(parts) >= 2 and parts[0].lower() == "/backtest":
        sid = parts[1].lower().replace("-", "_")
        if sid not in _strategy_ids():
            hint = (
                f"\n\nNote: '{parts[1]}' is not a known strategy id. "
                "Run /backtest list to see all 12 strategies."
            )
    return f"Unrecognized: {head}\n\n{_usage_block()}{hint}"


def _arg_csv(parts: list[str], name: str, default: str) -> tuple[str, ...]:
    raw = _arg_value(parts, name, default) or default
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _run_intraday_editorial_report_command(parts: list[str], *, project_root: Path | None = None) -> str:
    root = project_root or Path.cwd()
    source = Path(_arg_value(parts, "--source", "reports/latest/intraday_fno_indicator_study.md"))
    if not source.is_absolute():
        source = root / source
    allow_llm = "--no-llm" not in parts
    detailed = "--detailed" in parts or "--paper" in parts
    try:
        result = run_editorial_report(
            source,
            output_dir=root / "reports" / "latest",
            allow_llm=allow_llm,
            detailed=detailed,
        )
    except Exception as exc:
        return f"Intraday F&O Editorial Report failed: {type(exc).__name__}: {exc}"
    paths = result.get("paths") or {}
    lines = [
        "Intraday F&O Editorial Report: OK",
        f"Headline: {result.get('headline') or '-'}",
        f"Narrative source: {(result.get('metadata') or {}).get('source') or '-'}",
        f"Markdown: {paths.get('markdown')}",
        f"HTML: {paths.get('html')}",
        f"JSON: {paths.get('json')}",
        "",
        "Research only. Not investment advice.",
    ]
    if (result.get("metadata") or {}).get("llm_error"):
        lines.insert(3, f"LLM note: {(result.get('metadata') or {}).get('llm_error')}")
    detailed_paths = result.get("detailed_paths") or {}
    if detailed_paths:
        lines.insert(-2, f"Detailed paper: {detailed_paths.get('html')}")
    return "\n".join(lines)


def _run_intraday_indicator_study_command(parts: list[str], *, project_root: Path | None = None) -> str:
    root = Path(project_root or Path.cwd())
    try:
        universe = _arg_value(parts, "--universe", "fno") or "fno"
        symbols = _arg_csv(parts, "--symbols", "")
        timeframes = _arg_csv(parts, "--timeframes", "5m,15m")
        max_symbols = int(_arg_value(parts, "--max-symbols", "75") or "75")
        max_hold_bars = int(_arg_value(parts, "--max-hold-bars", "12") or "12")
        min_bars = int(_arg_value(parts, "--min-bars", "80") or "80")
        slippage_bps = float(_arg_value(parts, "--slippage-bps", "3.0") or "3.0")
        brokerage_bps = float(_arg_value(parts, "--brokerage-bps", "2.0") or "2.0")
        promote_min_trades = int(_arg_value(parts, "--promote-min-trades", "10") or "10")
        promote_min_expectancy_r = float(_arg_value(parts, "--promote-min-expectancy-r", "0.05") or "0.05")
        promote_min_profit_factor = float(_arg_value(parts, "--promote-min-profit-factor", "1.10") or "1.10")
        watch_min_trades = int(_arg_value(parts, "--watch-min-trades", "5") or "5")
        watch_min_expectancy_r = float(_arg_value(parts, "--watch-min-expectancy-r", "0.0") or "0.0")
        include_fno_context = "--no-fno-context" not in parts
        persist_edges = "--persist-edges" in parts
        start = _arg_value(parts, "--from")
        end = _arg_value(parts, "--to")
        lookback_days = _arg_value(parts, "--lookback-days")
        if lookback_days and not start:
            start = (date.today() - timedelta(days=int(lookback_days))).isoformat()
        data_arg = _arg_value(parts, "--data")
        data_path = Path(data_arg) if data_arg else None
        if data_path and not data_path.is_absolute():
            data_path = root / data_path
        output_arg = _arg_value(parts, "--output-dir", "reports/research") or "reports/research"
        output_dir = Path(output_arg)
        if not output_dir.is_absolute():
            output_dir = root / output_dir

        config = StudyConfig(
            universe=universe,
            symbols=symbols,
            timeframes=timeframes,
            start=start,
            end=end,
            max_symbols=max_symbols,
            max_hold_bars=max_hold_bars,
            slippage_bps=slippage_bps,
            brokerage_bps=brokerage_bps,
            min_bars=min_bars,
            data_path=data_path,
            output_dir=output_dir,
            include_fno_context=include_fno_context,
            promote_min_trades=promote_min_trades,
            promote_min_expectancy_r=promote_min_expectancy_r,
            promote_min_profit_factor=promote_min_profit_factor,
            watch_min_trades=watch_min_trades,
            watch_min_expectancy_r=watch_min_expectancy_r,
            persist_edges=persist_edges,
        )
        result = run_intraday_indicator_study(config)
    except Exception as exc:
        return f"Intraday Indicator Study failed: {type(exc).__name__}: {exc}"

    report = result.get("report") or {}
    leaderboard = result.get("leaderboard")
    top_line = "No setup leaderboard produced."
    if leaderboard is not None and not leaderboard.empty:
        top = leaderboard.iloc[0]
        top_line = (
            f"Top setup: {top['setup']} {top['direction']} on {top['timeframe']} — "
            f"trades={int(top['trades'])}, win={top['win_rate']:.1f}%, expectancy={top['expectancy_r']:.2f}R"
        )
    strategy_frame = result.get("strategy_map_frame")
    strategy_line = "Strategy map: no symbol-level map produced."
    if strategy_frame is not None and not strategy_frame.empty:
        counts = strategy_frame["status"].value_counts().to_dict()
        strategy_line = (
            "Strategy map: "
            f"promoted={counts.get('promoted', 0)}, "
            f"watch={counts.get('watch_candidate', 0)}, "
            f"avoid={counts.get('avoid', 0)}, "
            f"insufficient={counts.get('insufficient_data', 0)}"
        )
    source = "; ".join(result.get("source_notes") or [])
    state = "OK" if result.get("ok") else "DATA LIMITED"
    edge_persistence = result.get("edge_persistence")
    edge_line = None
    if edge_persistence:
        edge_line = (
            f"Edge nodes: persisted={edge_persistence.get('nodes', 0)} "
            f"refresh={edge_persistence.get('refresh_id') or '-'}"
        )
    output_lines = [
        f"Intraday F&O Indicator Study: {state}",
        f"Bars: {result.get('bars', 0)} | Symbols: {result.get('symbols', 0)} | Trades tested: {result.get('trades', 0)}",
        f"F&O context rows: {len(result.get('fno_context')) if result.get('fno_context') is not None else 0}",
        top_line,
        strategy_line,
    ]
    if edge_line:
        output_lines.append(edge_line)
    output_lines.extend(
        [
            f"Source trail: {source or 'not reported'}",
            f"Report: {report.get('html') or '-'}",
            f"Latest: {report.get('latest_html') or '-'}",
            f"Strategy map JSON: {report.get('latest_strategy_map') or '-'}",
            "",
            "Research only. Not investment advice.",
        ]
    )
    return "\n".join(
        output_lines
    )


def _run_edge_memory_report_command(parts: list[str], *, project_root: Path | None = None) -> str:
    root = Path(project_root or Path.cwd())
    output_arg = _arg_value(parts, "--output-dir", "reports/latest") or "reports/latest"
    output_dir = Path(output_arg)
    if not output_dir.is_absolute():
        output_dir = root / output_dir
    try:
        result = generate_edge_memory_report(output_dir=output_dir)
    except Exception as exc:
        return f"Edge Knowledge Report failed: {type(exc).__name__}: {exc}"
    summary = result.get("summary") or {}
    paths = result.get("paths") or {}
    status_counts = summary.get("status_counts") or {}
    status_line = ", ".join(f"{key}={value}" for key, value in sorted(status_counts.items())) or "none"
    return "\n".join(
        [
            "Edge Knowledge Report: OK",
            f"Edges: {summary.get('total_edges', 0)}",
            f"Status: {status_line}",
            f"Active: {summary.get('active_edges', 0)} | Retired: {summary.get('retired_edges', 0)}",
            f"HTML: {paths.get('html') or '-'}",
            f"Markdown: {paths.get('markdown') or '-'}",
            f"JSON: {paths.get('json') or '-'}",
            "",
            "Research only. Not investment advice.",
        ]
    )


def _arg_value(parts: list[str], name: str, default: str | None = None) -> str | None:
    if name not in parts:
        return default
    idx = parts.index(name)
    if idx + 1 >= len(parts):
        raise ValueError(f"Missing value for {name}")
    return parts[idx + 1]


def _read_strategy_lab_summary(output_dir: Path) -> dict[str, Any]:
    for summary_path in (
        output_dir / "reports" / "strategy_comparison_summary.json",
        output_dir / "summary.json",
    ):
        if not summary_path.exists():
            continue
        with summary_path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return data
    return {}


def _run_portfolio_strategy_lab_command(parts: list[str], *, project_root: Path | None = None) -> str:
    root = Path(project_root or Path.cwd())
    output_arg = _arg_value(parts, "--output-dir", "portfolio/data/nse_pg_strategy_lab/latest")
    output_dir = Path(output_arg or "portfolio/data/nse_pg_strategy_lab/latest")
    if not output_dir.is_absolute():
        output_dir = root / output_dir

    start = _arg_value(parts, "--start", "2025-01-01")
    lookback = _arg_value(parts, "--lookback", "2024-01-01")
    top_n = _arg_value(parts, "--top-n", "200")
    slippage_bps = _arg_value(parts, "--slippage-bps", "5.0")
    brokerage_bps = _arg_value(parts, "--brokerage-bps", "3.0")
    run_id = _arg_value(parts, "--run-id", "NSE-PG-AGENT-STRATEGY-LAB")

    cmd = [
        sys.executable,
        "-m",
        "portfolio.cli",
        "strategy-lab",
        "--output-dir",
        str(output_dir),
        "--start",
        str(start),
        "--lookback",
        str(lookback),
        "--top-n",
        str(top_n),
        "--slippage-bps",
        str(slippage_bps),
        "--brokerage-bps",
        str(brokerage_bps),
        "--run-id",
        str(run_id),
    ]
    if "--no-db-persist" in parts:
        cmd.append("--no-db-persist")

    try:
        result = subprocess.run(cmd, cwd=root, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip()
            return f"Strategy Lab portfolio replay failed with exit code {result.returncode}:\n{err}"

        report = generate_preset_report("strategy-lab", "html")
        summary = _read_strategy_lab_summary(output_dir)
    except Exception as exc:
        return f"Strategy Lab portfolio replay failed: {exc}"

    latest_path = report.get("latest_path") or report.get("path") or ""
    report_path = report.get("path") or latest_path
    db = ((summary.get("paper_portfolio") or {}).get("database") or {})

    lines = [
        "Strategy Lab portfolio replay complete",
        f"Output: {output_dir}",
    ]
    if report_path:
        lines.append(f"Report: {report_path}")
    if latest_path and latest_path != report_path:
        lines.append(f"Latest: {latest_path}")
    if db:
        status = "OK" if db.get("success") else "FAILED"
        daily_pnl_count = db.get("daily_pnl", db.get("daily_pnl_rows", 0))
        lines.append(
            "PostgreSQL: "
            f"{status} "
            f"(positions={db.get('positions', 0)}, "
            f"daily_pnl={daily_pnl_count}, "
            f"transactions={db.get('transactions', 0)}, "
            f"agent_actions={db.get('agent_actions', 0)})"
        )
    else:
        lines.append("PostgreSQL: not reported in strategy_comparison_summary.json")
    stdout = _summarize_strategy_lab_stdout(result.stdout)
    if stdout:
        lines.append("")
        lines.append("CLI output:")
        lines.append(stdout)
    return "\n".join(lines)


def _summarize_strategy_lab_stdout(stdout: str) -> str:
    """Return CLI stdout without raw artifact paths that trigger auto-analysis."""
    keep: list[str] = []
    for line in (stdout or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if lower.startswith(("leaderboard:", "report:", "summary:")):
            continue
        keep.append(stripped)
    return "\n".join(keep)[-1200:]


def _run_backtest_command(parts: list[str], *, project_root: Path | None = None) -> str:
    strategy_id = parts[0].lower().replace("-", "_")
    root = Path(project_root or Path.cwd())
    try:
        data_arg = _arg_value(parts, "--data")
        if data_arg:
            data_path = Path(data_arg)
            if not data_path.is_absolute():
                data_path = root / data_path
            data_label = str(data_path)
        else:
            data_path = root / "data" / "nse_sec_full_data.csv"
            data_label = "data/nse_sec_full_data.csv"

        capital = float(_arg_value(parts, "--capital", "100000") or "100000")
        symbol = _arg_value(parts, "--symbol")
        max_symbols = _arg_value(parts, "--max-symbols")
        universe = _arg_value(parts, "--universe")
        from_date = _arg_value(parts, "--from")
        to_date = _arg_value(parts, "--to")
        persist = "--persist" in parts or "--postgres" in parts
        universe_symbols: list[str] | None = None
        universe_label: str | None = None
        if universe:
            universe_label, universe_symbols = _resolve_universe(universe, root)
            if not universe_symbols:
                return f"Universe '{universe}' resolved to 0 symbols — check data/index_stock_mapping.csv"
        if not data_arg and not symbol and not max_symbols and not universe_symbols:
            return (
                "Need a scope. Pass one of:\n"
                "  --symbol <SYM>           (single ticker)\n"
                "  --universe <name>        (e.g. nifty500, nifty50, niftysmallcap250)\n"
                "  --max-symbols <N>        (first N tickers in the CSV)\n"
                "  --data <path>            (custom CSV that defines its own scope)"
            )

        df = pd.read_csv(data_path)
        df = df.rename(columns={col: col.strip().lower() for col in df.columns})
        if "timestamp" in df.columns and "date" not in df.columns:
            df = df.rename(columns={"timestamp": "date"})
        if "tottrdqty" in df.columns and "volume" not in df.columns:
            df = df.rename(columns={"tottrdqty": "volume"})
        if symbol and "symbol" in df.columns:
            df = df[df["symbol"].astype(str).str.upper() == symbol.upper()]
        elif universe_symbols and "symbol" in df.columns:
            df = df[df["symbol"].astype(str).str.upper().isin(set(universe_symbols))]
        elif max_symbols and "symbol" in df.columns:
            symbols = sorted(df["symbol"].dropna().astype(str).str.upper().unique().tolist())
            keep = set(symbols[: int(max_symbols)])
            df = df[df["symbol"].astype(str).str.upper().isin(keep)]
        if from_date and "date" in df.columns:
            df = df[pd.to_datetime(df["date"], errors="coerce") >= pd.to_datetime(from_date)]
        if to_date and to_date.lower() != "today" and "date" in df.columns:
            df = df[pd.to_datetime(df["date"], errors="coerce") <= pd.to_datetime(to_date)]

        if df.empty:
            scope_bits = []
            if symbol: scope_bits.append(f"symbol={symbol}")
            if universe_label: scope_bits.append(f"universe={universe_label} ({len(universe_symbols or [])} tickers)")
            if from_date: scope_bits.append(f"from={from_date}")
            if to_date: scope_bits.append(f"to={to_date}")
            return f"No rows after filtering ({', '.join(scope_bits) or 'no filters'}). Try a different symbol/universe/date range."

        result = run_backtest(
            df,
            BacktestConfig(strategy_id=strategy_id, initial_capital=capital),
        )
        persisted = None
        if persist:
            persisted = persist_backtest_result(
                result,
                BacktestConfig(strategy_id=strategy_id, initial_capital=capital),
                universe=str(data_path),
                from_date=from_date,
                to_date=None if to_date and to_date.lower() == "today" else to_date,
            )
    except Exception as exc:
        return f"Backtest failed: {exc}"

    lines = [
        f"Backtest: {result.strategy_id}",
        f"Data: {data_label}",
        f"Trades: {result.metrics.get('trade_count', 0)}",
        f"Total return: {result.metrics.get('total_return_pct')}%",
        f"Total P&L: {result.metrics.get('total_pnl')}",
        f"Win rate: {result.metrics.get('win_rate_pct')}%",
        "Mode: EOD deterministic next-open execution",
    ]
    if persisted:
        lines.append(f"PostgreSQL run id: {persisted['run_id']}")
        lines.append(
            f"Persisted: {persisted['trades_inserted']} trades, "
            f"{persisted['metrics_inserted']} metrics"
        )
    return "\n".join(lines)


def _render_latest_report() -> str:
    try:
        report = load_latest_backtest_report()
    except Exception as exc:
        return f"Backtest report failed: {exc}"

    run = report.get("run")
    if not run:
        return "No persisted backtest runs found in PostgreSQL."

    metrics = report.get("metrics") or {}
    trades = report.get("trades") or []
    lines = [
        f"Backtest Report: #{run['id']}",
        f"Strategy: {run.get('strategy_id')}",
        f"Universe: {run.get('universe') or 'N/A'}",
        f"Date range: {run.get('from_date') or 'N/A'} to {run.get('to_date') or 'latest'}",
        f"Trades: {run.get('trade_count', 0)}",
        f"Total return: {run.get('total_return_pct')}%",
        f"Total P&L: {run.get('total_pnl')}",
    ]
    if "win_rate_pct" in metrics:
        lines.append(f"Win rate: {metrics['win_rate_pct']}%")

    if trades:
        lines.extend(["", "| Symbol | Entry | Exit | Qty | P&L | Return % |", "|---|---|---|---:|---:|---:|"])
        for trade in trades[:20]:
            lines.append(
                f"| {trade.get('symbol')} | "
                f"{trade.get('entry_date')} @ {trade.get('entry_price')} | "
                f"{trade.get('exit_date')} @ {trade.get('exit_price')} | "
                f"{trade.get('quantity')} | {trade.get('pnl')} | {trade.get('return_pct')} |"
            )
        if len(trades) > 20:
            lines.append(f"\nShowing first 20 of {len(trades)} trades.")

    return "\n".join(lines)
