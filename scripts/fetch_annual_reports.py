"""Fetch, parse, and index NSE annual reports into the Agent Adda knowledge base.

Downloads annual report PDFs from NSE Archives for any listed symbol, then
ingests them into ChromaDB (KB Layer 2) so they are searchable via:

    python -m knowledge_base query "CUPID annual report revenue FY2025"
    python -m knowledge_base query "CUPID risk factors"
    python -m knowledge_base query "CUPID management discussion"

Usage
-----
    # Latest annual report for one symbol (default: most recent year)
    python scripts/fetch_annual_reports.py CUPID

    # Last 3 years
    python scripts/fetch_annual_reports.py CUPID --years 3

    # Specific year
    python scripts/fetch_annual_reports.py CUPID --from-year 2024 --to-year 2025

    # Multiple symbols
    python scripts/fetch_annual_reports.py CUPID RATEGAIN SKYGOLD --years 2

    # List available reports without downloading
    python scripts/fetch_annual_reports.py CUPID --list

    # Bulk: all positions in your fund
    python scripts/fetch_annual_reports.py --fund SC
    python scripts/fetch_annual_reports.py --fund MC
    python scripts/fetch_annual_reports.py --fund all

Architecture
------------
    NSE API → PDF URLs → knowledge_base.ingest → ChromaDB
              ↓
    data/knowledge_base/raw/annual_report_SYMBOL_FYYY_TYYY/

Each report is indexed with metadata:
    category    = "annual_report"
    hub_label   = "annual_report"
    source_id   = "annual_report_CUPID_FY2025"
    source_name = "Cupid Limited — Annual Report FY2024-25"
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from knowledge_base.ingest import ingest_pdf_url

# ─────────────────────────────────────────────────────────────────────────────
# NSE API
# ─────────────────────────────────────────────────────────────────────────────

NSE_BASE      = "https://www.nseindia.com"
NSE_AR_API    = f"{NSE_BASE}/api/annual-reports?index=equities&symbol={{symbol}}"
NSE_AR_DELAY  = 2.0   # seconds between requests (NSE rate-limit)

_NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": NSE_BASE,
}

_session: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    """Lazily create a session with NSE cookies (required to avoid 401)."""
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update(_NSE_HEADERS)
        try:
            _session.get(NSE_BASE, timeout=10)
        except Exception:
            pass  # cookies best-effort
    return _session


def fetch_ar_listing(symbol: str) -> list[dict]:
    """Return the NSE annual report listing for a symbol, newest first.

    Each entry: {companyName, fromYr, toYr, fileName (PDF URL), attFileSize}
    """
    s = _get_session()
    url = NSE_AR_API.format(symbol=symbol.upper())
    try:
        r = s.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
        return data.get("data", [])
    except Exception as exc:
        raise RuntimeError(f"NSE API error for {symbol}: {exc}") from exc


# ─────────────────────────────────────────────────────────────────────────────
# Fund positions helper
# ─────────────────────────────────────────────────────────────────────────────

def _fund_symbols(fund: str) -> list[str]:
    """Return NSE symbols currently held in SC / MC / both funds from PostgreSQL."""
    try:
        import psycopg2
        conn = psycopg2.connect(host="/tmp", dbname="nse_market", user="nse_admin")
        cur  = conn.cursor()
        if fund.upper() == "ALL":
            cur.execute("SELECT DISTINCT symbol FROM portfolio.fund_daily_pnl ORDER BY symbol")
        else:
            cur.execute(
                "SELECT DISTINCT symbol FROM portfolio.fund_daily_pnl WHERE fund=%s ORDER BY symbol",
                (fund.upper(),)
            )
        syms = [r[0] for r in cur.fetchall()]
        conn.close()
        return syms
    except Exception as exc:
        print(f"  ⚠️  DB error fetching fund positions: {exc}")
        syms = _fund_symbols_from_json(fund)
        if syms:
            print(f"  ↪ falling back to data/fund_holdings.json ({len(syms)} symbols)")
        return syms


def _fund_symbols_from_json(fund: str) -> list[str]:
    holdings = ROOT / "data" / "fund_holdings.json"
    if not holdings.exists():
        return []
    try:
        payload = json.loads(holdings.read_text(encoding="utf-8"))
    except Exception:
        return []
    fund_key = fund.upper()
    books: list[str]
    if fund_key == "SC":
        books = ["smallcap"]
    elif fund_key == "MC":
        books = ["midcap"]
    else:
        books = ["smallcap", "midcap"]
    symbols: list[str] = []
    for book in books:
        book_payload = payload.get(book) or {}
        for sym in book_payload.keys():
            if str(sym).startswith("_"):
                continue
            symbols.append(str(sym).strip().upper())
    return sorted(set(symbols))


# ─────────────────────────────────────────────────────────────────────────────
# Core ingest
# ─────────────────────────────────────────────────────────────────────────────

def _source_id(symbol: str, from_yr: str, to_yr: str) -> str:
    fy = f"FY{str(from_yr)[-2:]}{str(to_yr)[-2:]}"  # e.g. FY2425
    return f"annual_report_{symbol.upper()}_{fy}"


def ingest_annual_report(
    symbol: str,
    entry: dict,
    *,
    dry_run: bool = False,
    force: bool = False,
) -> dict:
    """Download and index one annual report PDF entry from the NSE listing."""
    from_yr    = entry.get("fromYr", "?")
    to_yr      = entry.get("toYr", "?")
    pdf_url    = entry.get("fileName", "")
    company    = entry.get("companyName", symbol)
    size_label = entry.get("attFileSize") or "?"
    fy_label   = f"FY{str(from_yr)[-2:]}-{str(to_yr)[-2:]}"

    source_id   = _source_id(symbol, from_yr, to_yr)
    source_name = f"{company} — Annual Report {fy_label}"

    print(f"\n  📄 {source_name}  ({size_label})")
    print(f"     {pdf_url}")

    if not pdf_url or not pdf_url.startswith("http"):
        print("     ⚠️  No valid PDF URL — skipping")
        return {"status": "skipped", "reason": "no_url"}

    if dry_run:
        print("     [dry-run] would ingest")
        return {"status": "dry_run"}

    # Check if already indexed (skip unless --force)
    if not force:
        raw_dir = ROOT / "data" / "knowledge_base" / "raw" / source_id
        if raw_dir.exists() and any(raw_dir.rglob("*.pdf")):
            print("     ✅ Already indexed — use --force to re-ingest")
            return {"status": "cached", "source_id": source_id}

    try:
        result = ingest_pdf_url(
            pdf_url,
            source_id=source_id,
            source_name=source_name,
            category="annual_report",
            tier=2,
            hub_label="annual_report",
            do_qa=True,
        )
        chunks = result.get("chunks_upserted", result.get("chunk_count", "?"))
        qa     = result.get("qa_pairs", 0)
        print(f"     ✅ Indexed: {chunks} chunks, {qa} Q&A pairs → ChromaDB")
        return {"status": "ok", "source_id": source_id, "chunks": chunks, "qa": qa}
    except Exception as exc:
        print(f"     ❌ Ingest failed: {exc}")
        return {"status": "error", "error": str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
# Main per-symbol handler
# ─────────────────────────────────────────────────────────────────────────────

def process_symbol(
    symbol: str,
    *,
    years: int = 1,
    from_year: Optional[int] = None,
    to_year: Optional[int] = None,
    list_only: bool = False,
    dry_run: bool = False,
    force: bool = False,
) -> list[dict]:
    print(f"\n{'='*60}")
    print(f"  {symbol.upper()}")
    print(f"{'='*60}")

    try:
        entries = fetch_ar_listing(symbol)
    except Exception as exc:
        print(f"  ❌ {exc}")
        return [{"status": "error", "error": str(exc)}]
    if not entries:
        print("  ⚠️  No annual reports found on NSE")
        return []

    # Filter by year range if specified
    if from_year and to_year:
        entries = [
            e for e in entries
            if str(e.get("fromYr", "")) == str(from_year)
            and str(e.get("toYr", ""))   == str(to_year)
        ]
    else:
        entries = entries[:years]  # newest first, take N

    if list_only:
        try:
            all_entries = fetch_ar_listing(symbol)
        except Exception as exc:
            print(f"  ❌ {exc}")
            return [{"status": "error", "error": str(exc)}]
        print(f"  Found {len(all_entries)} reports on NSE:")
        for e in all_entries:
            fy = f"FY{str(e.get('fromYr','?'))[-2:]}-{str(e.get('toYr','?'))[-2:]}"
            sz = e.get("attFileSize") or "?"
            print(f"    {fy}  {sz:>8}  {e.get('fileName','')[:80]}")
        return []

    results = []
    for i, entry in enumerate(entries):
        if i > 0:
            time.sleep(NSE_AR_DELAY)  # rate-limit between PDFs
        result = ingest_annual_report(symbol, entry, dry_run=dry_run, force=force)
        results.append(result)

    return results


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Fetch and index NSE annual reports into the Agent Adda KB.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Architecture")[0],
    )
    p.add_argument("symbols", nargs="*", metavar="SYMBOL", help="NSE symbol(s)")
    p.add_argument("--fund", choices=["SC", "MC", "all"], metavar="FUND",
                   help="Fetch for all positions in SC / MC / both funds")
    p.add_argument("--years", type=int, default=1, metavar="N",
                   help="Number of most-recent years to fetch (default: 1)")
    p.add_argument("--from-year", type=int, metavar="YYYY",
                   help="Fetch only this start year (pair with --to-year)")
    p.add_argument("--to-year", type=int, metavar="YYYY",
                   help="Fetch only this end year (pair with --from-year)")
    p.add_argument("--list", action="store_true",
                   help="List available reports without downloading")
    p.add_argument("--dry-run", action="store_true",
                   help="Show what would be ingested without doing it")
    p.add_argument("--force", action="store_true",
                   help="Re-ingest even if already cached in ChromaDB")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    symbols: list[str] = [s.upper() for s in args.symbols]

    if args.fund:
        fund_syms = _fund_symbols(args.fund)
        if not fund_syms:
            print(f"⚠️  No positions found for fund={args.fund}")
            return 1
        print(f"Fund {args.fund.upper()}: {len(fund_syms)} symbols — {', '.join(fund_syms)}")
        symbols = list(dict.fromkeys(symbols + fund_syms))  # deduplicate, preserve order

    if not symbols:
        print("Error: provide at least one SYMBOL or use --fund")
        build_parser().print_help()
        return 1

    all_results: dict[str, list[dict]] = {}
    for i, sym in enumerate(symbols):
        if i > 0:
            time.sleep(NSE_AR_DELAY)
        all_results[sym] = process_symbol(
            sym,
            years=args.years,
            from_year=args.from_year,
            to_year=args.to_year,
            list_only=args.list,
            dry_run=args.dry_run,
            force=args.force,
        )

    # Summary
    if not args.list and not args.dry_run:
        ok    = sum(1 for rs in all_results.values() for r in rs if r.get("status") == "ok")
        cached = sum(1 for rs in all_results.values() for r in rs if r.get("status") == "cached")
        errors = sum(1 for rs in all_results.values() for r in rs if r.get("status") == "error")
        total_chunks = sum(r.get("chunks", 0) for rs in all_results.values() for r in rs if isinstance(r.get("chunks"), int))
        print(f"\n{'='*60}")
        print(f"  Done — {ok} ingested, {cached} already cached, {errors} errors")
        if total_chunks:
            print(f"  Total chunks indexed: {total_chunks}")
        print(f"  Query: python -m knowledge_base query \"SYMBOL annual report ...\"")
        print(f"{'='*60}")

    if any(r.get("status") == "error" for rs in all_results.values() for r in rs):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
