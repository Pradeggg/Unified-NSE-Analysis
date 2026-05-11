"""Terminal helpers for the EOD Strategy Lab."""

from __future__ import annotations

import shlex
from pathlib import Path

import pandas as pd

from backtesting.data import inspect_backtest_data
from backtesting.engine import BacktestConfig, run_backtest
from backtesting.storage import load_latest_backtest_report, persist_backtest_result
from backtesting.strategy_registry import list_strategies


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
    if len(parts) >= 3 and parts[0].lower() == "/backtest" and parts[1].lower() == "run":
        return _run_backtest_command(parts[2:], project_root=project_root)

    return (
        "Usage:\n"
        "  /backtest list\n"
        "  /strategy-lab validate\n"
        "  /backtest run <strategy> --universe nifty500 --from YYYY-MM-DD  "
        "(engine implementation pending)"
    )


def _arg_value(parts: list[str], name: str, default: str | None = None) -> str | None:
    if name not in parts:
        return default
    idx = parts.index(name)
    if idx + 1 >= len(parts):
        raise ValueError(f"Missing value for {name}")
    return parts[idx + 1]


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
        from_date = _arg_value(parts, "--from")
        to_date = _arg_value(parts, "--to")
        persist = "--persist" in parts or "--postgres" in parts
        if not data_arg and not symbol and not max_symbols:
            return "Default NSE backtest requires --symbol or --max-symbols to avoid accidental all-universe runs."

        df = pd.read_csv(data_path)
        df = df.rename(columns={col: col.strip().lower() for col in df.columns})
        if "timestamp" in df.columns and "date" not in df.columns:
            df = df.rename(columns={"timestamp": "date"})
        if "tottrdqty" in df.columns and "volume" not in df.columns:
            df = df.rename(columns={"tottrdqty": "volume"})
        if symbol and "symbol" in df.columns:
            df = df[df["symbol"].astype(str).str.upper() == symbol.upper()]
        elif max_symbols and "symbol" in df.columns:
            symbols = sorted(df["symbol"].dropna().astype(str).str.upper().unique().tolist())
            keep = set(symbols[: int(max_symbols)])
            df = df[df["symbol"].astype(str).str.upper().isin(keep)]
        if from_date and "date" in df.columns:
            df = df[pd.to_datetime(df["date"], errors="coerce") >= pd.to_datetime(from_date)]
        if to_date and to_date.lower() != "today" and "date" in df.columns:
            df = df[pd.to_datetime(df["date"], errors="coerce") <= pd.to_datetime(to_date)]

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
