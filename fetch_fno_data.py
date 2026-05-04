#!/usr/bin/env python3
"""F&O Open Interest + Put-Call Ratio signal generator (P1-2).

Downloads NSE FO bhavcopy data, computes per-symbol derivative signals,
and exposes an enrichment function for sector_rotation_report.py.

Signals computed:
  - PCR (put-call ratio by open interest)
  - OI change % (5-day rolling)
  - Max pain (strike where most options expire worthless)
  - FNO buildup classification (long/short buildup, unwinding, covering)
  - Composite FNO signal (BULL / BEAR / NEUTRAL)

Data source: NSE FO UDiFF Common Bhavcopy (free, daily)
  URL: https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{YYYYMMDD}_F_0000.csv.zip
  Fallback (legacy): https://nsearchives.nseindia.com/content/historical/DERIVATIVES/{YYYY}/{MMM}/fo{DDMMMYYYY}bhav.csv.zip

Cache: data/_fno_cache/ directory with per-date CSV files; 24h TTL for latest.

Usage:
  # Standalone
  python fetch_fno_data.py                        # fetch today's data
  python fetch_fno_data.py --date 2026-05-02      # fetch specific date
  python fetch_fno_data.py --backfill 5           # fetch last 5 trading days

  # As module (from sector_rotation_report.py)
  from fetch_fno_data import enrich_with_fno_signals
  candidates = enrich_with_fno_signals(candidates)
"""

from __future__ import annotations

import argparse
import io
import math
import os
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# ── Paths ──
ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / "data" / "_fno_cache"
SIGNALS_CSV = ROOT / "data" / "fno_signals.csv"
CACHE_TTL_HOURS = 24

# ── NSE access config ──
_NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.8",
    "Referer": "https://www.nseindia.com/market-data/derivatives-market-watch",
}
_SLEEP_BETWEEN_CALLS = 2  # seconds — NSE rate-limit courtesy

# ── FNO bhavcopy column names (new format) ──
# The NSE FO bhavcopy CSV columns may vary slightly; we normalise on load.
_COL_MAP = {
    "TckrSymb": "SYMBOL",
    "FinInstrmTp": "INSTRUMENT",
    "XpryDt": "EXPIRY_DATE",
    "StrkPric": "STRIKE_PRICE",
    "OptnTp": "OPTION_TYPE",
    "OpnIntrst": "OPEN_INTEREST",
    "ChngInOpnIntrst": "CHANGE_IN_OI",
    "TtlTradgVol": "VOLUME",
    "ClsPric": "CLOSE",
    "SttlmPric": "SETTLE_PRICE",
    "PrvsClsgPric": "PREV_CLOSE",
    # Fallback legacy column names
    "SYMBOL": "SYMBOL",
    "INSTRUMENT": "INSTRUMENT",
    "EXPIRY_DT": "EXPIRY_DATE",
    "STRIKE_PR": "STRIKE_PRICE",
    "OPTION_TYP": "OPTION_TYPE",
    "OPEN_INT": "OPEN_INTEREST",
    "CHG_IN_OI": "CHANGE_IN_OI",
    "CONTRACTS": "VOLUME",
    "CLOSE": "CLOSE",
    "SETTLE_PR": "SETTLE_PRICE",
}


# ─────────────────────────────────────────────
# SECTION 1: DATA FETCHING
# ─────────────────────────────────────────────

# PG: NSE archives require session cookies — we must first visit the main page
# to obtain them, then download with that session. Using curl with a cookie jar.
_COOKIE_JAR = CACHE_DIR / "_nse_cookies.txt"


def _ensure_nse_cookies() -> bool:
    """Hit the NSE homepage to populate the cookie jar (required for archive downloads).

    Cookies are refreshed if older than 10 minutes.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if _COOKIE_JAR.exists():
        age_minutes = (time.time() - _COOKIE_JAR.stat().st_mtime) / 60
        if age_minutes < 10:
            return True

    cmd = [
        "curl", "-sS", "-L",
        "-c", str(_COOKIE_JAR),
        "-o", "/dev/null",
        "--max-time", "30",
        "-H", f"User-Agent: {_NSE_HEADERS['User-Agent']}",
        "-H", "Accept: text/html,application/xhtml+xml",
        "-H", f"Accept-Language: {_NSE_HEADERS['Accept-Language']}",
        "https://www.nseindia.com/market-data/derivatives-market-watch",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
        return _COOKIE_JAR.exists() and _COOKIE_JAR.stat().st_size > 0
    except (subprocess.TimeoutExpired, OSError) as exc:
        print(f"  Cookie setup failed: {exc}")
        return False


def _curl_download(url: str, out_path: Path, timeout: int = 60) -> bool:
    """Download a URL using curl subprocess with NSE session cookies.

    Returns True on success, False on failure (e.g. 404, timeout).
    """
    # PG: using curl subprocess per design principle #3 in docs/BACKLOG.md
    _ensure_nse_cookies()
    cmd = [
        "curl", "-sS", "-L",
        "-b", str(_COOKIE_JAR),
        "-o", str(out_path),
        "-w", "%{http_code}",
        "--max-time", str(timeout),
        "-H", f"User-Agent: {_NSE_HEADERS['User-Agent']}",
        "-H", f"Referer: {_NSE_HEADERS['Referer']}",
        "-H", "Accept: */*",
        url,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 10)
        http_code = result.stdout.strip()
        if http_code == "200" and out_path.exists() and out_path.stat().st_size > 100:
            return True
        # Clean up failed download
        if out_path.exists():
            out_path.unlink()
        return False
    except (subprocess.TimeoutExpired, OSError) as exc:
        print(f"  curl failed for {url}: {exc}")
        if out_path.exists():
            out_path.unlink()
        return False


def _bhavcopy_url_new(dt: datetime) -> str:
    """New-format FO UDiFF bhavcopy URL (2024+ format). Uses YYYYMMDD."""
    # PG: discovered from NSE reports page — date is YYYYMMDD, not DDMMYYYY
    return (
        f"https://nsearchives.nseindia.com/content/fo/"
        f"BhavCopy_NSE_FO_0_0_0_{dt.strftime('%Y%m%d')}_F_0000.csv.zip"
    )


def _bhavcopy_url_legacy(dt: datetime) -> str:
    """Legacy FO bhavcopy URL (fallback)."""
    return (
        f"https://nsearchives.nseindia.com/content/historical/DERIVATIVES/"
        f"{dt.strftime('%Y')}/{dt.strftime('%b').upper()}/"
        f"fo{dt.strftime('%d%b%Y').upper()}bhav.csv.zip"
    )


def fetch_fo_bhavcopy(dt: datetime) -> pd.DataFrame | None:
    """Download and parse NSE FO bhavcopy for a given date.

    Tries new URL format first, then legacy. Caches to data/_fno_cache/.
    Returns normalised DataFrame or None if data unavailable (e.g. holiday).
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    date_str = dt.strftime("%Y%m%d")
    cache_csv = CACHE_DIR / f"fo_bhav_{date_str}.csv"

    # Check cache first
    if cache_csv.exists() and cache_csv.stat().st_size > 100:
        try:
            df = pd.read_csv(cache_csv)
            if len(df) > 0:
                return df
        except Exception:
            pass  # re-download if cache is corrupt

    # Download ZIP → extract CSV
    zip_path = CACHE_DIR / f"fo_bhav_{date_str}.zip"
    downloaded = False

    for url_fn in [_bhavcopy_url_new, _bhavcopy_url_legacy]:
        url = url_fn(dt)
        print(f"  Fetching FO bhavcopy: {url}")
        if _curl_download(url, zip_path):
            downloaded = True
            break
        time.sleep(_SLEEP_BETWEEN_CALLS)

    if not downloaded:
        print(f"  FO bhavcopy not available for {dt.strftime('%Y-%m-%d')} (holiday or not yet published).")
        return None

    # Extract CSV from ZIP
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if not csv_names:
                print(f"  No CSV found inside ZIP for {date_str}.")
                return None
            with zf.open(csv_names[0]) as f:
                df = pd.read_csv(io.TextIOWrapper(f, encoding="utf-8"))
    except (zipfile.BadZipFile, Exception) as exc:
        print(f"  Failed to extract FO bhavcopy: {exc}")
        return None
    finally:
        if zip_path.exists():
            zip_path.unlink()

    # Normalise column names
    df = df.rename(columns=lambda c: c.strip())
    rename_map = {}
    for orig, target in _COL_MAP.items():
        if orig in df.columns and target not in rename_map.values():
            rename_map[orig] = target
    df = df.rename(columns=rename_map)

    # Save to cache
    df.to_csv(cache_csv, index=False)
    print(f"  Cached FO data: {len(df)} rows → {cache_csv.name}")
    return df


def _previous_trading_days(n: int, from_date: datetime | None = None) -> list[datetime]:
    """Return the last N calendar dates to try (skipping weekends).

    NSE holidays are not known here, so we try dates and let 404s handle holidays.
    """
    dt = from_date or datetime.now()
    days = []
    attempt = 0
    while len(days) < n and attempt < n * 3:
        attempt += 1
        dt -= timedelta(days=1)
        if dt.weekday() < 5:  # Mon-Fri
            days.append(dt)
    return days


def load_recent_fo_data(lookback_days: int = 6, reference_date: datetime | None = None) -> pd.DataFrame:
    """Load FO bhavcopy for the last N trading days (for OI change computation).

    Returns combined DataFrame with a DATE column, or empty DataFrame if no data.
    """
    ref = reference_date or datetime.now()
    # Try today first (if market day), then previous days
    dates_to_try = []
    if ref.weekday() < 5:
        dates_to_try.append(ref)
    dates_to_try.extend(_previous_trading_days(lookback_days, ref))

    frames = []
    for dt in dates_to_try:
        df = fetch_fo_bhavcopy(dt)
        if df is not None and not df.empty:
            df["DATE"] = dt.strftime("%Y-%m-%d")
            frames.append(df)
        time.sleep(0.5)  # courtesy pause between downloads

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


# ─────────────────────────────────────────────
# SECTION 2: SIGNAL COMPUTATION
# ─────────────────────────────────────────────

def compute_pcr(fo_df: pd.DataFrame) -> pd.DataFrame:
    """Compute Put-Call Ratio by Open Interest for each symbol (latest date).

    PCR > 1.2: BULLISH (contrarian — heavy put writing = support)
    PCR < 0.7: BEARISH (complacency — too many calls)
    PCR 0.7-1.2: NEUTRAL
    """
    # Filter to options only — UDiFF uses STO (stock option), IDO (index option)
    # PG: new format instrument types: STF/STO/IDF/IDO; legacy: FUTSTK/OPTSTK/FUTIDX/OPTIDX
    opts = fo_df[
        (fo_df["INSTRUMENT"].isin(["OPTSTK", "OPTIDX", "STO", "IDO"]))
        & (fo_df["OPTION_TYPE"].isin(["CE", "PE"]))
    ].copy()

    if opts.empty:
        return pd.DataFrame(columns=["SYMBOL", "FNO_PCR"])

    # Use latest date only
    if "DATE" in opts.columns:
        latest = opts["DATE"].max()
        opts = opts[opts["DATE"] == latest]

    # Ensure OI is numeric
    opts["OPEN_INTEREST"] = pd.to_numeric(opts["OPEN_INTEREST"], errors="coerce").fillna(0)

    # PCR = put OI / call OI per symbol
    call_oi = opts[opts["OPTION_TYPE"] == "CE"].groupby("SYMBOL")["OPEN_INTEREST"].sum()
    put_oi = opts[opts["OPTION_TYPE"] == "PE"].groupby("SYMBOL")["OPEN_INTEREST"].sum()
    pcr = (put_oi / call_oi.replace(0, np.nan)).round(3)
    pcr = pcr.reset_index()
    pcr.columns = ["SYMBOL", "FNO_PCR"]
    return pcr


def compute_oi_change(fo_df: pd.DataFrame) -> pd.DataFrame:
    """Compute 5-day OI change % for futures (nearest expiry).

    OI increase + price up = long buildup (BULLISH)
    OI increase + price down = short buildup (BEARISH)
    OI decrease + price up = short covering (MILDLY BULLISH)
    OI decrease + price down = long unwinding (MILDLY BEARISH)
    """
    # Filter to futures only — UDiFF uses STF (stock future), IDF (index future)
    # PG: support both new (STF/IDF) and legacy (FUTSTK/FUTIDX) instrument codes
    futs = fo_df[fo_df["INSTRUMENT"].isin(["FUTSTK", "FUTIDX", "STF", "IDF"])].copy()
    if futs.empty or "DATE" not in futs.columns:
        return pd.DataFrame(columns=["SYMBOL", "FNO_OI_CHANGE_5D", "FNO_PRICE_CHANGE", "FNO_BUILDUP"])

    futs["OPEN_INTEREST"] = pd.to_numeric(futs["OPEN_INTEREST"], errors="coerce").fillna(0)
    futs["CLOSE"] = pd.to_numeric(futs["CLOSE"], errors="coerce").fillna(0)

    # For each symbol, take nearest expiry on each date
    dates = sorted(futs["DATE"].unique())
    if len(dates) < 2:
        return pd.DataFrame(columns=["SYMBOL", "FNO_OI_CHANGE_5D", "FNO_PRICE_CHANGE", "FNO_BUILDUP"])

    latest_date = dates[-1]
    earliest_date = dates[0]

    # Latest day data — pick nearest expiry per symbol
    latest = futs[futs["DATE"] == latest_date].copy()
    if "EXPIRY_DATE" in latest.columns:
        # PG: UDiFF uses YYYY-MM-DD; legacy uses DD-MMM-YYYY — let pandas infer
        latest["EXPIRY_DATE"] = pd.to_datetime(latest["EXPIRY_DATE"], errors="coerce")
        latest = latest.sort_values("EXPIRY_DATE").drop_duplicates(subset=["SYMBOL"], keep="first")

    # Earliest day data — pick nearest expiry per symbol
    earliest = futs[futs["DATE"] == earliest_date].copy()
    if "EXPIRY_DATE" in earliest.columns:
        earliest["EXPIRY_DATE"] = pd.to_datetime(earliest["EXPIRY_DATE"], errors="coerce")
        earliest = earliest.sort_values("EXPIRY_DATE").drop_duplicates(subset=["SYMBOL"], keep="first")

    merged = latest[["SYMBOL", "OPEN_INTEREST", "CLOSE"]].merge(
        earliest[["SYMBOL", "OPEN_INTEREST", "CLOSE"]],
        on="SYMBOL", suffixes=("_now", "_prev"),
    )

    # OI change %
    merged["FNO_OI_CHANGE_5D"] = (
        (merged["OPEN_INTEREST_now"] - merged["OPEN_INTEREST_prev"])
        / merged["OPEN_INTEREST_prev"].replace(0, np.nan) * 100
    ).round(2)

    # Price change %
    merged["FNO_PRICE_CHANGE"] = (
        (merged["CLOSE_now"] - merged["CLOSE_prev"])
        / merged["CLOSE_prev"].replace(0, np.nan) * 100
    ).round(2)

    # Buildup classification
    # PG: classify based on OI+price direction per standard F&O analysis framework
    conditions = [
        (merged["FNO_OI_CHANGE_5D"] > 5) & (merged["FNO_PRICE_CHANGE"] > 0),
        (merged["FNO_OI_CHANGE_5D"] > 5) & (merged["FNO_PRICE_CHANGE"] <= 0),
        (merged["FNO_OI_CHANGE_5D"] <= -5) & (merged["FNO_PRICE_CHANGE"] > 0),
        (merged["FNO_OI_CHANGE_5D"] <= -5) & (merged["FNO_PRICE_CHANGE"] <= 0),
    ]
    choices = ["LONG_BUILDUP", "SHORT_BUILDUP", "SHORT_COVERING", "LONG_UNWINDING"]
    merged["FNO_BUILDUP"] = np.select(conditions, choices, default="NEUTRAL")

    return merged[["SYMBOL", "FNO_OI_CHANGE_5D", "FNO_PRICE_CHANGE", "FNO_BUILDUP"]]


def compute_max_pain(fo_df: pd.DataFrame) -> pd.DataFrame:
    """Compute max pain (price at which most options expire worthless) per symbol.

    Max pain = strike price where the total value of puts + calls that expire ITM is minimised.
    Useful as a magnet level — price tends to gravitate toward max pain near expiry.
    """
    # PG: support both new (STO/IDO) and legacy (OPTSTK/OPTIDX) instrument codes
    opts = fo_df[
        (fo_df["INSTRUMENT"].isin(["OPTSTK", "OPTIDX", "STO", "IDO"]))
        & (fo_df["OPTION_TYPE"].isin(["CE", "PE"]))
    ].copy()

    if opts.empty:
        return pd.DataFrame(columns=["SYMBOL", "FNO_MAX_PAIN"])

    # Use latest date only
    if "DATE" in opts.columns:
        latest = opts["DATE"].max()
        opts = opts[opts["DATE"] == latest]

    opts["STRIKE_PRICE"] = pd.to_numeric(opts["STRIKE_PRICE"], errors="coerce")
    opts["OPEN_INTEREST"] = pd.to_numeric(opts["OPEN_INTEREST"], errors="coerce").fillna(0)

    # Pick nearest expiry per symbol
    if "EXPIRY_DATE" in opts.columns:
        opts["EXPIRY_DATE"] = pd.to_datetime(opts["EXPIRY_DATE"], errors="coerce")
        nearest_expiry = opts.groupby("SYMBOL")["EXPIRY_DATE"].min().reset_index()
        nearest_expiry.columns = ["SYMBOL", "NEAREST_EXPIRY"]
        opts = opts.merge(nearest_expiry, on="SYMBOL")
        opts = opts[opts["EXPIRY_DATE"] == opts["NEAREST_EXPIRY"]]

    results = []
    for sym, group in opts.groupby("SYMBOL"):
        strikes = sorted(group["STRIKE_PRICE"].dropna().unique())
        if len(strikes) < 3:
            continue

        calls = group[group["OPTION_TYPE"] == "CE"][["STRIKE_PRICE", "OPEN_INTEREST"]].set_index("STRIKE_PRICE")
        puts = group[group["OPTION_TYPE"] == "PE"][["STRIKE_PRICE", "OPEN_INTEREST"]].set_index("STRIKE_PRICE")

        min_pain = float("inf")
        max_pain_strike = np.nan

        for test_price in strikes:
            # Pain for call buyers: call is ITM when strike < test_price
            call_pain = 0
            for strike, row in calls.iterrows():
                if strike < test_price:
                    call_pain += (test_price - strike) * row["OPEN_INTEREST"]

            # Pain for put buyers: put is ITM when strike > test_price
            put_pain = 0
            for strike, row in puts.iterrows():
                if strike > test_price:
                    put_pain += (strike - test_price) * row["OPEN_INTEREST"]

            total_pain = call_pain + put_pain
            if total_pain < min_pain:
                min_pain = total_pain
                max_pain_strike = test_price

        results.append({"SYMBOL": sym, "FNO_MAX_PAIN": max_pain_strike})

    if not results:
        return pd.DataFrame(columns=["SYMBOL", "FNO_MAX_PAIN"])
    return pd.DataFrame(results)


def compute_fno_composite_signal(pcr_df: pd.DataFrame, oi_df: pd.DataFrame) -> pd.DataFrame:
    """Derive composite FNO signal from PCR + OI buildup.

    Signal logic:
      BULL: PCR > 1.0 AND (LONG_BUILDUP or SHORT_COVERING)
      BEAR: PCR < 0.7 AND (SHORT_BUILDUP or LONG_UNWINDING)
      NEUTRAL: everything else
    """
    # Start with all symbols from both sources
    if pcr_df.empty and oi_df.empty:
        return pd.DataFrame(columns=["SYMBOL", "FNO_SIGNAL"])

    merged = pcr_df.merge(oi_df, on="SYMBOL", how="outer") if not pcr_df.empty and not oi_df.empty else (
        pcr_df.copy() if not pcr_df.empty else oi_df.copy()
    )

    pcr = merged.get("FNO_PCR", pd.Series(dtype=float))
    buildup = merged.get("FNO_BUILDUP", pd.Series(dtype=str)).fillna("")

    # PG: composite signal blends contrarian PCR with directional OI buildup
    conditions = [
        (pcr > 1.0) & (buildup.isin(["LONG_BUILDUP", "SHORT_COVERING"])),
        (pcr < 0.7) & (buildup.isin(["SHORT_BUILDUP", "LONG_UNWINDING"])),
        (buildup == "LONG_BUILDUP") & (pcr >= 0.7),    # OI confirms even if PCR is neutral
        (buildup == "SHORT_BUILDUP") & (pcr <= 1.0),   # OI confirms bearish
    ]
    choices = ["BULL", "BEAR", "MILD_BULL", "MILD_BEAR"]
    merged["FNO_SIGNAL"] = np.select(conditions, choices, default="NEUTRAL")

    return merged[["SYMBOL", "FNO_SIGNAL"]]


def generate_fno_signals(reference_date: datetime | None = None) -> pd.DataFrame:
    """Full pipeline: fetch data → compute all signals → return merged DataFrame.

    Returns DataFrame with columns:
      SYMBOL, FNO_PCR, FNO_OI_CHANGE_5D, FNO_PRICE_CHANGE, FNO_BUILDUP,
      FNO_MAX_PAIN, FNO_SIGNAL
    """
    ref = reference_date or datetime.now()
    print(f"\n{'='*60}")
    print(f"F&O Signal Generation — {ref.strftime('%Y-%m-%d')}")
    print(f"{'='*60}")

    # Load recent FO data (today + 5 previous trading days)
    fo_data = load_recent_fo_data(lookback_days=6, reference_date=ref)
    if fo_data.empty:
        print("  No FO bhavcopy data available. Returning empty signals.")
        return pd.DataFrame(columns=["SYMBOL", "FNO_PCR", "FNO_OI_CHANGE_5D",
                                      "FNO_PRICE_CHANGE", "FNO_BUILDUP",
                                      "FNO_MAX_PAIN", "FNO_SIGNAL"])

    dates_loaded = sorted(fo_data["DATE"].unique())
    print(f"  Loaded {len(fo_data)} FO rows across {len(dates_loaded)} trading days: {dates_loaded[0]} → {dates_loaded[-1]}")

    # Compute individual signal components
    pcr_df = compute_pcr(fo_data)
    print(f"  PCR computed for {len(pcr_df)} symbols")

    oi_df = compute_oi_change(fo_data)
    print(f"  OI change computed for {len(oi_df)} symbols")

    mp_df = compute_max_pain(fo_data)
    print(f"  Max pain computed for {len(mp_df)} symbols")

    signal_df = compute_fno_composite_signal(pcr_df, oi_df)
    print(f"  Composite signal: {signal_df['FNO_SIGNAL'].value_counts().to_dict()}")

    # Merge all signal components
    result = pcr_df
    for df in [oi_df, mp_df, signal_df]:
        if not df.empty:
            result = result.merge(df, on="SYMBOL", how="outer") if not result.empty else df

    # Save to cache
    SIGNALS_CSV.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(SIGNALS_CSV, index=False)
    print(f"  Saved {len(result)} FNO signals → {SIGNALS_CSV}")

    return result


# ─────────────────────────────────────────────
# SECTION 3: INTEGRATION API (for sector_rotation_report.py)
# ─────────────────────────────────────────────

def _cache_is_fresh() -> bool:
    """Check if the cached signals CSV is within TTL."""
    if not SIGNALS_CSV.exists():
        return False
    age_hours = (time.time() - SIGNALS_CSV.stat().st_mtime) / 3600
    return age_hours < CACHE_TTL_HOURS


def load_fno_signals() -> pd.DataFrame:
    """Load FNO signals — from cache if fresh, otherwise regenerate.

    This is the primary entry point for sector_rotation_report.py.
    """
    if _cache_is_fresh():
        try:
            df = pd.read_csv(SIGNALS_CSV)
            if not df.empty:
                print(f"  FNO signals: loaded {len(df)} rows from cache.")
                return df
        except Exception:
            pass

    return generate_fno_signals()


def enrich_with_fno_signals(candidates: pd.DataFrame) -> pd.DataFrame:
    """Merge FNO signals into the candidates DataFrame.

    Adds columns: FNO_PCR, FNO_OI_CHANGE_5D, FNO_BUILDUP, FNO_MAX_PAIN, FNO_SIGNAL.
    Non-F&O stocks get None values (graceful degradation).

    Called from sector_rotation_report.py → generate_report() after rank_stock_candidates().
    """
    if candidates.empty or "SYMBOL" not in candidates.columns:
        return candidates

    try:
        fno = load_fno_signals()
    except Exception as exc:
        print(f"  FNO signal enrichment skipped ({exc}). Filling with None.")
        fno = pd.DataFrame()

    fno_cols = ["FNO_PCR", "FNO_OI_CHANGE_5D", "FNO_BUILDUP", "FNO_MAX_PAIN", "FNO_SIGNAL"]

    if fno.empty:
        # PG: graceful degradation — add empty FNO columns so downstream code doesn't break
        for col in fno_cols:
            candidates[col] = None
        return candidates

    # Merge on SYMBOL (left join — keep all candidates, add FNO where available)
    merge_cols = ["SYMBOL"] + [c for c in fno_cols if c in fno.columns]
    result = candidates.merge(fno[merge_cols], on="SYMBOL", how="left")

    # Ensure all FNO columns exist even if some signal components were empty
    for col in fno_cols:
        if col not in result.columns:
            result[col] = None

    n_enriched = result["FNO_SIGNAL"].notna().sum()
    print(f"  FNO enrichment: {n_enriched}/{len(result)} candidates have F&O data.")

    return result


# ─────────────────────────────────────────────
# SECTION 4: HTML BADGE (for render_html_interactive)
# ─────────────────────────────────────────────

def fno_badge_html(fno_signal: str, buildup: str = "", pcr: float | None = None) -> str:
    """Return an HTML badge for the FNO signal.

    Used by sector_rotation_report.py in the candidates table.
    """
    signal = str(fno_signal or "").strip().upper()
    if not signal or signal in ("", "NAN", "NONE"):
        return '<span class="fno fno-na">—</span>'

    label_map = {
        "BULL":      "🟢 Bull",
        "MILD_BULL": "🟡 Mild Bull",
        "NEUTRAL":   "⚪ Neutral",
        "MILD_BEAR": "🟠 Mild Bear",
        "BEAR":      "🔴 Bear",
    }
    css_map = {
        "BULL":      "fno-bull",
        "MILD_BULL": "fno-mbull",
        "NEUTRAL":   "fno-neutral",
        "MILD_BEAR": "fno-mbear",
        "BEAR":      "fno-bear",
    }
    label = label_map.get(signal, signal)
    css = css_map.get(signal, "fno-neutral")

    # Add buildup detail if available
    buildup_str = str(buildup or "").strip().upper()
    buildup_label = {
        "LONG_BUILDUP":   "Long Buildup",
        "SHORT_BUILDUP":  "Short Buildup",
        "SHORT_COVERING": "Short Cover",
        "LONG_UNWINDING": "Long Unwind",
    }.get(buildup_str, "")

    pcr_str = f"PCR: {float(pcr):.2f}" if pcr and not (isinstance(pcr, float) and math.isnan(pcr)) else ""

    detail_parts = [p for p in [buildup_label, pcr_str] if p]
    detail = f'<div class="fno-detail">{" · ".join(detail_parts)}</div>' if detail_parts else ""

    return f'<span class="fno {css}">{label}</span>{detail}'


# CSS rules to inject into the HTML <style> block
FNO_CSS = """
/* ---- F&O SIGNAL BADGES (P1-2) ---- */
.fno{display:inline-block;padding:2px 7px;border-radius:10px;font-size:9.5px;font-weight:700;white-space:nowrap}
.fno-bull{background:#dcfce7;color:#15803d;border:1px solid #86efac}
.fno-mbull{background:#fef9c3;color:#854d0e}
.fno-neutral{background:#f1f5f9;color:#64748b}
.fno-mbear{background:#ffedd5;color:#c2410c}
.fno-bear{background:#fee2e2;color:#991b1b;border:1px solid #fca5a5}
.fno-na{color:#cbd5e1;font-size:9px}
.fno-detail{font-size:9px;color:#64748b;margin-top:2px;line-height:1.3}
"""


# ─────────────────────────────────────────────
# SECTION 5: CLI
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fetch NSE F&O data and compute derivative signals.")
    parser.add_argument("--date", type=str, help="Date to fetch (YYYY-MM-DD). Default: today.")
    parser.add_argument("--backfill", type=int, default=0,
                        help="Number of additional past trading days to backfill.")
    parser.add_argument("--force", action="store_true", help="Ignore cache and re-fetch.")
    args = parser.parse_args()

    if args.force and SIGNALS_CSV.exists():
        SIGNALS_CSV.unlink()

    ref_date = datetime.strptime(args.date, "%Y-%m-%d") if args.date else datetime.now()
    signals = generate_fno_signals(reference_date=ref_date)

    if signals.empty:
        print("\nNo FNO signals generated.")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"Signal Summary ({len(signals)} symbols):")
    print(f"{'='*60}")
    if "FNO_SIGNAL" in signals.columns:
        print(signals["FNO_SIGNAL"].value_counts().to_string())
    if "FNO_BUILDUP" in signals.columns:
        print(f"\nBuildup breakdown:")
        print(signals["FNO_BUILDUP"].value_counts().to_string())
    if "FNO_PCR" in signals.columns:
        pcr = signals["FNO_PCR"].dropna()
        if not pcr.empty:
            print(f"\nPCR: mean={pcr.mean():.2f}, median={pcr.median():.2f}, "
                  f"min={pcr.min():.2f}, max={pcr.max():.2f}")


if __name__ == "__main__":
    main()
