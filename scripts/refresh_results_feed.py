#!/usr/bin/env python3
"""
refresh_results_feed.py
========================
Daily-tail refresher: for every company that has filed quarterly results
in the last N days (as reported by the NSE `corporates-financial-results`
feed), re-scrape screener.in and refresh the structured financials cache
in PG.

This is the daily counterpart to ``backfill_screener_fundamentals.py``
(which sweeps a full index weekly). Where the backfill is a wide low-
frequency job, this script is a narrow high-frequency one — it only
touches the symbols that actually published numbers recently, so the
cache stays current with minimal scraping.

Run from cron or ``daily_refresh.py`` after market close.

Usage:
  python -m scripts.refresh_results_feed
  python -m scripts.refresh_results_feed --days-back 21 --limit 200
  python -m scripts.refresh_results_feed --delay 3.0
  python -m scripts.refresh_results_feed --skip-fresh-hours 6
"""

from __future__ import annotations

import argparse
import random
import sys
import time
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

import psycopg2  # noqa: E402

from terminal.financials_cache import (  # noqa: E402
    DEFAULT_DSN,
    log_refresh_run,
    upsert_screener_payload,
)
from terminal.tools import get_latest_results_feed  # noqa: E402
from terminal.web_research import scrape_screener_in  # noqa: E402


JOB_NAME = "refresh_results_feed"


def _fresh_symbols(cur, hours: float) -> set[str]:
    if hours <= 0:
        return set()
    cur.execute(
        "SELECT DISTINCT symbol FROM scores.quarterly_results "
        "WHERE fetched_at >= %s",
        (datetime.now() - timedelta(hours=hours),),
    )
    return {r[0].upper() for r in cur.fetchall()}


def _collect_symbols(days_back: int, limit: int) -> list[str]:
    feed = get_latest_results_feed(days_back=days_back, limit=limit)
    out: list[str] = []
    seen: set[str] = set()
    for row in feed.get("results") or []:
        sym = str((row or {}).get("symbol") or "").strip().upper()
        if sym and sym not in seen:
            seen.add(sym)
            out.append(sym)
    return out


def run(args) -> int:
    symbols = _collect_symbols(args.days_back, args.limit)
    if not symbols:
        print(f"[results-feed] no symbols in window (days_back={args.days_back})")
        log_refresh_run(
            JOB_NAME,
            symbols_attempted=0, symbols_loaded=0, rows_upserted=0,
            errors=0, notes=f"empty feed days_back={args.days_back}",
        )
        return 0

    print(f"[results-feed] window={args.days_back}d  candidates={len(symbols)}  "
          f"delay={args.delay}s±{args.jitter}s  skip_fresh_hours={args.skip_fresh_hours}")

    conn = psycopg2.connect(args.dsn)
    conn.autocommit = False
    attempted = loaded = total_rows = errors = 0
    error_log: list[tuple[str, str]] = []
    try:
        with conn.cursor() as cur:
            fresh = _fresh_symbols(cur, args.skip_fresh_hours)

        pending = [s for s in symbols if s not in fresh]
        skipped = len(symbols) - len(pending)
        print(f"[results-feed] pending={len(pending)}  skipped_fresh={skipped}")

        for i, sym in enumerate(pending, 1):
            attempted += 1
            t0 = time.time()
            try:
                payload = scrape_screener_in(sym)
            except Exception as exc:
                errors += 1
                error_log.append((sym, f"scrape: {exc}"))
                print(f"[{i}/{len(pending)}] {sym:<14} SCRAPE-ERR {exc}")
                time.sleep(args.backoff_on_error)
                continue

            if payload.get("error"):
                errors += 1
                error_log.append((sym, payload["error"][:120]))
                print(f"[{i}/{len(pending)}] {sym:<14} EMPTY {payload['error'][:60]}")
            else:
                try:
                    counts = upsert_screener_payload(sym, payload, conn=conn)
                    n = sum(counts.values())
                    if n:
                        loaded += 1
                        total_rows += n
                        print(f"[{i}/{len(pending)}] {sym:<14} ok  rows={n}  {time.time()-t0:.1f}s")
                    else:
                        print(f"[{i}/{len(pending)}] {sym:<14} no_struct  {time.time()-t0:.1f}s")
                    conn.commit()
                except Exception as exc:
                    errors += 1
                    error_log.append((sym, f"upsert: {exc}"))
                    conn.rollback()
                    print(f"[{i}/{len(pending)}] {sym:<14} UPSERT-ERR {exc}")
                    traceback.print_exc()

            if i < len(pending):
                jitter = random.uniform(-args.jitter, args.jitter)
                time.sleep(max(0.2, args.delay + jitter))
    finally:
        conn.close()

    notes = f"days_back={args.days_back};errors={len(error_log)}"
    if error_log:
        notes += ";first_err=" + ",".join(s for s, _ in error_log[:3])
    log_refresh_run(
        JOB_NAME,
        symbols_attempted=attempted,
        symbols_loaded=loaded,
        rows_upserted=total_rows,
        errors=errors,
        notes=notes,
    )

    print(
        f"\n[results-feed] done  attempted={attempted}  loaded={loaded}  "
        f"rows_upserted={total_rows}  errors={errors}"
    )
    return 0 if errors == 0 else 0  # non-fatal — partial loads still useful


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--days-back", type=int, default=14,
                   help="Calendar days of results-feed window (default 14)")
    p.add_argument("--limit", type=int, default=200,
                   help="Max symbols to consider from the feed (default 200)")
    p.add_argument("--delay", type=float, default=2.5,
                   help="Base delay between scrapes in seconds")
    p.add_argument("--jitter", type=float, default=0.5,
                   help="Random jitter ± seconds")
    p.add_argument("--backoff-on-error", type=float, default=30.0)
    p.add_argument("--skip-fresh-hours", type=float, default=6.0,
                   help="Skip symbols whose quarterly_results row is fresher than N hours")
    p.add_argument("--dsn", default=DEFAULT_DSN)
    args = p.parse_args()
    sys.exit(run(args))


if __name__ == "__main__":
    main()
