#!/usr/bin/env python3
"""
Download and build historical NSE securities file: data/nse_sec_full_data.csv

This script:
- Downloads daily NSE equity bhavcopy files from the NSE archives
- Extracts and normalizes the data
- Builds or updates a consolidated historical CSV compatible with:
  - load_latest_data.R  (expects data/nse_sec_full_data.csv)
  - fixed_nse_universe_analysis.py
"""

from __future__ import annotations

import argparse
import io
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
from zipfile import ZipFile, BadZipFile


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def get_project_root() -> Path:
    """
    Repo root: python/core/ → go up twice (core, python) to .../python, once more to repo.
    Writes consolidated CSV to <repo>/data/nse_sec_full_data.csv.
    """
    return Path(__file__).resolve().parent.parent.parent


PROJECT_ROOT: Path = get_project_root()
DATA_DIR: Path = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True, parents=True)

HIST_FILE: Path = DATA_DIR / "nse_sec_full_data.csv"


def nse_bhav_url(d: date) -> str:
    """
    Construct the NSE bhavcopy URL for a given date.

    NSE equity bhavcopy archives typically follow the pattern:
    https://archives.nseindia.com/content/historical/EQUITIES/YYYY/MON/cmDDMONYYYYbhav.csv.zip
    """
    yyyy = d.strftime("%Y")
    mon = d.strftime("%b").upper()
    dd = d.strftime("%d")
    return (
        f"https://archives.nseindia.com/content/historical/EQUITIES/"
        f"{yyyy}/{mon}/cm{dd}{mon}{yyyy}bhav.csv.zip"
    )


# ---------------------------------------------------------------------------
# Core download & parsing logic
# ---------------------------------------------------------------------------

def download_bhavcopy_for_date(d: date, session: Optional[requests.Session] = None) -> Optional[pd.DataFrame]:
    """
    Download and parse the NSE bhavcopy for a single date.

    Returns:
        pandas.DataFrame with at least SYMBOL and TIMESTAMP columns,
        or None if download/parse fails (e.g., holiday, missing file).
    """
    url = nse_bhav_url(d)
    print(f"Downloading bhavcopy for {d.isoformat()} from {url}")

    sess = session or requests.Session()
    try:
        resp = sess.get(
            url,
            headers={
                # Use a browser-like User-Agent to avoid simple blocks
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        print(f"  ❌ HTTP error for {d}: {exc}")
        return None

    if resp.status_code != 200:
        print(f"  ❌ HTTP {resp.status_code} for {d} (likely holiday or missing file)")
        return None

    try:
        with ZipFile(io.BytesIO(resp.content)) as zf:
            # Find first CSV file inside the ZIP
            csv_name = next((n for n in zf.namelist() if n.lower().endswith(".csv")), None)
            if not csv_name:
                print(f"  ❌ No CSV found in ZIP for {d}")
                return None

            with zf.open(csv_name) as f:
                df = pd.read_csv(f)
    except BadZipFile as exc:
        print(f"  ❌ Invalid ZIP for {d}: {exc}")
        return None
    except Exception as exc:
        print(f"  ❌ Error reading CSV for {d}: {exc}")
        return None

    # Basic structural validation
    required_cols = {"SYMBOL", "TIMESTAMP"}
    if not required_cols.issubset(df.columns):
        print(f"  ❌ Missing required columns in bhavcopy for {d}: {required_cols - set(df.columns)}")
        return None

    # Normalize and filter rows
    try:
        df["TIMESTAMP"] = pd.to_datetime(df["TIMESTAMP"], format="%d-%b-%Y").dt.date
    except Exception:
        # Fallback: let pandas infer date format if explicit parsing fails
        df["TIMESTAMP"] = pd.to_datetime(df["TIMESTAMP"], errors="coerce").dt.date

    df = df[
        df["SYMBOL"].notna()
        & (df["SYMBOL"] != "")
        & df["TIMESTAMP"].notna()
    ].copy()

    print(f"  ✓ Loaded {len(df)} rows for {d}")
    return df


def build_or_update_historical_file(start_date: date, end_date: date) -> pd.DataFrame:
    """
    Build or update the consolidated historical securities file.

    - Reads existing data from HIST_FILE if present
    - Downloads bhavcopies for the requested date range
    - Appends new rows and deduplicates by (SYMBOL, TIMESTAMP)
    - Writes the result back to HIST_FILE
    """
    if start_date > end_date:
        raise ValueError("start_date must be <= end_date")

    print("=== BUILDING / UPDATING NSE HISTORICAL SECURITIES FILE ===")
    print(f"Project root : {PROJECT_ROOT}")
    print(f"Data dir     : {DATA_DIR}")
    print(f"Output file  : {HIST_FILE}")
    print(f"Date range   : {start_date.isoformat()} to {end_date.isoformat()}\n")

    existing: Optional[pd.DataFrame] = None
    if HIST_FILE.exists():
        print("Loading existing historical file...")
        existing = pd.read_csv(HIST_FILE, low_memory=False)
        if "TIMESTAMP" not in existing.columns:
            raise ValueError("Existing nse_sec_full_data.csv has no TIMESTAMP column.")
        existing["TIMESTAMP"] = pd.to_datetime(existing["TIMESTAMP"]).dt.date
        print(f"  ✓ Existing rows: {len(existing)}")

    all_dates = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]
    session = requests.Session()

    new_frames: list[pd.DataFrame] = []
    for d in all_dates:
        # Skip days already present in existing data, if available
        if existing is not None and (existing["TIMESTAMP"] == d).any():
            print(f"Skipping {d.isoformat()} - already present in existing file")
            continue

        day_df = download_bhavcopy_for_date(d, session=session)
        if day_df is not None and not day_df.empty:
            new_frames.append(day_df)

    if not new_frames and existing is not None:
        print("\nNo new data downloaded; existing file already covers this range.")
        return existing

    new_data = pd.concat(new_frames, ignore_index=True) if new_frames else None

    if existing is not None and new_data is not None:
        combined = pd.concat([existing, new_data], ignore_index=True)
    elif existing is not None:
        combined = existing
    elif new_data is not None:
        combined = new_data
    else:
        raise RuntimeError("No data available to write to nse_sec_full_data.csv")

    # Ensure key numeric fields are numeric to avoid later issues
    for col in ["OPEN", "HIGH", "LOW", "CLOSE", "TOTTRDQTY", "TOTTRDVAL"]:
        if col in combined.columns:
            combined[col] = pd.to_numeric(combined[col], errors="coerce")

    # Deduplicate by SYMBOL/TIMESTAMP, keeping row with highest TOTTRDVAL
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

    # Write final consolidated CSV
    combined.to_csv(HIST_FILE, index=False)

    print("\n=== SUMMARY ===")
    print(f"Total rows written : {len(combined)}")
    print(f"Date range         : {combined['TIMESTAMP'].min()} to {combined['TIMESTAMP'].max()}")
    print(f"Unique symbols     : {combined['SYMBOL'].nunique()}")
    print(f"File               : {HIST_FILE}")
    print("✅ Historical NSE securities file is ready.")

    return combined


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """
    Parse command-line arguments for controlling the download range.
    """
    parser = argparse.ArgumentParser(
        description="Download NSE historical equity data and build data/nse_sec_full_data.csv"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--days",
        type=int,
        default=60,
        help="Number of most recent calendar days to download (default: 60)",
    )
    group.add_argument(
        "--start-date",
        type=str,
        help="Start date in YYYY-MM-DD format (overrides --days when used with --end-date)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        help="End date in YYYY-MM-DD format (used with --start-date; defaults to today)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> None:
    """
    Main entry point: determine date range, then build/update the historical file.
    """
    args = parse_args(argv)

    today = date.today()

    if args.start_date:
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
            end = today
    else:
        # Use relative range based on --days (optionally anchor --end-date for backfills)
        if args.days <= 0:
            raise SystemExit("--days must be a positive integer")
        if args.end_date:
            try:
                end = datetime.strptime(args.end_date, "%Y-%m-%d").date()
            except ValueError:
                raise SystemExit("Invalid --end-date, expected YYYY-MM-DD")
        else:
            end = today
        start = end - timedelta(days=args.days - 1)

    build_or_update_historical_file(start, end)


if __name__ == "__main__":
    main(sys.argv[1:])

