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

import psycopg2

from data_pipeline.equity_eod_backfill import (
    fetch_history,
    pg_dsn,
    upsert_rows,
)


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

    with closing(psycopg2.connect(pg_dsn())) as conn:
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
                    n = upsert_rows(conn, df)
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
