"""PostgreSQL persistence for intraday market data.

This module keeps intraday data in its own PostgreSQL schema so live quote
snapshots, intraday candles, and future scanner outputs do not get mixed with
EOD market tables.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import psycopg2
from psycopg2.extras import Json, execute_values


PG_DSN = os.environ.get("AGENT_ADDA_PG_DSN") or os.environ.get("PG_DSN") or "dbname=nse_market user=nse_admin host=/tmp"


SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS intraday;

CREATE TABLE IF NOT EXISTS intraday.quote_snapshots (
    symbol          TEXT NOT NULL,
    source          TEXT NOT NULL,
    as_of           TIMESTAMPTZ NOT NULL,
    captured_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    name            TEXT,
    last_price      NUMERIC(18,6),
    change          NUMERIC(18,6),
    pct_change      NUMERIC(18,6),
    day_high        NUMERIC(18,6),
    day_low         NUMERIC(18,6),
    vwap            NUMERIC(18,6),
    volume          BIGINT,
    source_priority TEXT[],
    raw_json        JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (symbol, source, as_of)
);

CREATE TABLE IF NOT EXISTS intraday.ohlcv_bars (
    symbol       TEXT NOT NULL,
    timeframe    TEXT NOT NULL,
    timestamp    TIMESTAMPTZ NOT NULL,
    source       TEXT NOT NULL,
    open         NUMERIC(18,6),
    high         NUMERIC(18,6),
    low          NUMERIC(18,6),
    close        NUMERIC(18,6),
    volume       BIGINT,
    captured_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw_json     JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (symbol, timeframe, timestamp, source)
);

CREATE TABLE IF NOT EXISTS intraday.scan_signals (
    snapshot_ts              TIMESTAMPTZ NOT NULL,
    scan_key                 TEXT NOT NULL,
    symbol                   TEXT NOT NULL,
    strategy                 TEXT NOT NULL,
    direction                TEXT NOT NULL,
    timeframe                TEXT,
    entry                    NUMERIC(18,6),
    stop                     NUMERIC(18,6),
    target                   NUMERIC(18,6),
    rr                       NUMERIC(18,6),
    technical_score          NUMERIC(18,6),
    trend_score              NUMERIC(18,6),
    momentum_score           NUMERIC(18,6),
    volume_score             NUMERIC(18,6),
    support_resistance_score NUMERIC(18,6),
    volatility_score         NUMERIC(18,6),
    raw_json                 JSONB NOT NULL DEFAULT '{}'::jsonb,
    captured_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (snapshot_ts, scan_key, symbol, strategy, direction)
);

CREATE INDEX IF NOT EXISTS idx_intraday_quote_symbol_time
    ON intraday.quote_snapshots (symbol, as_of DESC);
CREATE INDEX IF NOT EXISTS idx_intraday_ohlcv_symbol_timeframe_time
    ON intraday.ohlcv_bars (symbol, timeframe, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_intraday_scan_symbol_time
    ON intraday.scan_signals (symbol, snapshot_ts DESC);
"""


def connect(dsn: str | None = None):
    return psycopg2.connect(dsn or PG_DSN)


def ensure_intraday_schema(conn, *, commit: bool = True) -> None:
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)
    if commit:
        conn.commit()


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        text = str(value).replace(",", "").strip()
        if not text or text.lower() in {"na", "nan", "none", "null"}:
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        text = str(value).replace(",", "").strip()
        if not text or text.lower() in {"na", "nan", "none", "null"}:
            return None
        return int(float(text))
    except (TypeError, ValueError):
        return None


def _parse_timestamp(value: Any) -> datetime:
    ist = timezone(timedelta(hours=5, minutes=30))
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=ist)
    if not value:
        return datetime.now(timezone.utc)
    text = str(value).strip()
    formats = (
        "%d-%b-%Y %H:%M:%S",
        "%d-%b-%Y %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
    )
    for fmt in formats:
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=ist)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=ist)
    except ValueError:
        return datetime.now(timezone.utc)


def persist_intraday_snapshot(
    snapshot: dict[str, Any],
    *,
    conn=None,
    dsn: str | None = None,
) -> dict[str, Any]:
    """Persist one NSE live quote/index snapshot into intraday.quote_snapshots."""
    if not snapshot or snapshot.get("error"):
        return {"ok": False, "rows_inserted": 0, "reason": snapshot.get("error") if snapshot else "empty_snapshot"}

    symbol = str(snapshot.get("symbol") or "").strip().upper()
    if not symbol:
        return {"ok": False, "rows_inserted": 0, "reason": "missing_symbol"}

    row = {
        "symbol": symbol,
        "source": str(snapshot.get("source") or "unknown").strip() or "unknown",
        "as_of": _parse_timestamp(snapshot.get("as_of")),
        "name": snapshot.get("name"),
        "last_price": _safe_float(snapshot.get("last_price")),
        "change": _safe_float(snapshot.get("change")),
        "pct_change": _safe_float(snapshot.get("pct_change")),
        "day_high": _safe_float(snapshot.get("day_high")),
        "day_low": _safe_float(snapshot.get("day_low")),
        "vwap": _safe_float(snapshot.get("vwap")),
        "volume": _safe_int(snapshot.get("volume") or snapshot.get("total_traded_volume")),
        "source_priority": list(snapshot.get("source_priority") or []),
        "raw_json": Json(_jsonable(snapshot)),
    }

    cols = list(row.keys())
    values = [[row[col] for col in cols]]
    sql = (
        f"INSERT INTO intraday.quote_snapshots ({', '.join(cols)}) VALUES %s "
        "ON CONFLICT (symbol, source, as_of) DO UPDATE SET "
        "captured_at = now(), "
        "name = EXCLUDED.name, "
        "last_price = EXCLUDED.last_price, "
        "change = EXCLUDED.change, "
        "pct_change = EXCLUDED.pct_change, "
        "day_high = EXCLUDED.day_high, "
        "day_low = EXCLUDED.day_low, "
        "vwap = EXCLUDED.vwap, "
        "volume = EXCLUDED.volume, "
        "source_priority = EXCLUDED.source_priority, "
        "raw_json = EXCLUDED.raw_json"
    )

    own_conn = conn is None
    db = conn or connect(dsn)
    try:
        ensure_intraday_schema(db, commit=False)
        with db.cursor() as cur:
            execute_values(cur, sql, values, page_size=100)
        db.commit()
        return {"ok": True, "rows_inserted": 1, "schema": "intraday", "table": "quote_snapshots"}
    except Exception:
        db.rollback()
        raise
    finally:
        if own_conn:
            db.close()


def persist_intraday_bars(
    symbol: str,
    bars: list[dict[str, Any]],
    *,
    timeframe: str = "15m",
    source: str = "unknown",
    conn=None,
    dsn: str | None = None,
) -> dict[str, Any]:
    """Persist OHLCV bars into intraday.ohlcv_bars."""
    sym = str(symbol or "").strip().upper()
    if not sym or not bars:
        return {"ok": False, "rows_inserted": 0, "reason": "missing_symbol_or_bars"}

    rows = []
    for bar in bars:
        ts = bar.get("timestamp") or bar.get("Datetime") or bar.get("date")
        if not ts:
            continue
        rows.append(
            {
                "symbol": sym,
                "timeframe": timeframe,
                "timestamp": _parse_timestamp(ts),
                "source": source,
                "open": _safe_float(bar.get("open")),
                "high": _safe_float(bar.get("high")),
                "low": _safe_float(bar.get("low")),
                "close": _safe_float(bar.get("close")),
                "volume": _safe_int(bar.get("volume")),
                "raw_json": Json(_jsonable(bar)),
            }
        )

    if not rows:
        return {"ok": False, "rows_inserted": 0, "reason": "no_valid_bars"}

    cols = list(rows[0].keys())
    values = [[row[col] for col in cols] for row in rows]
    sql = (
        f"INSERT INTO intraday.ohlcv_bars ({', '.join(cols)}) VALUES %s "
        "ON CONFLICT (symbol, timeframe, timestamp, source) DO UPDATE SET "
        "open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low, "
        "close = EXCLUDED.close, volume = EXCLUDED.volume, "
        "captured_at = now(), raw_json = EXCLUDED.raw_json"
    )

    own_conn = conn is None
    db = conn or connect(dsn)
    try:
        ensure_intraday_schema(db, commit=False)
        with db.cursor() as cur:
            execute_values(cur, sql, values, page_size=500)
        db.commit()
        return {"ok": True, "rows_inserted": len(rows), "schema": "intraday", "table": "ohlcv_bars"}
    except Exception:
        db.rollback()
        raise
    finally:
        if own_conn:
            db.close()


def persist_intraday_scan_result(
    scan_result: dict[str, Any],
    *,
    conn=None,
    dsn: str | None = None,
) -> dict[str, Any]:
    """Persist scanner buy/sell/watch signals into intraday.scan_signals."""
    if not scan_result:
        return {"ok": False, "rows_inserted": 0, "reason": "empty_scan_result"}

    snapshot_ts = _parse_timestamp(scan_result.get("as_of"))
    timeframe = scan_result.get("interval") or scan_result.get("timeframe")
    strategies = scan_result.get("strategies") or []
    scan_key = ",".join(str(item) for item in strategies) if strategies else str(scan_result.get("screen_type") or "intraday_scan")

    rows: list[dict[str, Any]] = []
    buckets = (
        ("buy_signals", "BUY"),
        ("sell_signals", "SELL"),
        ("watch_alerts", "WATCH"),
    )
    for bucket, default_direction in buckets:
        for signal in scan_result.get(bucket) or []:
            symbol = str(signal.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            strategy = str(signal.get("strategy") or signal.get("strategy_key") or bucket).strip() or bucket
            direction = str(signal.get("direction") or default_direction).strip().upper() or default_direction
            rows.append(
                {
                    "snapshot_ts": snapshot_ts,
                    "scan_key": scan_key,
                    "symbol": symbol,
                    "strategy": strategy,
                    "direction": direction,
                    "timeframe": timeframe,
                    "entry": _safe_float(signal.get("entry")),
                    "stop": _safe_float(signal.get("stop")),
                    "target": _safe_float(signal.get("target")),
                    "rr": _safe_float(signal.get("rr")),
                    "technical_score": _safe_float(signal.get("technical_score")),
                    "trend_score": _safe_float(signal.get("trend_score")),
                    "momentum_score": _safe_float(signal.get("momentum_score")),
                    "volume_score": _safe_float(signal.get("volume_score")),
                    "support_resistance_score": _safe_float(signal.get("support_resistance_score")),
                    "volatility_score": _safe_float(signal.get("volatility_score")),
                    "raw_json": Json(_jsonable(signal)),
                }
            )

    if not rows:
        return {"ok": False, "rows_inserted": 0, "reason": "no_signals"}

    cols = list(rows[0].keys())
    values = [[row[col] for col in cols] for row in rows]
    sql = (
        f"INSERT INTO intraday.scan_signals ({', '.join(cols)}) VALUES %s "
        "ON CONFLICT (snapshot_ts, scan_key, symbol, strategy, direction) DO UPDATE SET "
        "timeframe = EXCLUDED.timeframe, "
        "entry = EXCLUDED.entry, "
        "stop = EXCLUDED.stop, "
        "target = EXCLUDED.target, "
        "rr = EXCLUDED.rr, "
        "technical_score = EXCLUDED.technical_score, "
        "trend_score = EXCLUDED.trend_score, "
        "momentum_score = EXCLUDED.momentum_score, "
        "volume_score = EXCLUDED.volume_score, "
        "support_resistance_score = EXCLUDED.support_resistance_score, "
        "volatility_score = EXCLUDED.volatility_score, "
        "raw_json = EXCLUDED.raw_json, "
        "captured_at = now()"
    )

    own_conn = conn is None
    db = conn or connect(dsn)
    try:
        ensure_intraday_schema(db, commit=False)
        with db.cursor() as cur:
            execute_values(cur, sql, values, page_size=500)
        db.commit()
        return {"ok": True, "rows_inserted": len(rows), "schema": "intraday", "table": "scan_signals"}
    except Exception:
        db.rollback()
        raise
    finally:
        if own_conn:
            db.close()
