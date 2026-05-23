"""Load NSE master equity list + sector/industry mappings into Postgres.

Pipeline:
  Phase 1 — download EQUITY_L.csv  → seed ref.instruments (symbol/ISIN/name/series/listing_date/face_value).
  Phase 2 — download key NIFTY constituent CSVs (have Industry column)
            → upsert industry into ref.instruments and populate ref.indices /
              ref.index_compositions / is_nifty50 / is_nifty500 flags.
  Phase 3 — for each symbol still missing sector, hit NSE's
            /api/quote-equity?symbol=X (returns industryInfo.{macro,sector,
            industry,basicIndustry}) with a polite delay; checkpoint to a JSON
            cache so the script is resumable.

Usage:
    .venv/bin/python scripts/load_nse_instrument_sectors.py            # full run
    .venv/bin/python scripts/load_nse_instrument_sectors.py --skip-meta  # phase 1+2 only
    .venv/bin/python scripts/load_nse_instrument_sectors.py --symbols INSPIRISYS,GVPIL  # only meta for given
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "data" / "_nse_master_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
META_CACHE = CACHE_DIR / "quote_equity_meta.json"

DSN = os.environ.get("AGENT_ADDA_PG_DSN") or os.environ.get("PG_DSN") or "dbname=nse_market user=nse_admin host=/tmp"

INDEX_FILES = [
    # (index_symbol,                       csv_filename,                          flags)
    ("NIFTY 50",                           "ind_nifty50list.csv",                 {"is_nifty50": True, "is_nifty500": True}),
    ("NIFTY NEXT 50",                      "ind_niftynext50list.csv",             {"is_nifty500": True}),
    ("NIFTY 100",                          "ind_nifty100list.csv",                {"is_nifty500": True}),
    ("NIFTY 200",                          "ind_nifty200list.csv",                {"is_nifty500": True}),
    ("NIFTY 500",                          "ind_nifty500list.csv",                {"is_nifty500": True}),
    ("NIFTY MIDCAP 50",                    "ind_niftymidcap50list.csv",           {}),
    ("NIFTY MIDCAP 100",                   "ind_niftymidcap100list.csv",          {}),
    ("NIFTY MIDCAP 150",                   "ind_niftymidcap150list.csv",          {}),
    ("NIFTY SMALLCAP 50",                  "ind_niftysmallcap50list.csv",         {}),
    ("NIFTY SMALLCAP 100",                 "ind_niftysmallcap100list.csv",        {}),
    ("NIFTY SMALLCAP 250",                 "ind_niftysmallcap250list.csv",        {}),
    ("NIFTY MICROCAP 250",                 "ind_niftymicrocap250_list.csv",       {}),
    ("NIFTY LARGEMIDCAP 250",              "ind_niftylargemidcap250list.csv",     {}),
    ("NIFTY MIDSMALLCAP 400",              "ind_niftymidsmallcap400list.csv",     {}),
    ("NIFTY TOTAL MARKET",                 "ind_niftytotalmarket_list.csv",       {}),
]

NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json,text/csv,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(NSE_HEADERS)
    s.get("https://www.nseindia.com/", timeout=15)
    s.get("https://www.nseindia.com/market-data/live-equity-market?symbol=NIFTY+50", timeout=15)
    return s


def _parse_date(s: str | None) -> str | None:
    if not s:
        return None
    s = s.strip()
    if not s:
        return None
    for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _to_float(s: str | None) -> float | None:
    if s is None:
        return None
    s = str(s).strip().replace(",", "")
    if not s or s in {"-", "N/A", "NA"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1 — master list
# ─────────────────────────────────────────────────────────────────────────────
def fetch_master(sess: requests.Session) -> list[dict]:
    url = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
    r = sess.get(url, timeout=30)
    r.raise_for_status()
    rows = []
    rd = csv.DictReader(io.StringIO(r.text))
    for raw in rd:
        row = {(k or "").strip().upper().lstrip("\ufeff"): (v or "").strip() for k, v in raw.items()}
        sym = row.get("SYMBOL")
        if not sym:
            continue
        rows.append({
            "symbol": sym.upper(),
            "isin": row.get("ISIN NUMBER") or None,
            "company_name": row.get("NAME OF COMPANY") or sym,
            "series": (row.get("SERIES") or "EQ").upper(),
            "listing_date": _parse_date(row.get("DATE OF LISTING")),
            "face_value": _to_float(row.get("FACE VALUE")),
        })
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2 — constituent CSVs
# ─────────────────────────────────────────────────────────────────────────────
def fetch_constituents(sess: requests.Session) -> tuple[dict[str, dict], list[tuple[str, str]]]:
    """Returns (industry_by_symbol, [(index_symbol, symbol), ...])."""
    industry_map: dict[str, dict] = {}
    memberships: list[tuple[str, str]] = []
    for index_symbol, fname, _flags in INDEX_FILES:
        url = f"https://nsearchives.nseindia.com/content/indices/{fname}"
        try:
            r = sess.get(url, timeout=30)
            r.raise_for_status()
        except Exception as e:
            print(f"  [warn] {index_symbol}: {e}")
            continue
        rd = csv.DictReader(io.StringIO(r.text))
        cnt = 0
        for raw in rd:
            row = {(k or "").strip(): (v or "").strip() for k, v in raw.items()}
            sym = (row.get("Symbol") or row.get("SYMBOL") or "").upper()
            if not sym:
                continue
            ind = row.get("Industry") or None
            company = row.get("Company Name") or row.get("COMPANY NAME") or None
            if sym not in industry_map:
                industry_map[sym] = {"industry_from_csv": ind, "company_name_csv": company}
            elif ind and not industry_map[sym].get("industry_from_csv"):
                industry_map[sym]["industry_from_csv"] = ind
            memberships.append((index_symbol, sym))
            cnt += 1
        print(f"  {index_symbol}: {cnt} constituents")
    return industry_map, memberships


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3 — per-symbol industryInfo
# ─────────────────────────────────────────────────────────────────────────────
def load_meta_cache() -> dict[str, dict]:
    if META_CACHE.exists():
        try:
            return json.loads(META_CACHE.read_text())
        except Exception:
            return {}
    return {}


def save_meta_cache(cache: dict[str, dict]) -> None:
    META_CACHE.write_text(json.dumps(cache, indent=0))


def fetch_industry_info(sess: requests.Session, symbol: str) -> dict | None:
    url = f"https://www.nseindia.com/api/quote-equity?symbol={requests.utils.quote(symbol)}"
    try:
        r = sess.get(url, timeout=12)
        if r.status_code != 200:
            return None
        d = r.json()
    except Exception:
        return None
    info = d.get("industryInfo") or {}
    meta = d.get("metadata") or {}
    if not info and not meta:
        return None
    return {
        "macro": info.get("macro"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "basic_industry": info.get("basicIndustry"),
        "isin": meta.get("isin"),
        "listing_date": _parse_date(meta.get("listingDate")),
        "status": meta.get("status"),
        "fetched_at": datetime.utcnow().isoformat(),
    }


def enrich_with_meta(sess: requests.Session, symbols: list[str], delay: float = 0.35) -> dict[str, dict]:
    cache = load_meta_cache()
    n_new = 0
    for i, sym in enumerate(symbols, 1):
        if sym in cache and cache[sym].get("sector"):
            continue
        info = fetch_industry_info(sess, sym)
        if info:
            cache[sym] = info
            n_new += 1
        if i % 25 == 0:
            save_meta_cache(cache)
            print(f"  [{i}/{len(symbols)}] new={n_new}  last={sym} sector={info.get('sector') if info else 'NONE'}")
        time.sleep(delay)
    save_meta_cache(cache)
    print(f"  meta enrichment done: {n_new} new, total cached {len(cache)}")
    return cache


# ─────────────────────────────────────────────────────────────────────────────
# Postgres writes
# ─────────────────────────────────────────────────────────────────────────────
def upsert_instruments(rows: list[dict], industry_map: dict[str, dict],
                       meta_cache: dict[str, dict], nifty50_set: set[str],
                       nifty500_set: set[str]) -> int:
    import psycopg2
    import psycopg2.extras as ext
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor()
    payload = []
    for r in rows:
        sym = r["symbol"]
        meta = meta_cache.get(sym) or {}
        csv_ind = (industry_map.get(sym) or {}).get("industry_from_csv")
        sector = meta.get("sector")
        industry = meta.get("industry") or csv_ind
        isin = r["isin"] or meta.get("isin")
        payload.append((
            sym, isin, r["company_name"], r["series"], r["face_value"],
            r["listing_date"] or meta.get("listing_date"),
            sector, industry,
            sym in nifty50_set, sym in nifty500_set,
        ))
    sql = """
        INSERT INTO ref.instruments
            (symbol, isin, company_name, series, face_value, listing_date,
             sector, industry, is_nifty50, is_nifty500, updated_at)
        VALUES %s
        ON CONFLICT (symbol) DO UPDATE SET
            isin         = COALESCE(EXCLUDED.isin, ref.instruments.isin),
            company_name = COALESCE(EXCLUDED.company_name, ref.instruments.company_name),
            series       = COALESCE(EXCLUDED.series, ref.instruments.series),
            face_value   = COALESCE(EXCLUDED.face_value, ref.instruments.face_value),
            listing_date = COALESCE(EXCLUDED.listing_date, ref.instruments.listing_date),
            sector       = COALESCE(EXCLUDED.sector, ref.instruments.sector),
            industry     = COALESCE(EXCLUDED.industry, ref.instruments.industry),
            is_nifty50   = EXCLUDED.is_nifty50,
            is_nifty500  = EXCLUDED.is_nifty500,
            updated_at   = now();
    """
    ext.execute_values(
        cur, sql, payload,
        template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())",
        page_size=500,
    )
    conn.commit()
    n = len(payload)
    cur.close(); conn.close()
    return n


def upsert_indices_and_memberships(memberships: list[tuple[str, str]]) -> tuple[int, int]:
    import psycopg2
    import psycopg2.extras as ext
    conn = psycopg2.connect(DSN)
    cur = conn.cursor()

    unique_indices = sorted({m[0] for m in memberships})
    ext.execute_values(
        cur,
        """INSERT INTO ref.indices (index_symbol, display_name, updated_at)
           VALUES %s
           ON CONFLICT (index_symbol) DO UPDATE SET updated_at = now();""",
        [(ix, ix) for ix in unique_indices],
        template="(%s,%s, now())",
    )

    # Only insert memberships whose symbol exists in ref.instruments to satisfy FK
    cur.execute("SELECT symbol FROM ref.instruments;")
    known = {r[0] for r in cur.fetchall()}
    rows = sorted({(ix, sym) for ix, sym in memberships if sym in known})
    ext.execute_values(
        cur,
        """INSERT INTO ref.index_compositions (index_symbol, symbol, as_of_date)
           VALUES %s
           ON CONFLICT (index_symbol, symbol) DO UPDATE SET as_of_date = EXCLUDED.as_of_date;""",
        [(ix, sym, datetime.utcnow().date().isoformat()) for ix, sym in rows],
        template="(%s,%s,%s)",
        page_size=1000,
    )
    conn.commit()
    n_ix, n_mem = len(unique_indices), len(rows)
    cur.close(); conn.close()
    return n_ix, n_mem


# ─────────────────────────────────────────────────────────────────────────────
# Driver
# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-meta", action="store_true", help="skip per-symbol industryInfo fetch")
    ap.add_argument("--meta-delay", type=float, default=0.35)
    ap.add_argument("--symbols", default=None, help="comma-separated symbols to limit meta phase to")
    ap.add_argument("--meta-limit", type=int, default=None, help="cap number of symbols enriched this run")
    args = ap.parse_args()

    sess = make_session()

    print("PHASE 1 — master list (EQUITY_L.csv)")
    master = fetch_master(sess)
    print(f"  master rows: {len(master)}")

    print("PHASE 2 — constituent index CSVs")
    industry_map, memberships = fetch_constituents(sess)
    nifty50_set = {sym for ix, sym in memberships if ix == "NIFTY 50"}
    nifty500_set = {sym for ix, sym in memberships if ix == "NIFTY 500"}
    print(f"  unique symbols w/ industry: {sum(1 for v in industry_map.values() if v.get('industry_from_csv'))}")

    meta_cache: dict[str, dict] = load_meta_cache()
    if not args.skip_meta:
        print("PHASE 3 — /api/quote-equity per symbol (industryInfo)")
        all_syms = [r["symbol"] for r in master]
        if args.symbols:
            wanted = {s.strip().upper() for s in args.symbols.split(",") if s.strip()}
            target = [s for s in all_syms if s in wanted]
        else:
            target = [s for s in all_syms if s not in meta_cache or not meta_cache[s].get("sector")]
        if args.meta_limit:
            target = target[: args.meta_limit]
        print(f"  symbols to enrich: {len(target)}")
        meta_cache = enrich_with_meta(sess, target, delay=args.meta_delay)
    else:
        print("PHASE 3 — skipped (--skip-meta)")

    print("WRITE — ref.instruments upsert")
    n = upsert_instruments(master, industry_map, meta_cache, nifty50_set, nifty500_set)
    print(f"  upserted: {n}")

    print("WRITE — ref.indices + ref.index_compositions upsert")
    n_ix, n_mem = upsert_indices_and_memberships(memberships)
    print(f"  indices: {n_ix}, memberships: {n_mem}")

    print("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
