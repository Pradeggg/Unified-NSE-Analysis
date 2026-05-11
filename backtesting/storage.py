"""PostgreSQL persistence for EOD Strategy Lab backtests."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, is_dataclass
from datetime import date
from typing import Any

import psycopg2
from psycopg2.extras import Json, execute_values

from backtesting.engine import BacktestConfig, BacktestResult


PG_DSN = os.environ.get("AGENT_ADDA_PG_DSN") or os.environ.get("PG_DSN") or "dbname=nse_market user=nse_admin host=/tmp"


SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS backtesting;

CREATE TABLE IF NOT EXISTS backtesting.strategy_definitions (
    strategy_id     TEXT PRIMARY KEY,
    name            TEXT,
    family          TEXT,
    status          TEXT,
    definition_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS backtesting.backtest_runs (
    id                  BIGSERIAL PRIMARY KEY,
    strategy_id          TEXT NOT NULL,
    status               TEXT NOT NULL DEFAULT 'completed',
    universe             TEXT,
    from_date            DATE,
    to_date              DATE,
    initial_capital      NUMERIC(18,4),
    allocation_pct       NUMERIC(10,6),
    entry_policy         TEXT,
    exit_policy          TEXT,
    trade_count          INTEGER NOT NULL DEFAULT 0,
    total_return_pct     NUMERIC(18,6),
    total_pnl            NUMERIC(18,4),
    run_config           JSONB NOT NULL DEFAULT '{}'::jsonb,
    data_readiness       JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS backtesting.backtest_trades (
    id              BIGSERIAL PRIMARY KEY,
    run_id          BIGINT NOT NULL REFERENCES backtesting.backtest_runs(id) ON DELETE CASCADE,
    symbol          TEXT NOT NULL,
    entry_date      DATE NOT NULL,
    entry_price     NUMERIC(18,6) NOT NULL,
    exit_date       DATE NOT NULL,
    exit_price      NUMERIC(18,6) NOT NULL,
    quantity        INTEGER NOT NULL,
    pnl             NUMERIC(18,6),
    return_pct      NUMERIC(18,6),
    entry_reason    TEXT,
    exit_reason     TEXT
);

CREATE TABLE IF NOT EXISTS backtesting.backtest_metrics (
    run_id          BIGINT NOT NULL REFERENCES backtesting.backtest_runs(id) ON DELETE CASCADE,
    metric_name     TEXT NOT NULL,
    metric_value    NUMERIC(18,6),
    metric_json     JSONB,
    PRIMARY KEY (run_id, metric_name)
);

CREATE TABLE IF NOT EXISTS backtesting.backtest_skipped_candidates (
    id              BIGSERIAL PRIMARY KEY,
    run_id          BIGINT NOT NULL REFERENCES backtesting.backtest_runs(id) ON DELETE CASCADE,
    symbol          TEXT,
    signal_date     DATE,
    reason          TEXT NOT NULL,
    details         JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_backtest_runs_strategy_created
    ON backtesting.backtest_runs (strategy_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_backtest_trades_run_symbol
    ON backtesting.backtest_trades (run_id, symbol);
CREATE INDEX IF NOT EXISTS idx_backtest_trades_symbol_entry
    ON backtesting.backtest_trades (symbol, entry_date DESC);
"""


def connect(dsn: str | None = None):
    return psycopg2.connect(dsn or PG_DSN)


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, date):
        return value.isoformat()
    return value


def ensure_backtest_schema(conn, *, commit: bool = True) -> None:
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)
    if commit:
        conn.commit()


def persist_backtest_result(
    result: BacktestResult,
    config: BacktestConfig,
    *,
    conn=None,
    dsn: str | None = None,
    universe: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    data_readiness: dict[str, Any] | None = None,
) -> dict[str, Any]:
    own_conn = conn is None
    db = conn or connect(dsn)
    try:
        ensure_backtest_schema(db, commit=False)
        with db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO backtesting.backtest_runs (
                    strategy_id, status, universe, from_date, to_date,
                    initial_capital, allocation_pct, entry_policy, exit_policy,
                    trade_count, total_return_pct, total_pnl, run_config, data_readiness
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    result.strategy_id,
                    "completed",
                    universe,
                    from_date,
                    to_date,
                    config.initial_capital,
                    config.allocation_pct,
                    config.entry_policy,
                    config.exit_policy,
                    int(result.metrics.get("trade_count") or len(result.trades)),
                    result.metrics.get("total_return_pct"),
                    result.metrics.get("total_pnl"),
                    Json(_jsonable(config)),
                    Json(_jsonable(data_readiness or {})),
                ),
            )
            run_id = int(cur.fetchone()[0])

            trade_values = [
                (
                    run_id,
                    trade.symbol,
                    trade.entry_date,
                    trade.entry_price,
                    trade.exit_date,
                    trade.exit_price,
                    trade.quantity,
                    trade.pnl,
                    trade.return_pct,
                    trade.entry_reason,
                    trade.exit_reason,
                )
                for trade in result.trades
            ]
            if trade_values:
                execute_values(
                    cur,
                    """
                    INSERT INTO backtesting.backtest_trades (
                        run_id, symbol, entry_date, entry_price, exit_date, exit_price,
                        quantity, pnl, return_pct, entry_reason, exit_reason
                    )
                    VALUES %s
                    """,
                    trade_values,
                    page_size=500,
                )

            metric_values = [
                (
                    run_id,
                    name,
                    value if isinstance(value, (int, float)) and value is not None else None,
                    Json(_jsonable(value)),
                )
                for name, value in result.metrics.items()
            ]
            if metric_values:
                execute_values(
                    cur,
                    """
                    INSERT INTO backtesting.backtest_metrics (
                        run_id, metric_name, metric_value, metric_json
                    )
                    VALUES %s
                    ON CONFLICT (run_id, metric_name) DO UPDATE
                    SET metric_value = EXCLUDED.metric_value,
                        metric_json = EXCLUDED.metric_json
                    """,
                    metric_values,
                    page_size=500,
                )

            skipped_values = [
                (
                    run_id,
                    item.get("symbol"),
                    item.get("date"),
                    item.get("reason") or "unknown",
                    Json(_jsonable(item)),
                )
                for item in result.skipped
            ]
            if skipped_values:
                execute_values(
                    cur,
                    """
                    INSERT INTO backtesting.backtest_skipped_candidates (
                        run_id, symbol, signal_date, reason, details
                    )
                    VALUES %s
                    """,
                    skipped_values,
                    page_size=500,
                )

        db.commit()
        return {
            "ok": True,
            "run_id": run_id,
            "trades_inserted": len(trade_values),
            "metrics_inserted": len(metric_values),
            "skipped_inserted": len(result.skipped),
        }
    except Exception:
        db.rollback()
        raise
    finally:
        if own_conn:
            db.close()


def load_latest_backtest_report(*, conn=None, dsn: str | None = None, run_id: int | None = None) -> dict[str, Any]:
    """Load the latest persisted backtest run with trades and metrics."""
    own_conn = conn is None
    db = conn or connect(dsn)
    try:
        with db.cursor() as cur:
            if run_id is None:
                cur.execute(
                    """
                    SELECT id, strategy_id, universe, from_date, to_date,
                           initial_capital, trade_count, total_return_pct, total_pnl,
                           run_config, data_readiness, created_at
                    FROM backtesting.backtest_runs
                    ORDER BY id DESC
                    LIMIT 1
                    """
                )
            else:
                cur.execute(
                    """
                    SELECT id, strategy_id, universe, from_date, to_date,
                           initial_capital, trade_count, total_return_pct, total_pnl,
                           run_config, data_readiness, created_at
                    FROM backtesting.backtest_runs
                    WHERE id = %s
                    """,
                    (run_id,),
                )
            row = cur.fetchone()
            if not row:
                return {"run": None, "trades": [], "metrics": {}}

            run = {
                "id": int(row[0]),
                "strategy_id": row[1],
                "universe": row[2],
                "from_date": _jsonable(row[3]),
                "to_date": _jsonable(row[4]),
                "initial_capital": float(row[5]) if row[5] is not None else None,
                "trade_count": int(row[6] or 0),
                "total_return_pct": float(row[7]) if row[7] is not None else None,
                "total_pnl": float(row[8]) if row[8] is not None else None,
                "run_config": row[9] or {},
                "data_readiness": row[10] or {},
                "created_at": _jsonable(row[11]),
            }

            cur.execute(
                """
                SELECT symbol, entry_date, entry_price, exit_date, exit_price,
                       quantity, pnl, return_pct, entry_reason, exit_reason
                FROM backtesting.backtest_trades
                WHERE run_id = %s
                ORDER BY entry_date, symbol
                """,
                (run["id"],),
            )
            trades = [
                {
                    "symbol": item[0],
                    "entry_date": _jsonable(item[1]),
                    "entry_price": float(item[2]) if item[2] is not None else None,
                    "exit_date": _jsonable(item[3]),
                    "exit_price": float(item[4]) if item[4] is not None else None,
                    "quantity": int(item[5]) if item[5] is not None else None,
                    "pnl": float(item[6]) if item[6] is not None else None,
                    "return_pct": float(item[7]) if item[7] is not None else None,
                    "entry_reason": item[8],
                    "exit_reason": item[9],
                }
                for item in cur.fetchall()
            ]

            cur.execute(
                """
                SELECT metric_name, metric_value, metric_json
                FROM backtesting.backtest_metrics
                WHERE run_id = %s
                ORDER BY metric_name
                """,
                (run["id"],),
            )
            metrics = {}
            for name, value, metric_json in cur.fetchall():
                if value is not None:
                    metrics[name] = float(value)
                else:
                    metrics[name] = metric_json

            return {"run": run, "trades": trades, "metrics": metrics}
    finally:
        if own_conn:
            db.close()
