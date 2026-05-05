#!/usr/bin/env python3
"""
NSE Bloomberg Terminal
======================
Live market scanner with Bloomberg-style terminal UI.
Refreshes every 5 minutes. Shows indices, sectors, breakouts,
supertrend signals, VCP setups, and Stage 2 leaders.

Usage:
  python nse_terminal.py              # live mode, refresh every 5 min
  python nse_terminal.py --once       # run once, no refresh
  python nse_terminal.py --refresh 2  # refresh every 2 minutes
  python nse_terminal.py --top 20     # show top 20 stocks per signal
"""
from __future__ import annotations

import argparse
import io
import json
import queue
import re
import select
import sqlite3
import sys
import threading
import time
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "sector_rotation_tracker.db"
STOCK_CSV = ROOT / "data" / "nse_sec_full_data.csv"
INDEX_CSV = ROOT / "data" / "nse_index_data.csv"

try:
    from rich.console import Console
    from rich.layout import Layout
    from rich.live import Live
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich import box
    from rich.columns import Columns
    from rich.rule import Rule
    from rich.align import Align
    from rich.padding import Padding
except ImportError:
    print("Install rich:  pip install rich")
    sys.exit(1)

try:
    import pandas_ta as ta
    HAS_TA = True
except ImportError:
    HAS_TA = False

console = Console()

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

WATCHLIST_INDICES = [
    ("NIFTY 50",          "Nifty 50"),
    ("NIFTY BANK",        "Nifty Bank"),
    ("NIFTY IT",          "Nifty IT"),
    ("NIFTY PHARMA",      "Nifty Pharma"),
    ("NIFTY METAL",       "Nifty Metal"),
    ("NIFTY AUTO",        "Nifty Auto"),
    ("NIFTY FMCG",        "Nifty FMCG"),
    ("NIFTY MIDCAP 100",  "Midcap 100"),
    ("NIFTY SMLCAP 100",  "Smlcap 100"),
    ("INDIA VIX",         "India VIX"),
]

SECTOR_INDEX_MAP = {
    "Metals & Mining":       "Nifty Metal",
    "Pharma & Healthcare":   "Nifty Pharma",
    "IT & Technology":       "Nifty IT",
    "Banking & Finance":     "Nifty Bank",
    "Auto & EV":             "Nifty Auto",
    "FMCG":                  "Nifty FMCG",
}

NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json,text/html,*/*",
    "Referer": "https://www.nseindia.com/",
    "Accept-Language": "en-US,en;q=0.9",
}

# ─────────────────────────────────────────────────────────────────────────────
# NSE live data fetchers
# ─────────────────────────────────────────────────────────────────────────────

_nse_session: Optional[requests.Session] = None
_nse_session_ts: float = 0.0          # epoch time session was last initialised
_SESSION_TTL: float = 4 * 60          # re-handshake with NSE every 4 minutes

# ── Price flash animation state ───────────────────────────────────────────────
_prev_prices:     dict[str, float] = {}   # key → last rendered price
_flash_direction: dict[str, str]   = {}   # key → "up" | "dn"
_flash_expires:   dict[str, float] = {}   # key → epoch when flash expires
_FLASH_SECS = 4                           # seconds to hold the bright colour

# ── Market narrative cache ────────────────────────────────────────────────────
_narrative_cache: dict = {"text": "", "ts": 0.0}
_narrative_lock   = threading.Lock()
_NARRATIVE_TTL    = 5 * 60               # regenerate narrative every 5 minutes

# ── NLP / Agent Adda state ───────────────────────────────────────────────────
_nlp_state:   dict        = {"query": "", "response": "", "ts": "", "pending": False}
_nlp_history: list[dict]  = []    # last 5 Q&A pairs [{query, response, ts}, ...]
_nlp_lock     = threading.Lock()
_NLP_HISTORY_MAX = 5

def _get_nse_session(force: bool = False) -> requests.Session:
    """Return a live NSE session, renewing the cookie every _SESSION_TTL seconds."""
    global _nse_session, _nse_session_ts
    age = time.time() - _nse_session_ts
    if _nse_session is None or force or age > _SESSION_TTL:
        s = requests.Session()
        s.headers.update(NSE_HEADERS)
        try:
            s.get("https://www.nseindia.com/", timeout=10)
            time.sleep(0.5)
        except Exception:
            pass
        _nse_session = s
        _nse_session_ts = time.time()
    return _nse_session


def fetch_index_quote(index_name: str) -> Optional[dict]:
    """Fetch live quote for a single index from NSE."""
    try:
        s = _get_nse_session()
        url = f"https://www.nseindia.com/api/allIndices"
        r = s.get(url, timeout=10)
        data = r.json().get("data", [])
        for item in data:
            if item.get("index", "").upper() == index_name.upper():
                return item
    except Exception:
        pass
    return None


def fetch_all_indices() -> dict[str, dict]:
    """Fetch all NSE index quotes in one call. Returns {index_name: quote_dict}.
    Normalises the 'last' field (allIndices API) to 'lastPrice' so callers can
    use a single field name regardless of whether data is live or EOD.
    """
    out: dict[str, dict] = {}
    try:
        s = _get_nse_session()
        r = s.get("https://www.nseindia.com/api/allIndices", timeout=12)
        for item in r.json().get("data", []):
            # allIndices uses 'last'; normalise to 'lastPrice' for consistency
            if "lastPrice" not in item or not item["lastPrice"]:
                item["lastPrice"] = item.get("last", 0)
            out[item.get("index", "").upper()] = item
    except Exception:
        pass
    return out


def load_eod_indices() -> dict[str, dict]:
    """Load last EOD close for all indices from nse_index_data.csv.
    Computes change vs prior day's close since PREVCLOSE column is 0."""
    out: dict[str, dict] = {}
    if not INDEX_CSV.exists():
        return out
    try:
        df = pd.read_csv(INDEX_CSV, usecols=["SYMBOL", "OPEN", "HIGH", "LOW", "CLOSE",
                                              "TOTTRDQTY", "TIMESTAMP", "HI_52_WK", "LO_52_WK"],
                         low_memory=False)
        df["TIMESTAMP"] = pd.to_datetime(df["TIMESTAMP"], errors="coerce")
        for c in ["OPEN", "HIGH", "LOW", "CLOSE", "TOTTRDQTY", "HI_52_WK", "LO_52_WK"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.dropna(subset=["TIMESTAMP", "CLOSE"])
        df = df.sort_values(["SYMBOL", "TIMESTAMP"])

        last_date = df["TIMESTAMP"].max()
        eod_tag   = last_date.strftime("%d %b") if pd.notna(last_date) else "EOD"

        for sym, grp in df.groupby("SYMBOL"):
            grp   = grp.sort_values("TIMESTAMP")
            today = grp.iloc[-1]
            prev  = grp.iloc[-2] if len(grp) >= 2 else None

            close  = float(today["CLOSE"])
            open_  = float(today["OPEN"]  or 0)
            high   = float(today["HIGH"]  or 0)
            low    = float(today["LOW"]   or 0)
            vol    = float(today["TOTTRDQTY"] or 0)
            hi52   = float(today.get("HI_52_WK", 0) or 0)
            lo52   = float(today.get("LO_52_WK", 0) or 0)
            prev_c = float(prev["CLOSE"]) if prev is not None else 0.0
            chg    = round(close - prev_c, 2) if prev_c > 0 else 0.0
            pchg   = round(chg / prev_c * 100, 2) if prev_c > 0 else 0.0
            key    = str(sym).upper()
            out[key] = {
                "index":     key,
                "lastPrice": close,
                "open":      open_,
                "dayHigh":   high,
                "dayLow":    low,
                "volume":    vol,
                "change":    chg,
                "pChange":   pchg,
                "yearHigh":  hi52,
                "yearLow":   lo52,
                "_eod_date": eod_tag,
            }
    except Exception:
        pass
    return out


def load_eod_stock_prices() -> dict[str, float]:
    """Load last EOD close for all stocks from nse_sec_full_data.csv."""
    if not STOCK_CSV.exists():
        return {}
    try:
        df = pd.read_csv(STOCK_CSV, usecols=["SYMBOL", "TIMESTAMP", "CLOSE"], low_memory=False)
        df["TIMESTAMP"] = pd.to_datetime(df["TIMESTAMP"], errors="coerce")
        df = df.dropna(subset=["TIMESTAMP", "CLOSE"])
        df["CLOSE"] = pd.to_numeric(df["CLOSE"], errors="coerce")
        latest = df.sort_values("TIMESTAMP").groupby("SYMBOL")["CLOSE"].last()
        return latest.to_dict()
    except Exception:
        return {}


def load_nifty_trend(days: int = 10) -> list[dict]:
    """Return last N NIFTY 50 closes from nse_index_data.csv for sparkline display."""
    if not INDEX_CSV.exists():
        return []
    try:
        df = pd.read_csv(INDEX_CSV, usecols=["SYMBOL", "CLOSE", "TIMESTAMP"], low_memory=False)
        df = df[df["SYMBOL"].str.upper() == "NIFTY 50"].copy()
        df["TIMESTAMP"] = pd.to_datetime(df["TIMESTAMP"], errors="coerce")
        df["CLOSE"] = pd.to_numeric(df["CLOSE"], errors="coerce")
        df = df.dropna(subset=["TIMESTAMP", "CLOSE"]).sort_values("TIMESTAMP").tail(days)
        return df[["TIMESTAMP", "CLOSE"]].to_dict("records")
    except Exception:
        return []


def compute_breadth(hist: pd.DataFrame) -> dict:
    """Compute NSE market breadth: A/D, 52w-high, %>200MA, McClellan Oscillator, TRIN."""
    if hist.empty:
        return {}
    try:
        df = hist.copy()
        df = df.sort_values(["SYMBOL", "TIMESTAMP"])

        dates = sorted(df["TIMESTAMP"].dt.date.unique())
        if len(dates) < 2:
            return {}
        d1, d0 = dates[-1], dates[-2]

        today_df = df[df["TIMESTAMP"].dt.date == d1]
        prev_df  = df[df["TIMESTAMP"].dt.date == d0]
        today = today_df.groupby("SYMBOL")["CLOSE"].last()
        prev  = prev_df.groupby("SYMBOL")["CLOSE"].last()
        common = today.index.intersection(prev.index)
        chgs = today[common] / prev[common] - 1

        advances  = int((chgs > 0).sum())
        declines  = int((chgs < 0).sum())
        unchanged = int((chgs == 0).sum())
        total     = advances + declines + unchanged
        ad_ratio  = round(advances / declines, 2) if declines > 0 else 0.0

        # 52w-high proximity: close within 2% of symbol's all-time-high in dataset
        w52_high   = df.groupby("SYMBOL")["HIGH"].max()
        common_idx = today.index.intersection(w52_high.index)
        near52     = int((today[common_idx] >= w52_high[common_idx] * 0.98).sum())

        # % above 200MA — use only symbols present in today's data for speed
        syms_today = set(today.index)
        df_filt = df[df["SYMBOL"].isin(syms_today)]
        ma200_ser = df_filt.groupby("SYMBOL")["CLOSE"].apply(
            lambda x: x.iloc[-200:].mean() if len(x) >= 200 else float("nan")
        )
        last_close = df_filt.groupby("SYMBOL")["CLOSE"].last()
        valid = ma200_ser.dropna()
        above200 = int((last_close.reindex(valid.index) > valid).sum())
        total200 = len(valid)
        pct200   = round(above200 / total200 * 100, 1) if total200 > 0 else 0.0

        # ── McClellan Oscillator: EMA19 - EMA39 of daily (Advances - Declines) ──
        mco = None
        try:
            daily_ad: list[float] = []
            for d in sorted(dates[-60:]):      # last 60 trading days
                tod  = df[df["TIMESTAMP"].dt.date == d].groupby("SYMBOL")["CLOSE"].last()
                prv_d_idx = dates.index(d) - 1
                if prv_d_idx < 0:
                    continue
                prv  = df[df["TIMESTAMP"].dt.date == dates[prv_d_idx]].groupby("SYMBOL")["CLOSE"].last()
                com  = tod.index.intersection(prv.index)
                ch   = tod[com] / prv[com] - 1
                daily_ad.append(float((ch > 0).sum() - (ch < 0).sum()))
            if len(daily_ad) >= 39:
                s = pd.Series(daily_ad)
                ema19 = s.ewm(span=19, adjust=False).mean().iloc[-1]
                ema39 = s.ewm(span=39, adjust=False).mean().iloc[-1]
                mco = round(ema19 - ema39, 1)
        except Exception:
            pass

        # ── TRIN (Arms Index): (Adv/Dec) / (AdvVol/DecVol) ──
        trin = None
        try:
            adv_vol = today_df[today_df["SYMBOL"].isin(common[chgs > 0])]["TOTTRDQTY"].sum()
            dec_vol = today_df[today_df["SYMBOL"].isin(common[chgs < 0])]["TOTTRDQTY"].sum()
            if declines > 0 and dec_vol > 0:
                trin = round((advances / declines) / (adv_vol / dec_vol), 2)
        except Exception:
            pass

        return {
            "advances": advances, "declines": declines, "unchanged": unchanged,
            "total": total, "ad_ratio": ad_ratio, "near_52w_high": near52,
            "above_200ma": above200, "total_200ma": total200,
            "pct_above_200ma": pct200, "date": str(d1),
            "mco": mco, "trin": trin,
        }
    except Exception:
        return {}


def compute_sector_breadth(hist: pd.DataFrame) -> dict[str, dict]:
    """Compute %stocks above 50DMA and 200DMA per sector, using DB sector mapping."""
    result: dict[str, dict] = {}
    if not DB_PATH.exists() or hist.empty:
        return result
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT symbol, sector FROM stage_snapshots "
            "WHERE snapshot_date=(SELECT MAX(snapshot_date) FROM stage_snapshots) "
            "AND sector IS NOT NULL"
        ).fetchall()
        conn.close()
        sector_map = {r[0]: r[1] for r in rows}

        df = hist.copy().sort_values(["SYMBOL", "TIMESTAMP"])
        for sector in set(sector_map.values()):
            syms = [s for s, sec in sector_map.items() if sec == sector]
            d = df[df["SYMBOL"].isin(syms)]
            if d.empty:
                continue
            above50, above200, total = 0, 0, 0
            for sym, grp in d.groupby("SYMBOL"):
                c = grp["CLOSE"].values
                if len(c) < 5:
                    continue
                total += 1
                if len(c) >= 50  and c[-1] > c[-50:].mean():
                    above50  += 1
                if len(c) >= 200 and c[-1] > c[-200:].mean():
                    above200 += 1
            if total:
                result[sector] = {
                    "pct_above_50":  round(above50  / total * 100),
                    "pct_above_200": round(above200 / total * 100),
                    "count": total,
                }
    except Exception:
        pass
    return result




    """Fetch top gainers and losers from NSE."""
    result = {"gainers": [], "losers": []}
    try:
        s = _get_nse_session()
        for side, key in [("gainers", "NIFTY"), ("losers", "NIFTY")]:
            url = f"https://www.nseindia.com/api/live-analysis-variations?index={key}"
            r = s.get(url, timeout=10)
            d = r.json()
            result["gainers"] = d.get("gainers", {}).get("data", [])[:10]
            result["losers"]  = d.get("losers",  {}).get("data", [])[:10]
    except Exception:
        pass
    return result


def fetch_live_ohlcv() -> tuple[dict[str, float], pd.DataFrame]:
    """Fetch live OHLCV + volume for all NSE stocks via equity-stockIndices API.

    Returns:
        live_prices: {SYMBOL: lastPrice}
        live_ohlcv:  DataFrame with columns [SYMBOL, TIMESTAMP, OPEN, HIGH, LOW, CLOSE, TOTTRDQTY]
                     containing today's intraday data for all fetched stocks
    """
    prices: dict[str, float] = {}
    rows:   list[dict]       = []
    today   = pd.Timestamp(datetime.now().date())
    session = _get_nse_session()

    index_names = [
        "NIFTY 500", "NIFTY SMALLCAP 250", "NIFTY MICROCAP 250",
        "NIFTY MIDSMALLCAP 400", "NIFTY TOTAL MARKET",
    ]
    seen: set[str] = set()
    for idx in index_names:
        try:
            url = f"https://www.nseindia.com/api/equity-stockIndices?index={requests.utils.quote(idx)}"
            r   = session.get(url, timeout=12)
            for item in r.json().get("data", []):
                sym = item.get("symbol", "").upper()
                if not sym or sym in seen:
                    continue
                seen.add(sym)
                last = float(item.get("lastPrice",  0) or 0)
                o    = float(item.get("open",        item.get("openPrice",  last)) or last)
                h    = float(item.get("dayHigh",     item.get("highPrice",  last)) or last)
                l    = float(item.get("dayLow",      item.get("lowPrice",   last)) or last)
                vol  = float(item.get("totalTradedVolume", item.get("tradedVolume", 0)) or 0)
                prices[sym] = last
                if last > 0:
                    rows.append({
                        "SYMBOL":    sym,
                        "TIMESTAMP": today,
                        "OPEN":      o,
                        "HIGH":      h,
                        "LOW":       l,
                        "CLOSE":     last,
                        "TOTTRDQTY": vol,
                    })
        except Exception:
            pass
        time.sleep(0.3)

    live_ohlcv = pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["SYMBOL", "TIMESTAMP", "OPEN", "HIGH", "LOW", "CLOSE", "TOTTRDQTY"]
    )
    return prices, live_ohlcv


def fetch_live_prices(symbols: list[str]) -> dict[str, float]:
    """Fetch live prices only (lightweight wrapper around fetch_live_ohlcv)."""
    prices, _ = fetch_live_ohlcv()
    return prices


def patch_live_ohlcv(hist: pd.DataFrame, live_ohlcv: pd.DataFrame) -> pd.DataFrame:
    """Replace / append today's rows in history with live NSE intraday OHLCV.

    This ensures that RSI, ADX, MACD, supertrend etc. are computed on
    today's live price action — not on yesterday's EOD data.
    """
    if live_ohlcv.empty or hist.empty:
        return hist

    today = pd.Timestamp(datetime.now().date())
    # Drop any existing rows for today (could be partial from CSV)
    hist_no_today = hist[hist["TIMESTAMP"].dt.date != today.date()]
    # Append live data
    combined = pd.concat([hist_no_today, live_ohlcv], ignore_index=True)
    return combined.sort_values(["SYMBOL", "TIMESTAMP"])



# ─────────────────────────────────────────────────────────────────────────────
# Technical signal computation
# ─────────────────────────────────────────────────────────────────────────────

def load_price_history(days: int = 260) -> pd.DataFrame:
    """Load recent price history from nse_sec_full_data.csv."""
    if not STOCK_CSV.exists():
        return pd.DataFrame()
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    df = pd.read_csv(STOCK_CSV, usecols=["SYMBOL", "TIMESTAMP", "OPEN", "HIGH", "LOW", "CLOSE", "TOTTRDQTY"])
    df = df[df["TIMESTAMP"] >= cutoff]
    df["TIMESTAMP"] = pd.to_datetime(df["TIMESTAMP"])
    for c in ["OPEN", "HIGH", "LOW", "CLOSE", "TOTTRDQTY"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def detect_darvas(grp: pd.DataFrame, box_days: int = 20) -> dict:
    """Darvas Box: find recent consolidation box and detect breakout above box top."""
    grp = grp.sort_values("TIMESTAMP")
    if len(grp) < box_days + 5:
        return {"is_darvas": False}
    try:
        h = grp["HIGH"].values
        l = grp["LOW"].values
        c = grp["CLOSE"].values
        v = grp["TOTTRDQTY"].values

        # Box defined by last box_days bars (excluding today)
        box_h  = h[-(box_days+1):-1].max()
        box_l  = l[-(box_days+1):-1].min()
        today  = c[-1]
        prev_c = c[-2]

        # Breakout above box top with volume confirmation
        avg_vol = v[-(box_days+1):-1].mean() if len(v) > box_days else v[-1]
        vol_ok  = v[-1] > avg_vol * 1.3
        is_darvas = (today > box_h) and (prev_c <= box_h) and vol_ok

        # Box tightness: smaller box = better setup
        box_range_pct = round((box_h - box_l) / box_l * 100, 1) if box_l > 0 else 0

        return {
            "is_darvas":     is_darvas,
            "box_top":       round(box_h, 2),
            "box_bottom":    round(box_l, 2),
            "box_range_pct": box_range_pct,
            "vol_confirmed": vol_ok,
            "current":       today,
        }
    except Exception:
        return {"is_darvas": False}


def is_52w_momentum(grp: pd.DataFrame) -> dict:
    """52-Week High Momentum: close within 5% of 52w high AND rising RS proxy."""
    grp = grp.sort_values("TIMESTAMP")
    if len(grp) < 50:
        return {"is_52w_mom": False}
    try:
        c   = grp["CLOSE"].values
        h   = grp["HIGH"].values
        w52 = h[:-1].max()
        cur = c[-1]

        near_high = cur >= w52 * 0.95          # within 5% of 52w high
        # Rising RS proxy: 20d return > 50d return (momentum accelerating)
        ret_20 = (c[-1] / c[-20] - 1) if len(c) >= 20 else 0
        ret_50 = (c[-1] / c[-50] - 1) if len(c) >= 50 else 0
        rising_rs = ret_20 > ret_50 * 0.5     # 20d stronger than half of 50d

        return {
            "is_52w_mom": near_high and rising_rs,
            "w52_high":   round(w52, 2),
            "pct_from_52h": round((cur / w52 - 1) * 100, 1) if w52 > 0 else 0,
            "ret_20d":    round(ret_20 * 100, 1),
            "current":    cur,
        }
    except Exception:
        return {"is_52w_mom": False}


def detect_breakout(grp: pd.DataFrame, lookback: int = 52) -> dict:
    """Detect 52-week high breakout and recent resistance breakout."""
    grp = grp.sort_values("TIMESTAMP")
    if len(grp) < 20:
        return {}
    close = grp["CLOSE"].values
    vol   = grp["TOTTRDQTY"].values
    high  = grp["HIGH"].values

    current  = close[-1]
    prev_c   = close[-2] if len(close) > 1 else current
    w52_high = high[:-1].max() if len(high) > 1 else high[-1]
    w20_high = high[max(0, len(high)-20):-1].max() if len(high) > 20 else high[-1]

    avg_vol_20 = vol[max(0, len(vol)-21):-1].mean() if len(vol) > 20 else vol[-1]
    today_vol  = vol[-1]

    is_52w_breakout   = current >= w52_high and current > prev_c
    is_20d_breakout   = current >= w20_high and current > prev_c
    vol_confirmed     = today_vol > avg_vol_20 * 1.5 if avg_vol_20 > 0 else False
    chg_pct           = (current / prev_c - 1) * 100 if prev_c > 0 else 0

    return {
        "is_52w_breakout": is_52w_breakout,
        "is_20d_breakout": is_20d_breakout,
        "vol_confirmed":   vol_confirmed,
        "chg_pct":         round(chg_pct, 2),
        "current":         current,
        "w52_high":        round(w52_high, 2),
        "w20_high":        round(w20_high, 2),
    }


def detect_vcp(grp: pd.DataFrame) -> dict:
    """
    Volatility Contraction Pattern:
    - At least 3 pivots of contracting high-low range
    - Volume declining on each contraction
    - Price holding above 50-day MA
    """
    grp = grp.sort_values("TIMESTAMP")
    if len(grp) < 30:
        return {"is_vcp": False}

    # Slice last 30 bars into 3 x 10-bar windows
    windows = [grp.iloc[i*10:(i+1)*10] for i in range(3)]
    ranges  = [(w["HIGH"].max() - w["LOW"].min()) / w["CLOSE"].mean() * 100 for w in windows]
    vols    = [w["TOTTRDQTY"].mean() for w in windows]

    contracting_range = ranges[0] > ranges[1] > ranges[2]
    contracting_vol   = vols[0] > vols[1]  # at least first two declining

    close  = grp["CLOSE"].values
    sma50  = close[-50:].mean() if len(close) >= 50 else None
    above_sma50 = close[-1] > sma50 if sma50 else False

    tightness = round(ranges[2], 2)  # last window range %
    is_vcp = contracting_range and contracting_vol and above_sma50 and tightness < 8

    return {
        "is_vcp":    is_vcp,
        "tightness": tightness,
        "ranges":    [round(r, 2) for r in ranges],
        "current":   float(close[-1]),
    }


def compute_supertrend(grp: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> Optional[str]:
    """Returns 'BUY' or 'SELL' based on Supertrend."""
    grp = grp.sort_values("TIMESTAMP").tail(60)
    if len(grp) < 20:
        return None
    if HAS_TA:
        try:
            st = ta.supertrend(grp["HIGH"], grp["LOW"], grp["CLOSE"],
                               length=period, multiplier=multiplier)
            if st is not None and not st.empty:
                col = [c for c in st.columns if "SUPERTd" in c]
                if col:
                    val = st[col[0]].iloc[-1]
                    return "BUY" if val == 1 else "SELL"
        except Exception:
            pass
    # Fallback: manual supertrend
    try:
        h, l, c = grp["HIGH"].values, grp["LOW"].values, grp["CLOSE"].values
        atr = pd.Series(
            [max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1])) for i in range(1, len(c))],
        ).rolling(period).mean().values
        basic_upper = (h[1:] + l[1:]) / 2 + multiplier * atr
        basic_lower = (h[1:] + l[1:]) / 2 - multiplier * atr
        if len(c) > 2:
            return "BUY" if c[-1] > basic_lower[-1] else "SELL"
    except Exception:
        pass
    return None


def compute_rsi(series: pd.Series, period: int = 14) -> float:
    """Compute RSI."""
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, 1e-9)
    rsi   = 100 - 100 / (1 + rs)
    return float(rsi.iloc[-1]) if not rsi.empty else 50.0


def is_above_key_mas(grp: pd.DataFrame) -> dict:
    """Check if price is above SMA20, SMA50, SMA200."""
    grp  = grp.sort_values("TIMESTAMP")
    c    = grp["CLOSE"].values
    cur  = c[-1]
    sma20  = c[-20:].mean()  if len(c) >= 20  else None
    sma50  = c[-50:].mean()  if len(c) >= 50  else None
    sma200 = c[-200:].mean() if len(c) >= 200 else None
    return {
        "above_sma20":  cur > sma20  if sma20  else False,
        "above_sma50":  cur > sma50  if sma50  else False,
        "above_sma200": cur > sma200 if sma200 else False,
        "sma20":  round(sma20, 2)  if sma20  else None,
        "sma50":  round(sma50, 2)  if sma50  else None,
        "sma200": round(sma200, 2) if sma200 else None,
    }


_ETF_KEYWORDS = {"LIQUID", "BEES", "NIFTY", "SENSEX", "GOLDETF", "SILVER", "IETF",
                  "NIFTYBEES", "JUNIORBEES", "BANKBEES", "SETFNN50", "COMMOIETF",
                  "GROWW", "CASHGRO", "HDFCL", "LIQGRO"}

def _is_etf(sym: str) -> bool:
    s = sym.upper()
    return any(kw in s for kw in _ETF_KEYWORDS) or s.endswith("ETF") or s.endswith("FUND")


def compute_adx(grp: pd.DataFrame, period: int = 14) -> float:
    """Average Directional Index — trend strength 0–100."""
    grp = grp.sort_values("TIMESTAMP").tail(60)
    if len(grp) < period + 2:
        return 0.0
    try:
        h = grp["HIGH"].values
        l = grp["LOW"].values
        c = grp["CLOSE"].values
        tr  = [max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1])) for i in range(1, len(c))]
        pdm = [max(h[i]-h[i-1], 0) if (h[i]-h[i-1]) > (l[i-1]-l[i]) else 0 for i in range(1, len(h))]
        ndm = [max(l[i-1]-l[i], 0) if (l[i-1]-l[i]) > (h[i]-h[i-1]) else 0 for i in range(1, len(l))]
        atr  = pd.Series(tr).ewm(span=period, adjust=False).mean()
        pdi  = 100 * pd.Series(pdm).ewm(span=period, adjust=False).mean() / atr.replace(0, 1e-9)
        ndi  = 100 * pd.Series(ndm).ewm(span=period, adjust=False).mean() / atr.replace(0, 1e-9)
        dsum = (pdi + ndi).replace(0, 1e-9)
        dx   = 100 * abs(pdi - ndi) / dsum
        adx  = dx.ewm(span=period, adjust=False).mean()
        return round(float(adx.iloc[-1]), 1)
    except Exception:
        return 0.0


def compute_macd_hist(closes: pd.Series) -> float:
    """MACD histogram value (positive = bullish momentum, negative = bearish)."""
    if len(closes) < 26:
        return 0.0
    try:
        ema12  = closes.ewm(span=12, adjust=False).mean()
        ema26  = closes.ewm(span=26, adjust=False).mean()
        macd   = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        return round(float(macd.iloc[-1] - signal.iloc[-1]), 4)
    except Exception:
        return 0.0


def load_rs_from_db() -> dict[str, dict]:
    """Load relative_strength, change_1w_pct, change_1m_pct, supertrend_state
    for all symbols from the latest DB snapshot."""
    if not DB_PATH.exists():
        return {}
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT symbol, relative_strength, change_1w_pct, change_1m_pct, supertrend_state "
            "FROM stage_snapshots "
            "WHERE snapshot_date=(SELECT MAX(snapshot_date) FROM stage_snapshots)"
        ).fetchall()
        conn.close()
        return {
            r[0]: {
                "rs":       float(r[1]) if r[1] is not None else None,
                "chg_1w":   float(r[2]) if r[2] is not None else None,
                "chg_1m":   float(r[3]) if r[3] is not None else None,
                "st_state": r[4] or None,
            }
            for r in rows
        }
    except Exception:
        return {}


def run_screener(hist: pd.DataFrame, live_prices: dict, top_n: int = 20) -> dict:
    """
    Run all technical screens. Returns dict of signal → list of stock dicts.
    """
    results = {
        "supertrend_buy":  [],
        "breakouts_52w":   [],
        "breakouts_20d":   [],
        "vcp_setups":      [],
        "stage2_leaders":  [],
        "darvas_setups":   [],
        "momentum_52w":    [],
    }

    # Load Stage 2 stocks + RS + extended data from DB
    stage2_syms: set[str] = set()
    stage2_info: dict[str, dict] = {}
    db_data = load_rs_from_db()   # rs, chg_1w, chg_1m, st_state for all universe stocks
    if DB_PATH.exists():
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT symbol, stage_score, investment_score, sector, trading_signal "
            "FROM stage_snapshots WHERE snapshot_date=(SELECT MAX(snapshot_date) FROM stage_snapshots) "
            "AND stage='STAGE_2' ORDER BY investment_score DESC"
        ).fetchall()
        conn.close()
        for r in rows:
            stage2_syms.add(r[0])
            stage2_info[r[0]] = {
                "stage_score": r[1], "investment_score": r[2],
                "sector": r[3], "trading_signal": r[4],
            }

    for sym, grp in hist.groupby("SYMBOL"):
        if _is_etf(sym):
            continue
        grp = grp.sort_values("TIMESTAMP")
        if len(grp) < 20:
            continue

        live    = live_prices.get(sym.upper())
        current = live or float(grp["CLOSE"].iloc[-1])
        prev_c  = float(grp["CLOSE"].iloc[-2]) if len(grp) > 1 else current
        chg_pct = round((current / prev_c - 1) * 100, 2) if prev_c else 0

        rsi  = compute_rsi(grp["CLOSE"])
        mas  = is_above_key_mas(grp)
        st   = compute_supertrend(grp)
        adx  = compute_adx(grp)
        macd = compute_macd_hist(grp["CLOSE"])

        # RS: from DB (decimal × 100 → show as %) or None
        db_extra = db_data.get(sym, {})
        rs_raw   = db_extra.get("rs")
        rs_pct   = round(rs_raw * 100, 1) if rs_raw is not None else None

        base = {
            "symbol":  sym,
            "price":   current,
            "chg_pct": chg_pct,
            "rsi":     round(rsi, 1),
            "st":      st,
            "adx":     adx,
            "macd":    macd,
            "rs":      rs_pct,
            "chg_1w":  db_extra.get("chg_1w"),
            "chg_1m":  db_extra.get("chg_1m"),
            **mas,
        }

        # 1. Supertrend BUY + above SMA50
        if st == "BUY" and mas["above_sma50"] and rsi > 50:
            results["supertrend_buy"].append({**base, **stage2_info.get(sym, {})})

        # 2. Breakouts
        bo = detect_breakout(grp)
        if bo.get("is_52w_breakout"):
            results["breakouts_52w"].append({**base, **bo, **stage2_info.get(sym, {})})
        elif bo.get("is_20d_breakout") and bo.get("vol_confirmed"):
            results["breakouts_20d"].append({**base, **bo, **stage2_info.get(sym, {})})

        # 3. VCP
        vcp = detect_vcp(grp)
        if vcp.get("is_vcp"):
            results["vcp_setups"].append({**base, **vcp, **stage2_info.get(sym, {})})

        # 4. Darvas Box Breakout
        darvas = detect_darvas(grp)
        if darvas.get("is_darvas"):
            results["darvas_setups"].append({**base, **darvas, **stage2_info.get(sym, {})})

        # 5. 52-Week High Momentum
        mom = is_52w_momentum(grp)
        if mom.get("is_52w_mom") and (rs_pct is None or rs_pct >= 0):
            results["momentum_52w"].append({**base, **mom, **stage2_info.get(sym, {})})

    # 6. Stage 2 leaders (from DB, sorted by investment score)
    for sym, info in stage2_info.items():
        grp = hist[hist["SYMBOL"] == sym]
        if grp.empty:
            continue
        grp     = grp.sort_values("TIMESTAMP")
        live    = live_prices.get(sym.upper())
        current = live or float(grp["CLOSE"].iloc[-1])
        prev_c  = float(grp["CLOSE"].iloc[-2]) if len(grp) > 1 else current
        chg_pct = round((current / prev_c - 1) * 100, 2) if prev_c else 0
        rsi     = compute_rsi(grp["CLOSE"])
        mas     = is_above_key_mas(grp)
        db_extra = db_data.get(sym, {})
        rs_raw   = db_extra.get("rs")
        results["stage2_leaders"].append({
            "symbol": sym, "price": current, "chg_pct": chg_pct,
            "rsi": round(rsi, 1),
            "rs":  round(rs_raw * 100, 1) if rs_raw is not None else None,
            "chg_1w": db_extra.get("chg_1w"),
            "chg_1m": db_extra.get("chg_1m"),
            **mas, **info,
        })

    # Sort and trim
    results["supertrend_buy"].sort(key=lambda x: x.get("rsi", 0), reverse=True)
    results["breakouts_52w"].sort(key=lambda x: x.get("chg_pct", 0), reverse=True)
    results["breakouts_20d"].sort(key=lambda x: x.get("chg_pct", 0), reverse=True)
    results["vcp_setups"].sort(key=lambda x: x.get("tightness", 99))
    results["stage2_leaders"].sort(key=lambda x: float(x.get("investment_score") or 0), reverse=True)
    results["darvas_setups"].sort(key=lambda x: x.get("chg_pct", 0), reverse=True)
    results["momentum_52w"].sort(key=lambda x: x.get("pct_from_52h", -99), reverse=True)

    for k in results:
        results[k] = results[k][:top_n]

    # Market breadth from same history
    results["breadth"] = compute_breadth(hist)

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Rich UI builders
# ─────────────────────────────────────────────────────────────────────────────

def _update_flash(key: str, cur: float) -> Optional[str]:
    """Track price changes and return a bright flash style when price moves.
    Returns None when no recent change (caller uses their own base colour).
    """
    now = time.time()
    prev = _prev_prices.get(key)
    if prev is not None and cur != prev:
        _flash_expires[key]   = now + _FLASH_SECS
        _flash_direction[key] = "up" if cur > prev else "dn"
    _prev_prices[key] = cur
    if _flash_expires.get(key, 0) > now:
        return "bold bright_green" if _flash_direction.get(key) == "up" else "bold bright_red"
    return None


def _rule_narrative(indices: dict, breadth: dict, signals: dict) -> str:
    """Build a concise market narrative from current data without an LLM."""
    nifty  = indices.get("NIFTY 50", {})
    nv     = _parse_price(nifty.get("lastPrice", 0))
    pchg   = _parse_price(nifty.get("pChange",   0))
    adv    = breadth.get("advances", 0)
    dec    = breadth.get("declines", 0)
    mco    = breadth.get("mco",      0)
    trin   = breadth.get("trin",     1.0)
    hi52   = breadth.get("new_highs", 0)
    ab200  = breadth.get("above_200ma_pct", 0)

    dir_w  = "gaining" if pchg > 0.3 else ("under pressure" if pchg < -0.3 else "flat")
    trin_w = ("institutional accumulation" if trin < 0.7
               else "net distribution" if trin > 1.3 else "balanced flows")
    mco_w  = "expanding breadth" if mco > 20 else ("deteriorating breadth" if mco < -20 else "neutral breadth")

    # Top sector by pChange
    top_sec = max(
        ((k, _parse_price(indices.get(v.replace("Nifty ", "NIFTY ").upper(), {}).get("pChange", 0)))
         for k, v in SECTOR_INDEX_MAP.items()),
        key=lambda x: x[1], default=("—", 0)
    )

    l1 = (f"NIFTY 50 is {dir_w} at {nv:,.0f} ({pchg:+.2f}%).")
    l2 = (f"Breadth {adv}↑/{dec}↓; MCO {mco:+.0f} ({mco_w}), "
          f"TRIN {trin:.2f} signals {trin_w}.")
    l3 = (f"{hi52} stocks hit 52W highs; {ab200:.0f}% above 200DMA. "
          f"Leading sector: {top_sec[0]} ({top_sec[1]:+.2f}%).")
    return f"{l1}  {l2}  {l3}"


def _fetch_llm_narrative(indices: dict, breadth: dict, signals: dict) -> None:
    """Background thread: ask OpenAI for a 2-sentence market summary and update cache."""
    import os
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        return
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key)
        nifty = indices.get("NIFTY 50", {})
        payload = {
            "nifty": _parse_price(nifty.get("lastPrice", 0)),
            "nifty_pchg": _parse_price(nifty.get("pChange", 0)),
            "advances": breadth.get("advances", 0),
            "declines": breadth.get("declines", 0),
            "mco": breadth.get("mco", 0),
            "trin": breadth.get("trin", 1),
            "new_highs_52w": breadth.get("new_highs", 0),
            "above_200dma_pct": breadth.get("above_200ma_pct", 0),
            "supertrend_buys": len(signals.get("supertrend_buy", [])),
            "vcp_setups": len(signals.get("vcp_setups", [])),
            "darvas_breakouts": len(signals.get("darvas_setups", [])),
        }
        prompt = (
            "You are a terse NSE market analyst. Write exactly 2 sentences of market commentary "
            f"based on this live data: {json.dumps(payload)}. "
            "Be specific with numbers. No bullet points. No investment advice disclaimer."
        )
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=120, temperature=0.6,
        )
        text = resp.choices[0].message.content.strip()
        with _narrative_lock:
            _narrative_cache["text"] = text
            _narrative_cache["ts"]   = time.time()
    except Exception:
        pass


def _ensure_narrative(indices: dict, breadth: dict, signals: dict) -> str:
    """Return a current narrative string, refreshing via LLM if stale."""
    now = time.time()
    with _narrative_lock:
        age  = now - _narrative_cache.get("ts", 0)
        text = _narrative_cache.get("text", "")

    if age > _NARRATIVE_TTL or not text:
        # Fire background LLM call; return rule-based immediately
        threading.Thread(
            target=_fetch_llm_narrative,
            args=(indices, breadth, signals),
            daemon=True,
        ).start()

    return text or _rule_narrative(indices, breadth, signals)


def build_narrative_panel(text: str) -> Panel:
    """One-line market narrative strip below breadth bar."""
    t = Text()
    t.append("  📰 ", style="bold yellow")
    t.append(text, style="italic white")
    return Panel(t, height=3, style="on grey11")


def build_nlp_panel(query: str, response: str, ts: str, pending: bool) -> Panel:
    """Agent Adda inline Q&A panel shown at the bottom of the terminal."""
    grid = Table.grid(expand=True, padding=(0, 1))
    grid.add_column()

    if pending:
        grid.add_row(Text("  ⏳ Agent thinking…", style="bold yellow"))
    elif query and response:
        q_line = Text()
        q_line.append("  ❓ ", style="bold cyan")
        q_line.append(query, style="bold white")
        a_line = Text()
        a_line.append("  🤖 ", style="bold green")
        a_line.append(response, style="white")
        grid.add_row(q_line)
        grid.add_row(a_line)
    else:
        grid.add_row(Text(
            "  💬 Agent Adda ready  —  press [/] then type your query and hit Enter",
            style="dim italic",
        ))

    hint = Text()
    hint.append("  Press ", style="dim")
    hint.append("[/]", style="bold cyan")
    hint.append(" to query  │  ", style="dim")
    if ts:
        hint.append(f"last answered {ts}", style="dim")
    return Panel(grid, title="[bold cyan]💬 Agent Adda[/bold cyan]",
                 subtitle=hint, style="on grey7", height=6 if (query and response) else 4)


def _chg_color(v: float) -> str:
    if v > 1.5:  return "bold green"
    if v > 0:    return "green"
    if v < -1.5: return "bold red"
    if v < 0:    return "red"
    return "white"


def _rsi_color(v: float) -> str:
    if v >= 70: return "bold red"
    if v >= 55: return "green"
    if v >= 40: return "white"
    return "cyan"


def _st_color(s: Optional[str]) -> str:
    return "green" if s == "BUY" else ("red" if s == "SELL" else "white")


def build_header(indices: dict, refresh_mins: int = 5) -> Panel:
    now_ist = datetime.now().strftime("%a %d %b %Y  %H:%M:%S IST")
    nifty   = indices.get("NIFTY 50", {})
    nv      = _parse_price(nifty.get("lastPrice", 0))
    nc      = _parse_price(nifty.get("change",    0))
    np_     = _parse_price(nifty.get("pChange",   0))
    is_eod  = bool(nifty.get("_eod_date"))
    market_open = _market_is_open()

    arrow = "▲" if nc >= 0 else "▼"
    base_clr = "green" if nc >= 0 else "red"
    flash_clr = _update_flash("NIFTY50", nv)   # bright flash when price ticks
    nv_clr  = flash_clr or f"bold {base_clr}"
    chg_clr = flash_clr or base_clr

    txt = Text()
    txt.append("  ⚡ NSE TERMINAL  ", style="bold white on dark_blue")
    txt.append("  ")
    txt.append(now_ist, style="bold cyan")
    txt.append("    ")
    if market_open:
        txt.append("● MARKET OPEN", style="bold green")
    elif is_eod:
        eod_date = nifty.get("_eod_date", "EOD")
        txt.append(f"● CLOSED  │  EOD {eod_date}", style="bold yellow")
    else:
        txt.append("● MARKET CLOSED", style="bold red")
    txt.append("    NIFTY 50  ", style="bold white")
    txt.append(f"{nv:,.0f}" if nv else "—", style=nv_clr)
    if nc != 0:
        txt.append(f"  {arrow} {abs(nc):,.0f}  ({np_:+.2f}%)", style=chg_clr)
    txt.append(f"  │  🔄 /{refresh_mins}min  │  [/] to query", style="dim")

    return Panel(txt, style="on dark_blue", height=3)


def _parse_price(v) -> float:
    """Parse NSE price which may be a string like '24,119.30' or a float."""
    try:
        if isinstance(v, str):
            return float(v.replace(",", ""))
        return float(v or 0)
    except Exception:
        return 0.0


def build_indices_bar(indices: dict) -> Panel:
    """Full-width horizontal indices ticker showing OHLC + CHG% for all watchlist indices."""
    tbl = Table(box=None, padding=(0, 2), expand=True, show_header=False)
    tbl.add_column("data", no_wrap=True)

    cells: list[Text] = []
    for key, label in WATCHLIST_INDICES:
        d = indices.get(key.upper(), {})
        if not d:
            continue
        price = _parse_price(d.get("lastPrice", 0))
        pchg  = _parse_price(d.get("pChange",   0))
        high  = _parse_price(d.get("dayHigh",  d.get("highPrice",  0)))
        low   = _parse_price(d.get("dayLow",   d.get("lowPrice",   0)))
        base_clr = _chg_color(pchg)
        flash    = _update_flash(f"IDX:{key}", price)
        p_clr    = flash or f"bold {base_clr}"
        arrow    = "▲" if pchg >= 0 else "▼"

        cell = Text()
        cell.append(f"{label.strip()} ", style="bold white")
        cell.append(f"{price:,.0f}", style=p_clr) if price else cell.append("—", style="dim")
        if pchg != 0:
            cell.append(f"  {arrow}{abs(pchg):.2f}%", style=flash or base_clr)
        if high and low:
            cell.append(f"  H:{high:,.0f} L:{low:,.0f}", style="dim")
        cells.append(cell)

    # Lay cells out in a single row separated by dim │
    row_text = Text()
    for i, cell in enumerate(cells):
        row_text.append_text(cell)
        if i < len(cells) - 1:
            row_text.append("  │  ", style="dim")

    tbl.add_row(row_text)
    is_eod   = any(v.get("_eod_date") for v in indices.values())
    subtitle = (f"[dim]EOD {next((v['_eod_date'] for v in indices.values() if v.get('_eod_date')), '')}[/dim]"
                if is_eod else "[dim]Live NSE[/dim]")
    return Panel(tbl, title="[bold cyan]■ INDICES  O/H/L/C[/bold cyan]", border_style="cyan",
                 height=4, subtitle=subtitle)



def build_sector_table(indices: dict, sector_breadth: dict | None = None) -> Panel:
    """Full-width horizontal sector bar sorted by performance, with breadth %50DMA."""
    sector_perf: list[tuple] = []
    for sector, idx_name in SECTOR_INDEX_MAP.items():
        d     = indices.get(idx_name.upper(), {})
        pchg  = _parse_price(d.get("pChange",   0)) if d else 0
        price = _parse_price(d.get("lastPrice", 0)) if d else 0
        sector_perf.append((sector, idx_name, pchg, price))
    sector_perf.sort(key=lambda x: x[2], reverse=True)

    row_text = Text()
    sb = sector_breadth or {}
    for i, (sector, idx_name, pchg, price) in enumerate(sector_perf):
        clr     = _chg_color(pchg)
        arrow   = "▲" if pchg >= 0 else "▼"
        signal  = "LEAD" if pchg > 1 else ("LAG" if pchg < -1 else "NEUT")
        sig_clr = "bold green" if signal == "LEAD" else ("bold red" if signal == "LAG" else "yellow")

        row_text.append(f"{sector} ", style="bold white")
        if price:
            row_text.append(f"{price:,.0f}", style=f"bold {clr}")
        if pchg != 0:
            row_text.append(f" {arrow}{abs(pchg):.2f}%", style=clr)
        row_text.append(f" [{signal}]", style=sig_clr)
        # Sector breadth: % above 50DMA
        bd = sb.get(idx_name) or sb.get(sector)
        if bd:
            p50 = bd.get("pct_above_50", 0)
            b_clr = "green" if p50 >= 60 else ("yellow" if p50 >= 40 else "red")
            row_text.append(f" {p50}%>50d", style=b_clr)
        if i < len(sector_perf) - 1:
            row_text.append("  │  ", style="dim")

    tbl = Table(box=None, padding=(0, 1), expand=True, show_header=False)
    tbl.add_column("data", no_wrap=True)
    tbl.add_row(row_text)
    return Panel(tbl, title="[bold magenta]■ SECTOR ROTATION[/bold magenta]",
                 border_style="magenta", height=4, subtitle="[dim]sorted by CHG%  │  %>50DMA breadth[/dim]")


def _sparkline(values: list[float]) -> Text:
    """Unicode block sparkline coloured green/red per direction."""
    BLOCKS = "▁▂▃▄▅▆▇█"
    t = Text()
    if not values or len(values) < 2:
        return t
    mn, mx = min(values), max(values)
    prev = None
    for v in values:
        idx = int((v - mn) / (mx - mn) * 7) if mx > mn else 3
        clr = "green" if (prev is None or v >= prev) else "red"
        t.append(BLOCKS[idx], style=clr)
        prev = v
    return t


def build_breadth_bar(breadth: dict, trend: list[dict]) -> Panel:
    """Full-width market breadth + McClellan Oscillator + TRIN + Nifty sparkline."""
    row = Text()

    if breadth:
        adv    = breadth.get("advances",  0)
        dec    = breadth.get("declines",  0)
        unch   = breadth.get("unchanged", 0)
        adr    = breadth.get("ad_ratio",  0.0)
        n52    = breadth.get("near_52w_high", 0)
        p200   = breadth.get("pct_above_200ma", 0.0)
        ab200  = breadth.get("above_200ma", 0)
        tot200 = breadth.get("total_200ma", 0)
        mco    = breadth.get("mco")
        trin   = breadth.get("trin")

        row.append("A/D  ", style="bold white")
        row.append(f"{adv}▲", style="bold green")
        row.append(" / ", style="dim")
        row.append(f"{dec}▼", style="bold red")
        if unch:
            row.append(f" / {unch}─", style="dim")
        adr_clr = "bold green" if adr >= 1.2 else ("green" if adr >= 1 else "red")
        row.append("  ratio ", style="dim")
        row.append(f"{adr:.2f}", style=adr_clr)

        row.append("  │  52W-Hi: ", style="dim")
        row.append(f"{n52}", style="bold yellow")

        row.append("  │  >200MA: ", style="dim")
        p200_clr = ("bold green" if p200 >= 60 else "green" if p200 >= 50 else
                    "yellow" if p200 >= 40 else "red")
        row.append(f"{p200:.0f}%", style=p200_clr)
        row.append(f" ({ab200}/{tot200})", style="dim")

        # McClellan Oscillator
        if mco is not None:
            row.append("  │  MCO: ", style="dim")
            mco_clr = "bold green" if mco > 50 else ("green" if mco > 0 else ("red" if mco > -50 else "bold red"))
            row.append(f"{mco:+.0f}", style=mco_clr)

        # TRIN (Arms Index): <0.85 overbought/bull, >1.15 oversold/bear
        if trin is not None:
            row.append("  │  TRIN: ", style="dim")
            trin_clr = "bold green" if trin < 0.7 else ("green" if trin < 0.9 else
                       "yellow" if trin < 1.1 else ("red" if trin < 1.3 else "bold red"))
            trin_lbl = " (bull)" if trin < 0.9 else (" (bear)" if trin > 1.1 else "")
            row.append(f"{trin:.2f}", style=trin_clr)
            row.append(trin_lbl, style="dim")

    if trend:
        closes = [float(r["CLOSE"]) for r in trend]
        dates  = [r["TIMESTAMP"]    for r in trend]
        d0 = dates[0].strftime("%d%b")  if hasattr(dates[0],  "strftime") else str(dates[0])[:5]
        d1 = dates[-1].strftime("%d%b") if hasattr(dates[-1], "strftime") else str(dates[-1])[:5]
        chg    = round((closes[-1] / closes[0] - 1) * 100, 2) if closes[0] > 0 else 0
        updays = sum(1 for i in range(1, len(closes)) if closes[i] >= closes[i - 1])
        chg_clr = "green" if chg >= 0 else "red"

        row.append("  │  ", style="dim")
        row.append(f"Nifty {len(closes)}d  ", style="bold white")
        row.append_text(_sparkline(closes))
        row.append(f"  {d0}→{d1}  ", style="dim")
        row.append(f"{chg:+.2f}%", style=f"bold {chg_clr}")
        row.append(f"  ({updays}/{len(closes)-1} up)", style="dim")

    tbl = Table(box=None, padding=(0, 1), expand=True, show_header=False)
    tbl.add_column("data", no_wrap=True)
    tbl.add_row(row)
    return Panel(tbl, title="[bold blue]■ MARKET BREADTH  MCO  TRIN[/bold blue]",
                 border_style="blue", height=4, subtitle="[dim]NSE universe[/dim]")


def build_signal_table(title: str, icon: str, items: list, columns: list,
                        border_color: str = "green") -> Panel:
    tbl = Table(box=box.SIMPLE_HEAD, header_style=f"bold {border_color}",
                expand=True, padding=(0, 1))
    for col_name, justify, width in columns:
        tbl.add_column(col_name, justify=justify, width=width, no_wrap=True)

    for item in items:
        row = _build_row(item, columns)
        tbl.add_row(*row)

    count = f"[dim]{len(items)} stocks[/dim]"
    return Panel(tbl, title=f"[bold {border_color}]{icon} {title}[/bold {border_color}]",
                 border_style=border_color, subtitle=count)


def _build_row(item: dict, columns: list) -> list:
    """Build a formatted row using Text objects (prevents ANSI bleed on truncation)."""
    row = []
    for col_name, justify, width in columns:
        val = item.get(col_name.lower().replace(" ", "_").replace("%", "pct").replace("/", "_"))

        if col_name == "SYMBOL":
            s = str(item.get("symbol", "—"))
            t = Text(s, style="bold white", no_wrap=True)
            if item.get("investment_score") is not None:
                t.append(" ★", style="green")
            row.append(t)

        elif col_name in ("PRICE", "W52H", "W20H"):
            key_map = {"PRICE": "price", "W52H": "w52_high", "W20H": "w20_high"}
            v = item.get(key_map.get(col_name, col_name.lower()), 0)
            row.append(Text(f"₹{float(v or 0):,.1f}", no_wrap=True) if v else Text("—", style="dim"))

        elif col_name == "CHG%":
            v   = float(item.get("chg_pct", 0) or 0)
            row.append(Text(f"{v:+.2f}%", style=_chg_color(v), no_wrap=True))

        elif col_name == "RSI":
            v   = float(item.get("rsi", 50) or 50)
            row.append(Text(f"{v:.0f}", style=_rsi_color(v), no_wrap=True))

        elif col_name == "ADX":
            v   = float(item.get("adx", 0) or 0)
            clr = "bold green" if v >= 40 else ("green" if v >= 25 else ("yellow" if v >= 20 else "dim"))
            row.append(Text(f"{v:.0f}", style=clr, no_wrap=True) if v else Text("—", style="dim"))

        elif col_name == "RS":
            v = item.get("rs")
            if v is not None:
                fv  = float(v)
                clr = "bold green" if fv >= 20 else ("green" if fv >= 5 else ("red" if fv <= -5 else "yellow"))
                row.append(Text(f"{fv:+.0f}", style=clr, no_wrap=True))
            else:
                row.append(Text("—", style="dim"))

        elif col_name == "MACD":
            v = item.get("macd", 0) or 0
            if float(v) > 0:
                row.append(Text("▲", style="green", no_wrap=True))
            elif float(v) < 0:
                row.append(Text("▼", style="red", no_wrap=True))
            else:
                row.append(Text("─", style="dim", no_wrap=True))

        elif col_name == "1W%":
            v = item.get("chg_1w")
            if v is not None:
                fv  = float(v)
                row.append(Text(f"{fv:+.1f}%", style=_chg_color(fv), no_wrap=True))
            else:
                row.append(Text("—", style="dim"))

        elif col_name == "1M%":
            v = item.get("chg_1m")
            if v is not None:
                fv  = float(v)
                row.append(Text(f"{fv:+.1f}%", style=_chg_color(fv), no_wrap=True))
            else:
                row.append(Text("—", style="dim"))

        elif col_name == "ST":
            s   = item.get("st") or "—"
            row.append(Text(s, style=_st_color(s), no_wrap=True))

        elif col_name == "MA":
            a20  = item.get("above_sma20",  False)
            a50  = item.get("above_sma50",  False)
            a200 = item.get("above_sma200", False)
            dots = ("●" if a20 else "○") + ("●" if a50 else "○") + ("●" if a200 else "○")
            clr  = "green" if a200 else ("yellow" if a50 else "red")
            row.append(Text(dots, style=clr, no_wrap=True))

        elif col_name == "VOL✓":
            if item.get("vol_confirmed"):
                row.append(Text("✓", style="green"))
            else:
                row.append(Text("—", style="dim"))

        elif col_name == "TIGHTNESS":
            v = item.get("tightness")
            row.append(Text(f"{v:.1f}%", no_wrap=True) if v is not None else Text("—", style="dim"))

        elif col_name == "SECTOR":
            s = str(item.get("sector", "—") or "—")
            row.append(Text(s, style="dim", no_wrap=True))

        elif col_name == "SIGNAL":
            s   = str(item.get("trading_signal", "—") or "—")
            clr = {"STRONG_BUY": "bold green", "BUY": "green", "HOLD": "yellow",
                   "WEAK_HOLD": "yellow", "SELL": "red"}.get(s, "white")
            row.append(Text(s, style=clr, no_wrap=True))

        elif col_name == "INV":
            v = item.get("investment_score")
            if v:
                fv  = float(v)
                clr = "green" if fv >= 60 else ("yellow" if fv >= 40 else "red")
                row.append(Text(f"{fv:.0f}", style=clr, no_wrap=True))
            else:
                row.append(Text("—", style="dim"))

        elif col_name == "BOX TOP":
            v = item.get("box_top")
            row.append(Text(f"{v:,.0f}" if v else "—", no_wrap=True))

        elif col_name == "BOX RNG":
            v = item.get("box_range_pct")
            row.append(Text(f"{v:.1f}%" if v is not None else "—", no_wrap=True))

        elif col_name == "52H%":
            v = item.get("pct_from_52h")
            if v is not None:
                fv  = float(v)
                clr = "bold green" if fv >= -1 else ("green" if fv >= -3 else "yellow")
                row.append(Text(f"{fv:.1f}%", style=clr, no_wrap=True))
            else:
                row.append(Text("—", style="dim"))

        else:
            row.append(Text(str(val or "—"), no_wrap=True))
    return row


def build_supertrend_panel(items: list) -> Panel:
    # ST col removed (all are BUY); MA replaced by ADX + RS
    cols = [
        ("SYMBOL", "left",  11), ("PRICE", "right",  9), ("CHG%", "right", 7),
        ("RSI",    "right",   4), ("ADX",   "right",   4), ("RS",  "right", 5),
    ]
    return build_signal_table("SUPERTREND BUY", "🟢", items, cols, "green")


def build_breakout_panel(items: list, label: str = "52W BREAKOUT") -> Panel:
    cols = [
        ("SYMBOL", "left",  10), ("PRICE", "right",  9), ("CHG%", "right", 8),
        ("RS",     "right",   5), ("RSI",  "right",  4), ("VOL✓", "center", 4),
    ]
    return build_signal_table(label, "🚀", items, cols, "yellow")


def build_vcp_panel(items: list) -> Panel:
    cols = [
        ("SYMBOL",    "left",  10), ("PRICE", "right",  9), ("CHG%",  "right", 7),
        ("TIGHTNESS", "right",  9), ("RSI",   "right",  4), ("RS",  "right", 5),
    ]
    return build_signal_table("VCP SETUPS (Volatility Contraction)", "🎯", items, cols, "cyan")


def build_stage2_panel(items: list) -> Panel:
    # Show 1M% change (from DB) instead of 1D chg; RS from DB
    cols = [
        ("SYMBOL", "left",  10), ("PRICE",  "right",  9), ("1M%",    "right",  8),
        ("RS",     "right",   5), ("RSI",   "right",   4), ("SIGNAL", "center", 9),
    ]
    return build_signal_table("STAGE 2 LEADERS (Weinstein Advancing)", "⭐", items, cols, "gold1")


def build_darvas_panel(items: list) -> Panel:
    cols = [
        ("SYMBOL",  "left",  10), ("PRICE",   "right",  9), ("CHG%",    "right", 7),
        ("BOX TOP", "right",  9), ("BOX RNG", "right",  7), ("VOL✓", "center", 4),
    ]
    return build_signal_table("DARVAS BOX BREAKOUT", "📦", items, cols, "magenta")


def build_momentum52w_panel(items: list) -> Panel:
    cols = [
        ("SYMBOL", "left",  10), ("PRICE", "right",  9), ("CHG%", "right", 7),
        ("52H%",   "right",   6), ("RS",   "right",  5), ("RSI",  "right", 4),
    ]
    return build_signal_table("52W HIGH MOMENTUM", "🏔", items, cols, "bright_cyan")


def build_watchlist_panel(syms: list[str], live_prices: dict,
                           hist: pd.DataFrame, db_data: dict) -> Panel:
    """Personal watchlist — one row per symbol with price, RSI, ADX, RS, signal."""
    cols = [
        ("SYMBOL", "left",  11), ("PRICE", "right",  9), ("CHG%",   "right", 8),
        ("RSI",    "right",   4), ("ADX",  "right",  4), ("RS",     "right", 5),
        ("SIGNAL", "center",  9),
    ]
    items: list[dict] = []
    for sym in syms:
        grp = hist[hist["SYMBOL"] == sym.upper()] if not hist.empty else pd.DataFrame()
        grp = grp.sort_values("TIMESTAMP") if not grp.empty else grp
        live    = live_prices.get(sym.upper())
        current = live or (float(grp["CLOSE"].iloc[-1]) if not grp.empty else 0)
        prev_c  = float(grp["CLOSE"].iloc[-2]) if len(grp) > 1 else current
        chg_pct = round((current / prev_c - 1) * 100, 2) if prev_c else 0

        rsi = compute_rsi(grp["CLOSE"]) if not grp.empty else 0
        adx = compute_adx(grp) if not grp.empty else 0
        db  = db_data.get(sym.upper(), {})
        rs_raw = db.get("rs")
        rs_pct = round(rs_raw * 100, 1) if rs_raw is not None else None
        signal = db.get("st_state") or "—"

        items.append({
            "symbol":   sym.upper(),
            "price":    current,
            "chg_pct":  chg_pct,
            "rsi":      round(rsi, 1),
            "adx":      adx,
            "rs":       rs_pct,
            "trading_signal": signal,
        })
    return build_signal_table("WATCHLIST", "👁", items, cols, "white")


def build_status_bar(last_update: str, hist_rows: int, signals: dict) -> Panel:
    counts = "  ".join([
        f"[green]ST:{len(signals.get('supertrend_buy',[]))}[/green]",
        f"[yellow]BO52:{len(signals.get('breakouts_52w',[]))}[/yellow]",
        f"[cyan]VCP:{len(signals.get('vcp_setups',[]))}[/cyan]",
        f"[gold1]S2:{len(signals.get('stage2_leaders',[]))}[/gold1]",
        f"[magenta]DARVAS:{len(signals.get('darvas_setups',[]))}[/magenta]",
        f"[bright_cyan]52MOM:{len(signals.get('momentum_52w',[]))}[/bright_cyan]",
    ])
    hint = "[dim]/ query  │  SYMBOL drilldown  │  HEALTH  │  PORT  │  REFRESH[/dim]"
    txt = (
        f"[dim]Last update:[/dim] [white]{last_update}[/white]  │  {counts}  │  "
        f"[dim]Price history: {hist_rows:,} rows[/dim]  │  {hint}"
    )
    return Panel(txt, height=3, style="on grey15")


def _adaptive_signal_rows(requested: int, has_watchlist: bool = False,
                          terminal_height: int | None = None) -> int:
    """Return rows per signal panel that fit the current terminal height."""
    if requested <= 0:
        return requested

    term_h = terminal_height or console.size.height or 68
    fixed_h = 3 + 4 + 4 + 4 + 3  # header + index/sector/breadth bars + status
    signal_sections = 3 + (1 if has_watchlist else 0)

    # Each signal panel section needs border/title/table-header/subtitle chrome
    # around data rows. Rich renders this as about six non-data rows per section.
    max_rows = ((term_h - fixed_h) // signal_sections) - 6
    min_rows = min(3, requested)
    return max(min_rows, min(requested, max_rows))


# ─────────────────────────────────────────────────────────────────────────────
# Right sidebar
# ─────────────────────────────────────────────────────────────────────────────

def build_right_sidebar(indices: dict, signals: dict, sector_breadth: dict,
                        nlp_history: list[dict], nlp_pending: bool,
                        narrative: str) -> Panel:
    """Vertical right panel: Market Pulse stats (top) + Agent Adda chat (bottom)."""
    grid = Table.grid(expand=True, padding=(0, 0))
    grid.add_column()

    # ── Market Pulse ─────────────────────────────────────────────────────────
    breadth = signals.get("breadth", {})
    adv     = breadth.get("advances", 0)
    dec     = breadth.get("declines", 0)
    mco     = breadth.get("mco", 0)
    trin    = breadth.get("trin", 1.0)
    hi52    = breadth.get("new_highs", 0)
    ab200   = breadth.get("above_200ma_pct", 0)
    ad_ratio = round(adv / dec, 2) if dec else 0

    def _idx_row(key: str, label: str) -> Text:
        d     = indices.get(key.upper(), {})
        price = _parse_price(d.get("lastPrice", 0))
        pchg  = _parse_price(d.get("pChange",   0))
        flash = _update_flash(f"SB:{key}", price)
        clr   = flash or _chg_color(pchg)
        arrow = "▲" if pchg >= 0 else "▼"
        t = Text()
        t.append(f"{label:<10}", style="white")
        t.append(f"{price:>8,.0f}  ", style=clr)
        t.append(f"{arrow}{abs(pchg):.1f}%", style=clr)
        return t

    pulse_tbl = Table(box=None, padding=(0, 1), expand=True, show_header=False)
    pulse_tbl.add_column("c", no_wrap=True)
    for key, lbl in [("NIFTY 50","NIFTY"), ("NIFTY BANK","BANK"),
                     ("NIFTY IT","IT"), ("NIFTY METAL","METAL"),
                     ("INDIA VIX","VIX")]:
        pulse_tbl.add_row(_idx_row(key, lbl))

    pulse_tbl.add_row(Text("─" * 28, style="dim"))

    def _stat(label: str, val, style: str = "white", suffix: str = "") -> Text:
        t = Text()
        t.append(f"{label:<14}", style="dim")
        t.append(f"{val}{suffix}", style=style)
        return t

    mco_clr  = "bold bright_green" if mco > 20 else ("bold bright_red" if mco < -20 else "yellow")
    trin_clr = "bold bright_green" if trin < 0.8 else ("bold bright_red" if trin > 1.2 else "yellow")
    ad_clr   = "green" if ad_ratio >= 1 else "red"

    pulse_tbl.add_row(_stat("Advances",  adv,  "green"))
    pulse_tbl.add_row(_stat("Declines",  dec,  "red"))
    pulse_tbl.add_row(_stat("A/D Ratio", f"{ad_ratio:.2f}", ad_clr))
    pulse_tbl.add_row(_stat("MCO",       f"{mco:+.0f}", mco_clr))
    pulse_tbl.add_row(_stat("TRIN",      f"{trin:.2f}",  trin_clr,
                             " 🟢" if trin < 0.8 else (" 🔴" if trin > 1.2 else "")))
    pulse_tbl.add_row(_stat("52W Highs", hi52, "cyan"))
    pulse_tbl.add_row(_stat(">200 DMA",  f"{ab200:.0f}%", "cyan"))
    pulse_tbl.add_row(Text("─" * 28, style="dim"))

    # Sector heat rows
    for sector, idx_label in SECTOR_INDEX_MAP.items():
        idx_key = idx_label.upper().replace("NIFTY ", "NIFTY ")
        d    = indices.get(idx_key, {})
        pchg = _parse_price(d.get("pChange", 0))
        sb   = sector_breadth.get(sector, {})
        pct  = sb.get("pct_above_50dma", 0)
        clr  = _chg_color(pchg)
        arrow = "▲" if pchg >= 0 else "▼"
        short = sector.split("&")[0].strip()[:9]
        t = Text()
        t.append(f"{short:<10}", style="dim white")
        t.append(f"{arrow}{abs(pchg):.1f}% ", style=clr)
        t.append(f"{pct:.0f}%", style="dim cyan")
        pulse_tbl.add_row(t)

    pulse_panel = Panel(pulse_tbl, title="[bold cyan]📊 PULSE[/bold cyan]",
                        border_style="cyan", padding=(0, 0))
    grid.add_row(pulse_panel)

    # ── Narrative ─────────────────────────────────────────────────────────────
    if narrative:
        nt = Text(narrative, style="italic dim white")
        nt.overflow = "fold"
        grid.add_row(Panel(nt, title="[yellow]📰[/yellow]",
                           border_style="yellow", padding=(0, 1), height=5))

    # ── Agent Adda chat history ───────────────────────────────────────────────
    chat_tbl = Table(box=None, padding=(0, 0), expand=True, show_header=False)
    chat_tbl.add_column("c", no_wrap=False, overflow="fold")

    if nlp_pending:
        chat_tbl.add_row(Text("⏳ Agent thinking…", style="bold yellow"))
    elif nlp_history:
        for entry in nlp_history[-4:]:  # show last 4 exchanges
            q = Text()
            q.append("❓ ", style="bold cyan")
            q.append(entry["query"][:60], style="white")
            chat_tbl.add_row(q)
            a = Text()
            a.append("🤖 ", style="bold green")
            a.append(entry["response"][:120], style="dim white")
            chat_tbl.add_row(a)
            chat_tbl.add_row(Text("·" * 26, style="dim"))
    else:
        chat_tbl.add_row(Text(
            "No queries yet.\nType  /your question\nthen press Enter.",
            style="dim italic",
        ))

    hint = Text()
    hint.append("  [/] to query", style="bold cyan")
    grid.add_row(Panel(chat_tbl, title="[bold cyan]💬 Agent Adda[/bold cyan]",
                       subtitle=hint, border_style="cyan", padding=(0, 1)))

    return Panel(grid, style="on grey7", padding=(0, 0))


# ─────────────────────────────────────────────────────────────────────────────
# Main render loop
# ─────────────────────────────────────────────────────────────────────────────

def build_full_layout(indices: dict, signals: dict, last_update: str,
                       hist_rows: int, top_n: int, refresh_mins: int = 5,
                       watchlist: list[str] | None = None,
                       hist: "pd.DataFrame | None" = None,
                       live_prices: dict | None = None,
                       db_data: dict | None = None,
                       sector_breadth: dict | None = None,
                       narrative: str = "",
                       nlp_history: list[dict] | None = None,
                       nlp_pending: bool = False) -> Table:
    """Compose the full terminal layout: left main content + right sidebar."""
    nlp_history = nlp_history or []
    visible_top_n = _adaptive_signal_rows(top_n, has_watchlist=bool(watchlist))

    # ── Left column: all market content ──────────────────────────────────────
    left = Table.grid(expand=True)
    left.add_column()

    left.add_row(build_header(indices, refresh_mins))
    left.add_row(build_indices_bar(indices))
    left.add_row(build_sector_table(indices, sector_breadth))
    left.add_row(build_breadth_bar(signals.get("breadth", {}), signals.get("nifty_trend", [])))

    row4 = Table.grid(expand=True)
    row4.add_column(ratio=1); row4.add_column(ratio=1)
    st_items = signals.get("supertrend_buy", [])[:visible_top_n]
    bo_items = (signals.get("breakouts_52w", []) + signals.get("breakouts_20d", []))[:visible_top_n]
    row4.add_row(build_supertrend_panel(st_items),
                 build_breakout_panel(bo_items, "52W / 20D BREAKOUTS"))
    left.add_row(row4)

    row5 = Table.grid(expand=True)
    row5.add_column(ratio=1); row5.add_column(ratio=1)
    row5.add_row(build_vcp_panel(signals.get("vcp_setups", [])[:visible_top_n]),
                 build_stage2_panel(signals.get("stage2_leaders", [])[:visible_top_n]))
    left.add_row(row5)

    row6 = Table.grid(expand=True)
    row6.add_column(ratio=1); row6.add_column(ratio=1)
    row6.add_row(build_darvas_panel(signals.get("darvas_setups", [])[:visible_top_n]),
                 build_momentum52w_panel(signals.get("momentum_52w", [])[:visible_top_n]))
    left.add_row(row6)

    if watchlist and hist is not None and live_prices is not None and db_data is not None:
        left.add_row(build_watchlist_panel(watchlist[:visible_top_n], live_prices, hist, db_data))

    left.add_row(build_status_bar(last_update, hist_rows, signals))

    # ── Right column: sidebar ─────────────────────────────────────────────────
    right = build_right_sidebar(indices, signals, sector_breadth or {},
                                nlp_history, nlp_pending, narrative)

    # ── Outer two-column grid ────────────────────────────────────────────────
    outer = Table.grid(expand=True)
    outer.add_column(ratio=4)          # left: main content
    outer.add_column(min_width=38)     # right: sidebar, fixed width
    outer.add_row(left, right)
    return outer


def _market_is_open() -> bool:
    now = datetime.now()
    return now.weekday() < 5 and 9 <= now.hour < 16


def refresh_data(top_n: int) -> tuple[dict, dict, str, int, pd.DataFrame, dict, dict, dict]:
    """Fetch all live data and compute signals.
    Returns (indices, signals, last_update, hist_rows, hist, live_prices, db_data, sector_breadth).

    Data sources:
      Historical OHLCV  → local CSV  (data/nse_sec_full_data.csv)
      Today's OHLCV     → NSE API    (equity-stockIndices, market hours only)
      Index quotes      → NSE API    (allIndices, market hours) / local CSV fallback
    """
    market_open = _market_is_open()

    console.log("[dim]Fetching index data from NSE…[/dim]")
    indices = fetch_all_indices() if market_open else {}

    # Always load EOD for fallback; fill any missing/zero indices
    eod_indices  = load_eod_indices()
    eod_date_tag = ""
    if eod_indices:
        sample = next(iter(eod_indices.values()), {})
        eod_date_tag = sample.get("_eod_date", "EOD")

    for key, eod in eod_indices.items():
        live = indices.get(key, {})
        if not live or _parse_price(live.get("lastPrice", 0)) == 0:
            indices[key] = eod   # use local EOD when NSE live is absent/zero

    console.log("[dim]Loading historical price data from local CSV…[/dim]")
    hist = load_price_history(days=400)
    hist_rows = len(hist)

    if market_open:
        # Fetch full OHLCV + volume from NSE for all available stocks
        console.log("[dim]Fetching live OHLCV from NSE (equity-stockIndices)…[/dim]")
        live_prices, live_ohlcv = fetch_live_ohlcv()
        # Patch today's live data into history so indicators reflect intraday price action
        if not live_ohlcv.empty:
            console.log(f"[dim]Patching {len(live_ohlcv):,} live rows into history…[/dim]")
            hist = patch_live_ohlcv(hist, live_ohlcv)
    else:
        console.log("[dim]Market closed — using local EOD prices…[/dim]")
        live_prices = load_eod_stock_prices()

    console.log("[dim]Running technical screener…[/dim]")
    signals  = run_screener(hist, live_prices, top_n=top_n)
    db_data  = load_rs_from_db()
    signals["nifty_trend"] = load_nifty_trend(10)

    console.log("[dim]Computing sector breadth…[/dim]")
    sector_breadth = compute_sector_breadth(hist)

    ts = datetime.now().strftime("%H:%M:%S")
    if not market_open:
        ts = f"{ts}  [dim](EOD {eod_date_tag})[/dim]"
    return indices, signals, ts, hist_rows, hist, live_prices, db_data, sector_breadth


# ─────────────────────────────────────────────────────────────────────────────
# Bloomberg-style command mode helpers
# ─────────────────────────────────────────────────────────────────────────────

_CMD_KEYWORDS: frozenset[str] = frozenset({
    "STAGE2", "BREAKOUTS", "VCP", "SUPERTREND", "DARVAS", "52W",
    "HEALTH", "PORT", "PORTFOLIO", "REPORT", "REFRESH", "EOD",
})
_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9&-]{0,19}$")


def _parse_input(raw: str) -> tuple[str, str]:
    """Classify terminal input into (cmd_type, arg).

    Returns one of:
      ('nlp', query_text) — route to Agent Adda
      ('signal', SIGNAL)  — show full signal screen
      ('sector', NAME)    — sector drilldown
      ('health', '')      — data health screen
      ('portfolio', '')   — portfolio screen
      ('report', '')      — reports screen
      ('refresh', '')     — force immediate data refresh
      ('eod', '')         — print EOD run hint
      ('symbol', SYMBOL)  — stock drilldown
      ('ignore', '')      — empty / whitespace only
    """
    raw = raw.strip()
    if not raw:
        return ("ignore", "")

    # /query prefix always → NLP (strip leading slashes)
    if raw.startswith("/"):
        query_text = raw.lstrip("/").strip()
        return ("nlp", query_text) if query_text else ("ignore", "")

    upper = raw.upper()

    if upper in ("STAGE2", "BREAKOUTS", "VCP", "SUPERTREND", "DARVAS", "52W"):
        return ("signal", upper)

    if upper.startswith("SECTOR "):
        sector = raw[7:].strip()
        return ("sector", sector.upper()) if sector else ("ignore", "")

    if upper == "HEALTH":
        return ("health", "")
    if upper in ("PORT", "PORTFOLIO"):
        return ("portfolio", "")
    if upper == "REPORT":
        return ("report", "")
    if upper == "REFRESH":
        return ("refresh", "")
    if upper == "EOD":
        return ("eod", "")

    # Bare NSE symbol: matches regex and not a command keyword
    if _SYMBOL_RE.match(upper) and upper not in _CMD_KEYWORDS:
        return ("symbol", upper)

    # Everything else → NLP
    return ("nlp", raw)


def _load_symbol_db_extra(symbol: str) -> dict:
    """Load richer DB snapshot fields for a single symbol (for drilldown)."""
    if not DB_PATH.exists():
        return {}
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute(
            "SELECT stage, stage_score, investment_score, sector, trading_signal, "
            "relative_strength, supertrend_state, rsi "
            "FROM stage_snapshots WHERE symbol=? "
            "AND snapshot_date=(SELECT MAX(snapshot_date) FROM stage_snapshots)",
            (symbol,),
        ).fetchone()
        conn.close()
        if row:
            return {
                "stage": row[0],
                "stage_score": row[1],
                "investment_score": row[2],
                "sector": row[3],
                "trading_signal": row[4],
                "relative_strength": row[5],
                "supertrend_state": row[6],
                "rsi_db": row[7],
            }
    except Exception:
        pass
    return {}


def _show_symbol_drilldown(
    symbol: str,
    hist: pd.DataFrame,
    live_prices: dict,
    db_data: dict,
    indices: dict,
    sector_breadth: dict,
) -> None:
    """Full Bloomberg-style symbol drilldown printed to console."""
    console.rule(f"[bold cyan]📊 {symbol}[/bold cyan]")

    grp = hist[hist["SYMBOL"] == symbol].copy() if not hist.empty else pd.DataFrame()
    db  = {**db_data.get(symbol, {}), **_load_symbol_db_extra(symbol)}

    # ── Section A: Price Header ───────────────────────────────────────────────
    if not grp.empty:
        grp = grp.sort_values("TIMESTAMP")
        last_close = float(grp["CLOSE"].iloc[-1])
        prev_close = float(grp["CLOSE"].iloc[-2]) if len(grp) > 1 else last_close
        price  = live_prices.get(symbol) or last_close
        chg_pct = ((price - prev_close) / prev_close * 100) if prev_close else 0
        arrow   = "▲" if chg_pct >= 0 else "▼"
        color   = "green" if chg_pct >= 0 else "red"

        open_p = float(grp["OPEN"].iloc[-1])
        high_p = float(grp["HIGH"].iloc[-1])
        low_p  = float(grp["LOW"].iloc[-1])

        hist_252 = grp.tail(252)
        w52_high = float(hist_252["HIGH"].max())
        w52_low  = float(hist_252["LOW"].min())

        console.print(
            f"  [bold white]₹{price:,.2f}[/bold white]  "
            f"[{color}]{arrow} {chg_pct:+.2f}%[/{color}]  "
            f"[dim]O:{open_p:.2f}  H:{high_p:.2f}  L:{low_p:.2f}[/dim]  "
            f"[dim]52W H:[/dim][green]{w52_high:.2f}[/green]  "
            f"[dim]52W L:[/dim][red]{w52_low:.2f}[/red]"
        )
    else:
        console.print(f"[yellow]No price history found for {symbol}[/yellow]")
    console.print()

    # ── Section B: Technical Indicators ──────────────────────────────────────
    tech_t = Table(
        title="📈 Technical Indicators",
        show_header=True, header_style="bold magenta", box=box.SIMPLE,
    )
    tech_t.add_column("Indicator", style="bold")
    tech_t.add_column("Value")
    tech_t.add_column("Signal")

    if not grp.empty:
        rsi_val = compute_rsi(grp["CLOSE"])
        adx_val = compute_adx(grp)
        rsi_c   = _rsi_color(rsi_val)
        tech_t.add_row("RSI(14)",  f"[{rsi_c}]{rsi_val:.1f}[/{rsi_c}]",
                       "Overbought" if rsi_val > 70 else ("Oversold" if rsi_val < 30 else "Neutral"))
        tech_t.add_row("ADX(14)",  f"{adx_val:.1f}",
                       "[green]Trending[/green]" if adx_val > 25 else "Ranging")

    st_state  = db.get("supertrend_state") or db.get("st_state") or "—"
    stage     = db.get("stage") or "—"
    rs_raw    = db.get("relative_strength") or db.get("rs")
    rs_str    = f"{float(rs_raw) * 100:.1f}" if rs_raw is not None else "—"
    inv_score = db.get("investment_score")
    inv_str   = f"{float(inv_score):.1f}" if inv_score is not None else "—"

    tech_t.add_row("Supertrend", _st_color(st_state) if st_state != "—" else "—", "")
    tech_t.add_row("Stage",      str(stage), "")
    tech_t.add_row("RS Score",   rs_str, "")
    tech_t.add_row("Inv. Score", inv_str, "")
    console.print(tech_t)
    console.print()

    # ── Section C: Sector Context ─────────────────────────────────────────────
    sector_name = db.get("sector") or "—"
    console.print(f"[bold cyan]🏭 Sector:[/bold cyan] [white]{sector_name}[/white]")
    if sector_name != "—":
        sb = sector_breadth.get(sector_name, {})
        pct50 = sb.get("pct_above_50dma")
        if pct50 is not None:
            sb_c = "green" if pct50 > 60 else ("yellow" if pct50 > 40 else "red")
            console.print(f"  [dim]Sector %>50DMA:[/dim] [{sb_c}]{pct50:.1f}%[/{sb_c}]")
        # Sector index performance
        for idx_sector_label, idx_key in SECTOR_INDEX_MAP.items():
            if sector_name.lower() in idx_sector_label.lower():
                for iname, idata in indices.items():
                    if idx_key.lower() in idata.get("index", iname).lower():
                        try:
                            idx_chg = float(idata.get("percentChange") or idata.get("pChange") or 0)
                        except (TypeError, ValueError):
                            idx_chg = 0
                        ic = "green" if idx_chg >= 0 else "red"
                        console.print(f"  [dim]{idx_key}:[/dim] [{ic}]{idx_chg:+.2f}%[/{ic}]")
                        break
                break
    console.print()

    # ── Section D: 20-Day Price Sparkline ────────────────────────────────────
    if not grp.empty:
        closes_20 = grp["CLOSE"].tail(20).tolist()
        console.print("[bold cyan]📉 20-Day:[/bold cyan] ", end="")
        console.print(_sparkline(closes_20))
    console.print()

    # ── Section E: Trading Signals ────────────────────────────────────────────
    active: list[str] = []
    st_lower = str(st_state).lower()
    if st_lower in ("buy", "bullish"):
        active.append("[green]✅ Supertrend BUY[/green]")
    if str(stage).upper() in ("STAGE_2", "2", "STAGE 2"):
        active.append("[gold1]✅ Stage 2 Leader[/gold1]")
    ts_signal = db.get("trading_signal") or ""
    if "buy" in str(ts_signal).lower():
        active.append(f"[cyan]✅ Signal: {ts_signal}[/cyan]")

    if active:
        console.print("[bold cyan]🚦 Active Signals:[/bold cyan]")
        for sig in active:
            console.print(f"  {sig}")
    else:
        console.print("[dim]No active screener signals in DB snapshot.[/dim]")
    console.print()
    console.print("[dim]Press Enter to return…[/dim]")


def _show_health_screen() -> None:
    """Display data-source freshness / health status."""
    console.rule("[bold cyan]🏥 Data Health[/bold cyan]")

    t = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE, expand=False)
    t.add_column("Source", style="bold")
    t.add_column("File / Table")
    t.add_column("Last Updated")
    t.add_column("Age")
    t.add_column("Status")

    now_dt = datetime.now()

    def _row(source: str, path_str: str, ts: Optional[datetime]) -> None:
        if ts is None:
            t.add_row(source, path_str, "[red]missing[/red]", "—", "[red]❌ MISSING[/red]")
            return
        age_secs = (now_dt - ts).total_seconds()
        days = age_secs / 86400
        age_str = f"{days:.1f}d" if days >= 1 else f"{age_secs / 3600:.1f}h"
        if days < 1:
            status = "[green]✅ Fresh[/green]"
        elif days < 3:
            status = "[yellow]⚠️  Stale[/yellow]"
        else:
            status = "[red]❌ Old[/red]"
        t.add_row(source, path_str, ts.strftime("%Y-%m-%d %H:%M"), age_str, status)

    # Price history CSV
    if STOCK_CSV.exists():
        _row("Price History CSV", "data/nse_sec_full_data.csv",
             datetime.fromtimestamp(STOCK_CSV.stat().st_mtime))
    else:
        _row("Price History CSV", "data/nse_sec_full_data.csv", None)

    # Index history CSV
    if INDEX_CSV.exists():
        _row("Index History CSV", "data/nse_index_data.csv",
             datetime.fromtimestamp(INDEX_CSV.stat().st_mtime))
    else:
        _row("Index History CSV", "data/nse_index_data.csv", None)

    # Stage snapshot DB
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(DB_PATH)
            row  = conn.execute("SELECT MAX(snapshot_date) FROM stage_snapshots").fetchone()
            conn.close()
            if row and row[0]:
                snap_ts = datetime.strptime(row[0], "%Y-%m-%d")
                _row("Stage Snapshot DB", "data/sector_rotation_tracker.db", snap_ts)
            else:
                _row("Stage Snapshot DB", "data/sector_rotation_tracker.db", None)
        except Exception:
            _row("Stage Snapshot DB", "data/sector_rotation_tracker.db", None)
    else:
        _row("Stage Snapshot DB", "data/sector_rotation_tracker.db", None)

    # NSE live session
    if _nse_session_ts > 0:
        sess_ts  = datetime.fromtimestamp(_nse_session_ts)
        sess_age = time.time() - _nse_session_ts
        status   = "[green]✅ Active[/green]" if sess_age < _SESSION_TTL else "[yellow]⚠️  Expired[/yellow]"
        t.add_row("NSE Session", "live API", sess_ts.strftime("%H:%M:%S"),
                  f"{int(sess_age)}s", status)
    else:
        t.add_row("NSE Session", "live API", "[dim]not started[/dim]", "—", "[dim]—[/dim]")

    console.print(t)
    console.print()
    console.print("[dim]Press Enter to return…[/dim]")


def _show_signal_screen(signal_name: str, signals: dict) -> None:
    """Display full screener results for a signal command."""
    _SIGNAL_MAP: dict[str, list[str]] = {
        "STAGE2":     ["stage2_leaders"],
        "BREAKOUTS":  ["breakouts_52w", "breakouts_20d"],
        "VCP":        ["vcp_setups"],
        "SUPERTREND": ["supertrend_buy"],
        "DARVAS":     ["darvas_setups"],
        "52W":        ["momentum_52w"],
    }
    keys  = _SIGNAL_MAP.get(signal_name.upper(), [])
    items: list[dict] = []
    for k in keys:
        items.extend(signals.get(k, []))

    console.rule(f"[bold cyan]{signal_name}  —  {len(items)} stocks[/bold cyan]")

    if not items:
        console.print(f"[yellow]No {signal_name} signals currently active.[/yellow]")
        console.print()
        console.print("[dim]Press Enter to return…[/dim]")
        return

    sig_t = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE)
    cols = list(items[0].keys())
    for c in cols:
        sig_t.add_column(str(c).upper(), overflow="fold")
    for item in items:
        sig_t.add_row(*[str(item.get(c, "—")) for c in cols])

    console.print(sig_t)
    console.print()
    console.print("[dim]Press Enter to return…[/dim]")


def _show_portfolio_screen() -> None:
    """Display portfolio holdings summary."""
    holdings_path = ROOT / "portfolio-analyzer" / "output" / "holdings.csv"
    summary_path  = ROOT / "portfolio-analyzer" / "output" / "portfolio_summary.json"

    console.rule("[bold cyan]💼 Portfolio[/bold cyan]")

    if not holdings_path.exists():
        console.print(f"[red]Holdings file not found: {holdings_path}[/red]")
        console.print()
        console.print("[dim]Press Enter to return…[/dim]")
        return

    try:
        df = pd.read_csv(holdings_path)
    except Exception as e:
        console.print(f"[red]Error reading holdings: {e}[/red]")
        console.print()
        console.print("[dim]Press Enter to return…[/dim]")
        return

    df.columns = df.columns.str.lower()
    sym_col = "symbol"   if "symbol"   in df.columns else df.columns[0]
    qty_col = next((c for c in ["quantity", "shares", "qty"] if c in df.columns), None)
    val_col = next((c for c in ["value_rs", "value", "current_value"] if c in df.columns), None)

    console.print(f"[bold white]Total Holdings:[/bold white] {len(df)} stocks")
    console.print()

    # Sector distribution from JSON summary (if exists)
    if summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text())
            sec_dist = summary.get("sector_distribution", {})
            if sec_dist:
                sec_t = Table(title="Sector Distribution", show_header=True,
                              header_style="bold magenta", box=box.SIMPLE)
                sec_t.add_column("Sector")
                sec_t.add_column("Count",  justify="right")
                sec_t.add_column("Value ₹", justify="right")
                for sec_name, sdata in sec_dist.items():
                    sec_t.add_row(
                        sec_name,
                        str(sdata.get("count", "—")),
                        f"₹{float(sdata['value']):,.0f}" if sdata.get("value") else "—",
                    )
                console.print(sec_t)
                console.print()
        except Exception:
            pass

    # Top 10 holdings by value
    if val_col and val_col in df.columns:
        df[val_col] = pd.to_numeric(df[val_col], errors="coerce").fillna(0)
        top10 = df.nlargest(10, val_col)
    else:
        top10 = df.head(10)

    top_t = Table(title="Top 10 Holdings by Value", show_header=True,
                  header_style="bold cyan", box=box.SIMPLE)
    top_t.add_column("Symbol", style="bold")
    if qty_col and qty_col in df.columns:
        top_t.add_column("Qty", justify="right")
    if val_col and val_col in df.columns:
        top_t.add_column("Value ₹", justify="right")

    for _, row in top10.iterrows():
        cells = [str(row.get(sym_col, "—"))]
        if qty_col and qty_col in df.columns:
            cells.append(str(row.get(qty_col, "—")))
        if val_col and val_col in df.columns:
            v = row.get(val_col, 0)
            cells.append(f"₹{float(v):,.2f}" if v else "—")
        top_t.add_row(*cells)

    console.print(top_t)
    console.print()
    console.print("[dim]Press Enter to return…[/dim]")


def _show_sector_screen(sector_name: str, indices: dict, sector_breadth: dict) -> None:
    """Display sector breadth and index performance."""
    console.rule(f"[bold cyan]🏭 Sector: {sector_name}[/bold cyan]")

    sb = sector_breadth.get(sector_name, {})
    if not sb:
        for key in sector_breadth:
            if sector_name.lower() in key.lower():
                sb = sector_breadth[key]
                sector_name = key
                break

    if sb:
        sb_t = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE)
        sb_t.add_column("Metric")
        sb_t.add_column("Value")
        for metric, label in [
            ("pct_above_50dma",  "% Above 50DMA"),
            ("pct_above_200dma", "% Above 200DMA"),
            ("total_stocks",     "Total Stocks"),
            ("stage2_count",     "Stage 2 Count"),
            ("stage4_count",     "Stage 4 Count"),
        ]:
            val = sb.get(metric)
            if val is None:
                continue
            if "pct" in metric:
                color = "green" if float(val) > 60 else ("yellow" if float(val) > 40 else "red")
                sb_t.add_row(label, f"[{color}]{val:.1f}%[/{color}]")
            else:
                sb_t.add_row(label, str(val))
        top_stocks = sb.get("top_stocks", [])
        if top_stocks:
            sb_t.add_row("Top Stocks", ", ".join(str(s) for s in top_stocks[:8]))
        console.print(sb_t)
    else:
        console.print(f"[yellow]No sector breadth data for '{sector_name}'.[/yellow]")
        if sector_breadth:
            console.print(f"Available: {', '.join(list(sector_breadth.keys())[:8])}")

    # Matching index performance
    for idx_label, idx_key in SECTOR_INDEX_MAP.items():
        if sector_name.lower() in idx_label.lower():
            for iname, idata in indices.items():
                lbl = idata.get("index", iname)
                if idx_key.lower() in lbl.lower():
                    try:
                        chg = float(idata.get("percentChange") or idata.get("pChange") or 0)
                    except (TypeError, ValueError):
                        chg = 0
                    ic = "green" if chg >= 0 else "red"
                    console.print(f"\n[bold white]{lbl}:[/bold white] [{ic}]{chg:+.2f}%[/{ic}]")
                    break
            break
    console.print()
    console.print("[dim]Press Enter to return…[/dim]")


def _show_report_screen() -> None:
    """List available generated reports."""
    console.rule("[bold cyan]📄 Reports[/bold cyan]")
    reports_dir = ROOT / "reports"
    if not reports_dir.exists():
        console.print("[yellow]reports/ directory not found.[/yellow]")
        console.print()
        console.print("[dim]Press Enter to return…[/dim]")
        return

    files = sorted(reports_dir.glob("*"), key=lambda f: f.stat().st_mtime, reverse=True)[:20]
    if not files:
        console.print("[yellow]No reports found.[/yellow]")
    else:
        rep_t = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE)
        rep_t.add_column("File")
        rep_t.add_column("Size", justify="right")
        rep_t.add_column("Last Modified")
        for f in files:
            st   = f.stat()
            size = f"{st.st_size / 1024:.1f} KB"
            mtime = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
            rep_t.add_row(f.name, size, mtime)
        console.print(rep_t)
    console.print()
    console.print("[dim]Press Enter to return…[/dim]")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def _run_agent_query(query: str) -> str:
    """Run a query through Agent Adda and return the response string."""
    try:
        from terminal.agent import Agent
        agent = Agent()
        result = agent.query(query, show_trace=False)
        if isinstance(result, dict):
            return result.get("answer", str(result))
        return str(result)
    except Exception as e:
        return f"Agent error: {e}"


def main():
    parser = argparse.ArgumentParser(description="NSE Bloomberg Terminal")
    parser.add_argument("--once",      action="store_true", help="Run once, no live refresh")
    parser.add_argument("--refresh",   type=int, default=2, metavar="MIN",
                        help="Refresh interval in minutes (default: 2)")
    parser.add_argument("--top",       type=int, default=15, metavar="N",
                        help="Max stocks per signal panel (default: 15)")
    parser.add_argument("--watchlist", type=str, default="", metavar="SYMS",
                        help="Comma-separated watchlist symbols, e.g. RELIANCE,TCS,INFY")
    args = parser.parse_args()

    # Watchlist: CLI flag overrides watchlist.txt
    watchlist: list[str] = []
    if args.watchlist:
        watchlist = [s.strip().upper() for s in args.watchlist.split(",") if s.strip()]
    else:
        wl_file = ROOT / "watchlist.txt"
        if wl_file.exists():
            watchlist = [l.strip().upper() for l in wl_file.read_text().splitlines()
                         if l.strip() and not l.startswith("#")]

    refresh_secs = args.refresh * 60

    def _build(indices, signals, label, hist_rows, hist, live_prices, db_data, sector_breadth,
               narrative="", nlp_hist=None, nlp_pending=False):
        return build_full_layout(
            indices, signals, label, hist_rows, args.top, args.refresh,
            watchlist=watchlist or None,
            hist=hist if watchlist else None,
            live_prices=live_prices if watchlist else None,
            db_data=db_data if watchlist else None,
            sector_breadth=sector_breadth,
            narrative=narrative,
            nlp_history=nlp_hist or [],
            nlp_pending=nlp_pending,
        )

    if args.once:
        with console.status("[bold cyan]Loading NSE Terminal…"):
            res = refresh_data(args.top)
        indices, signals, last_update, hist_rows, hist, live_prices, db_data, sb = res
        narrative = _rule_narrative(indices, signals.get("breadth", {}), signals)
        layout = _build(indices, signals, last_update, hist_rows, hist, live_prices, db_data, sb,
                        narrative=narrative)
        console.print(layout)
        return

    # Live refresh mode
    with Live(console=console, screen=True, refresh_per_second=1) as live:
        indices, signals = {}, {}
        last_update      = "loading…"
        hist_rows        = 0
        hist             = pd.DataFrame()
        live_prices: dict = {}
        db_data: dict    = {}
        sector_breadth: dict = {}
        next_refresh     = 0.0
        narrative        = ""

        while True:
            now = time.time()
            if now >= next_refresh:
                try:
                    res = refresh_data(args.top)
                    indices, signals, last_update, hist_rows, hist, live_prices, db_data, sector_breadth = res
                    narrative = _ensure_narrative(indices, signals.get("breadth", {}), signals)
                except Exception as e:
                    last_update = f"ERROR: {e}"
                next_refresh = time.time() + refresh_secs

            secs_left = max(0, int(next_refresh - time.time()))
            mins, secs_r = divmod(secs_left, 60)
            countdown = f"{last_update}  │  Next refresh in {mins:02d}:{secs_r:02d}"

            with _nlp_lock:
                nlp_hist    = list(_nlp_history)
                nlp_pending = _nlp_state["pending"]

            with _narrative_lock:
                cached = _narrative_cache.get("text", "")
                if cached:
                    narrative = cached

            layout = _build(indices, signals, countdown, hist_rows, hist, live_prices,
                            db_data, sector_breadth, narrative=narrative,
                            nlp_hist=nlp_hist, nlp_pending=nlp_pending)
            live.update(layout)

            # Non-blocking stdin: command mode dispatcher
            ready = select.select([sys.stdin], [], [], 1.0)[0]
            if ready:
                raw = sys.stdin.readline().strip()
                cmd_type, arg = _parse_input(raw)
                if cmd_type == "ignore":
                    pass
                else:
                    live.stop()
                    if cmd_type == "nlp":
                        query = arg
                        with _nlp_lock:
                            _nlp_state["pending"] = True
                        console.rule("[bold cyan]💬 Agent Adda[/bold cyan]")
                        console.print(f"[bold cyan]❓[/bold cyan] [white]{query}[/white]")
                        with console.status("[bold yellow]Agent thinking…[/bold yellow]"):
                            response = _run_agent_query(query)
                        console.print(f"[bold green]🤖[/bold green] {response}")
                        console.rule()
                        console.print("\n[dim]Press Enter to return to terminal…[/dim]")
                        sys.stdin.readline()
                        ts_str = datetime.now().strftime("%H:%M")
                        with _nlp_lock:
                            entry = {"query": query, "response": response, "ts": ts_str}
                            _nlp_history.append(entry)
                            if len(_nlp_history) > _NLP_HISTORY_MAX:
                                _nlp_history.pop(0)
                            _nlp_state["pending"] = False
                    elif cmd_type == "symbol":
                        _show_symbol_drilldown(arg, hist, live_prices, db_data,
                                               indices, sector_breadth)
                        sys.stdin.readline()
                    elif cmd_type == "health":
                        _show_health_screen()
                        sys.stdin.readline()
                    elif cmd_type == "signal":
                        _show_signal_screen(arg, signals)
                        sys.stdin.readline()
                    elif cmd_type == "sector":
                        _show_sector_screen(arg, indices, sector_breadth)
                        sys.stdin.readline()
                    elif cmd_type == "portfolio":
                        _show_portfolio_screen()
                        sys.stdin.readline()
                    elif cmd_type == "report":
                        _show_report_screen()
                        sys.stdin.readline()
                    elif cmd_type == "refresh":
                        next_refresh = 0.0  # trigger immediate refresh on next tick
                    elif cmd_type == "eod":
                        console.print("[yellow]Run:[/yellow] [bold]python daily_refresh.py[/bold] after market close")
                        console.print("\n[dim]Press Enter to return to terminal…[/dim]")
                        sys.stdin.readline()
                    live.start()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[bold cyan]NSE Terminal closed.[/bold cyan]")
