#!/usr/bin/env python3
"""
backfill_screener_fundamentals.py
=================================
Backfill scores.fundamental_snapshots / scores.fundamentals /
scores.fundamental_section_snapshots for the NIFTY 500 universe by
calling screener.in directly via terminal.web_research.scrape_screener_in.

Why this exists:
  Only ~10% of the equity universe has fundamentals pre-loaded in PG, so
  /analyze and related commands fall back to live screener.in scrapes
  for most symbols. This script seeds the cache for the NIFTY 500 list
  with polite delays between requests.

Usage:
  python -m scripts.backfill_screener_fundamentals          # all NIFTY 500
  python -m scripts.backfill_screener_fundamentals --index "NIFTY 500"
  python -m scripts.backfill_screener_fundamentals --symbols SCHAEFFLER,DMART
  python -m scripts.backfill_screener_fundamentals --limit 50 --delay 3.0
  python -m scripts.backfill_screener_fundamentals --skip-fresh-days 7
  python -m scripts.backfill_screener_fundamentals --resume

Defaults:
  --delay              2.5s between scrapes (with ±0.5s jitter)
  --backoff-on-error   30s after an exception, then continue
  --skip-fresh-days    1  (skip symbols already loaded today)
  --batch-commit       10 symbols
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import signal
import sys
import time
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parent.parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from postgres.loader import pg, upsert  # noqa: E402
from terminal.financials_cache import upsert_screener_payload  # noqa: E402
from terminal.web_research import scrape_screener_in  # noqa: E402

INDEX_CSV = BASE / "data" / "index_stock_mapping.csv"


# ---------------------------------------------------------------------------
# Symbol loading
# ---------------------------------------------------------------------------

def load_symbols_for_index(index_name: str) -> list[str]:
    if not INDEX_CSV.exists():
        raise SystemExit(f"index mapping CSV not found: {INDEX_CSV}")
    out: list[str] = []
    with INDEX_CSV.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (row.get("INDEX_NAME") or "").strip().upper() == index_name.upper():
                sym = (row.get("STOCK_SYMBOL") or "").strip().upper()
                if sym:
                    out.append(sym)
    seen, dedup = set(), []
    for s in out:
        if s not in seen:
            seen.add(s)
            dedup.append(s)
    return dedup


# ---------------------------------------------------------------------------
# Payload → summary string transforms
# ---------------------------------------------------------------------------

def _norm_key(k: str) -> str:
    return str(k).strip().rstrip("+").strip()


def _row_no_label(values: list, key: str) -> list:
    """Drop label-leak first cell (annual rows include label as cell[0])."""
    if values and isinstance(values[0], str) and values[0].strip().rstrip("+").strip().lower() == _norm_key(key).lower():
        return list(values[1:])
    return list(values)


def _pick_row(table: dict, *labels: str) -> tuple[str | None, list]:
    if not isinstance(table, dict):
        return None, []
    wanted = {l.strip().lower() for l in labels}
    for k, v in table.items():
        if str(k).startswith("_") or not isinstance(v, list):
            continue
        if _norm_key(k).lower() in wanted:
            return _norm_key(k), _row_no_label(v, str(k))
    return None, []


def _pct_change(a: str, b: str) -> str | None:
    try:
        af = float(str(a).replace(",", "").replace("%", ""))
        bf = float(str(b).replace(",", "").replace("%", ""))
        if af == 0:
            return None
        return f"{(bf - af) / abs(af) * 100:+.1f}%"
    except Exception:
        return None


def build_pnl_summary(payload: dict) -> str | None:
    annual = payload.get("annual_pl") or {}
    if not isinstance(annual, dict) or "_headers" not in annual:
        return None
    _, sales = _pick_row(annual, "Sales", "Revenue")
    _, net   = _pick_row(annual, "Net Profit", "Profit after tax")
    _, eps   = _pick_row(annual, "EPS in Rs", "EPS")
    parts: list[str] = []
    if sales and len(sales) >= 2:
        chg = _pct_change(sales[-2], sales[-1])
        parts.append(f"Sales: {sales[-1]} Cr" + (f" (YoY {chg})" if chg else ""))
    if net and len(net) >= 2:
        chg = _pct_change(net[-2], net[-1])
        parts.append(f"NetProfit: {net[-1]} Cr" + (f" (YoY {chg})" if chg else ""))
    if eps:
        parts.append(f"EPS: {eps[-1]}")
    return "; ".join(parts) if parts else None


def build_quarterly_summary(payload: dict) -> str | None:
    q = payload.get("quarterly") or {}
    if not isinstance(q, dict) or "_headers" not in q:
        return None
    _, sales = _pick_row(q, "Sales", "Revenue")
    _, net   = _pick_row(q, "Net Profit", "Profit after tax")
    parts: list[str] = []
    if sales:
        last3 = sales[-3:]
        parts.append(f"Sales last 3Q: {', '.join(str(x) for x in last3)} Cr")
    if net:
        last3 = net[-3:]
        parts.append(f"Net Profit last 3Q: {', '.join(str(x) for x in last3)} Cr")
    return "; ".join(parts) if parts else None


def build_ratios_summary(payload: dict) -> str | None:
    ratios = payload.get("ratios") or {}
    if not isinstance(ratios, dict) or not ratios:
        return None
    norm = {_norm_key(k).lower(): v for k, v in ratios.items()}
    parts: list[str] = []
    for label, keys in (
        ("P/E", ("stock p/e", "p/e")),
        ("ROCE", ("roce",)),
        ("ROE", ("roe", "return on equity")),
        ("Div Yield", ("dividend yield",)),
        ("Book Value", ("book value",)),
        ("Mkt Cap", ("market cap",)),
    ):
        for k in keys:
            v = norm.get(k)
            if v not in (None, "", "—"):
                parts.append(f"{label}: {v}")
                break
    return "; ".join(parts) if parts else None


def build_investor_summary(payload: dict) -> str | None:
    shp = payload.get("shareholding") or {}
    if not isinstance(shp, dict) or not shp:
        return None
    bits: list[str] = []
    for label, keys in (
        ("Promoters", ("Promoters", "Promoter")),
        ("FII", ("FIIs", "FII")),
        ("DII", ("DIIs", "DII")),
        ("Govt", ("Government",)),
        ("Public", ("Public",)),
    ):
        for k in keys:
            v = shp.get(k)
            if v not in (None, ""):
                bits.append(f"{label} {v}")
                break
    return " | ".join(bits) if bits else None


def build_balance_sheet_summary(payload: dict) -> str | None:
    # Screener page doesn't expose balance sheet from the consolidated landing
    # request. Leave None so existing pipeline rows aren't overwritten with stub.
    return None


def build_cash_flow_summary(payload: dict) -> str | None:
    return None


# ---------------------------------------------------------------------------
# Backfill driver
# ---------------------------------------------------------------------------

class BackfillStats:
    def __init__(self):
        self.attempted = 0
        self.scraped = 0
        self.upserted = 0
        self.skipped_fresh = 0
        self.empty = 0
        self.errors = 0
        self.structured_rows = 0
        self.error_symbols: list[tuple[str, str]] = []


def fresh_symbols(cur, days: int) -> set[str]:
    cur.execute(
        "SELECT symbol FROM scores.fundamental_snapshots "
        "WHERE snapshot_date >= %s",
        (date.today() - timedelta(days=days),),
    )
    return {r[0].upper() for r in cur.fetchall()}


def upsert_symbol(cur, sym: str, payload: dict, source_tag: str) -> tuple[int, int]:
    if payload.get("error"):
        return (0, 0)
    snap_date = date.today()
    row = {
        "snapshot_date": snap_date,
        "symbol": sym,
        "pnl_summary": build_pnl_summary(payload),
        "quarterly_summary": build_quarterly_summary(payload),
        "balance_sheet_summary": build_balance_sheet_summary(payload),
        "cash_flow_summary": build_cash_flow_summary(payload),
        "investor_summary": build_investor_summary(payload),
        "ratios_summary": build_ratios_summary(payload),
        "source_file": source_tag,
    }
    if not any(row[c] for c in (
        "pnl_summary", "quarterly_summary", "balance_sheet_summary",
        "cash_flow_summary", "investor_summary", "ratios_summary",
    )):
        return (0, 0)
    upsert(
        cur, "scores.fundamental_snapshots", [row],
        ["snapshot_date", "symbol"],
        ["pnl_summary", "quarterly_summary", "balance_sheet_summary",
         "cash_flow_summary", "investor_summary", "ratios_summary",
         "source_file", "loaded_at"],
    )
    latest = {
        "symbol": sym,
        "pnl_summary": row["pnl_summary"],
        "quarterly_summary": row["quarterly_summary"],
        "balance_sheet_summary": row["balance_sheet_summary"],
        "cash_flow_summary": row["cash_flow_summary"],
        "investor_summary": row["investor_summary"],
        "ratios_summary": row["ratios_summary"],
        "updated_at": datetime.now(),
    }
    upsert(
        cur, "scores.fundamentals", [latest],
        ["symbol"],
        ["pnl_summary", "quarterly_summary", "balance_sheet_summary",
         "cash_flow_summary", "investor_summary", "ratios_summary", "updated_at"],
    )
    cur.execute("SELECT to_regclass('scores.fundamental_section_snapshots')")
    if cur.fetchone()[0] is not None:
        section_map = {
            "pnl": "pnl_summary",
            "quarterly": "quarterly_summary",
            "balance_sheet": "balance_sheet_summary",
            "cash_flow": "cash_flow_summary",
            "investor": "investor_summary",
            "ratios": "ratios_summary",
        }
        section_rows = []
        for section_name, col in section_map.items():
            v = row.get(col)
            if not v:
                continue
            section_rows.append({
                "snapshot_date": snap_date,
                "symbol": sym,
                "section_name": section_name,
                "section_summary": v,
                "source_file": source_tag,
                "loaded_at": datetime.now(),
            })
        if section_rows:
            upsert(
                cur, "scores.fundamental_section_snapshots", section_rows,
                ["snapshot_date", "symbol", "section_name"],
                ["section_summary", "source_file", "loaded_at"],
            )
    structured_n = 0
    try:
        counts = upsert_screener_payload(sym, payload, conn=cur.connection)
        structured_n = sum(counts.values())
    except Exception as e:
        print(f"        [structured-cache] {sym} WARN {e}")
    return (1, structured_n)


_STOP = False
def _handle_signal(signum, frame):  # noqa: ARG001
    global _STOP
    _STOP = True
    print("\n[backfill] stop requested — finishing current symbol and flushing…")


def run(args) -> int:
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    else:
        symbols = load_symbols_for_index(args.index)
    if args.limit:
        symbols = symbols[: args.limit]
    if not symbols:
        print("[backfill] no symbols selected")
        return 1

    print(f"[backfill] index={args.index!r}  total={len(symbols)}  "
          f"delay={args.delay}s±{args.jitter}s  skip_fresh_days={args.skip_fresh_days}")

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    stats = BackfillStats()
    source_tag = f"screener_backfill:{args.index.lower().replace(' ', '_')}"

    conn = pg()
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            fresh = fresh_symbols(cur, args.skip_fresh_days) if args.skip_fresh_days > 0 else set()

        pending = [s for s in symbols if s not in fresh]
        stats.skipped_fresh = len(symbols) - len(pending)
        print(f"[backfill] pending={len(pending)}  skipped_fresh={stats.skipped_fresh}")

        batch_since_commit = 0
        cur = conn.cursor()
        for i, sym in enumerate(pending, 1):
            if _STOP:
                break
            stats.attempted += 1
            t0 = time.time()
            try:
                payload = scrape_screener_in(sym)
            except Exception as e:
                stats.errors += 1
                stats.error_symbols.append((sym, f"exception: {e}"))
                print(f"[{i}/{len(pending)}] {sym:<14} ERROR {e}")
                time.sleep(args.backoff_on_error)
                continue

            if payload.get("error"):
                stats.errors += 1
                stats.error_symbols.append((sym, payload["error"][:120]))
                print(f"[{i}/{len(pending)}] {sym:<14} ERROR {payload['error'][:80]}")
            else:
                stats.scraped += 1
                try:
                    n, structured_n = upsert_symbol(cur, sym, payload, source_tag)
                    if n:
                        stats.upserted += 1
                        stats.structured_rows += structured_n
                        elapsed = time.time() - t0
                        bits = []
                        if build_pnl_summary(payload): bits.append("pnl")
                        if build_quarterly_summary(payload): bits.append("q")
                        if build_ratios_summary(payload): bits.append("ratios")
                        if build_investor_summary(payload): bits.append("shp")
                        if structured_n: bits.append(f"struct={structured_n}")
                        print(f"[{i}/{len(pending)}] {sym:<14} ok  ({','.join(bits)})  {elapsed:.1f}s")
                    else:
                        stats.empty += 1
                        print(f"[{i}/{len(pending)}] {sym:<14} EMPTY  (no sections extractable)")
                except Exception as e:
                    stats.errors += 1
                    stats.error_symbols.append((sym, f"upsert: {e}"))
                    print(f"[{i}/{len(pending)}] {sym:<14} UPSERT-ERR {e}")
                    traceback.print_exc()
                    conn.rollback()
                    cur = conn.cursor()
                    continue

            batch_since_commit += 1
            if batch_since_commit >= args.batch_commit:
                conn.commit()
                batch_since_commit = 0

            if i < len(pending):
                jitter = random.uniform(-args.jitter, args.jitter)
                time.sleep(max(0.2, args.delay + jitter))

        conn.commit()
    finally:
        conn.close()

    print(
        f"\n[backfill] done  attempted={stats.attempted}  scraped={stats.scraped}  "
        f"upserted={stats.upserted}  structured_rows={stats.structured_rows}  "
        f"empty={stats.empty}  errors={stats.errors}  "
        f"skipped_fresh={stats.skipped_fresh}"
    )
    if stats.error_symbols:
        log_path = BASE / "reports" / f"backfill_screener_errors_{date.today().isoformat()}.json"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(json.dumps(stats.error_symbols, indent=2))
        print(f"[backfill] error detail: {log_path}")
    return 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--index", default="NIFTY 500", help="Index label in data/index_stock_mapping.csv")
    p.add_argument("--symbols", default=None, help="Comma-separated symbol list (overrides --index)")
    p.add_argument("--limit", type=int, default=0, help="Cap number of symbols (0=all)")
    p.add_argument("--delay", type=float, default=2.5, help="Base delay between scrapes (seconds)")
    p.add_argument("--jitter", type=float, default=0.5, help="Random jitter ± seconds")
    p.add_argument("--backoff-on-error", type=float, default=30.0,
                   help="Pause this many seconds after an exception")
    p.add_argument("--skip-fresh-days", type=int, default=1,
                   help="Skip symbols already snapshotted within N days (0 = no skip)")
    p.add_argument("--batch-commit", type=int, default=10, help="Commit every N successful upserts")
    args = p.parse_args()
    sys.exit(run(args))


if __name__ == "__main__":
    main()
