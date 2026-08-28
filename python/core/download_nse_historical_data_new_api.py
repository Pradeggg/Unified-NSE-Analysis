#!/usr/bin/env python3
"""
Download NSE equity CM-UDiFF bhavcopy via new NSE API (post 2024-07-05)
and append it to data/nse_sec_full_data.csv WITHOUT changing the schema.

We:
- Call the new reports API:
  https://www.nseindia.com/api/reports?archives=[{...}]&date=DD-MMM-YYYY&type=equities&mode=single
- Extract the ZIP, read the CSV
- Map its columns back to the classic bhavcopy schema:
  SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,TOTTRDQTY,TOTTRDVAL,TIMESTAMP,TOTALTRADES,ISIN
- Append & deduplicate against existing nse_sec_full_data.csv
"""

from __future__ import annotations

import argparse
import io
import json
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional, List

import pandas as pd
import requests
from zipfile import ZipFile, BadZipFile


# Repo root: python/core/this_file.py → .parent.parent.parent
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True, parents=True)
HIST_FILE = DATA_DIR / "nse_sec_full_data.csv"


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def nse_reports_url(d: date) -> str:
    """
    Build the new NSE reports API URL for CM-UDiFF Common Bhavcopy Final (zip)
    for a given date.
    """
    date_str = d.strftime("%d-%b-%Y")  # e.g. 08-Jul-2024
    archives_param = json.dumps(
        [
            {
                "name": "CM-UDiFF Common Bhavcopy Final (zip)",
                "type": "daily-reports",
                "category": "capital-market",
                "section": "equities",
            }
        ]
    )
    return (
        "https://www.nseindia.com/api/reports"
        f"?archives={archives_param}"
        f"&date={date_str}&type=equities&mode=single"
    )


def _new_session() -> requests.Session:
    sess = requests.Session()
    # Basic headers to mimic a browser; NSE is sensitive to UA & referer
    sess.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": "https://www.nseindia.com/resources/historical-reports-capital-market-daily-monthly-archives",
        }
    )
    return sess


def download_new_bhavcopy_for_date(d: date, session: Optional[requests.Session] = None) -> Optional[pd.DataFrame]:
    """
    Download and parse the new CM-UDiFF bhavcopy for a single date.

    Returns a DataFrame mapped to the classic bhavcopy schema columns.
    """
    url = nse_reports_url(d)
    print(f"Downloading CM-UDiFF bhavcopy for {d.isoformat()} from\n  {url}")

    sess = session or _new_session()

    try:
        resp = sess.get(url, timeout=40)
    except requests.RequestException as exc:
        print(f"  ❌ HTTP error for {d}: {exc}")
        return None

    if resp.status_code != 200:
        print(f"  ❌ HTTP {resp.status_code} for {d}")
        return None

    # The response is usually a ZIP file as raw bytes
    try:
        with ZipFile(io.BytesIO(resp.content)) as zf:
            csv_name = next((n for n in zf.namelist() if n.lower().endswith(".csv")), None)
            if not csv_name:
                print(f"  ❌ No CSV in ZIP for {d}")
                return None
            with zf.open(csv_name) as f:
                raw_df = pd.read_csv(f)
    except BadZipFile as exc:
        print(f"  ❌ Invalid ZIP for {d}: {exc}")
        return None
    except Exception as exc:
        print(f"  ❌ Error reading CSV for {d}: {exc}")
        return None

    print(f"  ✓ Raw rows: {len(raw_df)}")

    # ------------------------------------------------------------------
    # Map new CM-UDiFF columns back to classic bhavcopy schema
    # NOTE: exact column names can change; this mapping is conservative
    # and falls back gracefully if a field is absent.
    # ------------------------------------------------------------------

    # Map new CM-UDiFF schema to legacy bhavcopy schema
    # New columns (from sample): TckrSymb, SctySrs, OpnPric, HghPric, LwPric,
    # ClsPric, LastPric, PrvsClsgPric, TtlTradgVol, TtlTrfVal, TtlNbOfTxsExctd,
    # BizDt / TradDt, ISIN, etc.
    colmap_candidates = {
        "SYMBOL": ["TckrSymb", "SYMBOL", "Symbol"],
        "SERIES": ["SctySrs", "SERIES", "Series"],
        "OPEN": ["OpnPric", "OPEN_PRICE", "Open Price", "OPEN"],
        "HIGH": ["HghPric", "HIGH_PRICE", "High Price", "HIGH"],
        "LOW": ["LwPric", "LOW_PRICE", "Low Price", "LOW"],
        "CLOSE": ["ClsPric", "CLOSE_PRICE", "Close Price", "CLOSE"],
        "LAST": ["LastPric", "LAST_PRICE", "Last Price", "LAST"],
        "PREVCLOSE": ["PrvsClsgPric", "PREV_CLOSE", "Prev Close", "PREVCLOSE"],
        "TOTTRDQTY": ["TtlTradgVol", "TTL_TRD_QNTY", "Traded Qty", "TOTTRDQTY"],
        "TOTTRDVAL": ["TtlTrfVal", "TOT_TRD_VAL", "TURNOVER_LACS", "Turnover Lacs", "TOTTRDVAL"],
        "TIMESTAMP": ["BizDt", "TradDt", "TIMESTAMP", "Date"],
        "TOTALTRADES": ["TtlNbOfTxsExctd", "NO_OF_TRADES", "No. of Trades", "TOTALTRADES"],
        "ISIN": ["ISIN", "ISIN_CODE"],
    }

    def resolve_column(target: str) -> Optional[str]:
        for cand in colmap_candidates.get(target, []):
            if cand in raw_df.columns:
                return cand
        return None

    mapped = pd.DataFrame()
    for target in colmap_candidates.keys():
        src = resolve_column(target)
        if src is not None:
            mapped[target] = raw_df[src]
        else:
            # Fill with NaN if not present; preserves schema
            mapped[target] = pd.NA

    # Normalize TIMESTAMP to date
    mapped["TIMESTAMP"] = pd.to_datetime(mapped["TIMESTAMP"], errors="coerce").dt.date

    # Basic row filtering
    mapped = mapped[
        mapped["SYMBOL"].notna()
        & (mapped["SYMBOL"] != "")
        & mapped["TIMESTAMP"].notna()
    ].copy()

    print(f"  ✓ Mapped rows: {len(mapped)}")
    return mapped


# ---------------------------------------------------------------------------
# Merge with existing nse_sec_full_data.csv
# ---------------------------------------------------------------------------

def append_new_api_data(start_date: date, end_date: date) -> pd.DataFrame:
    """
    Download CM-UDiFF bhavcopy data for [start_date, end_date] using the new API
    and append/deduplicate into nse_sec_full_data.csv, preserving its schema.
    """
    if start_date > end_date:
        raise ValueError("start_date must be <= end_date")

    print("=== APPENDING NEW-API NSE HISTORICAL SECURITIES DATA ===")
    print(f"Project root : {PROJECT_ROOT}")
    print(f"Data dir     : {DATA_DIR}")
    print(f"Output file  : {HIST_FILE}")
    print(f"Date range   : {start_date.isoformat()} to {end_date.isoformat()}\n")

    # Migrate from older layout (python/core/data or core/NSE-index) to repo data/
    if not HIST_FILE.exists():
        candidates = [
            Path(__file__).resolve().parent / "data" / "nse_sec_full_data.csv",
            PROJECT_ROOT / "core" / "NSE-index" / "nse_sec_full_data.csv",
        ]
        for alt in candidates:
            if alt.exists():
                DATA_DIR.mkdir(parents=True, exist_ok=True)
                shutil.copy2(alt, HIST_FILE)
                print(f"  ✓ Migrated existing stock file from {alt} → {HIST_FILE}\n")
                break
        else:
            raise FileNotFoundError(
                f"{HIST_FILE} does not exist. Run the legacy downloader first to create the base file."
            )

    existing = pd.read_csv(HIST_FILE, low_memory=False)
    if "TIMESTAMP" not in existing.columns:
        raise ValueError("Existing nse_sec_full_data.csv has no TIMESTAMP column.")
    existing["TIMESTAMP"] = pd.to_datetime(existing["TIMESTAMP"]).dt.date

    print(f"  ✓ Existing rows: {len(existing)}")
    min_existing = existing["TIMESTAMP"].min()
    max_existing = existing["TIMESTAMP"].max()
    print(f"  ✓ Existing date range: {min_existing} to {max_existing}")

    all_dates: List[date] = [
        start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)
    ]

    sess = _new_session()
    new_frames: List[pd.DataFrame] = []

    for d in all_dates:
        # Skip if this date is already in existing (by TIMESTAMP)
        if (existing["TIMESTAMP"] == d).any():
            print(f"Skipping {d.isoformat()} - already present in existing file")
            continue

        day_df = download_new_bhavcopy_for_date(d, session=sess)
        if day_df is not None and not day_df.empty:
            new_frames.append(day_df)

    if not new_frames:
        print("\nNo new data downloaded from new API for this range.")
        return existing

    new_data = pd.concat(new_frames, ignore_index=True)

    # Ensure consistent dtypes with existing where possible
    for col in ["OPEN", "HIGH", "LOW", "CLOSE", "LAST", "PREVCLOSE", "TOTTRDQTY", "TOTTRDVAL", "TOTALTRADES"]:
        if col in new_data.columns:
            new_data[col] = pd.to_numeric(new_data[col], errors="coerce")

    combined = pd.concat([existing, new_data], ignore_index=True)

    # Deduplicate by (SYMBOL, TIMESTAMP) keeping highest TOTTRDVAL
    if "TOTTRDVAL" in combined.columns:
        combined = (
            combined.sort_values(["SYMBOL", "TIMESTAMP", "TOTTRDVAL"], ascending=[True, True, False])
            .drop_duplicates(subset=["SYMBOL", "TIMESTAMP"], keep="first")
        )
    else:
        combined = (
            combined.sort_values(["SYMBOL", "TIMESTAMP"])
            .drop_duplicates(subset=["SYMBOL", "TIMESTAMP"], keep="first")
        )

    combined = combined.sort_values(["TIMESTAMP", "SYMBOL"])

    combined.to_csv(HIST_FILE, index=False)

    print("\n=== SUMMARY ===")
    print(f"Total rows after append : {len(combined)}")
    print(f"New overall date range  : {combined['TIMESTAMP'].min()} to {combined['TIMESTAMP'].max()}")
    print(f"Unique symbols          : {combined['SYMBOL'].nunique()}")
    print(f"File                    : {HIST_FILE}")
    print("✅ Append from new API completed.")

    return combined


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Append NSE CM-UDiFF equity bhavcopy data via new API into data/nse_sec_full_data.csv"
    )
    parser.add_argument(
        "--start-date",
        required=True,
        help="Start date (YYYY-MM-DD), typically the day AFTER the last date in nse_sec_full_data.csv",
    )
    parser.add_argument(
        "--end-date",
        help="End date (YYYY-MM-DD). Defaults to today if not specified.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> None:
    args = parse_args(argv)
    try:
        start = datetime.strptime(args.start_date, "%Y-%m-%d").date()
    except ValueError:
        raise SystemExit("Invalid --start-date, expected YYYY-MM-DD")

    if args.end_date:
        try:
            end = datetime.strptime(args.end_date, "%Y-%m-%d").date()
        except ValueError:
            raise SystemExit("Invalid --end-date, expected YYYY-MM-DD")
    else:
        end = date.today()

    append_new_api_data(start, end)


if __name__ == "__main__":
    main(sys.argv[1:])

