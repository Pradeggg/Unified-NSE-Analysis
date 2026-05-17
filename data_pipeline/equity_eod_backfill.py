"""Equity EOD backfill primitives shared by CLI and scripts.

Functions for fetching daily OHLCV via yfinance and upserting into
PostgreSQL ``market.equity_eod``. Used by:

- ``scripts/backfill_equity_eod_yfinance.py`` (CLI script)
- ``terminal/data_coverage.py`` (``/data-coverage`` slash-command)
"""

from __future__ import annotations

import contextlib
import io
import os
from dataclasses import dataclass
from typing import Iterable

import pandas as pd


DEFAULT_DSN = "dbname=nse_market user=nse_admin host=/tmp"
UPSERT_SQL = """
INSERT INTO market.equity_eod
    (trade_date, symbol, series, open, high, low, close, volume)
VALUES %s
ON CONFLICT (trade_date, symbol, series) DO NOTHING
"""


def pg_dsn() -> str:
    return (
        os.environ.get("AGENT_ADDA_PG_DSN")
        or os.environ.get("PG_DSN")
        or DEFAULT_DSN
    )


def _quiet_yf_download(yf, ticker: str, **kwargs) -> pd.DataFrame:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        return yf.download(ticker, **kwargs)


def fetch_history(symbol: str, period: str = "5y") -> pd.DataFrame:
    """Fetch daily OHLCV history for ``symbol`` via yfinance (.NS suffix)."""
    try:
        import yfinance as yf
    except Exception as exc:  # pragma: no cover - hard dep check
        raise RuntimeError(f"yfinance unavailable: {exc}")
    try:
        raw = _quiet_yf_download(
            yf,
            f"{symbol}.NS",
            period=period,
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=False,
        )
    except Exception:
        return pd.DataFrame()
    if raw is None or raw.empty:
        return pd.DataFrame()
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = [str(col[0]) for col in raw.columns]
    df = raw.reset_index().rename(
        columns={
            "Date": "trade_date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    )
    keep = ["trade_date", "open", "high", "low", "close", "volume"]
    df = df[[c for c in keep if c in df.columns]].copy()
    df = df.dropna(subset=["close"])
    df["symbol"] = symbol.upper()
    df["series"] = "EQ"
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    return df


def upsert_rows(conn, df: pd.DataFrame) -> int:
    """Idempotent upsert of OHLCV rows; returns number of rows sent."""
    if df.empty:
        return 0
    from psycopg2.extras import execute_values

    rows = [
        (
            r["trade_date"],
            r["symbol"],
            r["series"],
            None if pd.isna(r.get("open")) else float(r["open"]),
            None if pd.isna(r.get("high")) else float(r["high"]),
            None if pd.isna(r.get("low")) else float(r["low"]),
            float(r["close"]),
            None if pd.isna(r.get("volume")) else int(r["volume"]),
        )
        for _, r in df.iterrows()
    ]
    with conn.cursor() as cur:
        execute_values(cur, UPSERT_SQL, rows, page_size=500)
    return len(rows)


@dataclass(frozen=True)
class SymbolCoverage:
    symbol: str
    first_date: object  # date | None
    last_date: object  # date | None
    bar_count: int

    @property
    def covered(self) -> bool:
        return self.bar_count > 0


def coverage_for_symbols(conn, symbols: Iterable[str]) -> list[SymbolCoverage]:
    """Return per-symbol coverage rows (zero-fills missing symbols)."""
    sym_list = [s.strip().upper() for s in symbols if s and s.strip()]
    if not sym_list:
        return []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT symbol, MIN(trade_date), MAX(trade_date), COUNT(*)
            FROM market.equity_eod
            WHERE symbol = ANY(%s)
            GROUP BY symbol
            """,
            (sym_list,),
        )
        seen = {row[0]: row for row in cur.fetchall()}
    out: list[SymbolCoverage] = []
    for sym in sym_list:
        if sym in seen:
            _, first_d, last_d, n = seen[sym]
            out.append(SymbolCoverage(sym, first_d, last_d, int(n or 0)))
        else:
            out.append(SymbolCoverage(sym, None, None, 0))
    return out
