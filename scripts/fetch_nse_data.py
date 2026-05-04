#!/usr/bin/env python3
"""
Fetch latest NSE Bhavcopy data and append to:
  - data/nse_universe_stock_data.csv  (universe stocks OHLCV)
  - data/nse_index_data.csv           (index closes)

Usage:
  python scripts/fetch_nse_data.py              # fetch missing dates up to today
  python scripts/fetch_nse_data.py --date 2026-03-25   # fetch specific date
  python scripts/fetch_nse_data.py --from 2026-03-07   # fetch from date to today

Data sources (NSE public archives, no auth required):
  Stock: https://archives.nseindia.com/products/content/sec_bhavdata_full_DDMMYYYY.csv
  Index: https://archives.nseindia.com/content/indices/ind_close_all_DDMMYYYY.csv
"""

import argparse
import io
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
UNIVERSE_STOCK_CSV = DATA_DIR / "nse_universe_stock_data.csv"
NSE_SEC_FULL_CSV = DATA_DIR / "nse_sec_full_data.csv"   # also update the main historical file
INDEX_CSV = DATA_DIR / "nse_index_data.csv"

# NSE archive URLs
STOCK_BHAV_URL = "https://archives.nseindia.com/products/content/sec_bhavdata_full_{date}.csv"
INDEX_BHAV_URL = "https://archives.nseindia.com/content/indices/ind_close_all_{date}.csv"

# NSE session headers (required to bypass basic bot detection)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.nseindia.com/",
}

# Index name mapping: NSE archive name → our standard name
INDEX_NAME_MAP = {
    "Nifty 50": "Nifty 50",
    "Nifty Auto": "Nifty Auto",
    "Nifty 500": "Nifty 500",
    "NIFTY 500": "Nifty 500",
    "Nifty Next 50": "Nifty Next 50",
    "Nifty Midcap 100": "NIFTY MIDCAP 100",
    "Nifty Bank": "Nifty Bank",
    "Nifty IT": "Nifty IT",
}


def get_session() -> requests.Session:
    """Create a requests session with NSE homepage cookies."""
    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        session.get("https://www.nseindia.com/", timeout=10)
        time.sleep(1)
    except Exception as e:
        print(f"  Warning: could not load NSE homepage for cookies: {e}")
    return session


def load_universe_symbols() -> list[str]:
    """Load all NSE symbols from the tracker DB, or fall back to nse_sec_full_data.csv."""
    db_path = DATA_DIR / "sector_rotation_tracker.db"
    if db_path.exists():
        import sqlite3
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT DISTINCT symbol FROM stage_snapshots "
            "WHERE snapshot_date=(SELECT MAX(snapshot_date) FROM stage_snapshots)"
        ).fetchall()
        conn.close()
        syms = [r[0] for r in rows if r[0]]
        if syms:
            print(f"  Universe: {len(syms)} symbols from tracker DB")
            return syms

    # Fallback: all symbols from existing nse_sec_full_data.csv
    candidates = [NSE_SEC_FULL_CSV, DATA_DIR / "nse_universe_stock_data.csv"]
    for f in candidates:
        if f.exists():
            df = pd.read_csv(f, usecols=["SYMBOL"])
            syms = df["SYMBOL"].dropna().str.strip().unique().tolist()
            print(f"  Universe: {len(syms)} symbols from {f.name}")
            return syms

    print("  Warning: no universe file found — downloading all symbols")
    return []  # empty = no filter, download all


def get_latest_date_in_file(csv_path: Path, date_col: str = "TIMESTAMP") -> date | None:
    if not csv_path.exists():
        return None
    df = pd.read_csv(csv_path, usecols=[date_col])
    if df.empty:
        return None
    return pd.to_datetime(df[date_col]).max().date()


def trading_days_between(start: date, end: date) -> list[date]:
    """Return Mon-Fri dates in [start, end] inclusive (approx; NSE holidays not filtered)."""
    days = []
    d = start
    while d <= end:
        if d.weekday() < 5:  # Mon-Fri
            days.append(d)
        d += timedelta(days=1)
    return days


def fetch_stock_bhav(session: requests.Session, dt: date, symbols: list[str]) -> pd.DataFrame | None:
    """Download equity Bhavcopy for dt; filter to universe symbols; return standardised df."""
    url = STOCK_BHAV_URL.format(date=dt.strftime("%d%m%Y"))
    try:
        resp = session.get(url, timeout=30)
        if resp.status_code == 404:
            return None  # holiday or weekend
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))
        df.columns = df.columns.str.strip()
        # Filter EQ series and universe symbols
        if "SERIES" in df.columns:
            df = df[df["SERIES"].str.strip() == "EQ"]
        if "SYMBOL" in df.columns:
            df["SYMBOL"] = df["SYMBOL"].str.strip()
            if symbols:
                df = df[df["SYMBOL"].isin(symbols)]
        # Rename / select columns to match our schema
        col_map = {
            "SYMBOL": "SYMBOL",
            "OPEN_PRICE": "OPEN", "OPEN": "OPEN",
            "HIGH_PRICE": "HIGH", "HIGH": "HIGH",
            "LOW_PRICE": "LOW", "LOW": "LOW",
            "CLOSE_PRICE": "CLOSE", "CLOSE": "CLOSE",
            "TTL_TRD_QNTY": "TOTTRDQTY", "TOTTRDQTY": "TOTTRDQTY",
            "TURNOVER_LACS": "TOTTRDVAL", "TOTTRDVAL": "TOTTRDVAL",
            "PREV_CLOSE": "PREVCLOSE", "PREVCLOSE": "PREVCLOSE",
            "NO_OF_TRADES": "TOTALTRADES", "TOTALTRADES": "TOTALTRADES",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        needed = ["SYMBOL", "OPEN", "HIGH", "LOW", "CLOSE", "TOTTRDQTY", "TOTTRDVAL"]
        missing = [c for c in needed if c not in df.columns]
        if missing:
            print(f"  Warning: missing columns {missing} in stock bhav for {dt}")
            for c in missing:
                df[c] = 0.0
        df = df[needed + [c for c in ["PREVCLOSE", "TOTALTRADES"] if c in df.columns]].copy()
        df["TIMESTAMP"] = dt.isoformat()
        for col in ["OPEN", "HIGH", "LOW", "CLOSE", "TOTTRDQTY", "TOTTRDVAL", "PREVCLOSE", "TOTALTRADES"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        out_cols = ["SYMBOL", "TIMESTAMP", "OPEN", "HIGH", "LOW", "CLOSE", "TOTTRDQTY", "TOTTRDVAL"]
        for c in ["PREVCLOSE", "TOTALTRADES"]:
            if c not in df.columns:
                df[c] = 0.0
            out_cols.append(c)
        return df[out_cols]
    except Exception as e:
        print(f"  Error fetching stock bhav for {dt}: {e}")
        return None


def fetch_index_bhav(session: requests.Session, dt: date) -> pd.DataFrame | None:
    """Download index Bhavcopy for dt; return standardised df."""
    url = INDEX_BHAV_URL.format(date=dt.strftime("%d%m%Y"))
    try:
        resp = session.get(url, timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))
        df.columns = df.columns.str.strip()
        # Rename columns
        col_map = {
            "Index Name": "SYMBOL",
            "Open Index Value": "OPEN",
            "High Index Value": "HIGH",
            "Low Index Value": "LOW",
            "Closing Index Value": "CLOSE",
            "Volume": "TOTTRDQTY",
            "Turnover (Rs. Cr.)": "TOTTRDVAL",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        df["SYMBOL"] = df["SYMBOL"].str.strip()
        df["TIMESTAMP"] = dt.isoformat()
        for col in ["OPEN", "HIGH", "LOW", "CLOSE"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df["TOTTRDQTY"] = pd.to_numeric(df.get("TOTTRDQTY", 0), errors="coerce").fillna(0)
        df["TOTTRDVAL"] = pd.to_numeric(df.get("TOTTRDVAL", 0), errors="coerce").fillna(0)
        # Add placeholder columns to match existing schema
        for col in ["PREVCLOSE", "TOTALTRADES", "HI_52_WK", "LO_52_WK"]:
            df[col] = 0.0
        keep = ["SYMBOL", "OPEN", "HIGH", "LOW", "CLOSE", "PREVCLOSE",
                "TOTTRDQTY", "TOTTRDVAL", "TIMESTAMP", "TOTALTRADES", "HI_52_WK", "LO_52_WK"]
        keep = [c for c in keep if c in df.columns]
        return df[keep]
    except Exception as e:
        print(f"  Error fetching index bhav for {dt}: {e}")
        return None


def append_to_csv(new_df: pd.DataFrame, csv_path: Path) -> int:
    """Append new_df rows (deduplicating by SYMBOL+TIMESTAMP) to csv_path. Returns rows added."""
    if new_df is None or new_df.empty:
        return 0
    existing_len = 0
    if csv_path.exists():
        existing = pd.read_csv(csv_path, low_memory=False)
        existing_len = len(existing)
        combined = pd.concat([existing, new_df], ignore_index=True)
        combined = combined.drop_duplicates(subset=["SYMBOL", "TIMESTAMP"], keep="last")
        combined = combined.sort_values(["SYMBOL", "TIMESTAMP"])
    else:
        combined = new_df.sort_values(["SYMBOL", "TIMESTAMP"])
    combined.to_csv(csv_path, index=False)
    return max(len(combined) - existing_len, 0)


def run(fetch_dates: list[date]) -> None:
    if not fetch_dates:
        print("No dates to fetch.")
        return

    symbols = load_universe_symbols()
    print(f"Universe: {len(symbols)} symbols")
    print(f"Dates to fetch: {fetch_dates[0]} → {fetch_dates[-1]} ({len(fetch_dates)} days)")

    session = get_session()
    stock_rows, index_rows = [], []
    fetched, skipped = 0, 0

    for dt in fetch_dates:
        print(f"  Fetching {dt}...", end=" ")
        stock_df = fetch_stock_bhav(session, dt, symbols)
        idx_df = fetch_index_bhav(session, dt)
        if stock_df is not None and not stock_df.empty:
            stock_rows.append(stock_df)
            fetched += 1
            print(f"stocks:{len(stock_df)}", end=" ")
        else:
            skipped += 1
            print("(holiday/no data)", end=" ")
        if idx_df is not None and not idx_df.empty:
            index_rows.append(idx_df)
            print(f"indices:{len(idx_df)}")
        else:
            print()
        time.sleep(0.5)  # polite delay

    # Append stock data
    if stock_rows:
        new_stock = pd.concat(stock_rows, ignore_index=True)
        added = append_to_csv(new_stock, UNIVERSE_STOCK_CSV)
        print(f"\nStock data: {added} new rows appended to {UNIVERSE_STOCK_CSV.name}")
        # Also update nse_sec_full_data.csv (used by fixed_nse_universe_analysis.py)
        added2 = append_to_csv(new_stock, NSE_SEC_FULL_CSV)
        print(f"Stock data: {added2} new rows appended to {NSE_SEC_FULL_CSV.name}")
    else:
        print("\nNo new stock data fetched.")

    # Append index data
    if index_rows:
        new_idx = pd.concat(index_rows, ignore_index=True)
        added = append_to_csv(new_idx, INDEX_CSV)
        print(f"Index data: {added} new rows appended to {INDEX_CSV.name}")
    else:
        print("No new index data fetched.")

    print(f"\nDone. Fetched: {fetched} days | Skipped (holidays): {skipped} days")


def main():
    parser = argparse.ArgumentParser(description="Fetch NSE Bhavcopy data")
    parser.add_argument("--date", help="Fetch single date (YYYY-MM-DD)")
    parser.add_argument("--from", dest="from_date", help="Fetch from date to today (YYYY-MM-DD)")
    args = parser.parse_args()

    today = date.today()

    if args.date:
        fetch_dates = [datetime.strptime(args.date, "%Y-%m-%d").date()]
    elif args.from_date:
        start = datetime.strptime(args.from_date, "%Y-%m-%d").date()
        fetch_dates = trading_days_between(start, today)
    else:
        # Auto: find missing dates from latest in file to today
        latest_stock = get_latest_date_in_file(UNIVERSE_STOCK_CSV)
        latest_index = get_latest_date_in_file(INDEX_CSV)
        latest = min(d for d in [latest_stock, latest_index] if d is not None) if (latest_stock or latest_index) else None
        if latest is None:
            print("No existing data found; fetching last 30 days.")
            start = today - timedelta(days=30)
        else:
            start = latest + timedelta(days=1)
            print(f"Latest data: {latest} | Fetching from {start} to {today}")
        fetch_dates = trading_days_between(start, today)

    if not fetch_dates:
        print("Data is already up to date.")
        sys.exit(0)

    run(fetch_dates)


if __name__ == "__main__":
    main()
