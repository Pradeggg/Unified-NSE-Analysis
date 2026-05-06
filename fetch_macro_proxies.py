#!/usr/bin/env python3
"""
P1-6 — Macro-Economic Proxy Signals
====================================
Fetches macro indicator data from reliable public sources (FRED, NSE),
computes trend signals, and maps them to sector-level tailwinds/headwinds.

Data sources (all free, no API key required):
  FRED CSV API:
    - DEXINUS        : USD/INR daily
    - DCOILBRENTEU   : Brent crude daily
    - PCOPPUSDM      : Copper monthly (USD/MT)
    - DGS10          : US 10-Year Treasury yield daily
    - INDCPIALLMINMEI: India CPI monthly (OECD index)
    - MCOILBRENTEU   : Brent crude monthly avg
    - IRSTCI01INM156N: India short-term interest rate monthly
  NSE API:
    - /api/allIndices : India VIX, Nifty 50, sector indices (live)

Output:
  data/macro_proxy_signals.csv  — one row per indicator per date
  data/macro_sector_tailwind.csv — MACRO_TAILWIND score per sector

Usage:
  python fetch_macro_proxies.py              # use cache if fresh (<24h)
  python fetch_macro_proxies.py --refresh    # force re-download
  python fetch_macro_proxies.py --date 2026-04-29

Author: Optimus (ShunyaAI-CodingAgent) — P1-6
"""

from __future__ import annotations
import argparse
import csv
import io
import json
import math
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

# ── paths ──
_BASE_DIR = Path(__file__).resolve().parent
_CACHE_DIR = _BASE_DIR / "data" / "_macro_cache"
_SIGNALS_CSV = _BASE_DIR / "data" / "macro_proxy_signals.csv"
_TAILWIND_CSV = _BASE_DIR / "data" / "macro_sector_tailwind.csv"
_NSE_COOKIE = _BASE_DIR / "data" / "_fno_cache" / "_nse_cookies.txt"

_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ── FRED series definitions ──
_FRED_SERIES = {
    "DEXINUS":          {"name": "USD/INR",           "freq": "daily",   "direction": "lower_is_better"},
    "DCOILBRENTEU":     {"name": "Brent Crude",       "freq": "daily",   "direction": "lower_is_better"},
    "PCOPPUSDM":        {"name": "Copper (USD/MT)",   "freq": "monthly", "direction": "higher_is_better"},
    "DGS10":            {"name": "US 10Y Treasury",   "freq": "daily",   "direction": "lower_is_better"},
    "INDCPIALLMINMEI":  {"name": "India CPI Index",   "freq": "monthly", "direction": "lower_is_better"},
    "MCOILBRENTEU":     {"name": "Brent Monthly Avg", "freq": "monthly", "direction": "lower_is_better"},
    "IRSTCI01INM156N":  {"name": "India Interest Rate","freq": "monthly","direction": "lower_is_better"},
}

# ── NSE indicators ──
_NSE_INDEX_TARGETS = {
    "INDIA VIX":     {"name": "India VIX",   "direction": "lower_is_better"},
    "NIFTY 50":      {"name": "Nifty 50",    "direction": "higher_is_better"},
}


# ===== FETCHING =====

def _curl_text(url: str, cookies: str | None = None, referer: str | None = None,
               max_time: int = 20) -> str:
    """Fetch URL via curl subprocess (avoids macOS requests SSL hangs).
    Uses --http1.1 to avoid HTTP/2 stream reset errors on some endpoints."""
    cmd = ["curl", "-sS", "--http1.1", "--max-time", str(max_time), "-L", url]
    if cookies and Path(cookies).exists():
        cmd += ["-b", cookies]
    if referer:
        cmd += ["-H", f"Referer: {referer}"]
    # Accept header — FRED needs text/csv to return CSV instead of HTML
    cmd += ["-H", "Accept: text/csv, text/plain, application/json, */*"]
    cmd += ["-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=max_time + 10)
        if r.returncode != 0 and not r.stdout:
            print(f"  curl failed ({r.returncode}) for {url}: {r.stderr[:100]}", file=sys.stderr)
        return r.stdout
    except subprocess.TimeoutExpired:
        print(f"  curl timeout ({max_time}s) for {url}", file=sys.stderr)
        return ""
    except Exception as exc:
        print(f"  curl error for {url}: {exc}", file=sys.stderr)
        return ""


def fetch_fred_series(series_id: str, start_date: str = "",
                      force: bool = False) -> pd.DataFrame:
    """Download FRED CSV data for a single series. Caches locally.
    Uses a rolling 6-month window to avoid large payloads that FRED rate-limits."""
    cache_file = _CACHE_DIR / f"fred_{series_id}.csv"
    # Use cache if fresh (< 24 hours) and not forced
    if not force and cache_file.exists():
        age_h = (datetime.now().timestamp() - cache_file.stat().st_mtime) / 3600
        if age_h < 24:
            return pd.read_csv(cache_file, parse_dates=["observation_date"])

    # Use 6-month rolling window to keep payloads small (avoids FRED timeouts)
    if not start_date:
        start_date = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")

    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={start_date}"
    text = _curl_text(url)
    if not text or text.strip().startswith("<!DOCTYPE") or "observation_date" not in text:
        # Blocked or error — try cache anyway
        if cache_file.exists():
            print(f"  FRED {series_id}: download blocked, using stale cache.")
            return pd.read_csv(cache_file, parse_dates=["observation_date"])
        return pd.DataFrame(columns=["observation_date", series_id])

    # Parse and cache
    df = pd.read_csv(io.StringIO(text), parse_dates=["observation_date"])
    # FRED uses "." for missing values
    df[series_id] = pd.to_numeric(df[series_id], errors="coerce")
    df.dropna(subset=[series_id], inplace=True)
    df.to_csv(cache_file, index=False)
    return df


def fetch_nse_live_indices(force: bool = False) -> dict:
    """Fetch current NSE index values via /api/allIndices. Returns dict of index→data."""
    cache_file = _CACHE_DIR / f"nse_indices_{datetime.now().strftime('%Y%m%d')}.json"
    if not force and cache_file.exists():
        age_h = (datetime.now().timestamp() - cache_file.stat().st_mtime) / 3600
        if age_h < 4:  # 4-hour cache for live data
            with open(cache_file) as f:
                return json.load(f)

    text = _curl_text(
        "https://www.nseindia.com/api/allIndices",
        cookies=str(_NSE_COOKIE),
        referer="https://www.nseindia.com",
    )
    if not text:
        if cache_file.exists():
            with open(cache_file) as f:
                return json.load(f)
        return {}

    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        if cache_file.exists():
            with open(cache_file) as f:
                return json.load(f)
        return {}

    result = {}
    for item in raw.get("data", []):
        idx = item.get("index", "")
        result[idx] = {
            "last": item.get("last"),
            "open": item.get("open"),
            "high": item.get("high"),
            "low": item.get("low"),
            "percentChange": item.get("percentChange"),
            "previousClose": item.get("previousClose"),
        }

    with open(cache_file, "w") as f:
        json.dump(result, f, indent=2)
    return result


# ===== SIGNAL COMPUTATION =====

def _trend(values: list[float], window: int = 20) -> str:
    """Compute trend direction from a list of recent values."""
    if len(values) < 2:
        return "FLAT"
    recent = values[-window:] if len(values) >= window else values
    first_half = sum(recent[:len(recent)//2]) / max(1, len(recent)//2)
    second_half = sum(recent[len(recent)//2:]) / max(1, len(recent) - len(recent)//2)
    pct_chg = (second_half - first_half) / first_half * 100 if first_half != 0 else 0
    if pct_chg > 2:
        return "RISING"
    elif pct_chg < -2:
        return "FALLING"
    return "FLAT"


def _mom_pct(values: list[float], periods: int = 20) -> float:
    """Momentum: % change over last N periods."""
    if len(values) < periods + 1:
        return 0.0
    old = values[-(periods + 1)]
    new = values[-1]
    if old == 0:
        return 0.0
    return (new - old) / old * 100


def _zscore(value: float, values: list[float]) -> float:
    """Z-score of value vs recent history. Returns 0 if insufficient data."""
    if len(values) < 5:
        return 0.0
    mean = sum(values) / len(values)
    std = (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5
    if std < 1e-9:
        return 0.0
    z = (value - mean) / std
    # Clamp to [-3, +3] to avoid outlier domination
    return max(-3.0, min(3.0, z))


def compute_indicator_signals(force: bool = False) -> pd.DataFrame:
    """Fetch all FRED series, compute signals, return unified DataFrame."""
    rows = []
    today_str = datetime.now().strftime("%Y-%m-%d")

    # 1. FRED series
    for series_id, meta in _FRED_SERIES.items():
        df = fetch_fred_series(series_id, force=force)  # uses 6-month rolling window
        if df.empty:
            print(f"  {series_id}: no data available.")
            continue

        values = df[series_id].tolist()
        latest_val = values[-1]
        latest_date = df["observation_date"].iloc[-1]

        trend = _trend(values, window=20)
        mom_1m = _mom_pct(values, periods=20)
        mom_3m = _mom_pct(values, periods=60)
        z = _zscore(latest_val, values[-60:])

        # Signal: combine trend + z-score; NaN-safe
        if meta["direction"] == "higher_is_better":
            signal_score = z  # positive z → bullish
        else:
            signal_score = -z  # negative z → bullish (lower is better)
        # Replace NaN with 0 (insufficient history)
        if math.isnan(signal_score):
            signal_score = 0.0
        if math.isnan(z):
            z = 0.0

        rows.append({
            "date": today_str,
            "indicator": meta["name"],
            "series_id": series_id,
            "frequency": meta["freq"],
            "latest_value": round(latest_val, 4),
            "latest_date": latest_date.strftime("%Y-%m-%d") if hasattr(latest_date, "strftime") else str(latest_date),
            "trend": trend,
            "momentum_1m_pct": round(mom_1m, 2),
            "momentum_3m_pct": round(mom_3m, 2),
            "z_score": round(z, 2),
            "signal_score": round(signal_score, 2),
        })
        print(f"  {meta['name']:25s}: {latest_val:>12.2f}  trend={trend:8s}  z={z:+.2f}  signal={signal_score:+.2f}")

    # 2. NSE live indices (VIX, Nifty)
    nse_data = fetch_nse_live_indices(force=force)
    for idx_name, meta in _NSE_INDEX_TARGETS.items():
        item = nse_data.get(idx_name, {})
        if not item or item.get("last") is None:
            print(f"  {meta['name']:25s}: no data")
            continue
        val = float(item["last"])
        pct_chg = float(item.get("percentChange", 0) or 0)

        # For VIX: trend from daily change; for Nifty: from change%
        trend = "RISING" if pct_chg > 0.5 else "FALLING" if pct_chg < -0.5 else "FLAT"
        signal_score = -pct_chg / 2 if meta["direction"] == "lower_is_better" else pct_chg / 2

        rows.append({
            "date": today_str,
            "indicator": meta["name"],
            "series_id": idx_name,
            "frequency": "daily",
            "latest_value": round(val, 4),
            "latest_date": today_str,
            "trend": trend,
            "momentum_1m_pct": round(pct_chg, 2),  # today's change as proxy
            "momentum_3m_pct": 0,  # not available for live
            "z_score": 0,
            "signal_score": round(signal_score, 2),
        })
        print(f"  {meta['name']:25s}: {val:>12.2f}  today={pct_chg:+.2f}%  signal={signal_score:+.2f}")

    signals_df = pd.DataFrame(rows)
    if not signals_df.empty:
        signals_df.to_csv(_SIGNALS_CSV, index=False)
        print(f"\n  Saved {len(signals_df)} indicator signals → {_SIGNALS_CSV.name}")
    return signals_df


# ===== SECTOR TAILWIND MAPPING =====

# Sector → macro factor weights
# Positive weight = tailwind when indicator signal is positive
# Negative weight = headwind when indicator signal is positive
_SECTOR_MACRO_MAP: dict[str, dict[str, float]] = {
    # Cyclicals benefit from falling USD/INR, falling crude, rising copper, low VIX
    "Capital Goods":          {"Copper (USD/MT)": 0.35, "Brent Crude": -0.25, "India VIX": -0.20, "US 10Y Treasury": -0.20},
    "Metals & Mining":        {"Copper (USD/MT)": 0.40, "Brent Crude": 0.15, "USD/INR": -0.25, "India VIX": -0.20},
    "Infrastructure":         {"Copper (USD/MT)": 0.30, "India Interest Rate": -0.30, "Brent Crude": -0.20, "India VIX": -0.20},
    "Realty":                 {"India Interest Rate": -0.40, "India VIX": -0.25, "USD/INR": -0.20, "Nifty 50": 0.15},
    # Autos hurt by crude, helped by low rates + low VIX
    "Auto":                   {"Brent Crude": -0.30, "India Interest Rate": -0.25, "Copper (USD/MT)": 0.15, "India VIX": -0.15, "Nifty 50": 0.15},
    "Automobile":             {"Brent Crude": -0.30, "India Interest Rate": -0.25, "Copper (USD/MT)": 0.15, "India VIX": -0.15, "Nifty 50": 0.15},
    # Defensives benefit from rising VIX, rising crude (pharma)
    "FMCG":                   {"India VIX": 0.20, "India CPI Index": -0.30, "Brent Crude": -0.20, "India Interest Rate": -0.15, "Nifty 50": -0.15},
    "Pharma":                 {"USD/INR": 0.30, "India VIX": 0.20, "Brent Crude": -0.15, "Nifty 50": -0.15, "India Interest Rate": -0.20},
    "Healthcare":             {"USD/INR": 0.30, "India VIX": 0.20, "Brent Crude": -0.15, "Nifty 50": -0.15, "India Interest Rate": -0.20},
    # IT exports benefit from USD/INR rise
    "IT":                     {"USD/INR": 0.40, "US 10Y Treasury": -0.20, "India VIX": -0.15, "Nifty 50": 0.15, "Brent Crude": -0.10},
    "Technology":             {"USD/INR": 0.40, "US 10Y Treasury": -0.20, "India VIX": -0.15, "Nifty 50": 0.15, "Brent Crude": -0.10},
    # Banks benefit from rising rates (NIM expansion), low VIX
    "Banking & Finance":      {"India Interest Rate": 0.20, "India VIX": -0.30, "Nifty 50": 0.25, "Brent Crude": -0.15, "USD/INR": -0.10},
    "Financial Services":     {"India Interest Rate": 0.20, "India VIX": -0.30, "Nifty 50": 0.25, "Brent Crude": -0.15, "USD/INR": -0.10},
    "Private Bank":           {"India Interest Rate": 0.25, "India VIX": -0.30, "Nifty 50": 0.25, "Brent Crude": -0.10, "USD/INR": -0.10},
    "PSU Bank":               {"India Interest Rate": 0.25, "India VIX": -0.30, "Nifty 50": 0.25, "Brent Crude": -0.10, "USD/INR": -0.10},
    # Energy benefits from rising crude
    "Energy":                 {"Brent Crude": 0.40, "USD/INR": -0.20, "India VIX": -0.20, "Nifty 50": 0.20},
    "Oil & Gas":              {"Brent Crude": 0.40, "USD/INR": -0.20, "India VIX": -0.20, "Nifty 50": 0.20},
    # Consumer discretionary
    "Consumer Discretionary": {"India Interest Rate": -0.25, "India CPI Index": -0.25, "India VIX": -0.20, "Nifty 50": 0.20, "Brent Crude": -0.10},
    "Media & Entertainment":  {"India VIX": -0.25, "Nifty 50": 0.30, "India Interest Rate": -0.20, "India CPI Index": -0.25},
    # Chemicals / Specialty
    "Chemicals":              {"Brent Crude": 0.20, "Copper (USD/MT)": 0.20, "USD/INR": -0.25, "India VIX": -0.20, "Nifty 50": 0.15},
    # Telecom
    "Telecom":                {"India Interest Rate": -0.25, "India VIX": -0.20, "Nifty 50": 0.20, "Brent Crude": -0.15, "USD/INR": -0.20},
    # Defence
    "Defence":                {"Nifty 50": 0.20, "India VIX": -0.20, "India Interest Rate": -0.20, "Copper (USD/MT)": 0.20, "USD/INR": -0.20},
    "Defence & Shipbuilding": {"Nifty 50": 0.20, "India VIX": -0.20, "India Interest Rate": -0.20, "Copper (USD/MT)": 0.20, "USD/INR": -0.20},
}

# Fallback: generic market-wide weights for unmapped sectors
_DEFAULT_SECTOR_MAP = {"India VIX": -0.30, "Nifty 50": 0.25, "Brent Crude": -0.15, "India Interest Rate": -0.15, "USD/INR": -0.15}


def compute_sector_tailwinds(signals_df: pd.DataFrame) -> pd.DataFrame:
    """Map indicator signals to per-sector MACRO_TAILWIND scores."""
    if signals_df.empty:
        return pd.DataFrame(columns=["SECTOR_NAME", "MACRO_TAILWIND", "MACRO_DETAIL"])

    # Build lookup: indicator_name → signal_score
    sig_map = {}
    for _, row in signals_df.iterrows():
        sig_map[row["indicator"]] = row["signal_score"]

    rows = []
    all_sectors = set(_SECTOR_MACRO_MAP.keys())
    for sector, weights in _SECTOR_MACRO_MAP.items():
        score = 0.0
        details = []
        for indicator, weight in weights.items():
            s = sig_map.get(indicator, 0)
            contribution = weight * s
            score += contribution
            if abs(contribution) > 0.05:
                direction = "+" if contribution > 0 else "-"
                details.append(f"{indicator}({direction}{abs(contribution):.1f})")
        # Clamp to [-3, +3] range for readability
        score = max(-3, min(3, score))
        detail_str = ", ".join(details[:4]) if details else "neutral"
        rows.append({
            "SECTOR_NAME": sector,
            "MACRO_TAILWIND": round(score, 2),
            "MACRO_DETAIL": detail_str,
        })

    tw_df = pd.DataFrame(rows).sort_values("MACRO_TAILWIND", ascending=False)
    tw_df.to_csv(_TAILWIND_CSV, index=False)
    print(f"\n  Saved {len(tw_df)} sector tailwinds → {_TAILWIND_CSV.name}")
    return tw_df


# ===== PUBLIC API FOR INTEGRATION =====

def generate_macro_signals(force: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Main entry: fetch indicators + compute sector tailwinds. Returns (signals_df, tailwind_df)."""
    print("\n" + "=" * 60)
    print("Macro Proxy Signal Generation — P1-6")
    print("=" * 60)
    signals_df = compute_indicator_signals(force=force)
    tailwind_df = compute_sector_tailwinds(signals_df)
    return signals_df, tailwind_df


def load_macro_signals() -> pd.DataFrame:
    """Load cached macro indicator signals. Returns empty DataFrame if missing."""
    if _SIGNALS_CSV.exists():
        age_d = (datetime.now().timestamp() - _SIGNALS_CSV.stat().st_mtime) / 86400
        if age_d > 45:
            print(f"  WARNING: Macro signals are {age_d:.0f} days old (>45d stale threshold).")
        return pd.read_csv(_SIGNALS_CSV)
    return pd.DataFrame()


def load_sector_tailwinds() -> pd.DataFrame:
    """Load cached sector tailwind scores. Returns empty DataFrame if missing."""
    if _TAILWIND_CSV.exists():
        return pd.read_csv(_TAILWIND_CSV)
    return pd.DataFrame()


def enrich_sector_rank_with_tailwinds(sector_rank: pd.DataFrame) -> pd.DataFrame:
    """Merge MACRO_TAILWIND into sector_rank DataFrame by SECTOR_NAME.
    Uses fuzzy matching on sector names since they may differ slightly."""
    tw_df = load_sector_tailwinds()
    if tw_df.empty or sector_rank.empty:
        sector_rank["MACRO_TAILWIND"] = 0.0
        sector_rank["MACRO_DETAIL"] = ""
        return sector_rank

    # Build lookup with case-insensitive + partial matching
    tw_map = {}
    for _, row in tw_df.iterrows():
        name = str(row["SECTOR_NAME"]).strip()
        tw_map[name.lower()] = (row["MACRO_TAILWIND"], row.get("MACRO_DETAIL", ""))

    tailwinds = []
    details = []
    for _, row in sector_rank.iterrows():
        sname = str(row.get("SECTOR_NAME", "")).strip()
        # Try exact match first
        match = tw_map.get(sname.lower())
        if not match:
            # Try substring matching
            for tw_key, tw_val in tw_map.items():
                if tw_key in sname.lower() or sname.lower() in tw_key:
                    match = tw_val
                    break
        if match:
            tailwinds.append(match[0])
            details.append(match[1])
        else:
            # Use default fallback
            tailwinds.append(0.0)
            details.append("")

    sector_rank["MACRO_TAILWIND"] = tailwinds
    sector_rank["MACRO_DETAIL"] = details
    return sector_rank


def macro_context_for_llm(signals_df: pd.DataFrame | None = None) -> str:
    """Build a concise macro backdrop string for LLM narrative prompts."""
    if signals_df is None:
        signals_df = load_macro_signals()
    if signals_df.empty:
        return ""

    parts = []
    for _, row in signals_df.iterrows():
        name = row["indicator"]
        val = row["latest_value"]
        trend = row["trend"]
        mom = row.get("momentum_1m_pct", 0)
        # Format based on indicator type
        if "VIX" in name:
            parts.append(f"{name}: {val:.1f} ({trend.lower()}, {mom:+.1f}% today)")
        elif "CPI" in name:
            parts.append(f"{name}: {val:.1f} ({trend.lower()})")
        elif "Interest" in name:
            parts.append(f"{name}: {val:.2f}% ({trend.lower()})")
        elif "USD" in name:
            parts.append(f"{name}: ₹{val:.2f} ({trend.lower()}, {mom:+.1f}% 1m)")
        elif "10Y" in name:
            parts.append(f"{name}: {val:.2f}% ({trend.lower()})")
        elif "Brent" in name and "Monthly" not in name:
            parts.append(f"{name}: ${val:.1f} ({trend.lower()}, {mom:+.1f}% 1m)")
        elif "Copper" in name:
            parts.append(f"{name}: ${val:.0f}/MT ({trend.lower()}, {mom:+.1f}% 1m)")
        elif "Nifty" in name:
            parts.append(f"{name}: {val:.0f} ({trend.lower()}, {mom:+.1f}% today)")
        else:
            parts.append(f"{name}: {val:.2f} ({trend.lower()})")

    if not parts:
        return ""
    return "Macro backdrop: " + "; ".join(parts) + "."


# ===== CSS / HTML HELPERS FOR REPORT =====

MACRO_CSS = """
/* ---- MACRO TAILWIND BADGES (P1-6) ---- */
.mtw{display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:10px;font-size:9.5px;font-weight:700;white-space:nowrap}
.mtw-strong{background:#dcfce7;color:#15803d;border:1px solid #86efac}
.mtw-mild{background:#dbeafe;color:#1e40af;border:1px solid #93c5fd}
.mtw-neutral{background:#f1f5f9;color:#64748b}
.mtw-headwind{background:#fee2e2;color:#991b1b;border:1px solid #fca5a5}
.mtw-severe{background:#fecdd3;color:#881337;border:1px solid #fb7185}
.mtw-detail{font-size:9px;color:#64748b;margin-top:1px}
"""


def macro_tailwind_badge(score: float, detail: str = "") -> str:
    """Render macro tailwind badge HTML for a sector."""
    if score is None or (isinstance(score, float) and math.isnan(score)):
        return '<span class="mtw mtw-neutral">— Macro</span>'
    if score >= 1.0:
        cls = "mtw-strong"
        icon = "🌬️"
        label = f"Tailwind +{score:.1f}"
    elif score >= 0.3:
        cls = "mtw-mild"
        icon = "🌤️"
        label = f"Mild Tailwind +{score:.1f}"
    elif score > -0.3:
        cls = "mtw-neutral"
        icon = "➖"
        label = f"Neutral {score:+.1f}"
    elif score > -1.0:
        cls = "mtw-headwind"
        icon = "🌧️"
        label = f"Mild Headwind {score:.1f}"
    else:
        cls = "mtw-severe"
        icon = "🌩️"
        label = f"Headwind {score:.1f}"
    html = f'<span class="mtw {cls}">{icon} {label}</span>'
    if detail:
        import html as html_mod
        html += f'<div class="mtw-detail">{html_mod.escape(detail[:80])}</div>'
    return html


# ===== CLI =====

def main():
    parser = argparse.ArgumentParser(description="P1-6: Fetch macro-economic proxy signals")
    parser.add_argument("--refresh", action="store_true", help="Force re-download all data")
    parser.add_argument("--date", type=str, help="Target date (unused, for CLI compatibility)")
    args = parser.parse_args()

    signals_df, tailwind_df = generate_macro_signals(force=args.refresh)

    if not signals_df.empty:
        print("\n" + "=" * 60)
        print("Indicator Summary:")
        print("=" * 60)
        print(signals_df[["indicator", "latest_value", "trend", "signal_score"]].to_string(index=False))

    if not tailwind_df.empty:
        print("\n" + "=" * 60)
        print("Sector Tailwinds (Top 10):")
        print("=" * 60)
        print(tailwind_df.head(10)[["SECTOR_NAME", "MACRO_TAILWIND", "MACRO_DETAIL"]].to_string(index=False))
        print("\nSector Headwinds (Bottom 5):")
        print(tailwind_df.tail(5)[["SECTOR_NAME", "MACRO_TAILWIND", "MACRO_DETAIL"]].to_string(index=False))

    print(f"\nLLM context: {macro_context_for_llm(signals_df)}")


if __name__ == "__main__":
    main()
