"""Backfill market.equity_eod via yfinance.

Pulls ~5 years of daily OHLCV per symbol from Yahoo Finance and upserts
into market.equity_eod. Existing rows are preserved (ON CONFLICT DO
NOTHING for primary key), so this only fills gaps.

Usage:
    python scripts/backfill_equity_eod_yfinance.py            # all symbols
    python scripts/backfill_equity_eod_yfinance.py --limit 50 # first 50
    python scripts/backfill_equity_eod_yfinance.py --symbols DMART,TATASTEEL
    python scripts/backfill_equity_eod_yfinance.py --min-bars 800
        # skip symbols that already have >= 800 rows
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from contextlib import closing
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values


DEFAULT_DSN = "dbname=nse_market user=nse_admin host=/tmp"
UPSERT_SQL = """
INSERT INTO market.equity_eod
    (trade_date, symbol, series, open, high, low, close, volume)
VALUES %s
ON CONFLICT (trade_date, symbol, series) DO NOTHING
"""


def _dsn() -> str:
    return os.environ.get("AGENT_ADDA_PG_DSN") or os.environ.get("PG_DSN") or DEFAULT_DSN


def _quiet_yf_download(yf, ticker: str, **kwargs) -> pd.DataFrame:
    import io
    import contextlib

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        return yf.download(ticker, **kwargs)


def fetch_history(symbol: str, period: str = "5y") -> pd.DataFrame:
    try:
        import yfinance as yf
    except Exception as exc:
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


def upsert(conn, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
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


def list_symbols(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT symbol FROM market.equity_eod ORDER BY symbol")
        return [r[0] for r in cur.fetchall()]


def existing_row_count(conn, symbol: str) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM market.equity_eod WHERE symbol = %s", (symbol,))
        return int(cur.fetchone()[0])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbols", help="Comma-separated symbols (overrides DB scan)")
    ap.add_argument("--limit", type=int, help="Process only first N symbols")
    ap.add_argument("--min-bars", type=int, default=0,
                    help="Skip symbols already having >= this many rows")
    ap.add_argument("--period", default="5y", help="yfinance period (e.g. 2y, 5y, 10y, max)")
    ap.add_argument("--sleep", type=float, default=0.2,
                    help="Seconds to sleep between symbols (rate-limit guard)")
    ap.add_argument("--dry-run", action="store_true", help="Fetch but don't upsert")
    args = ap.parse_args()

    with closing(psycopg2.connect(_dsn())) as conn:
        conn.autocommit = False
        if args.symbols:
            symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        else:
            symbols = list_symbols(conn)
        if args.limit:
            symbols = symbols[: args.limit]
        print(f"Processing {len(symbols)} symbols (period={args.period}, min_bars={args.min_bars})")

        total_inserted = 0
        skipped = 0
        empty = 0
        errors = 0
        t0 = time.time()
        for i, sym in enumerate(symbols, 1):
            try:
                if args.min_bars and existing_row_count(conn, sym) >= args.min_bars:
                    skipped += 1
                    continue
                df = fetch_history(sym, period=args.period)
                if df.empty:
                    empty += 1
                    print(f"  [{i:>5}/{len(symbols)}] {sym:<20} no data")
                    time.sleep(args.sleep)
                    continue
                if args.dry_run:
                    print(f"  [{i:>5}/{len(symbols)}] {sym:<20} fetched {len(df)} rows (dry-run)")
                else:
                    n = upsert(conn, df)
                    conn.commit()
                    total_inserted += n
                    print(f"  [{i:>5}/{len(symbols)}] {sym:<20} upserted {n} rows")
            except KeyboardInterrupt:
                conn.rollback()
                print("Interrupted.")
                break
            except Exception as exc:
                conn.rollback()
                errors += 1
                print(f"  [{i:>5}/{len(symbols)}] {sym:<20} ERROR: {type(exc).__name__}: {exc}")
            time.sleep(args.sleep)

        dt = time.time() - t0
        print(
            f"\nDone in {dt:.1f}s. inserted_rows={total_inserted} "
            f"skipped={skipped} empty={empty} errors={errors}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
