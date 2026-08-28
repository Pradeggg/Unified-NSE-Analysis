#!/usr/bin/env python3
"""
Append NSE index daily data from PR bhavcopy archives (Pr*.csv inside PR*.zip)
into data/nse_index_data.csv — same schema as R/core/download_latest_missing_data.R
expects for fixed_nse_universe_analysis.py.
"""

from __future__ import annotations

import argparse
import io
import re
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
from zipfile import ZipFile, BadZipFile

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
INDEX_FILE = DATA_DIR / "nse_index_data.csv"

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def _pr_zip_url(d: date) -> str:
    ddmmyy = d.strftime("%d%m%y").upper()
    return f"https://nsearchives.nseindia.com/archives/equities/bhavcopy/pr/PR{ddmmyy}.zip"


def _pr_csv_name(d: date) -> str:
    return f"Pr{d.strftime('%d%m%y').upper()}.csv"


def _trading_days(start: date, end: date) -> list[date]:
    out: list[date] = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            out.append(cur)
        cur += timedelta(days=1)
    return out


_PR_COLS14 = [
    "MKT",
    "SECURITY",
    "PREVCLOSE",
    "OPEN",
    "HIGH",
    "LOW",
    "CLOSE",
    "TOTTRDVAL",
    "TOTTRDQTY",
    "IND_SEC",
    "CORP_IND",
    "TOTALTRADES",
    "HI_52_WK",
    "LO_52_WK",
]


def _parse_pr_index_rows(raw: pd.DataFrame, target_date: date) -> Optional[pd.DataFrame]:
    """Filter index rows (IND_SEC & MKT) and map to schema expected by analysis."""
    df = raw.copy()
    # NSE Pr*.csv often has headers that do not match R names; align first 14 cols to bhav schema.
    if len(df.columns) >= 14 and (
        "OPEN" not in df.columns or "HIGH" not in df.columns or "IND_SEC" not in df.columns
    ):
        rest = [f"_extra_{i}" for i in range(len(df.columns) - 14)]
        df.columns = _PR_COLS14 + rest

    for col in ("IND_SEC", "MKT"):
        if col not in df.columns:
            return None

    idx = df[
        (df["IND_SEC"].astype(str).str.strip() == "Y")
        & (df["MKT"].astype(str).str.strip() == "Y")
        & df["SECURITY"].notna()
        & (df["SECURITY"].astype(str).str.strip() != "")
    ].copy()
    if idx.empty:
        return None

    if "SECURITY" not in idx.columns:
        return None

    out = pd.DataFrame(
        {
            "SYMBOL": idx["SECURITY"].astype(str).str.strip(),
            "OPEN": pd.to_numeric(idx["OPEN"], errors="coerce"),
            "HIGH": pd.to_numeric(idx["HIGH"], errors="coerce"),
            "LOW": pd.to_numeric(idx["LOW"], errors="coerce"),
            "CLOSE": pd.to_numeric(idx["CLOSE"], errors="coerce"),
            "PREVCLOSE": pd.to_numeric(idx["PREVCLOSE"], errors="coerce"),
            "TOTTRDQTY": pd.to_numeric(idx["TOTTRDQTY"], errors="coerce"),
            "TOTTRDVAL": pd.to_numeric(idx["TOTTRDVAL"], errors="coerce"),
            "TIMESTAMP": target_date.isoformat(),
            "TOTALTRADES": pd.to_numeric(idx["TOTALTRADES"], errors="coerce"),
            "HI_52_WK": pd.to_numeric(idx.get("HI_52_WK"), errors="coerce"),
            "LO_52_WK": pd.to_numeric(idx.get("LO_52_WK"), errors="coerce"),
        }
    )
    out = out[out["CLOSE"].notna() & out["OPEN"].notna() & out["HIGH"].notna() & out["LOW"].notna()]
    return out if not out.empty else None


def download_index_for_date(d: date, session: requests.Session) -> Optional[pd.DataFrame]:
    url = _pr_zip_url(d)
    print(f"Downloading index PR zip for {d.isoformat()}:\n  {url}")
    try:
        r = session.get(url, headers={"User-Agent": UA}, timeout=120)
    except requests.RequestException as e:
        print(f"  ❌ Request error: {e}")
        return None

    if r.status_code != 200:
        print(f"  ❌ HTTP {r.status_code}")
        return None

    try:
        zf = ZipFile(io.BytesIO(r.content))
    except BadZipFile:
        print("  ❌ ZIP invalid")
        return None

    pr_pattern = re.compile(r"(?i)^pr\d{6}\.csv$")
    inner = None
    for name in zf.namelist():
        base = Path(name).name
        if pr_pattern.match(base):
            inner = name
            break
    if not inner:
        # Fallback: first Pr*.csv in archive
        for name in zf.namelist():
            if Path(name).name.lower().startswith("pr") and name.lower().endswith(".csv"):
                inner = name
                break
    if not inner:
        print("  ❌ No Pr*.csv in zip")
        return None

    with tempfile.TemporaryDirectory() as tmp:
        zf.extract(inner, Path(tmp))
        csv_path = Path(tmp) / Path(inner).name
        # PR files occasionally have ragged rows; skip bad lines.
        raw = pd.read_csv(
            csv_path,
            encoding="utf-8",
            engine="python",
            on_bad_lines="skip",
        )
        if "IND_SEC" not in raw.columns:
            raw = pd.read_csv(
                csv_path,
                encoding="utf-8",
                header=None,
                engine="python",
                on_bad_lines="skip",
            )
    return _parse_pr_index_rows(raw, d)


def append_index_range(start_date: date, end_date: date) -> None:
    if start_date > end_date:
        raise ValueError("start_date must be <= end_date")

    existing: Optional[pd.DataFrame] = None
    if INDEX_FILE.exists():
        existing = pd.read_csv(INDEX_FILE, low_memory=False)
        if "TIMESTAMP" in existing.columns:
            existing["TIMESTAMP"] = pd.to_datetime(existing["TIMESTAMP"]).dt.date
        print(f"Existing index rows: {len(existing)}, max date: {existing['TIMESTAMP'].max()}")
    else:
        print(f"No existing {INDEX_FILE}; will create new file.")

    sess = requests.Session()
    days = _trading_days(start_date, end_date)
    new_frames: list[pd.DataFrame] = []

    for d in days:
        if existing is not None and (existing["TIMESTAMP"] == d).any():
            print(f"Skipping {d.isoformat()} — already in index file")
            continue
        day_df = download_index_for_date(d, sess)
        if day_df is not None and not day_df.empty:
            new_frames.append(day_df)
            print(f"  ✓ {len(day_df)} index rows for {d.isoformat()}")
        else:
            print(f"  (no index rows for {d.isoformat()} — holiday or failed)")

    if not new_frames:
        print("\nNo new index data appended.")
        return

    new_df = pd.concat(new_frames, ignore_index=True)
    if existing is not None:
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df

    combined["TIMESTAMP"] = pd.to_datetime(combined["TIMESTAMP"]).dt.strftime("%Y-%m-%d")
    combined = combined.drop_duplicates(subset=["SYMBOL", "TIMESTAMP"], keep="first")
    combined = combined.sort_values(["TIMESTAMP", "SYMBOL"])
    combined.to_csv(INDEX_FILE, index=False)

    print("\n=== INDEX SUMMARY ===")
    print(f"Rows written: {len(combined)}")
    print(f"Date range:   {combined['TIMESTAMP'].min()} to {combined['TIMESTAMP'].max()}")
    print(f"File:         {INDEX_FILE}")


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Append NSE index data from PR archives into data/nse_index_data.csv")
    p.add_argument("--start-date", help="YYYY-MM-DD (default: day after last date in file, or 2024-01-01 if new)")
    p.add_argument("--end-date", required=True, help="YYYY-MM-DD inclusive")
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> None:
    args = parse_args(argv)
    end = datetime.strptime(args.end_date, "%Y-%m-%d").date()

    if args.start_date:
        start = datetime.strptime(args.start_date, "%Y-%m-%d").date()
    elif INDEX_FILE.exists():
        ex = pd.read_csv(INDEX_FILE, usecols=["TIMESTAMP"], low_memory=False)
        ex["TIMESTAMP"] = pd.to_datetime(ex["TIMESTAMP"]).dt.date
        last = ex["TIMESTAMP"].max()
        start = last + timedelta(days=1)
        print(f"Default start from existing file: {start.isoformat()} (after {last})")
    else:
        start = date(2024, 1, 1)
        print(f"No existing index file; using default start {start.isoformat()}")

    append_index_range(start, end)


if __name__ == "__main__":
    main(sys.argv[1:])
