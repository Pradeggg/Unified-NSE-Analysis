#!/usr/bin/env python3
"""Materialize Stage 2 VCP picks into PostgreSQL.

The portfolio strategy lab and Top Picks report both expect
`scores.stage2_vcp_picks` as the point-in-time VCP audit trail. This script
builds that table from `scores.stage_snapshots` plus `market.equity_eod`.
"""
from __future__ import annotations

import argparse
import os
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values, Json


PG_DSN = (
    os.environ.get("AGENT_ADDA_PG_DSN")
    or os.environ.get("PG_DSN")
    or "dbname=nse_market user=nse_admin host=/tmp"
)


def _connect():
    return psycopg2.connect(PG_DSN)


def _date_arg(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def _ensure_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE SCHEMA IF NOT EXISTS scores;
            CREATE TABLE IF NOT EXISTS scores.stage2_vcp_picks (
                snapshot_date date NOT NULL,
                symbol text NOT NULL,
                rank integer NOT NULL,
                company_name text,
                sector text,
                price numeric,
                investment_score numeric,
                enhanced_fund_score numeric,
                vcp_score numeric,
                vcp_breakout_pct numeric,
                vcp_contraction_pct numeric,
                rsi numeric,
                relative_strength numeric,
                trading_signal text,
                trend_signal text,
                supertrend_state text,
                narrative text,
                fund_details jsonb,
                created_at timestamptz NOT NULL DEFAULT now(),
                updated_at timestamptz NOT NULL DEFAULT now(),
                PRIMARY KEY (snapshot_date, symbol)
            );
            CREATE INDEX IF NOT EXISTS idx_stage2_vcp_picks_date_rank
                ON scores.stage2_vcp_picks (snapshot_date, rank);
            CREATE INDEX IF NOT EXISTS idx_stage2_vcp_picks_symbol_date
                ON scores.stage2_vcp_picks (symbol, snapshot_date);
            """
        )
    conn.commit()


def _resolve_dates(conn, start: date | None, end: date | None, lookback_days: int) -> tuple[date, date]:
    with conn.cursor() as cur:
        cur.execute("SELECT MAX(snapshot_date) FROM scores.stage_snapshots")
        latest = cur.fetchone()[0]
    if latest is None:
        raise RuntimeError("scores.stage_snapshots is empty; cannot build VCP picks")
    end_date = end or latest
    start_date = start or (end_date - timedelta(days=lookback_days))
    return start_date, end_date


def _load_stage_candidates(conn, start_date: date, end_date: date) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT
            snapshot_date,
            symbol,
            company_name,
            sector,
            price,
            investment_score,
            enhanced_fund_score,
            rsi,
            relative_strength,
            trading_signal,
            trend_signal,
            supertrend_state,
            narrative,
            fund_details
        FROM scores.stage_snapshots
        WHERE snapshot_date BETWEEN %(start_date)s AND %(end_date)s
          AND stage = 'STAGE_2'
          AND COALESCE(price, 0) >= 50
          AND COALESCE(supertrend_state, '') = 'BULLISH'
          AND COALESCE(trend_signal, '') IN ('BULLISH', 'STRONG_BULLISH')
        """,
        conn,
        params={"start_date": start_date, "end_date": end_date},
    )


def _load_eod(conn, symbols: list[str], start_date: date, end_date: date) -> pd.DataFrame:
    if not symbols:
        return pd.DataFrame()
    history_start = start_date - timedelta(days=140)
    return pd.read_sql_query(
        """
        SELECT trade_date, symbol, open, high, low, close, volume
        FROM market.equity_eod
        WHERE trade_date BETWEEN %(history_start)s AND %(end_date)s
          AND symbol = ANY(%(symbols)s)
          AND open > 0 AND high > 0 AND low > 0 AND close > 0 AND volume > 0
        ORDER BY symbol, trade_date
        """,
        conn,
        params={"history_start": history_start, "end_date": end_date, "symbols": symbols},
    )


def _compute_vcp_metrics(eod: pd.DataFrame) -> pd.DataFrame:
    if eod.empty:
        return pd.DataFrame(columns=["snapshot_date", "symbol", "vcp_breakout_pct", "vcp_contraction_pct", "volume_ratio_20d"])
    frame = eod.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.date
    for col in ("open", "high", "low", "close", "volume"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.sort_values(["symbol", "trade_date"])
    grouped = frame.groupby("symbol", group_keys=False)
    close = frame["close"].replace(0, pd.NA)
    range_10 = (grouped["high"].transform(lambda s: s.rolling(10, min_periods=8).max()) -
                grouped["low"].transform(lambda s: s.rolling(10, min_periods=8).min())) / close * 100
    range_40 = (grouped["high"].transform(lambda s: s.rolling(40, min_periods=25).max()) -
                grouped["low"].transform(lambda s: s.rolling(40, min_periods=25).min())) / close * 100
    prev_high_20 = grouped["high"].transform(lambda s: s.shift(1).rolling(20, min_periods=12).max())
    avg_vol_20 = grouped["volume"].transform(lambda s: s.rolling(20, min_periods=12).mean())
    frame["vcp_contraction_pct"] = ((range_40 - range_10) / range_40.replace(0, pd.NA) * 100).clip(lower=0, upper=100)
    frame["vcp_breakout_pct"] = ((frame["close"] - prev_high_20) / prev_high_20.replace(0, pd.NA) * 100).fillna(0)
    frame["volume_ratio_20d"] = (frame["volume"] / avg_vol_20.replace(0, pd.NA)).fillna(0)
    return frame.rename(columns={"trade_date": "snapshot_date"})[
        ["snapshot_date", "symbol", "vcp_breakout_pct", "vcp_contraction_pct", "volume_ratio_20d"]
    ]


def _score_candidates(stage: pd.DataFrame, metrics: pd.DataFrame) -> pd.DataFrame:
    if stage.empty:
        return pd.DataFrame()
    out = stage.copy()
    out["snapshot_date"] = pd.to_datetime(out["snapshot_date"]).dt.date
    out["symbol"] = out["symbol"].astype(str).str.upper().str.strip()
    if not metrics.empty:
        out = out.merge(metrics, on=["snapshot_date", "symbol"], how="left")
    else:
        out["vcp_breakout_pct"] = 0.0
        out["vcp_contraction_pct"] = 0.0
        out["volume_ratio_20d"] = 0.0
    for col in ("investment_score", "enhanced_fund_score", "rsi", "relative_strength", "vcp_breakout_pct", "vcp_contraction_pct", "volume_ratio_20d"):
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)

    rsi_fit = (100 - (out["rsi"] - 60).abs() * 3).clip(lower=0, upper=100)
    breakout_fit = (out["vcp_breakout_pct"].clip(lower=0, upper=8) / 8 * 100)
    volume_fit = (out["volume_ratio_20d"].clip(lower=0, upper=2.5) / 2.5 * 100)
    inv_fit = out["investment_score"].clip(lower=0, upper=100)
    rs_fit = out["relative_strength"].clip(lower=0, upper=100)
    contraction_fit = out["vcp_contraction_pct"].clip(lower=0, upper=100)
    out["vcp_score"] = (
        20.0
        + contraction_fit * 0.42
        + breakout_fit * 0.12
        + volume_fit * 0.12
        + rsi_fit * 0.14
        + inv_fit * 0.10
        + rs_fit * 0.10
    ).clip(upper=100).round(2)

    # Keep a broad audit trail, but require some evidence of contraction or
    # breakout so the table does not become a duplicate Stage 2 table.
    out = out[(out["vcp_score"] >= 50) & ((out["vcp_contraction_pct"] >= 10) | (out["vcp_breakout_pct"] >= 0.5))]
    if out.empty:
        return out
    out = out.sort_values(["snapshot_date", "vcp_score", "investment_score"], ascending=[True, False, False])
    out["rank"] = out.groupby("snapshot_date").cumcount() + 1
    out = out[out["rank"] <= 40].copy()
    out["narrative"] = out.apply(_narrative, axis=1)
    return out


def _narrative(row: pd.Series) -> str:
    return (
        f"Stage 2 bullish VCP candidate: contraction {row['vcp_contraction_pct']:.1f}%, "
        f"breakout {row['vcp_breakout_pct']:.1f}%, volume ratio {row['volume_ratio_20d']:.2f}x, "
        f"RS {row['relative_strength']:.1f}, RSI {row['rsi']:.1f}."
    )


def _jsonable(value: Any) -> Any:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return value
    return value


def _upsert(conn, picks: pd.DataFrame, start_date: date, end_date: date) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM scores.stage2_vcp_picks WHERE snapshot_date BETWEEN %s AND %s",
            (start_date, end_date),
        )
        if picks.empty:
            conn.commit()
            return 0
        rows = []
        for row in picks.itertuples(index=False):
            rows.append(
                (
                    row.snapshot_date,
                    row.symbol,
                    int(row.rank),
                    getattr(row, "company_name", None),
                    getattr(row, "sector", None),
                    getattr(row, "price", None),
                    getattr(row, "investment_score", None),
                    getattr(row, "enhanced_fund_score", None),
                    getattr(row, "vcp_score", None),
                    getattr(row, "vcp_breakout_pct", None),
                    getattr(row, "vcp_contraction_pct", None),
                    getattr(row, "rsi", None),
                    getattr(row, "relative_strength", None),
                    getattr(row, "trading_signal", None),
                    getattr(row, "trend_signal", None),
                    getattr(row, "supertrend_state", None),
                    getattr(row, "narrative", None),
                    Json(_jsonable(getattr(row, "fund_details", None))),
                )
            )
        execute_values(
            cur,
            """
            INSERT INTO scores.stage2_vcp_picks (
                snapshot_date, symbol, rank, company_name, sector, price,
                investment_score, enhanced_fund_score, vcp_score,
                vcp_breakout_pct, vcp_contraction_pct, rsi, relative_strength,
                trading_signal, trend_signal, supertrend_state, narrative, fund_details
            )
            VALUES %s
            ON CONFLICT (snapshot_date, symbol) DO UPDATE SET
                rank = EXCLUDED.rank,
                company_name = EXCLUDED.company_name,
                sector = EXCLUDED.sector,
                price = EXCLUDED.price,
                investment_score = EXCLUDED.investment_score,
                enhanced_fund_score = EXCLUDED.enhanced_fund_score,
                vcp_score = EXCLUDED.vcp_score,
                vcp_breakout_pct = EXCLUDED.vcp_breakout_pct,
                vcp_contraction_pct = EXCLUDED.vcp_contraction_pct,
                rsi = EXCLUDED.rsi,
                relative_strength = EXCLUDED.relative_strength,
                trading_signal = EXCLUDED.trading_signal,
                trend_signal = EXCLUDED.trend_signal,
                supertrend_state = EXCLUDED.supertrend_state,
                narrative = EXCLUDED.narrative,
                fund_details = EXCLUDED.fund_details,
                updated_at = now()
            """,
            rows,
            page_size=1000,
        )
    conn.commit()
    return len(rows)


def materialize(start: date | None, end: date | None, lookback_days: int) -> int:
    with _connect() as conn:
        _ensure_table(conn)
        start_date, end_date = _resolve_dates(conn, start, end, lookback_days)
        stage = _load_stage_candidates(conn, start_date, end_date)
        symbols = sorted(stage["symbol"].astype(str).str.upper().str.strip().unique().tolist()) if not stage.empty else []
        eod = _load_eod(conn, symbols, start_date, end_date)
        metrics = _compute_vcp_metrics(eod)
        picks = _score_candidates(stage, metrics)
        count = _upsert(conn, picks, start_date, end_date)
        latest_count = int((picks["snapshot_date"] == end_date).sum()) if not picks.empty else 0
        print(f"Materialized {count} VCP pick rows for {start_date} → {end_date}; latest date rows: {latest_count}")
        if latest_count:
            latest = picks[picks["snapshot_date"] == end_date].sort_values("rank").head(10)
            print("Latest:", ", ".join(f"{r.symbol}({r.vcp_score:.1f})" for r in latest.itertuples()))
        return count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", help="First snapshot date YYYY-MM-DD")
    parser.add_argument("--end-date", help="Last snapshot date YYYY-MM-DD")
    parser.add_argument("--lookback-days", type=int, default=365, help="Default range when --start-date is omitted")
    args = parser.parse_args()
    materialize(_date_arg(args.start_date), _date_arg(args.end_date), args.lookback_days)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
