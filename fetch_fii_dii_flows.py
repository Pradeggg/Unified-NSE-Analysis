#!/usr/bin/env python3
"""FII / DII daily flow signal generator (P1-3).

Downloads NSE institutional activity data, computes rolling flow signals,
and exposes an enrichment function for sector_rotation_report.py.

Signals computed:
  - FII_NET_5D: rolling 5-day FII net buy/sell (₹ crores)
  - DII_NET_5D: rolling 5-day DII net buy/sell (₹ crores)
  - FLOW_SIGNAL: composite classification
      FII_BUYING     — FII net 5D > +3000 Cr
      FII_SELLING    — FII net 5D < -3000 Cr
      BOTH_BUYING    — DII net 5D > +2000 Cr AND FII net 5D > 0
      DII_ABSORBING  — DII net 5D > +2000 Cr AND FII net 5D < 0  (support)
      NEUTRAL        — everything else

Data source: NSE institutional activity API (free, daily)
  URL: https://www.nseindia.com/api/fiidiiTradeReact
  Note: API returns only the latest available day. We cache daily snapshots
  to build the rolling window. Use --backfill with manual CSV to seed history.

Cache: data/_fii_dii_cache/ directory with per-date JSON files
Output: data/fii_dii_flows.csv (latest rolling signals)

Usage:
  # Standalone
  python fetch_fii_dii_flows.py                  # fetch today, compute signals
  python fetch_fii_dii_flows.py --seed seed.csv  # seed cache from a historical CSV

  # As module (from sector_rotation_report.py)
  from fetch_fii_dii_flows import load_flow_signals
  flow = load_flow_signals()  # returns dict with keys: fii_net_5d, dii_net_5d, flow_signal, etc.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

# ── Paths ──
ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / "data" / "_fii_dii_cache"
SIGNALS_CSV = ROOT / "data" / "fii_dii_flows.csv"
CACHE_TTL_HOURS = 18  # re-fetch if cache older than this

# ── NSE access config ──
_NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.nseindia.com/reports/equity-market",
}
_COOKIE_JAR = ROOT / "data" / "_fno_cache" / "_nse_cookies.txt"


# ─────────────────────────────────────────────
# SECTION 1: DATA FETCHING
# ─────────────────────────────────────────────

def _ensure_nse_cookies() -> bool:
    """Hit NSE homepage to populate cookie jar (shared with fetch_fno_data.py)."""
    _COOKIE_JAR.parent.mkdir(parents=True, exist_ok=True)
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
        "https://www.nseindia.com",
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=40)
        return _COOKIE_JAR.exists() and _COOKIE_JAR.stat().st_size > 0
    except (subprocess.TimeoutExpired, OSError) as exc:
        print(f"  Cookie setup failed: {exc}")
        return False


def fetch_fii_dii_latest() -> dict | None:
    """Fetch latest FII/DII trade data from NSE API.

    Returns dict: {date, fii_buy, fii_sell, fii_net, dii_buy, dii_sell, dii_net}
    or None on failure.
    """
    # PG: NSE API needs session cookies — using curl subprocess per project pattern
    _ensure_nse_cookies()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    tmp_path = CACHE_DIR / "_api_response.json"
    cmd = [
        "curl", "-sS", "-L", "--http1.1",
        "-b", str(_COOKIE_JAR),
        "-o", str(tmp_path),
        "-w", "%{http_code}",
        "--max-time", "30",
        "-H", f"User-Agent: {_NSE_HEADERS['User-Agent']}",
        "-H", f"Referer: {_NSE_HEADERS['Referer']}",
        "-H", "Accept: application/json",
        "https://www.nseindia.com/api/fiidiiTradeReact",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
        http_code = result.stdout.strip()
        if http_code != "200" or not tmp_path.exists():
            print(f"  FII/DII API returned HTTP {http_code}")
            return None

        with open(tmp_path, "r") as f:
            data = json.load(f)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as exc:
        print(f"  FII/DII API fetch failed: {exc}")
        return None
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    if not isinstance(data, list) or len(data) < 2:
        print(f"  Unexpected API response format: {str(data)[:200]}")
        return None

    # Parse the two entries (FII/FPI and DII)
    fii_entry = next((d for d in data if "FII" in str(d.get("category", "")).upper()), None)
    dii_entry = next((d for d in data if "DII" in str(d.get("category", "")).upper()), None)

    if not fii_entry or not dii_entry:
        print(f"  Missing FII or DII entry in API response")
        return None

    # Parse date — NSE uses "30-Apr-2026" format
    raw_date = fii_entry.get("date", "")
    try:
        dt = datetime.strptime(raw_date, "%d-%b-%Y")
        date_str = dt.strftime("%Y-%m-%d")
    except ValueError:
        print(f"  Could not parse date: {raw_date}")
        return None

    record = {
        "date": date_str,
        "fii_buy": float(fii_entry.get("buyValue", 0)),
        "fii_sell": float(fii_entry.get("sellValue", 0)),
        "fii_net": float(fii_entry.get("netValue", 0)),
        "dii_buy": float(dii_entry.get("buyValue", 0)),
        "dii_sell": float(dii_entry.get("sellValue", 0)),
        "dii_net": float(dii_entry.get("netValue", 0)),
    }

    # Cache this day's data
    cache_path = CACHE_DIR / f"{date_str}.json"
    with open(cache_path, "w") as f:
        json.dump(record, f, indent=2)
    print(f"  FII/DII data cached: {date_str} — FII net: ₹{record['fii_net']:+,.0f} Cr, DII net: ₹{record['dii_net']:+,.0f} Cr")

    return record


def _load_cached_days(n: int = 10) -> list[dict]:
    """Load the most recent N cached daily snapshots from disk.

    Returns list of dicts sorted by date (oldest first).
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(CACHE_DIR.glob("????-??-??.json"), reverse=True)[:n]

    records = []
    for f in files:
        try:
            with open(f, "r") as fh:
                records.append(json.load(fh))
        except (json.JSONDecodeError, OSError):
            continue

    # Sort oldest-first for rolling computation
    records.sort(key=lambda r: r.get("date", ""))
    return records


# ─────────────────────────────────────────────
# SECTION 2: SIGNAL COMPUTATION
# ─────────────────────────────────────────────

# PG: signal thresholds per backlog spec (P1-3)
_FII_STRONG_THRESHOLD = 3000   # crores — FII_BUYING / FII_SELLING
_DII_SUPPORT_THRESHOLD = 2000  # crores — DII_ABSORBING / BOTH_BUYING


def compute_flow_signals(records: list[dict], rolling_window: int = 5) -> dict:
    """Compute rolling flow signals from cached daily snapshots.

    Returns dict with keys:
      date, fii_net_today, dii_net_today,
      fii_net_5d, dii_net_5d, flow_signal,
      fii_trend (streak), dii_trend (streak),
      days_in_window
    """
    if not records:
        return {
            "date": "", "fii_net_today": 0, "dii_net_today": 0,
            "fii_net_5d": 0, "dii_net_5d": 0, "flow_signal": "NO_DATA",
            "fii_trend": "UNKNOWN", "dii_trend": "UNKNOWN",
            "days_in_window": 0,
        }

    latest = records[-1]
    window = records[-rolling_window:]

    fii_net_5d = sum(r.get("fii_net", 0) for r in window)
    dii_net_5d = sum(r.get("dii_net", 0) for r in window)
    fii_net_today = latest.get("fii_net", 0)
    dii_net_today = latest.get("dii_net", 0)

    # PG: signal classification per P1-3 spec
    if dii_net_5d > _DII_SUPPORT_THRESHOLD and fii_net_5d > 0:
        flow_signal = "BOTH_BUYING"
    elif fii_net_5d > _FII_STRONG_THRESHOLD:
        flow_signal = "FII_BUYING"
    elif fii_net_5d < -_FII_STRONG_THRESHOLD:
        if dii_net_5d > _DII_SUPPORT_THRESHOLD:
            flow_signal = "DII_ABSORBING"
        else:
            flow_signal = "FII_SELLING"
    else:
        flow_signal = "NEUTRAL"

    # Compute FII/DII daily streak (consecutive buy/sell days)
    def _streak(records: list[dict], key: str) -> str:
        if not records:
            return "UNKNOWN"
        streak_count = 0
        direction = None
        for r in reversed(records):
            v = r.get(key, 0)
            d = "BUY" if v > 0 else "SELL" if v < 0 else "FLAT"
            if direction is None:
                direction = d
            if d == direction and d != "FLAT":
                streak_count += 1
            else:
                break
        return f"{direction}_{streak_count}D" if streak_count > 0 else "FLAT"

    return {
        "date": latest.get("date", ""),
        "fii_net_today": round(fii_net_today, 2),
        "dii_net_today": round(dii_net_today, 2),
        "fii_net_5d": round(fii_net_5d, 2),
        "dii_net_5d": round(dii_net_5d, 2),
        "flow_signal": flow_signal,
        "fii_trend": _streak(records, "fii_net"),
        "dii_trend": _streak(records, "dii_net"),
        "days_in_window": len(window),
    }


def generate_flow_signals() -> dict:
    """Full pipeline: fetch latest → load cache → compute signals → save.

    Returns signal dict.
    """
    print(f"\n{'='*60}")
    print("FII/DII Flow Signal Generation")
    print(f"{'='*60}")

    # Fetch latest from NSE
    latest = fetch_fii_dii_latest()
    if latest:
        print(f"  Latest date: {latest['date']}")
    else:
        print("  Could not fetch latest data; using cached data only.")

    # Load cached daily snapshots
    cached = _load_cached_days(n=10)
    if not cached:
        print("  No cached FII/DII data available. Run --seed to import historical data.")
        return compute_flow_signals([])

    print(f"  Cached days: {len(cached)} ({cached[0]['date']} → {cached[-1]['date']})")

    # Compute signals
    signals = compute_flow_signals(cached)

    print(f"  FII net 5D: ₹{signals['fii_net_5d']:+,.0f} Cr ({signals['fii_trend']})")
    print(f"  DII net 5D: ₹{signals['dii_net_5d']:+,.0f} Cr ({signals['dii_trend']})")
    print(f"  Flow signal: {signals['flow_signal']}")

    # Save to CSV
    SIGNALS_CSV.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([signals])
    df.to_csv(SIGNALS_CSV, index=False)
    print(f"  Saved → {SIGNALS_CSV}")

    return signals


# ─────────────────────────────────────────────
# SECTION 3: INTEGRATION API (for sector_rotation_report.py)
# ─────────────────────────────────────────────

def _cache_is_fresh() -> bool:
    """Check if the cached signals CSV is within TTL."""
    if not SIGNALS_CSV.exists():
        return False
    age_hours = (time.time() - SIGNALS_CSV.stat().st_mtime) / 3600
    return age_hours < CACHE_TTL_HOURS


def load_flow_signals() -> dict:
    """Load FII/DII flow signals — from cache if fresh, otherwise regenerate.

    This is the primary entry point for sector_rotation_report.py.
    Returns dict with flow signal data (market-wide, not per-stock).
    """
    if _cache_is_fresh():
        try:
            df = pd.read_csv(SIGNALS_CSV)
            if not df.empty:
                row = df.iloc[0].to_dict()
                print(f"  FII/DII flows: loaded from cache ({row.get('date', '?')}, signal={row.get('flow_signal', '?')})")
                return row
        except Exception:
            pass

    return generate_flow_signals()


# ─────────────────────────────────────────────
# SECTION 4: HTML BADGE (for render_html_interactive)
# ─────────────────────────────────────────────

def flow_badge_html(flow: dict) -> str:
    """Return an HTML badge row for the FII/DII flow signal.

    Used by sector_rotation_report.py in the regime/flow info banner.
    """
    signal = str(flow.get("flow_signal", "NO_DATA")).strip().upper()
    fii_5d = flow.get("fii_net_5d", 0)
    dii_5d = flow.get("dii_net_5d", 0)
    fii_today = flow.get("fii_net_today", 0)
    dii_today = flow.get("dii_net_today", 0)
    fii_trend = flow.get("fii_trend", "")
    dii_trend = flow.get("dii_trend", "")

    label_map = {
        "BOTH_BUYING":   ("🟢 Both Buying", "flow-bull"),
        "FII_BUYING":    ("🟢 FII Buying",  "flow-bull"),
        "DII_ABSORBING": ("🟡 DII Absorbing", "flow-caution"),
        "FII_SELLING":   ("🔴 FII Selling", "flow-bear"),
        "NEUTRAL":       ("⚪ Neutral",     "flow-neutral"),
        "NO_DATA":       ("— No Data",      "flow-na"),
    }
    label, css_class = label_map.get(signal, ("— Unknown", "flow-na"))

    fii_sign = "+" if fii_5d > 0 else ""
    dii_sign = "+" if dii_5d > 0 else ""

    return (
        f'<div class="flow-banner">'
        f'<span class="flow-badge {css_class}">{label}</span>'
        f'<span class="flow-detail">'
        f'FII 5D: ₹{fii_sign}{fii_5d:,.0f} Cr ({fii_trend}) · '
        f'DII 5D: ₹{dii_sign}{dii_5d:,.0f} Cr ({dii_trend})'
        f'</span>'
        f'<span class="flow-today">'
        f'Today: FII ₹{"+" if fii_today > 0 else ""}{fii_today:,.0f} Cr · '
        f'DII ₹{"+" if dii_today > 0 else ""}{dii_today:,.0f} Cr'
        f'</span>'
        f'</div>'
    )


# CSS rules to inject into the HTML <style> block
FLOW_CSS = """
/* ---- FII/DII FLOW BADGES (P1-3) ---- */
.flow-banner{display:flex;align-items:center;gap:12px;padding:8px 14px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;margin-bottom:10px;flex-wrap:wrap}
.flow-badge{display:inline-block;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:700;white-space:nowrap}
.flow-bull{background:#dcfce7;color:#15803d;border:1px solid #86efac}
.flow-caution{background:#fef9c3;color:#854d0e;border:1px solid #fde047}
.flow-bear{background:#fee2e2;color:#991b1b;border:1px solid #fca5a5}
.flow-neutral{background:#f1f5f9;color:#64748b}
.flow-na{background:#f1f5f9;color:#94a3b8}
.flow-detail{font-size:11px;color:#475569}
.flow-today{font-size:10px;color:#94a3b8;margin-left:auto}
"""


# ─────────────────────────────────────────────
# SECTION 5: SEED / BACKFILL
# ─────────────────────────────────────────────

def seed_from_csv(csv_path: str) -> None:
    """Import historical FII/DII data from a CSV file into the cache.

    Expected CSV columns: date, fii_buy, fii_sell, fii_net, dii_buy, dii_sell, dii_net
    Or at minimum: date, fii_net, dii_net
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(csv_path)

    # Normalise column names
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    required = {"date", "fii_net", "dii_net"}
    if not required.issubset(set(df.columns)):
        print(f"  ERROR: CSV must have columns: {required}. Found: {set(df.columns)}")
        return

    count = 0
    for _, row in df.iterrows():
        try:
            dt = pd.to_datetime(row["date"])
            date_str = dt.strftime("%Y-%m-%d")
        except Exception:
            continue

        record = {
            "date": date_str,
            "fii_buy": float(row.get("fii_buy", 0) or 0),
            "fii_sell": float(row.get("fii_sell", 0) or 0),
            "fii_net": float(row["fii_net"]),
            "dii_buy": float(row.get("dii_buy", 0) or 0),
            "dii_sell": float(row.get("dii_sell", 0) or 0),
            "dii_net": float(row["dii_net"]),
        }

        cache_path = CACHE_DIR / f"{date_str}.json"
        if not cache_path.exists():
            with open(cache_path, "w") as f:
                json.dump(record, f, indent=2)
            count += 1

    print(f"  Seeded {count} new daily records into {CACHE_DIR}")


# ─────────────────────────────────────────────
# SECTION 6: CLI
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fetch NSE FII/DII flow data and compute signals.")
    parser.add_argument("--seed", type=str, help="Path to historical CSV to seed cache.")
    parser.add_argument("--force", action="store_true", help="Ignore cache and re-fetch.")
    args = parser.parse_args()

    if args.seed:
        seed_from_csv(args.seed)

    if args.force and SIGNALS_CSV.exists():
        SIGNALS_CSV.unlink()

    signals = generate_flow_signals()

    if signals.get("flow_signal") == "NO_DATA":
        print("\nNo FII/DII flow data available.")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"Flow Signal Summary:")
    print(f"{'='*60}")
    print(f"  Date:          {signals.get('date', '?')}")
    print(f"  FII today:     ₹{signals.get('fii_net_today', 0):+,.0f} Cr")
    print(f"  DII today:     ₹{signals.get('dii_net_today', 0):+,.0f} Cr")
    print(f"  FII net 5D:    ₹{signals.get('fii_net_5d', 0):+,.0f} Cr ({signals.get('fii_trend', '')})")
    print(f"  DII net 5D:    ₹{signals.get('dii_net_5d', 0):+,.0f} Cr ({signals.get('dii_trend', '')})")
    print(f"  Signal:        {signals.get('flow_signal', '?')}")
    print(f"  Window:        {signals.get('days_in_window', 0)} days")


if __name__ == "__main__":
    main()
