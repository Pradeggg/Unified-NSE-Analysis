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
import sqlite3
import sys
import time
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

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
    clr   = "green" if nc >= 0 else "red"

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
    txt.append(f"{nv:,.0f}" if nv else "—", style=f"bold {clr}")
    if nc != 0:
        txt.append(f"  {arrow} {abs(nc):,.0f}  ({np_:+.2f}%)", style=clr)
    txt.append(f"  │  🔄 /{refresh_mins}min  │  Ctrl+C to exit", style="dim")

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
        clr   = _chg_color(pchg)
        arrow = "▲" if pchg >= 0 else "▼"

        cell = Text()
        cell.append(f"{label.strip()} ", style="bold white")
        cell.append(f"{price:,.0f}", style=f"bold {clr}") if price else cell.append("—", style="dim")
        if pchg != 0:
            cell.append(f"  {arrow}{abs(pchg):.2f}%", style=clr)
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
    txt = f"[dim]Last update:[/dim] [white]{last_update}[/white]  │  {counts}  │  [dim]Price history: {hist_rows:,} rows[/dim]"
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
# Main render loop
# ─────────────────────────────────────────────────────────────────────────────

def build_full_layout(indices: dict, signals: dict, last_update: str,
                       hist_rows: int, top_n: int, refresh_mins: int = 5,
                       watchlist: list[str] | None = None,
                       hist: "pd.DataFrame | None" = None,
                       live_prices: dict | None = None,
                       db_data: dict | None = None,
                       sector_breadth: dict | None = None) -> Table:
    """Compose the full terminal layout as a Rich renderable."""
    grid = Table.grid(expand=True)
    grid.add_column()
    visible_top_n = _adaptive_signal_rows(top_n, has_watchlist=bool(watchlist))

    # Header
    grid.add_row(build_header(indices, refresh_mins))

    # Row 1: Full-width indices OHLC bar
    grid.add_row(build_indices_bar(indices))

    # Row 2: Sector rotation (full width, compact) + breadth %50DMA
    grid.add_row(build_sector_table(indices, sector_breadth))

    # Row 3: Market breadth + McClellan + TRIN + Nifty trend
    grid.add_row(build_breadth_bar(signals.get("breadth", {}), signals.get("nifty_trend", [])))

    # Row 4: Supertrend + Breakout
    row4 = Table.grid(expand=True)
    row4.add_column(ratio=1)
    row4.add_column(ratio=1)
    st_items = signals.get("supertrend_buy", [])[:visible_top_n]
    bo_items = (signals.get("breakouts_52w", []) + signals.get("breakouts_20d", []))[:visible_top_n]
    row4.add_row(
        build_supertrend_panel(st_items),
        build_breakout_panel(bo_items, "52W / 20D BREAKOUTS"),
    )
    grid.add_row(row4)

    # Row 5: VCP + Stage 2
    row5 = Table.grid(expand=True)
    row5.add_column(ratio=1)
    row5.add_column(ratio=1)
    row5.add_row(
        build_vcp_panel(signals.get("vcp_setups", [])[:visible_top_n]),
        build_stage2_panel(signals.get("stage2_leaders", [])[:visible_top_n]),
    )
    grid.add_row(row5)

    # Row 6: Darvas + 52W Momentum
    row6 = Table.grid(expand=True)
    row6.add_column(ratio=1)
    row6.add_column(ratio=1)
    row6.add_row(
        build_darvas_panel(signals.get("darvas_setups", [])[:visible_top_n]),
        build_momentum52w_panel(signals.get("momentum_52w", [])[:visible_top_n]),
    )
    grid.add_row(row6)

    # Row 7: Watchlist (optional — only if watchlist provided and non-empty)
    if watchlist and hist is not None and live_prices is not None and db_data is not None:
        grid.add_row(build_watchlist_panel(watchlist[:visible_top_n], live_prices, hist, db_data))

    # Status bar
    grid.add_row(build_status_bar(last_update, hist_rows, signals))

    return grid


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
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

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

    def _build(indices, signals, label, hist_rows, hist, live_prices, db_data, sector_breadth):
        return build_full_layout(
            indices, signals, label, hist_rows, args.top, args.refresh,
            watchlist=watchlist or None,
            hist=hist if watchlist else None,
            live_prices=live_prices if watchlist else None,
            db_data=db_data if watchlist else None,
            sector_breadth=sector_breadth,
        )

    if args.once:
        with console.status("[bold cyan]Loading NSE Terminal…"):
            res = refresh_data(args.top)
        indices, signals, last_update, hist_rows, hist, live_prices, db_data, sb = res
        layout = _build(indices, signals, last_update, hist_rows, hist, live_prices, db_data, sb)
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

        while True:
            now = time.time()
            if now >= next_refresh:
                try:
                    res = refresh_data(args.top)
                    indices, signals, last_update, hist_rows, hist, live_prices, db_data, sector_breadth = res
                except Exception as e:
                    last_update = f"ERROR: {e}"
                next_refresh = time.time() + refresh_secs

            # Countdown to next refresh
            secs_left = max(0, int(next_refresh - time.time()))
            mins, secs_r = divmod(secs_left, 60)
            countdown = f"{last_update}  │  Next refresh in {mins:02d}:{secs_r:02d}"

            layout = _build(indices, signals, countdown, hist_rows, hist, live_prices, db_data, sector_breadth)
            live.update(layout)
            time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[bold cyan]NSE Terminal closed.[/bold cyan]")
