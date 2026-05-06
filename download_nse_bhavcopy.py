#!/usr/bin/env python3
"""
NSE Bhavcopy Downloader (Python port of download_latest_missing_data.R)
========================================================================
Downloads missing NSE daily bhavcopy archives and appends stock + index
data to the project CSV files.

Data source:
  https://nsearchives.nseindia.com/archives/equities/bhavcopy/pr/PR{DDMMYY}.zip

Files updated:
  data/nse_sec_full_data.csv   — equity OHLCV (from Pd{DDMMYY}.csv inside ZIP)
  data/nse_index_data.csv      — index OHLCV (from Pr{DDMMYY}.csv inside ZIP)

PG: Ported from R to Python so the entire daily pipeline can run without R.
"""
from __future__ import annotations

import io
import os
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"

# NSE bhavcopy URL pattern
NSE_BHAVCOPY_URL = (
    "https://nsearchives.nseindia.com/archives/equities/bhavcopy/pr/PR{ddmmyy}.zip"
)

# Standard headers to mimic browser (NSE blocks raw bot requests)
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}

# Column mapping from bhavcopy to our standard schema
_STOCK_COLS_MAP = {
    "SYMBOL": "SYMBOL",
    "OPEN_PRICE": "OPEN",
    "HIGH_PRICE": "HIGH",
    "LOW_PRICE": "LOW",
    "CLOSE_PRICE": "CLOSE",
    "PREV_CL_PR": "PREVCLOSE",
    "NET_TRDQTY": "TOTTRDQTY",
    "NET_TRDVAL": "TOTTRDVAL",
    "TRADES": "TOTALTRADES",
}

# Stock CSV output columns (must match existing nse_sec_full_data.csv)
_STOCK_OUTPUT_COLS = [
    "SYMBOL", "ISIN", "TIMESTAMP", "OPEN", "HIGH", "LOW", "CLOSE",
    "LAST", "PREVCLOSE", "TOTTRDQTY", "TOTTRDVAL", "TOTALTRADES",
]

# Index CSV output columns (must match existing nse_index_data.csv)
_INDEX_OUTPUT_COLS = [
    "SYMBOL", "OPEN", "HIGH", "LOW", "CLOSE", "PREVCLOSE",
    "TOTTRDQTY", "TOTTRDVAL", "TIMESTAMP", "TOTALTRADES",
    "HI_52_WK", "LO_52_WK",
]


def _is_weekday(d: date) -> bool:
    return d.weekday() < 5  # Mon=0 .. Fri=4


def _get_latest_date(csv_path: Path, date_col: str = "TIMESTAMP") -> date | None:
    """Read the latest date from an existing CSV file."""
    if not csv_path.exists() or csv_path.stat().st_size < 100:
        return None
    try:
        df = pd.read_csv(csv_path, usecols=[date_col])
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        latest = df[date_col].max()
        if pd.isna(latest):
            return None
        return latest.date()
    except Exception as exc:
        print(f"  Warning: Could not read latest date from {csv_path.name}: {exc}")
        return None


def get_missing_dates(stock_csv: Path, index_csv: Path) -> list[date]:
    """
    Determine which weekday dates are missing from both stock and index CSVs.
    Returns dates from (latest_date + 1) to yesterday (today's data may not be posted yet).
    """
    stock_latest = _get_latest_date(stock_csv)
    index_latest = _get_latest_date(index_csv)

    # Use the older of the two as the starting point, so both get updated
    if stock_latest and index_latest:
        start_after = min(stock_latest, index_latest)
    elif stock_latest:
        start_after = stock_latest
    elif index_latest:
        start_after = index_latest
    else:
        print("  No existing data found — will not attempt bulk backfill.")
        return []

    today = date.today()
    # NSE bhavcopy is typically available by ~7 PM IST on the same day
    # To be safe, try up to today (will get 404 if not yet posted)
    end_date = today

    dates: list[date] = []
    d = start_after + timedelta(days=1)
    while d <= end_date:
        if _is_weekday(d):
            dates.append(d)
        d += timedelta(days=1)

    return dates


def _download_zip(target_date: date, session: requests.Session) -> bytes | None:
    """Download the bhavcopy ZIP for a given date. Returns raw bytes or None."""
    ddmmyy = target_date.strftime("%d%m%y").upper()
    url = NSE_BHAVCOPY_URL.format(ddmmyy=ddmmyy)

    try:
        resp = session.get(url, headers=_HEADERS, timeout=30)
        if resp.status_code == 200 and len(resp.content) > 200:
            return resp.content
        elif resp.status_code == 404:
            # Holiday or data not yet posted
            return None
        else:
            print(f"    HTTP {resp.status_code} for {target_date}")
            return None
    except requests.RequestException as exc:
        print(f"    Network error for {target_date}: {exc}")
        return None


def _extract_csv_from_zip(zip_bytes: bytes, filename: str) -> pd.DataFrame | None:
    """Extract a specific CSV from ZIP bytes and return as DataFrame."""
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
            # Try exact match first, then case-insensitive
            match = None
            for n in names:
                if n == filename:
                    match = n
                    break
                elif n.lower() == filename.lower():
                    match = n
                    break
            if match is None:
                return None
            with zf.open(match) as f:
                return pd.read_csv(f)
    except (zipfile.BadZipFile, Exception) as exc:
        print(f"    ZIP extraction error: {exc}")
        return None


def _process_stock_data(raw: pd.DataFrame, target_date: date) -> pd.DataFrame:
    """Filter equity rows and map columns to standard schema."""
    # Filter: SERIES == "EQ", non-empty SYMBOL
    eq = raw[raw["SERIES"].astype(str).str.strip() == "EQ"].copy()
    eq = eq[eq["SYMBOL"].astype(str).str.strip() != ""]

    out = pd.DataFrame()
    out["SYMBOL"] = eq["SYMBOL"].astype(str).str.strip()
    out["ISIN"] = pd.NA
    out["TIMESTAMP"] = target_date.isoformat()
    out["OPEN"] = pd.to_numeric(eq["OPEN_PRICE"], errors="coerce")
    out["HIGH"] = pd.to_numeric(eq["HIGH_PRICE"], errors="coerce")
    out["LOW"] = pd.to_numeric(eq["LOW_PRICE"], errors="coerce")
    out["CLOSE"] = pd.to_numeric(eq["CLOSE_PRICE"], errors="coerce")
    out["LAST"] = pd.to_numeric(eq["CLOSE_PRICE"], errors="coerce")
    out["PREVCLOSE"] = pd.to_numeric(eq["PREV_CL_PR"], errors="coerce")
    out["TOTTRDQTY"] = pd.to_numeric(eq["NET_TRDQTY"], errors="coerce")
    out["TOTTRDVAL"] = pd.to_numeric(eq["NET_TRDVAL"], errors="coerce")
    out["TOTALTRADES"] = pd.to_numeric(eq["TRADES"], errors="coerce")

    # Drop rows with missing price data
    out = out.dropna(subset=["OPEN", "HIGH", "LOW", "CLOSE"])
    return out[_STOCK_OUTPUT_COLS]


def _process_index_data(raw: pd.DataFrame, target_date: date) -> pd.DataFrame:
    """Filter index rows (IND_SEC=Y, MKT=Y) and map to standard schema."""
    # The Pr*.csv has different column names — need to handle both layouts
    # Standard layout: MKT, SECURITY, PREV_CLOSE, OPEN, HIGH, LOW, CLOSE, ...
    idx = raw.copy()

    # Filter for index rows
    if "IND_SEC" in idx.columns:
        idx = idx[(idx["IND_SEC"].astype(str).str.strip() == "Y")]
    if "MKT" in idx.columns:
        idx = idx[(idx["MKT"].astype(str).str.strip() == "Y")]

    # Identify the security/symbol column
    sym_col = None
    for candidate in ["SECURITY", "SYMBOL", "INDEX_NAME"]:
        if candidate in idx.columns:
            sym_col = candidate
            break
    if sym_col is None or idx.empty:
        return pd.DataFrame(columns=_INDEX_OUTPUT_COLS)

    idx = idx[idx[sym_col].astype(str).str.strip() != ""]

    out = pd.DataFrame()
    out["SYMBOL"] = idx[sym_col].astype(str).str.strip()

    # Map price columns — bhavcopy uses different names depending on layout
    for our_col, candidates in [
        ("OPEN", ["OPEN", "OPEN_PRICE"]),
        ("HIGH", ["HIGH", "HIGH_PRICE"]),
        ("LOW", ["LOW", "LOW_PRICE"]),
        ("CLOSE", ["CLOSE", "CLOSE_PRICE"]),
        ("PREVCLOSE", ["PREV_CLOSE", "PREVCLOSE", "PREV_CL_PR"]),
        ("TOTTRDQTY", ["TOTTRDQTY", "NET_TRDQTY", "TRADED_QTY"]),
        ("TOTTRDVAL", ["TOTTRDVAL", "NET_TRDVAL", "TRADED_VALUE"]),
        ("TOTALTRADES", ["TOTALTRADES", "NO_OF_TRADES", "TRADES"]),
        ("HI_52_WK", ["HI_52_WK", "52_WK_H"]),
        ("LO_52_WK", ["LO_52_WK", "52_WK_L"]),
    ]:
        matched = None
        for c in candidates:
            if c in idx.columns:
                matched = c
                break
        if matched:
            out[our_col] = pd.to_numeric(idx[matched], errors="coerce")
        else:
            out[our_col] = 0.0

    out["TIMESTAMP"] = target_date.isoformat()
    out = out.dropna(subset=["OPEN", "HIGH", "LOW", "CLOSE"])
    return out[_INDEX_OUTPUT_COLS]


def _append_and_dedup(csv_path: Path, new_data: pd.DataFrame, dedup_cols: list[str]) -> int:
    """Append new data to existing CSV, deduplicate, and write back. Returns new row count."""
    if csv_path.exists() and csv_path.stat().st_size > 100:
        existing = pd.read_csv(csv_path)
        combined = pd.concat([existing, new_data], ignore_index=True)
        before = len(combined)
        combined = combined.drop_duplicates(subset=dedup_cols, keep="last")
        added = len(combined) - len(existing)
    else:
        combined = new_data
        added = len(new_data)

    combined.to_csv(csv_path, index=False)
    return added


def download_missing_data(
    stock_csv: Path | None = None,
    index_csv: Path | None = None,
    max_dates: int = 60,
    delay: float = 1.5,
) -> dict[str, int]:
    """
    Main entry point: download all missing NSE bhavcopy data and append to CSVs.

    Returns dict with counts: stock_dates, index_dates, stock_rows, index_rows.
    """
    if stock_csv is None:
        stock_csv = DATA_DIR / "nse_sec_full_data.csv"
    if index_csv is None:
        index_csv = DATA_DIR / "nse_index_data.csv"

    print(f"\n{'═'*60}")
    print("  NSE Bhavcopy Data Download")
    print(f"  Stock CSV: {stock_csv.name}")
    print(f"  Index CSV: {index_csv.name}")
    print(f"{'═'*60}")

    missing = get_missing_dates(stock_csv, index_csv)
    if not missing:
        print("  ✅ Data is up to date — no missing dates.")
        return {"stock_dates": 0, "index_dates": 0, "stock_rows": 0, "index_rows": 0}

    if len(missing) > max_dates:
        print(f"  ⚠️  {len(missing)} missing dates — capping at {max_dates}")
        missing = missing[:max_dates]

    print(f"  Missing dates: {len(missing)} ({missing[0]} → {missing[-1]})")

    session = requests.Session()
    # PG: NSE requires cookies from the homepage before allowing archive downloads
    try:
        session.get("https://www.nseindia.com/", headers=_HEADERS, timeout=10)
    except Exception:
        pass  # Continue anyway — some dates may work without session cookies

    stats = {"stock_dates": 0, "index_dates": 0, "stock_rows": 0, "index_rows": 0}
    import time

    for i, d in enumerate(missing):
        ddmmyy = d.strftime("%d%m%y")
        print(f"\n  [{i+1}/{len(missing)}] {d} (PR{ddmmyy}.zip) …", end=" ")

        zip_bytes = _download_zip(d, session)
        if zip_bytes is None:
            print("skipped (holiday/not posted)")
            continue

        # ── Stock data (Pd*.csv) ──
        stock_file = f"Pd{ddmmyy}.csv"
        raw_stocks = _extract_csv_from_zip(zip_bytes, stock_file)
        if raw_stocks is not None and not raw_stocks.empty:
            processed = _process_stock_data(raw_stocks, d)
            if not processed.empty:
                added = _append_and_dedup(stock_csv, processed, ["SYMBOL", "TIMESTAMP"])
                stats["stock_dates"] += 1
                stats["stock_rows"] += added
                print(f"stocks={len(processed)}", end=" ")
            else:
                print("stocks=0", end=" ")
        else:
            print("no-stock-file", end=" ")

        # ── Index data (Pr*.csv) ──
        index_file = f"Pr{ddmmyy}.csv"
        raw_index = _extract_csv_from_zip(zip_bytes, index_file)
        if raw_index is not None and not raw_index.empty:
            processed = _process_index_data(raw_index, d)
            if not processed.empty:
                added = _append_and_dedup(index_csv, processed, ["SYMBOL", "TIMESTAMP"])
                stats["index_dates"] += 1
                stats["index_rows"] += added
                print(f"indexes={len(processed)}", end=" ")
            else:
                print("indexes=0", end=" ")
        else:
            print("no-index-file", end=" ")

        print("✓")

        # Delay between requests to avoid rate-limiting
        if i < len(missing) - 1:
            time.sleep(delay)

    print(f"\n{'─'*60}")
    print(f"  Download complete:")
    print(f"    Stock data: {stats['stock_dates']} dates, {stats['stock_rows']} new rows")
    print(f"    Index data: {stats['index_dates']} dates, {stats['index_rows']} new rows")
    return stats


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Download missing NSE bhavcopy data")
    parser.add_argument("--max-dates", type=int, default=60, help="Max number of dates to download (default: 60)")
    parser.add_argument("--delay", type=float, default=1.5, help="Delay between requests in seconds (default: 1.5)")
    args = parser.parse_args()

    result = download_missing_data(max_dates=args.max_dates, delay=args.delay)
    print(f"\n  Summary: {result}")
