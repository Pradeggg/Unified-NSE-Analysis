#!/usr/bin/env python3
"""
Fetch fundamental data from screener.in for NSE stocks.

Scrapes P&L, Quarterly Results, Balance Sheet, and Financial Ratios
for each symbol and writes to data/_sector_rotation_fund_cache.csv
and updates the sector_rotation_tracker.db.

Usage:
  python fetch_screener_fundamentals.py               # Stage 2 missing only
  python fetch_screener_fundamentals.py --all         # All 918 stocks
  python fetch_screener_fundamentals.py --symbols RELIANCE,TCS,INFY
  python fetch_screener_fundamentals.py --stage2      # Stage 2 missing (default)
  python fetch_screener_fundamentals.py --limit 50    # Cap number of fetches
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import time
import random
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "sector_rotation_tracker.db"
CACHE_CSV = ROOT / "data" / "_sector_rotation_fund_cache.csv"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.screener.in/",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


# ── Screener.in fetcher ───────────────────────────────────────────────────────

def _search_screener(symbol: str) -> Optional[str]:
    """Use screener.in search API to find the correct company URL slug."""
    try:
        resp = SESSION.get(
            f"https://www.screener.in/api/company/search/?q={symbol}&fields=name,url",
            timeout=10,
        )
        if resp.status_code == 200:
            results = resp.json()
            if results:
                # Return the URL slug of the best match
                url = results[0].get("url", "")
                # url is like /company/RELIANCE/
                slug = url.strip("/").split("/")[-1]
                return slug if slug else None
    except Exception:
        pass
    return None


def _fetch_page(symbol: str, consolidated: bool = True) -> Optional[BeautifulSoup]:
    suffix = "consolidated/" if consolidated else ""
    url = f"https://www.screener.in/company/{symbol}/{suffix}"
    try:
        resp = SESSION.get(url, timeout=20)
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        # Check for redirect to search results (symbol not found)
        if soup.find("div", class_="search-results") or "results for" in soup.get_text()[:500].lower():
            return None
        return soup
    except Exception:
        return None


def _parse_table(soup: BeautifulSoup, section_id: str) -> list[list[str]]:
    """Parse a financial table by its section id. Returns list of rows."""
    section = soup.find("section", id=section_id)
    if not section:
        return []
    table = section.find("table")
    if not table:
        return []
    rows = []
    for tr in table.find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all(["th", "td"])]
        if cells:
            rows.append(cells)
    return rows


def _safe_num(s: str) -> Optional[float]:
    try:
        return float(s.replace(",", "").replace("%", "").strip())
    except Exception:
        return None


def _yoy(cur: Optional[float], prev: Optional[float]) -> Optional[float]:
    if cur is None or prev is None or prev == 0:
        return None
    return round(100 * (cur - prev) / abs(prev), 1)


def _label_clean(label: str) -> str:
    """Normalize a screener.in row label for matching."""
    return label.strip().rstrip("+").strip().lower()


def _format_pnl(rows: list[list[str]]) -> str:
    if not rows or len(rows) < 2:
        return ""
    out = []
    for row in rows[1:]:
        if not row:
            continue
        label = _label_clean(row[0])
        vals = [_safe_num(v) for v in row[1:]]
        non_none = [v for v in vals if v is not None]
        if not non_none:
            continue
        cur = non_none[-1]
        prev = non_none[-2] if len(non_none) >= 2 else None
        yoy = _yoy(cur, prev)

        if label in ("sales", "revenue"):
            nice = "Sales"
        elif label in ("net profit", "pat", "netprofit"):
            nice = "NetProfit"
        elif label in ("eps in rs", "eps", "earningspershare"):
            out.append(f"EPS: {round(cur, 2)}")
            continue
        elif label == "operating profit":
            nice = "EBITDA"
        else:
            continue

        if yoy is not None:
            sign = "+" if yoy >= 0 else ""
            out.append(f"{nice}: {round(cur, 0):.0f} Cr (YoY {sign}{yoy}%)")
        else:
            out.append(f"{nice}: {round(cur, 0):.0f} Cr")
    return "; ".join(out)


def _format_quarterly(rows: list[list[str]]) -> str:
    if not rows or len(rows) < 2:
        return ""
    out = []
    for row in rows[1:]:
        if not row:
            continue
        label = _label_clean(row[0])
        if label in ("sales", "revenue", "net profit", "pat", "netprofit"):
            vals = [_safe_num(v) for v in row[1:]]
            non_none = [v for v in vals if v is not None][-4:]
            if non_none:
                nice = "Sales" if label in ("sales", "revenue") else "Net Profit"
                formatted = ", ".join(f"{round(v, 0):.0f}" for v in non_none)
                out.append(f"{nice} last {len(non_none)}Q: {formatted} Cr")
    return "; ".join(out)


def _format_balance_sheet(rows: list[list[str]]) -> str:
    if not rows or len(rows) < 2:
        return ""
    out = []
    for row in rows[1:]:
        if not row:
            continue
        label = _label_clean(row[0])
        vals = [_safe_num(v) for v in row[1:]]
        non_none = [v for v in vals if v is not None]
        if not non_none:
            continue
        cur = non_none[-1]
        if "borrowing" in label or label == "debt":
            out.append(f"Debt: {round(cur, 0):.0f} Cr")
        elif "equity capital" in label:
            out.append(f"Equity: {round(cur, 0):.0f} Cr")
        elif "total assets" in label or "total liabilities" in label:
            out.append(f"Assets: {round(cur, 0):.0f} Cr")
    return "; ".join(out)


def _parse_key_ratios(soup: BeautifulSoup) -> str:
    """Parse key ratios from the #top-ratios ul on screener.in."""
    out = []
    ul = soup.find("ul", id="top-ratios")
    if not ul:
        return ""
    for li in ul.find_all("li"):
        # Each li has: <span class="name">Label</span><span class="number">Value</span>
        name_el = li.find("span", class_="name")
        num_el = li.find("span", class_="number")
        if not name_el:
            continue
        name = name_el.get_text(strip=True).rstrip(":")
        # Value may be in .number span or plain text after the name span
        if num_el:
            val = num_el.get_text(strip=True)
        else:
            # Strip the name from full text
            full = li.get_text(strip=True)
            val = full.replace(name, "").strip().lstrip(":")
        if name and val:
            out.append(f"{name}: {val}")
    return "; ".join(out[:8])


def fetch_fundamentals(symbol: str) -> Optional[dict]:
    """Fetch and parse fundamentals for one symbol from screener.in."""
    # Try consolidated first, fallback to standalone
    soup = _fetch_page(symbol, consolidated=True)
    if soup is None:
        soup = _fetch_page(symbol, consolidated=False)

    # If still None, try screener search API to find the right slug
    if soup is None:
        slug = _search_screener(symbol)
        if slug and slug.upper() != symbol.upper():
            soup = _fetch_page(slug, consolidated=True)
            if soup is None:
                soup = _fetch_page(slug, consolidated=False)

    if soup is None:
        return None

    # Check if redirected to a different page (symbol not found)
    title = soup.find("title")
    if title and "not found" in title.get_text(strip=True).lower():
        return None

    pnl_rows = _parse_table(soup, "profit-loss")
    qtr_rows = _parse_table(soup, "quarters")
    bs_rows = _parse_table(soup, "balance-sheet")

    pnl_summary = _format_pnl(pnl_rows)
    quarterly_summary = _format_quarterly(qtr_rows)
    balance_sheet_summary = _format_balance_sheet(bs_rows)
    ratios_summary = _parse_key_ratios(soup)

    if not any([pnl_summary, quarterly_summary, ratios_summary]):
        return None

    return {
        "SYMBOL": symbol,
        "pnl_summary": pnl_summary,
        "quarterly_summary": quarterly_summary,
        "balance_sheet_summary": balance_sheet_summary,
        "ratios_summary": ratios_summary,
    }


# ── Cache management ──────────────────────────────────────────────────────────

def load_cache() -> dict[str, dict]:
    cache: dict[str, dict] = {}
    if CACHE_CSV.exists():
        with open(CACHE_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                sym = row.get("SYMBOL", "").upper()
                if sym:
                    cache[sym] = row
    return cache


def save_cache(cache: dict[str, dict]) -> None:
    CACHE_CSV.parent.mkdir(parents=True, exist_ok=True)
    fields = ["SYMBOL", "pnl_summary", "quarterly_summary", "balance_sheet_summary", "ratios_summary"]
    with open(CACHE_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in cache.values():
            writer.writerow(row)


def update_db(cache: dict[str, dict]) -> int:
    """Push fund_details into the DB for all snapshots."""
    if not DB_PATH.exists():
        return 0
    conn = sqlite3.connect(DB_PATH)
    updated = 0
    for sym, data in cache.items():
        fund_json = json.dumps({
            "pnl_summary": data.get("pnl_summary", ""),
            "quarterly_summary": data.get("quarterly_summary", ""),
            "balance_sheet_summary": data.get("balance_sheet_summary", ""),
            "ratios_summary": data.get("ratios_summary", ""),
        })
        conn.execute(
            "UPDATE stage_snapshots SET fund_details = ? WHERE symbol = ?",
            (fund_json, sym),
        )
        updated += conn.total_changes
    conn.commit()
    conn.close()
    return updated


# ── Symbol selection ──────────────────────────────────────────────────────────

def get_missing_stage2() -> list[str]:
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT symbol FROM stage_snapshots
        WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM stage_snapshots)
          AND stage = 'STAGE_2'
          AND (fund_details IS NULL OR fund_details = '' OR fund_details = '{}')
        ORDER BY investment_score DESC
    """).fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_all_symbols() -> list[str]:
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT DISTINCT symbol FROM stage_snapshots
        WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM stage_snapshots)
        ORDER BY symbol
    """).fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_symbols_missing_fund(limit: int = 0) -> list[str]:
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    # Stage 2 first, then rest
    rows = conn.execute("""
        SELECT symbol,
               CASE stage WHEN 'STAGE_2' THEN 0 WHEN 'STAGE_3' THEN 1 ELSE 2 END as ord
        FROM stage_snapshots
        WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM stage_snapshots)
          AND (fund_details IS NULL OR fund_details = '' OR fund_details = '{}')
        ORDER BY ord, investment_score DESC
    """).fetchall()
    conn.close()
    syms = [r[0] for r in rows]
    if limit:
        syms = syms[:limit]
    return syms


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch fundamentals from screener.in")
    ap.add_argument("--all", action="store_true", help="Fetch all 918 symbols")
    ap.add_argument("--stage2", action="store_true", help="Stage 2 missing only (default)")
    ap.add_argument("--symbols", help="Comma-separated symbol list")
    ap.add_argument("--limit", type=int, default=0, help="Max symbols to fetch")
    ap.add_argument("--delay", type=float, default=1.5, help="Seconds between requests (default 1.5)")
    ap.add_argument("--refresh", action="store_true", help="Re-fetch even if already cached")
    args = ap.parse_args()

    # Load existing cache
    cache = load_cache()
    print(f"Cache loaded: {len(cache)} symbols already have data")

    # Determine symbols to fetch
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    elif args.all:
        symbols = get_all_symbols()
        if not args.refresh:
            symbols = [s for s in symbols if s not in cache]
    else:
        # Default: missing stage 2 first, then rest
        symbols = get_symbols_missing_fund(limit=args.limit or 0)

    if args.limit and not args.all:
        symbols = symbols[:args.limit]

    if not symbols:
        print("No symbols to fetch. All already cached or DB empty.")
        return

    print(f"Fetching fundamentals for {len(symbols)} symbols from screener.in ...")
    print(f"  Delay: {args.delay}s between requests\n")

    fetched = 0
    failed = 0
    for i, sym in enumerate(symbols, 1):
        print(f"  [{i:3d}/{len(symbols)}] {sym:<15}", end=" ", flush=True)
        try:
            data = fetch_fundamentals(sym)
            if data:
                cache[sym] = data
                print(f"✓  {data['pnl_summary'][:60] if data['pnl_summary'] else 'no P&L'}")
                fetched += 1
            else:
                print("✗  not found on screener.in")
                failed += 1
        except Exception as e:
            print(f"✗  error: {e}")
            failed += 1

        # Save every 10 symbols
        if i % 10 == 0:
            save_cache(cache)
            updated = update_db(cache)
            print(f"\n  → Saved cache ({len(cache)} total), updated DB\n")

        # Rate limit with slight jitter
        time.sleep(args.delay + random.uniform(0, 0.5))

    # Final save
    save_cache(cache)
    db_rows = update_db(cache)
    print(f"\n{'='*60}")
    print(f"  Done: {fetched} fetched, {failed} failed")
    print(f"  Cache: {len(cache)} total symbols in {CACHE_CSV.name}")
    print(f"  DB updated for all cached symbols")


if __name__ == "__main__":
    main()
