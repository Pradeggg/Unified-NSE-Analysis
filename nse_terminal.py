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
    ("NIFTY SMLCAP 100",  "Smallcap 100"),
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

def _get_nse_session() -> requests.Session:
    global _nse_session
    if _nse_session is None:
        _nse_session = requests.Session()
        _nse_session.headers.update(NSE_HEADERS)
        try:
            _nse_session.get("https://www.nseindia.com/", timeout=10)
            time.sleep(0.5)
        except Exception:
            pass
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
    """Fetch all NSE index quotes in one call. Returns {index_name: quote_dict}."""
    out: dict[str, dict] = {}
    try:
        s = _get_nse_session()
        r = s.get("https://www.nseindia.com/api/allIndices", timeout=12)
        for item in r.json().get("data", []):
            out[item.get("index", "").upper()] = item
    except Exception:
        pass
    return out


def fetch_nse_gainers_losers() -> dict:
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


def fetch_live_prices(symbols: list[str]) -> dict[str, float]:
    """Fetch live prices for a list of symbols using NSE index pages."""
    prices: dict[str, float] = {}
    s = _get_nse_session()
    index_names = [
        "NIFTY 500", "NIFTY SMALLCAP 250", "NIFTY MICROCAP 250",
        "NIFTY MIDSMALLCAP 400", "NIFTY TOTAL MARKET",
    ]
    sym_set = {s.upper() for s in symbols}
    for idx in index_names:
        if len(prices) >= len(sym_set):
            break
        try:
            url = f"https://www.nseindia.com/api/equity-stockIndices?index={requests.utils.quote(idx)}"
            r = s.get(url, timeout=12)
            for item in r.json().get("data", []):
                sym = item.get("symbol", "").upper()
                if sym in sym_set and sym not in prices:
                    prices[sym] = float(item.get("lastPrice", 0) or 0)
        except Exception:
            pass
        time.sleep(0.3)
    return prices


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
    }

    # Load Stage 2 stocks from DB
    stage2_syms: set[str] = set()
    stage2_info: dict[str, dict] = {}
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

        live = live_prices.get(sym.upper())
        current = live or float(grp["CLOSE"].iloc[-1])
        prev_c  = float(grp["CLOSE"].iloc[-2]) if len(grp) > 1 else current
        chg_pct = round((current / prev_c - 1) * 100, 2) if prev_c else 0

        rsi   = compute_rsi(grp["CLOSE"])
        mas   = is_above_key_mas(grp)
        st    = compute_supertrend(grp)

        base = {
            "symbol":  sym,
            "price":   current,
            "chg_pct": chg_pct,
            "rsi":     round(rsi, 1),
            "st":      st,
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

    # 4. Stage 2 leaders (from DB, sorted by investment score)
    for sym, info in stage2_info.items():
        grp = hist[hist["SYMBOL"] == sym]
        if grp.empty:
            continue
        grp = grp.sort_values("TIMESTAMP")
        live  = live_prices.get(sym.upper())
        current = live or float(grp["CLOSE"].iloc[-1])
        prev_c  = float(grp["CLOSE"].iloc[-2]) if len(grp) > 1 else current
        chg_pct = round((current / prev_c - 1) * 100, 2) if prev_c else 0
        rsi   = compute_rsi(grp["CLOSE"])
        mas   = is_above_key_mas(grp)
        results["stage2_leaders"].append({
            "symbol": sym, "price": current, "chg_pct": chg_pct,
            "rsi": round(rsi, 1), **mas, **info,
        })

    # Sort and trim
    results["supertrend_buy"].sort(key=lambda x: x.get("rsi", 0), reverse=True)
    results["breakouts_52w"].sort(key=lambda x: x.get("chg_pct", 0), reverse=True)
    results["breakouts_20d"].sort(key=lambda x: x.get("chg_pct", 0), reverse=True)
    results["vcp_setups"].sort(key=lambda x: x.get("tightness", 99))
    results["stage2_leaders"].sort(key=lambda x: float(x.get("investment_score") or 0), reverse=True)

    for k in results:
        results[k] = results[k][:top_n]

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
    market_open = 9 <= datetime.now().hour < 16

    arrow = "▲" if nc >= 0 else "▼"
    clr   = "green" if nc >= 0 else "red"

    txt = Text()
    txt.append("  ⚡ NSE TERMINAL  ", style="bold white on dark_blue")
    txt.append("  ")
    txt.append(now_ist, style="bold cyan")
    txt.append("    ")
    if market_open:
        txt.append("● MARKET OPEN", style="bold green")
    else:
        txt.append("● MARKET CLOSED", style="bold red")
    txt.append("    NIFTY 50  ", style="bold white")
    txt.append(f"{nv:,.0f}" if nv else "—", style=f"bold {clr}")
    txt.append(f"  {arrow} {abs(nc):,.0f}  ({np_:+.2f}%)", style=clr)
    txt.append(f"  │  🔄 Refresh /{refresh_mins}min  │  Ctrl+C to exit", style="dim")

    return Panel(txt, style="on dark_blue", height=3)


def _parse_price(v) -> float:
    """Parse NSE price which may be a string like '24,119.30' or a float."""
    try:
        if isinstance(v, str):
            return float(v.replace(",", ""))
        return float(v or 0)
    except Exception:
        return 0.0


def build_indices_table(indices: dict) -> Panel:
    tbl = Table(box=box.SIMPLE_HEAD, header_style="bold cyan", show_footer=False,
                expand=True, padding=(0, 1))
    tbl.add_column("INDEX",    style="bold white", no_wrap=True, width=14)
    tbl.add_column("PRICE",    justify="right", width=11)
    tbl.add_column("CHG",      justify="right", width=9)
    tbl.add_column("%",        justify="right", width=8)
    tbl.add_column("52W POS",  justify="center", width=7)

    for key, label in WATCHLIST_INDICES:
        d = indices.get(key.upper(), {})
        if not d:
            tbl.add_row(label, "—", "—", "—", "—")
            continue
        price = _parse_price(d.get("lastPrice", 0))
        chg   = _parse_price(d.get("change",   0))
        pchg  = _parse_price(d.get("pChange",  0))
        hi52  = _parse_price(d.get("yearHigh", 0))
        lo52  = _parse_price(d.get("yearLow",  0))
        clr   = _chg_color(pchg)
        arrow = "▲" if chg >= 0 else "▼"

        # 52w position bar
        if hi52 > lo52 and price > 0:
            pct52  = min(100, max(0, (price - lo52) / (hi52 - lo52) * 100))
            filled = int(pct52 / 20)
            bar    = "█" * filled + "░" * (5 - filled)
            pos52  = f"[dim]{bar}[/dim]"
        else:
            pos52 = "—"

        tbl.add_row(
            label,
            Text(f"{price:,.0f}", style=clr, no_wrap=True) if price else Text("—", style="dim"),
            Text(f"{arrow} {abs(chg):,.0f}", style=clr, no_wrap=True),
            Text(f"{pchg:+.2f}%", style=clr, no_wrap=True),
            pos52,
        )

    return Panel(tbl, title="[bold cyan]■ INDICES[/bold cyan]", border_style="cyan",
                 subtitle="[dim]Live NSE[/dim]")


def build_sector_table(indices: dict) -> Panel:
    tbl = Table(box=box.SIMPLE_HEAD, header_style="bold magenta", expand=True, padding=(0, 1))
    tbl.add_column("SECTOR",   style="bold white", no_wrap=True)
    tbl.add_column("INDEX",    style="dim", no_wrap=True, width=12)
    tbl.add_column("PRICE",    justify="right", width=9)
    tbl.add_column("CHG%",     justify="right", width=8)
    tbl.add_column("SIGNAL",   justify="center", width=10)

    sector_perf: list[tuple] = []
    for sector, idx_name in SECTOR_INDEX_MAP.items():
        d     = indices.get(idx_name.upper(), {})
        pchg  = _parse_price(d.get("pChange",   0)) if d else 0
        price = _parse_price(d.get("lastPrice", 0)) if d else 0
        sector_perf.append((sector, idx_name, pchg, price))

    sector_perf.sort(key=lambda x: x[2], reverse=True)

    for sector, idx_name, pchg, price in sector_perf:
        clr     = _chg_color(pchg)
        arrow   = "▲" if pchg >= 0 else "▼"
        signal  = "LEADING" if pchg > 1 else ("LAGGING" if pchg < -1 else "NEUTRAL")
        sig_clr = "bold green" if signal == "LEADING" else ("bold red" if signal == "LAGGING" else "yellow")
        tbl.add_row(
            Text(sector, style="bold white", no_wrap=True),
            Text(idx_name, style="dim", no_wrap=True),
            Text(f"{price:,.0f}", style=clr, no_wrap=True) if price else Text("—", style="dim"),
            Text(f"{arrow} {pchg:+.2f}%", style=clr, no_wrap=True),
            Text(signal, style=sig_clr, no_wrap=True),
        )

    return Panel(tbl, title="[bold magenta]■ SECTOR ROTATION[/bold magenta]",
                 border_style="magenta", subtitle="[dim]Intraday Performance[/dim]")


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

        else:
            row.append(Text(str(val or "—"), no_wrap=True))
    return row


def build_supertrend_panel(items: list) -> Panel:
    cols = [
        ("SYMBOL", "left",  11), ("PRICE", "right",  9), ("CHG%", "right", 8),
        ("RSI",    "right",  5), ("ST",    "center",  6), ("MA",  "center", 5),
    ]
    return build_signal_table("SUPERTREND BUY", "🟢", items, cols, "green")


def build_breakout_panel(items: list, label: str = "52W BREAKOUT") -> Panel:
    cols = [
        ("SYMBOL", "left",  10), ("PRICE", "right",  9), ("CHG%", "right", 9),
        ("W52H",   "right",  9), ("RSI",   "right",  5), ("VOL✓", "center", 4),
    ]
    return build_signal_table(label, "🚀", items, cols, "yellow")


def build_vcp_panel(items: list) -> Panel:
    cols = [
        ("SYMBOL",    "left",  10), ("PRICE", "right",  9), ("CHG%",  "right", 8),
        ("TIGHTNESS", "right", 10), ("RSI",   "right",  5), ("MA",   "center", 5),
    ]
    return build_signal_table("VCP SETUPS (Volatility Contraction)", "🎯", items, cols, "cyan")


def build_stage2_panel(items: list) -> Panel:
    cols = [
        ("SYMBOL", "left",  10), ("PRICE",  "right",  9), ("CHG%",   "right",  9),
        ("RSI",    "right",  5), ("INV",    "right",   5), ("SIGNAL", "center", 10),
    ]
    return build_signal_table("STAGE 2 LEADERS (Weinstein Advancing)", "⭐", items, cols, "gold1")


def build_status_bar(last_update: str, hist_rows: int, signals: dict) -> Panel:
    counts = "  ".join([
        f"[green]ST:{len(signals.get('supertrend_buy',[]))}[/green]",
        f"[yellow]BO52:{len(signals.get('breakouts_52w',[]))}[/yellow]",
        f"[cyan]VCP:{len(signals.get('vcp_setups',[]))}[/cyan]",
        f"[gold1]S2:{len(signals.get('stage2_leaders',[]))}[/gold1]",
    ])
    txt = f"[dim]Last update:[/dim] [white]{last_update}[/white]  │  {counts}  │  [dim]Price history: {hist_rows:,} rows[/dim]"
    return Panel(txt, height=3, style="on grey15")


# ─────────────────────────────────────────────────────────────────────────────
# Main render loop
# ─────────────────────────────────────────────────────────────────────────────

def build_full_layout(indices: dict, signals: dict, last_update: str,
                       hist_rows: int, top_n: int, refresh_mins: int = 5) -> Table:
    """Compose the full terminal layout as a Rich renderable."""
    grid = Table.grid(expand=True)
    grid.add_column()

    # Header
    grid.add_row(build_header(indices, refresh_mins))

    # Row 1: Indices + Sector
    row1 = Table.grid(expand=True)
    row1.add_column(ratio=2)
    row1.add_column(ratio=3)
    row1.add_row(
        build_indices_table(indices),
        build_sector_table(indices),
    )
    grid.add_row(row1)

    # Row 2: Supertrend + Breakout
    row2 = Table.grid(expand=True)
    row2.add_column(ratio=1)
    row2.add_column(ratio=1)
    st_items = signals.get("supertrend_buy", [])[:top_n]
    bo_items = (signals.get("breakouts_52w", []) + signals.get("breakouts_20d", []))[:top_n]
    row2.add_row(
        build_supertrend_panel(st_items),
        build_breakout_panel(bo_items, "52W / 20D BREAKOUTS"),
    )
    grid.add_row(row2)

    # Row 3: VCP + Stage 2
    row3 = Table.grid(expand=True)
    row3.add_column(ratio=1)
    row3.add_column(ratio=1)
    row3.add_row(
        build_vcp_panel(signals.get("vcp_setups", [])[:top_n]),
        build_stage2_panel(signals.get("stage2_leaders", [])[:top_n]),
    )
    grid.add_row(row3)

    # Status bar
    grid.add_row(build_status_bar(last_update, hist_rows, signals))

    return grid


def refresh_data(top_n: int) -> tuple[dict, dict, str, int]:
    """Fetch all live data and compute signals. Returns (indices, signals, timestamp, hist_rows)."""
    console.log("[dim]Fetching live index data…[/dim]")
    indices = fetch_all_indices()

    console.log("[dim]Loading price history…[/dim]")
    hist = load_price_history(days=260)
    hist_rows = len(hist)

    console.log("[dim]Fetching live stock prices…[/dim]")
    symbols = hist["SYMBOL"].unique().tolist() if not hist.empty else []
    live_prices = fetch_live_prices(symbols[:200])  # top 200 most active

    console.log("[dim]Running technical screener…[/dim]")
    signals = run_screener(hist, live_prices, top_n=top_n)

    last_update = datetime.now().strftime("%H:%M:%S")
    return indices, signals, last_update, hist_rows


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="NSE Bloomberg Terminal")
    parser.add_argument("--once",    action="store_true", help="Run once, no live refresh")
    parser.add_argument("--refresh", type=int, default=5, metavar="MIN",
                        help="Refresh interval in minutes (default: 5)")
    parser.add_argument("--top",     type=int, default=15, metavar="N",
                        help="Max stocks per signal panel (default: 15)")
    args = parser.parse_args()

    refresh_secs = args.refresh * 60

    if args.once:
        with console.status("[bold cyan]Loading NSE Terminal…"):
            indices, signals, last_update, hist_rows = refresh_data(args.top)
        layout = build_full_layout(indices, signals, last_update, hist_rows, args.top, args.refresh)
        console.print(layout)
        return

    # Live refresh mode
    with Live(console=console, screen=True, refresh_per_second=1) as live:
        indices, signals, last_update, hist_rows = {}, {}, "loading…", 0
        next_refresh = 0.0

        while True:
            now = time.time()
            if now >= next_refresh:
                try:
                    indices, signals, last_update, hist_rows = refresh_data(args.top)
                except Exception as e:
                    last_update = f"ERROR: {e}"
                next_refresh = time.time() + refresh_secs

            # Countdown to next refresh
            secs_left = max(0, int(next_refresh - time.time()))
            mins, secs_r = divmod(secs_left, 60)
            countdown = f"{last_update}  │  Next refresh in {mins:02d}:{secs_r:02d}"

            layout = build_full_layout(indices, signals, countdown, hist_rows, args.top, args.refresh)
            live.update(layout)
            time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[bold cyan]NSE Terminal closed.[/bold cyan]")
