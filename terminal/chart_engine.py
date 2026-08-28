"""
terminal/chart_engine.py — Comprehensive equity chart generator for Agent Adda.

Indicators: SMA 20/50/200 · EMA 9 (intraday) · RSI 14 · Supertrend(10,3)
            Swing S/R clustering · Relative Strength vs Nifty 50 + sector index

Output: Self-contained dark-theme HTML file with 3 tabs:
        [6M Daily] [Intraday 15m] [RS Strength]

Usage:
    python -m terminal.chart_engine NHPC
    python -m terminal.chart_engine RELIANCE --period 1y --open
    python -m terminal.chart_engine HDFCBANK --no-open --out /tmp/chart.html
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

ROOT = Path(__file__).parent.parent
REPORTS = ROOT / "reports" / "latest" / "charts"

# ── Sector index map (yfinance tickers) ───────────────────────────────────────
_SECTOR_IDX = {
    "Financial Services":   "^CNXFIN",
    "Bank":                 "^NSEBANK",
    "Information Technology": "^CNXIT",
    "Pharma":               "^CNXPHARMA",
    "Auto":                 "^CNXAUTO",
    "Metal":                "^CNXMETAL",
    "Energy":               "^CNXENERGY",
    "Infrastructure":       "^CNXINFRA",
    "Realty":               "^CNXREALTY",
    "Media":                "^CNXMEDIA",
    "FMCG":                 "^CNXFMCG",
    "Consumer Durables":    "^CNXCONSUM",
    "PSU Bank":             "^CNXPSUBANK",
}

_INDEX_MAP = {
    "NIFTY": "^NSEI", "NIFTY 50": "^NSEI",
    "BANKNIFTY": "^NSEBANK", "NIFTY BANK": "^NSEBANK",
    "FINNIFTY": "NIFTY_FIN_SERVICE.NS",
    "SENSEX": "^BSESN",
}


def _yf_sym(symbol: str) -> str:
    s = symbol.strip().upper()
    if s in _INDEX_MAP:
        return _INDEX_MAP[s]
    if not s.endswith(".NS") and not s.startswith("^"):
        return s + ".NS"
    return s


# ── Data fetching ─────────────────────────────────────────────────────────────

def _fetch(ticker: str, period: str, interval: str) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError:
        raise RuntimeError("yfinance not installed — run: pip install yfinance")

    df = yf.download(ticker, period=period, interval=interval,
                     progress=False, auto_adjust=True)
    if df.empty:
        return pd.DataFrame()
    # Flatten multi-level columns from yfinance >= 0.2
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df.reset_index()
    date_col = "Datetime" if "Datetime" in df.columns else "Date"
    df = df.rename(columns={date_col: "dt", "Open": "o", "High": "h",
                             "Low": "l", "Close": "c", "Volume": "v"})
    df = df[["dt", "o", "h", "l", "c", "v"]].dropna(subset=["c"])
    for col in ["o", "h", "l", "c"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["v"] = pd.to_numeric(df["v"], errors="coerce").fillna(0).astype(int)
    return df.reset_index(drop=True)


def fetch_daily(symbol: str, months: int = 6) -> pd.DataFrame:
    # Meera Industries is available in the repository as BSE history, while
    # Yahoo Finance does not expose a working MEERA.NS quote. Keep the normal
    # Yahoo route for all other symbols and use the local audited snapshot for
    # this explicitly mapped BSE symbol.
    if symbol.strip().upper() == "MEERA":
        local = ROOT / "data" / "_meera_bse_eod.csv"
        if local.exists():
            df = pd.read_csv(local, parse_dates=["Date"])
            df = df.rename(columns={"Date": "dt", "Open": "o", "High": "h", "Low": "l", "Close": "c", "Volume": "v"})
            return df[["dt", "o", "h", "l", "c", "v"]].dropna(subset=["c"]).reset_index(drop=True)
    period = f"{months}mo" if months <= 11 else f"{months // 12}y"
    return _fetch(_yf_sym(symbol), period, "1d")


def fetch_intraday(symbol: str, days: int = 5) -> pd.DataFrame:
    # yfinance max: 60 days at 15m
    days = min(days, 59)
    return _fetch(_yf_sym(symbol), f"{days}d", "15m")


def fetch_rs_benchmark(symbol: str, benchmark: str, period: str = "6mo") -> pd.DataFrame:
    """Normalized RS: stock / benchmark, base = 100 at first common date."""
    try:
        import yfinance as yf
        stock_t   = _yf_sym(symbol)
        bench_raw = yf.download([stock_t, benchmark], period=period,
                                 interval="1d", progress=False, auto_adjust=True)
        if bench_raw.empty:
            return pd.DataFrame()
        close = bench_raw["Close"] if "Close" in bench_raw else bench_raw.xs("Close", axis=1, level=0)
        close = close.dropna()
        if stock_t not in close.columns or benchmark not in close.columns:
            return pd.DataFrame()
        ratio = close[stock_t] / close[benchmark]
        ratio = (ratio / ratio.iloc[0]) * 100
        out = ratio.reset_index()
        out.columns = ["dt", "rs"]
        return out
    except Exception:
        return pd.DataFrame()


def get_sector_index(symbol: str) -> Optional[str]:
    """Best-effort sector index lookup via yfinance info."""
    try:
        import yfinance as yf
        info = yf.Ticker(_yf_sym(symbol)).info
        sector = info.get("sector", "")
        for key, ticker in _SECTOR_IDX.items():
            if key.lower() in sector.lower():
                return ticker
    except Exception:
        pass
    return None


# ── Indicator computations ─────────────────────────────────────────────────────

def _sma(s: pd.Series, period: int) -> pd.Series:
    return s.rolling(period).mean()


def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False).mean()


def _rsi(s: pd.Series, period: int = 14) -> pd.Series:
    delta = s.diff()
    gain  = delta.clip(lower=0).ewm(com=period - 1, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(com=period - 1, adjust=False).mean()
    rs    = gain / loss.replace(0, 1e-9)
    return 100 - 100 / (1 + rs)


def _atr_wilder(df: pd.DataFrame, period: int = 10) -> pd.Series:
    h, l, c = df["h"], df["l"], df["c"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(com=period - 1, adjust=False).mean()


def _supertrend(df: pd.DataFrame, period: int = 10, mult: float = 3.0):
    """Returns (supertrend Series, direction Series: 1=bull/-1=bear)."""
    atr   = _atr_wilder(df, period)
    hl2   = (df["h"] + df["l"]) / 2
    upper = hl2 + mult * atr
    lower = hl2 - mult * atr

    n = len(df)
    fu = upper.copy()
    fl = lower.copy()
    st = pd.Series(index=df.index, dtype=float)
    di = pd.Series(0, index=df.index, dtype=int)

    for i in range(1, n):
        # Final upper band
        fu.iat[i] = upper.iat[i] if (upper.iat[i] < fu.iat[i-1] or df["c"].iat[i-1] > fu.iat[i-1]) else fu.iat[i-1]
        # Final lower band
        fl.iat[i] = lower.iat[i] if (lower.iat[i] > fl.iat[i-1] or df["c"].iat[i-1] < fl.iat[i-1]) else fl.iat[i-1]
        # Direction
        if df["c"].iat[i] > fu.iat[i-1]:
            di.iat[i] = 1
        elif df["c"].iat[i] < fl.iat[i-1]:
            di.iat[i] = -1
        else:
            di.iat[i] = di.iat[i-1] if di.iat[i-1] != 0 else 1
        st.iat[i] = fl.iat[i] if di.iat[i] == 1 else fu.iat[i]

    return st, di


def _swing_sr(df: pd.DataFrame, window: int = 10, band: float = 0.008, max_levels: int = 7) -> list[dict]:
    """Swing-pivot S/R clusters. Returns list of {price, label, strength}."""
    h, l = df["h"].values, df["l"].values
    n = len(df)
    levels: list[float] = []

    for i in range(window, n - window):
        is_sh = all(h[i] >= h[i-j] for j in range(1, window+1)) and \
                all(h[i] >= h[i+j] for j in range(1, window+1))
        is_sl = all(l[i] <= l[i-j] for j in range(1, window+1)) and \
                all(l[i] <= l[i+j] for j in range(1, window+1))
        if is_sh:
            levels.append(h[i])
        if is_sl:
            levels.append(l[i])

    if not levels:
        return []

    levels.sort()
    clusters: list[list[float]] = []
    cur = [levels[0]]
    for lv in levels[1:]:
        if (lv - cur[0]) / cur[0] <= band:
            cur.append(lv)
        else:
            clusters.append(cur)
            cur = [lv]
    clusters.append(cur)

    result = sorted(
        [{"price": round(sum(c)/len(c), 2), "strength": len(c)} for c in clusters],
        key=lambda x: -x["strength"]
    )[:max_levels]

    last_close = float(df["c"].iloc[-1])
    for r in result:
        r["label"] = "R" if r["price"] > last_close else "S"

    return sorted(result, key=lambda x: x["price"])


def _vavg(s: pd.Series, period: int = 20) -> pd.Series:
    return s.rolling(period).mean()


def _bb(close: pd.Series, period: int = 20, std: float = 2.0):
    """Bollinger Bands — upper, mid (SMA20), lower."""
    mid   = close.rolling(period).mean()
    sigma = close.rolling(period).std()
    return mid + std * sigma, mid, mid - std * sigma


def _macd(close: pd.Series, fast: int = 12, slow: int = 26, sig: int = 9):
    """MACD line, signal line, histogram."""
    ema_f  = close.ewm(span=fast, adjust=False).mean()
    ema_s  = close.ewm(span=slow, adjust=False).mean()
    macd   = ema_f - ema_s
    signal = macd.ewm(span=sig, adjust=False).mean()
    return macd, signal, macd - signal


def _vwap_intraday(df: pd.DataFrame) -> pd.Series:
    """VWAP that resets each calendar day."""
    df2 = df.copy()
    df2["_date"] = pd.to_datetime(df2["dt"]).dt.date
    tp           = (df2["h"] + df2["l"] + df2["c"]) / 3
    df2["_tpv"]  = tp * df2["v"]
    df2["_cumtpv"] = df2.groupby("_date")["_tpv"].cumsum()
    df2["_cumv"]   = df2.groupby("_date")["v"].cumsum()
    return df2["_cumtpv"] / df2["_cumv"]


# ── Serialise to JSON-safe list ───────────────────────────────────────────────

def _round(v, d=2):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return round(float(v), d)


def _series_to_list(s: pd.Series, d=2) -> list:
    return [_round(v, d) for v in s]


def _df_to_records(df: pd.DataFrame, extra_cols: dict[str, pd.Series] = None) -> list[dict]:
    rows = []
    ec = extra_cols or {}
    for i, row in df.iterrows():
        rec = {
            "dt": str(row["dt"]),
            "o": _round(row["o"]),
            "h": _round(row["h"]),
            "l": _round(row["l"]),
            "c": _round(row["c"]),
            "v": int(row["v"]),
        }
        for k, s in ec.items():
            rec[k] = _round(s.iloc[i] if hasattr(s, "iloc") else s[i])
        rows.append(rec)
    return rows


# ── Compute all indicators and package ────────────────────────────────────────

def build_chart_data(symbol: str, months: int = 6, intra_days: int = 5) -> dict:
    print(f"Fetching {symbol} daily ({months}mo)…", end=" ", flush=True)
    daily = fetch_daily(symbol, months)
    if daily.empty:
        raise RuntimeError(f"No daily data for {symbol}")
    print(f"{len(daily)} bars")

    print(f"Fetching {symbol} intraday ({intra_days}d 15m)…", end=" ", flush=True)
    intra = fetch_intraday(symbol, intra_days)
    print(f"{len(intra)} bars" if not intra.empty else "no data")

    # ── Daily indicators ──
    c = daily["c"]
    sma20  = _sma(c, 20)
    sma50  = _sma(c, 50)
    sma200 = _sma(c, 200)
    rsi14  = _rsi(c)
    vavg20 = _vavg(daily["v"])
    st, st_dir = _supertrend(daily)
    sr     = _swing_sr(daily)
    bb_upper, bb_mid, bb_lower = _bb(c)
    macd_line, macd_sig, macd_hist = _macd(c)

    daily_records = _df_to_records(daily, {
        "sma20": sma20, "sma50": sma50, "sma200": sma200,
        "rsi": rsi14, "vavg20": vavg20,
        "st": st, "st_dir": st_dir,
        "bb_upper": bb_upper, "bb_lower": bb_lower,
        "macd": macd_line, "macd_sig": macd_sig, "macd_hist": macd_hist,
    })

    # ── Intraday indicators ──
    intra_records = []
    if not intra.empty:
        ic = intra["c"]
        ema9  = _ema(ic, 9)
        irsi  = _rsi(ic)
        vwap  = _vwap_intraday(intra)
        intra_records = _df_to_records(intra, {"ema9": ema9, "rsi": irsi, "vwap": vwap})

    # ── RS vs Nifty ──
    print("Fetching RS vs Nifty…", end=" ", flush=True)
    rs_nifty = fetch_rs_benchmark(symbol, "^NSEI", f"{months}mo")
    print(f"{len(rs_nifty)} bars" if not rs_nifty.empty else "no data")

    # ── RS vs Sector ──
    sector_ticker = get_sector_index(symbol)
    rs_sector_records = []
    if sector_ticker:
        print(f"Fetching RS vs sector ({sector_ticker})…", end=" ", flush=True)
        rs_sec = fetch_rs_benchmark(symbol, sector_ticker, f"{months}mo")
        if not rs_sec.empty:
            rs_sector_records = [{"dt": str(r["dt"]), "rs": _round(r["rs"])}
                                  for _, r in rs_sec.iterrows()]
            print(f"{len(rs_sector_records)} bars")
        else:
            print("no data")

    rs_nifty_records = [{"dt": str(r["dt"]), "rs": _round(r["rs"])}
                         for _, r in rs_nifty.iterrows()] if not rs_nifty.empty else []

    # ── Summary stats ──
    last = float(c.iloc[-1])
    prev = float(c.iloc[-2]) if len(c) > 1 else last
    chg_pct = round((last - prev) / prev * 100, 2)
    h52  = round(float(daily["h"].max()), 2)
    l52  = round(float(daily["l"].min()), 2)
    last_rsi = _round(rsi14.dropna().iloc[-1]) if not rsi14.dropna().empty else None
    last_st_dir = int(st_dir.iloc[-1])
    last_sma20  = _round(sma20.dropna().iloc[-1]) if not sma20.dropna().empty else None
    last_sma50  = _round(sma50.dropna().iloc[-1]) if not sma50.dropna().empty else None
    last_sma200 = _round(sma200.dropna().iloc[-1]) if not sma200.dropna().empty else None

    _idx_to_sector = {v: k for k, v in _SECTOR_IDX.items()}
    sector_name = _idx_to_sector.get(sector_ticker, "") if sector_ticker else ""

    return {
        "symbol": symbol.upper(),
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "stats": {
            "last": _round(last),
            "chg_pct": chg_pct,
            "high52": h52,
            "low52": l52,
            "high52_raw": h52,
            "low52_raw": l52,
            "from_52h": round((last - h52) / h52 * 100, 1),
            "rsi": last_rsi,
            "sma20": last_sma20,
            "sma50": last_sma50,
            "sma200": last_sma200,
            "supertrend": "BULL" if last_st_dir == 1 else "BEAR",
        },
        "daily": daily_records,
        "intraday": intra_records,
        "rs_nifty": rs_nifty_records,
        "rs_sector": rs_sector_records,
        "sr_levels": sr,
        "sector_ticker": sector_ticker or "",
        "sector_name": sector_name,
    }


# ── HTML template ─────────────────────────────────────────────────────────────

_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__SYM__ — Chart</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=Inter:wght@400;500;600&display=swap">
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#0d1117;--surface:#161b22;--border:#21262d;--border2:#30363d;
  --text:#e6edf3;--dim:#8b949e;--dimmer:#484f58;
  --bull:#26a641;--bear:#f85149;--bull-dim:rgba(38,166,65,0.15);--bear-dim:rgba(248,81,73,0.15);
  --sma20:#58a6ff;--sma50:#f0883e;--sma200:#d2a8ff;--ema9:#39d353;
  --rsi-line:#a5d6ff;--st-bull:#26a641;--st-bear:#f85149;
  --rs-nifty:#58a6ff;--rs-sector:#f0883e;
  --vol-bull:rgba(38,166,65,0.45);--vol-bear:rgba(248,81,73,0.45);
  --vol-avg:rgba(240,136,62,0.7);--grid:rgba(48,54,61,0.5);
  --crosshair:rgba(139,148,158,0.5);--accent:#388bfd;
  --bb-upper:#58a6ff;--bb-lower:#58a6ff;--bb-fill:rgba(88,166,255,0.06);
  --vwap:#e3b341;--macd-line:#a5d6ff;--macd-sig:#f0883e;--macd-pos:rgba(38,166,65,0.55);--macd-neg:rgba(248,81,73,0.55);
}}
html,body{{background:var(--bg);color:var(--text);font-family:'Inter',sans-serif;font-size:13px;height:100%;overflow:hidden}}
.mono{{font-family:'JetBrains Mono',monospace}}
/* top bar */
#topbar{{display:flex;align-items:center;padding:0 14px;height:50px;background:var(--surface);border-bottom:1px solid var(--border);flex-shrink:0;gap:0;overflow:hidden}}
.sym{{font-family:'JetBrains Mono',monospace;font-size:17px;font-weight:600;margin-right:8px}}
.sname{{font-size:10px;color:var(--dim);margin-right:16px}}
.ltp{{font-family:'JetBrains Mono',monospace;font-size:19px;font-weight:600}}
.chg{{font-family:'JetBrains Mono',monospace;font-size:12px;margin-left:7px}}
.sep{{width:1px;height:26px;background:var(--border2);margin:0 12px;flex-shrink:0}}
.stat{{display:flex;flex-direction:column;gap:1px;flex-shrink:0}}
.slbl{{font-size:9px;color:var(--dimmer);text-transform:uppercase;letter-spacing:.06em}}
.sval{{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--dim)}}
.sval.hl{{color:var(--text)}}
.bull{{color:var(--bull)}}.bear{{color:var(--bear)}}.neutral{{color:var(--dim)}}
.st-bull{{background:rgba(38,166,65,0.15);color:var(--bull);border:1px solid rgba(38,166,65,0.4);border-radius:3px;padding:1px 6px;font-family:'JetBrains Mono',monospace;font-size:10px;font-weight:600}}
.st-bear{{background:rgba(248,81,73,0.15);color:var(--bear);border:1px solid rgba(248,81,73,0.4);border-radius:3px;padding:1px 6px;font-family:'JetBrains Mono',monospace;font-size:10px;font-weight:600}}
/* tab bar */
#tabbar{{display:flex;align-items:center;gap:2px;padding:5px 14px;background:var(--surface);border-bottom:1px solid var(--border);flex-shrink:0}}
.tab{{font-family:'JetBrains Mono',monospace;font-size:11px;font-weight:500;padding:3px 12px;border-radius:3px;cursor:pointer;color:var(--dim);background:transparent;border:1px solid transparent;transition:all .12s;user-select:none}}
.tab:hover{{color:var(--text);background:var(--border)}}
.tab.active{{color:var(--text);background:rgba(56,139,253,0.15);border-color:var(--accent)}}
/* legend */
#legend{{display:flex;align-items:center;gap:12px;padding:3px 14px;background:var(--bg);flex-shrink:0;flex-wrap:wrap;min-height:22px}}
.leg{{display:flex;align-items:center;gap:5px;font-size:10px;color:var(--dim);font-family:'JetBrains Mono',monospace}}
.leg-line{{width:16px;height:2px;border-radius:1px}}
.leg-dashed{{width:16px;height:0;border-top:2px dashed;border-radius:0}}
/* chart wrap */
#chart-wrap{{display:flex;flex-direction:column;flex:1;overflow:hidden;position:relative}}
canvas{{display:block}}
/* tooltip */
#tooltip{{position:absolute;pointer-events:none;z-index:10;background:rgba(22,27,34,0.97);border:1px solid var(--border2);border-radius:4px;padding:8px 11px;font-family:'JetBrains Mono',monospace;font-size:11px;line-height:1.75;display:none;backdrop-filter:blur(4px)}}
.tt-date{{font-size:9px;color:var(--dim);margin-bottom:3px}}
.tt-row{{display:flex;gap:8px}}
.tt-lbl{{color:var(--dimmer);min-width:36px}}
.tt-val{{color:var(--text)}}
/* sub-labels */
.sub-label{{position:absolute;font-size:9px;color:var(--dim);font-family:'JetBrains Mono',monospace;text-transform:uppercase;letter-spacing:.06em;left:14px;pointer-events:none}}
/* symbol switcher */
#sym-bar{{display:flex;align-items:center;gap:6px;padding:4px 14px;background:var(--surface);border-bottom:1px solid var(--border);flex-shrink:0}}
#sym-input{{font-family:'JetBrains Mono',monospace;font-size:12px;background:var(--bg);border:1px solid var(--border2);border-radius:3px;color:var(--text);padding:3px 8px;width:120px;outline:none}}
#sym-input:focus{{border-color:var(--accent)}}
#sym-go{{font-family:'JetBrains Mono',monospace;font-size:11px;background:var(--accent);color:#fff;border:none;border-radius:3px;padding:3px 10px;cursor:pointer}}
#sym-go:hover{{opacity:.85}}
/* legend wrap */
#legend-wrap{{display:flex;align-items:center;flex-shrink:0;background:var(--bg)}}
.sub-btn{{font-family:'JetBrains Mono',monospace;font-size:10px;background:transparent;border:1px solid var(--border2);border-radius:3px;color:var(--dim);padding:2px 8px;margin-right:10px;cursor:pointer;flex-shrink:0}}
.sub-btn:hover{{color:var(--text)}}
body{{display:flex;flex-direction:column;height:100vh}}
/* ── Command Palette (Cmd+K) ─────────────────────────────────────────────── */
#palette-overlay{{display:none;position:fixed;inset:0;background:rgba(0,0,0,0.6);z-index:100;backdrop-filter:blur(3px);align-items:flex-start;justify-content:center;padding-top:80px}}
#palette-overlay.open{{display:flex}}
#palette-box{{background:#161b22;border:1px solid #388bfd;border-radius:8px;width:560px;max-height:420px;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 24px 48px rgba(0,0,0,0.6)}}
#palette-input{{font-family:'JetBrains Mono',monospace;font-size:14px;background:transparent;color:#e6edf3;border:none;border-bottom:1px solid #30363d;padding:14px 16px;outline:none;width:100%}}
#palette-input::placeholder{{color:#484f58}}
#palette-results{{overflow-y:auto;flex:1}}
.pal-item{{padding:10px 16px;cursor:pointer;border-bottom:1px solid #21262d;display:flex;flex-direction:column;gap:3px}}
.pal-item:hover,.pal-item.active{{background:rgba(56,139,253,0.12)}}
.pal-name{{font-family:'JetBrains Mono',monospace;font-size:12px;color:#e6edf3;font-weight:600}}
.pal-desc{{font-size:11px;color:#8b949e}}
.pal-cli{{font-family:'JetBrains Mono',monospace;font-size:10px;color:#484f58;margin-top:2px}}
.pal-tags{{display:flex;gap:4px;flex-wrap:wrap}}
.pal-tag{{font-size:9px;padding:1px 5px;border-radius:2px;background:rgba(56,139,253,0.15);color:#58a6ff;font-family:'JetBrains Mono',monospace}}
#pal-hint{{font-size:10px;color:#484f58;padding:8px 16px;border-top:1px solid #21262d;font-family:'JetBrains Mono',monospace;flex-shrink:0}}
</style>
</head>
<body>
<div id="topbar">
  <span class="sym">__SYM__</span>
  <span class="sname" id="sname-el">NSE</span>
  <div class="sep"></div>
  <span class="ltp" id="ltp"></span>
  <span class="chg" id="chg"></span>
  <div class="sep"></div>
  <div class="stat"><span class="slbl">52W H</span><span class="sval mono" id="h52"></span></div>
  <div class="sep"></div>
  <div class="stat"><span class="slbl">52W L</span><span class="sval mono" id="l52"></span></div>
  <div class="sep"></div>
  <div class="stat"><span class="slbl">SMA 20</span><span class="sval mono hl" id="s20"></span></div>
  <div class="sep"></div>
  <div class="stat"><span class="slbl">SMA 50</span><span class="sval mono hl" id="s50"></span></div>
  <div class="sep"></div>
  <div class="stat"><span class="slbl">SMA 200</span><span class="sval mono hl" id="s200"></span></div>
  <div class="sep"></div>
  <div class="stat"><span class="slbl">RSI 14</span><span class="sval mono" id="rsi-val"></span></div>
  <div class="sep"></div>
  <div class="stat"><span class="slbl">Supertrend</span><span id="st-badge"></span></div>
  <div class="sep"></div>
  <div class="stat"><span class="slbl">From 52H</span><span class="sval mono bear" id="from52h"></span></div>
</div>

<div id="tabbar">
  <div class="tab active" onclick="switchTab('daily')">6M Daily</div>
  <div class="tab" onclick="switchTab('intraday')">Intraday 15m</div>
  <div class="tab" onclick="switchTab('rs')">RS Strength</div>
</div>

<div id="sym-bar">
  <input id="sym-input" type="text" placeholder="__SYM__" autocomplete="off" spellcheck="false">
  <button id="sym-go" onclick="goChart()">Go ↵</button>
  <span style="font-size:10px;color:var(--dim)">switch symbol</span>
</div>

<div id="legend-wrap">
  <div id="legend" style="display:flex;align-items:center;gap:12px;padding:3px 14px;flex-wrap:wrap;min-height:22px;flex:1"></div>
  <button class="sub-btn" id="sub-toggle" onclick="toggleSub()">MACD</button>
</div>

<div id="chart-wrap">
  <canvas id="main-c"></canvas>
  <canvas id="vol-c"></canvas>
  <canvas id="sub-c"></canvas>
  <div id="tooltip"></div>
  <div class="sub-label" id="sub-label"></div>
</div>

<script>
// ── Data (injected by Python) ──────────────────────────────────────────────
const DATA = __DATA_JSON__;

// ── Layout constants ──────────────────────────────────────────────────────
const MAIN_R = 0.56, VOL_R = 0.15, SUB_R = 0.22;
const PAD_L=8, PAD_R=64, PAD_T=14, PAD_B=22;
const DPR = window.devicePixelRatio || 1;
const CS = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

let currentTab = 'daily';
let subMode = 'rsi';   // 'rsi' | 'macd'
const mainC = document.getElementById('main-c');
const volC  = document.getElementById('vol-c');
const subC  = document.getElementById('sub-c');
const wrap  = document.getElementById('chart-wrap');
const tt    = document.getElementById('tooltip');
const subLbl = document.getElementById('sub-label');

// ── Legends per tab ──────────────────────────────────────────────────────
const LEGENDS = {
  daily: [
    {color:'var(--sma20)', label:'SMA 20'},
    {color:'var(--sma50)', label:'SMA 50'},
    {color:'var(--sma200)', label:'SMA 200'},
    {color:'var(--bb-upper)', label:'BB(20)', dashed:true},
    {color:'var(--st-bull)', label:'Supertrend', dashed:false, dot:true},
    {color:'var(--bull)', label:'Bull', dim:true},
    {color:'var(--bear)', label:'Bear', dim:true},
    {color:'var(--dimmer)', label:'S/R', dashed:true},
  ],
  intraday: [
    {color:'var(--ema9)', label:'EMA 9'},
    {color:'var(--vwap)', label:'VWAP'},
    {color:'var(--bull)', label:'Bull', dim:true},
    {color:'var(--bear)', label:'Bear', dim:true},
    {color:'var(--dimmer)', label:'S/R (daily)', dashed:true},
  ],
  rs: [
    {color:'var(--rs-nifty)', label:'vs Nifty 50'},
    {color:'var(--rs-sector)', label:'vs Sector'},
  ],
};

function buildLegend(tab) {
  const el = document.getElementById('legend');
  el.innerHTML = LEGENDS[tab].map(l => {
    if (l.dashed) return `<div class="leg"><div class="leg-dashed" style="border-color:${l.color}"></div>${l.label}</div>`;
    if (l.dot) return `<div class="leg"><div style="width:10px;height:10px;border-radius:50%;background:${l.color};opacity:.85"></div>${l.label}</div>`;
    return `<div class="leg"><div class="leg-line" style="background:${l.color};opacity:${l.dim ? 0.8 : 1}"></div>${l.label}</div>`;
  }).join('');
}

// ── Helpers ───────────────────────────────────────────────────────────────
function resize() {
  const wH = wrap.clientHeight, wW = wrap.clientWidth;
  const mh = Math.floor(wH * MAIN_R);
  const vh = Math.floor(wH * VOL_R);
  const sh = Math.floor(wH * SUB_R);
  for (const [c, h] of [[mainC, mh],[volC, vh],[subC, sh]]) {
    c.width = wW * DPR; c.height = h * DPR;
    c.style.width = wW + 'px'; c.style.height = h + 'px';
    c.style.display = 'block';
    c.getContext('2d').scale(DPR, DPR);
  }
  subLbl.style.top = (mh + vh + 4) + 'px';
}

function resizeRS() {
  // RS tab: mainC fills full wrap; vol/sub hidden
  const wH = wrap.clientHeight, wW = wrap.clientWidth;
  mainC.width = wW * DPR; mainC.height = wH * DPR;
  mainC.style.width = wW + 'px'; mainC.style.height = wH + 'px';
  mainC.style.display = 'block';
  mainC.getContext('2d').scale(DPR, DPR);
  volC.style.display = 'none';
  subC.style.display = 'none';
  subLbl.textContent = '';
}

function lay(canvas) {
  const W = canvas.width/DPR, H = canvas.height/DPR;
  return {W, H, L:PAD_L, R:W-PAD_R, T:PAD_T, B:H-PAD_B};
}

function ys(v, yMin, yMax, T, B) { return B-(v-yMin)/(yMax-yMin)*(B-T); }
function xs(i, n, L, R)          { return L+(i+0.5)/n*(R-L); }

function drawGrid(ctx, {L,R,T,B}, n=5) {
  ctx.strokeStyle=CS('--grid'); ctx.lineWidth=0.5;
  for(let i=0;i<=n;i++){const y=T+(B-T)*i/n;ctx.beginPath();ctx.moveTo(L,y);ctx.lineTo(R,y);ctx.stroke();}
}

function drawYLabels(ctx, {R,T,B}, yMin, yMax, n=5, fmt=v=>v.toFixed(2)) {
  ctx.fillStyle=CS('--dim'); ctx.font="10px 'JetBrains Mono',monospace"; ctx.textAlign='left';
  for(let i=0;i<=n;i++){
    const v=yMin+(yMax-yMin)*(1-i/n);
    ctx.fillText(fmt(v), R+4, T+(B-T)*i/n+3.5);
  }
}

function drawXLabels(ctx, data, {L,R,B}, isIntra) {
  const n=data.length; const step=Math.max(1,Math.floor(n/8));
  ctx.fillStyle=CS('--dim'); ctx.font="9px 'JetBrains Mono',monospace"; ctx.textAlign='center';
  for(let i=0;i<n;i+=step){
    const d=new Date(data[i].dt.replace(' ','T').replace('+05:30','+0530'));
    const lbl=isIntra
      ?d.toLocaleTimeString('en-IN',{hour:'2-digit',minute:'2-digit',hour12:false})
      :d.toLocaleDateString('en-IN',{day:'2-digit',month:'short'});
    ctx.fillText(lbl, xs(i,n,L,R), B+14);
  }
}

function fmtVol(v) {
  if(v>=1e7) return (v/1e7).toFixed(1)+'Cr';
  if(v>=1e5) return (v/1e5).toFixed(1)+'L';
  return (v/1e3).toFixed(0)+'K';
}

function fmtDt(dt, isIntra) {
  const d=new Date(dt.replace(' ','T').replace('+05:30','+0530'));
  if(isIntra) return d.toLocaleDateString('en-IN',{day:'2-digit',month:'short'})+' '+
               d.toLocaleTimeString('en-IN',{hour:'2-digit',minute:'2-digit',hour12:false});
  return d.toLocaleDateString('en-IN',{day:'2-digit',month:'short',year:'2-digit'});
}

// ── Draw candles ─────────────────────────────────────────────────────────
function drawCandles(data, isIntra) {
  const ctx=mainC.getContext('2d');
  const l=lay(mainC); const {L,R,T,B,W,H}=l;
  ctx.clearRect(0,0,W,H);

  const ps=data.flatMap(d=>[d.h,d.l]);
  let yMin=Math.min(...ps), yMax=Math.max(...ps);
  const pad=(yMax-yMin)*0.07; yMin-=pad; yMax+=pad;

  // ── Volume Profile (left margin, drawn before everything) ────────────────
  {
    const BUCKETS=30, PW=16; // 16px wide profile bars
    const bucket=Array(BUCKETS).fill(0);
    data.forEach(d=>{
      const idx=Math.min(BUCKETS-1,Math.floor((d.c-yMin)/(yMax-yMin)*BUCKETS));
      if(idx>=0) bucket[idx]+=d.v;
    });
    const maxB=Math.max(...bucket)||1;
    bucket.forEach((v,i)=>{
      const barH=Math.max(1,(B-T)/BUCKETS-1);
      const barW=(v/maxB)*PW;
      const y=B-(i+1)*(B-T)/BUCKETS;
      ctx.fillStyle='rgba(88,166,255,0.18)';
      ctx.fillRect(L, y, barW, barH);
    });
  }

  drawGrid(ctx,l); drawYLabels(ctx,l,yMin,yMax); drawXLabels(ctx,data,l,isIntra);

  const n=data.length;
  const cw=Math.max(1,(R-L)/n*0.68);

  if(!isIntra) {
    // ── Bollinger Bands fill + lines ─────────────────────────────────────
    // Fill between upper and lower
    ctx.beginPath(); let fi=true;
    data.forEach((d,i)=>{
      if(d.bb_upper==null) return;
      const x=xs(i,n,L,R);
      fi?ctx.moveTo(x,ys(d.bb_upper,yMin,yMax,T,B)):ctx.lineTo(x,ys(d.bb_upper,yMin,yMax,T,B));
      fi=false;
    });
    const lastBB=[...data].reverse().find(d=>d.bb_lower!=null);
    [...data].slice().reverse().forEach(d=>{
      if(d.bb_lower==null) return;
      const i=data.indexOf(d);
      ctx.lineTo(xs(i,n,L,R),ys(d.bb_lower,yMin,yMax,T,B));
    });
    ctx.closePath(); ctx.fillStyle=CS('--bb-fill'); ctx.fill();
    for(const k of ['bb_upper','bb_lower']) {
      ctx.beginPath(); ctx.setLineDash([3,3]); ctx.strokeStyle=CS('--bb-upper'); ctx.lineWidth=0.8; let first=true;
      data.forEach((d,i)=>{
        if(d[k]==null) return;
        const x=xs(i,n,L,R), y=ys(d[k],yMin,yMax,T,B);
        first?ctx.moveTo(x,y):ctx.lineTo(x,y); first=false;
      });
      ctx.stroke(); ctx.setLineDash([]);
    }
    // ── 52W H/L lines ────────────────────────────────────────────────────
    if(DATA.stats.high52_raw!=null) {
      const y52h=ys(DATA.stats.high52_raw,yMin,yMax,T,B);
      if(y52h>=T && y52h<=B) {
        ctx.setLineDash([6,4]); ctx.strokeStyle='rgba(88,166,255,0.45)'; ctx.lineWidth=0.8;
        ctx.beginPath(); ctx.moveTo(L,y52h); ctx.lineTo(R,y52h); ctx.stroke();
        ctx.setLineDash([]); ctx.fillStyle='rgba(88,166,255,0.7)'; ctx.font="8px 'JetBrains Mono',monospace"; ctx.textAlign='right';
        ctx.fillText('52H',R-2,y52h-2);
      }
    }
    if(DATA.stats.low52_raw!=null) {
      const y52l=ys(DATA.stats.low52_raw,yMin,yMax,T,B);
      if(y52l>=T && y52l<=B) {
        ctx.setLineDash([6,4]); ctx.strokeStyle='rgba(88,166,255,0.45)'; ctx.lineWidth=0.8;
        ctx.beginPath(); ctx.moveTo(L,y52l); ctx.lineTo(R,y52l); ctx.stroke();
        ctx.setLineDash([]); ctx.fillStyle='rgba(88,166,255,0.7)'; ctx.font="8px 'JetBrains Mono',monospace"; ctx.textAlign='right';
        ctx.fillText('52L',R-2,y52l+9);
      }
    }
    // ── SMAs ─────────────────────────────────────────────────────────────
    for(const [k,color] of [['sma20','--sma20'],['sma50','--sma50'],['sma200','--sma200']]) {
      ctx.beginPath(); ctx.strokeStyle=CS(color); ctx.lineWidth=1.1; let first=true;
      data.forEach((d,i)=>{
        if(d[k]==null) return;
        const x=xs(i,n,L,R), y=ys(d[k],yMin,yMax,T,B);
        first?ctx.moveTo(x,y):ctx.lineTo(x,y); first=false;
      });
      ctx.stroke();
    }
    // ── Supertrend ───────────────────────────────────────────────────────
    let prevDir=null, segPts=[];
    const flushSeg=(dir)=>{
      if(!segPts.length) return;
      ctx.beginPath(); ctx.strokeStyle=dir===1?CS('--st-bull'):CS('--st-bear');
      ctx.lineWidth=1.6;
      segPts.forEach(([x,y],i)=>i===0?ctx.moveTo(x,y):ctx.lineTo(x,y));
      ctx.stroke(); segPts=[];
    };
    data.forEach((d,i)=>{
      if(d.st==null||d.st_dir===0) return;
      if(d.st_dir!==prevDir){flushSeg(prevDir);prevDir=d.st_dir;}
      segPts.push([xs(i,n,L,R),ys(d.st,yMin,yMax,T,B)]);
    });
    flushSeg(prevDir);
  } else {
    // ── EMA 9 on intraday ─────────────────────────────────────────────────
    ctx.beginPath(); ctx.strokeStyle=CS('--ema9'); ctx.lineWidth=1.1; let first=true;
    data.forEach((d,i)=>{
      if(d.ema9==null) return;
      const x=xs(i,n,L,R), y=ys(d.ema9,yMin,yMax,T,B);
      first?ctx.moveTo(x,y):ctx.lineTo(x,y); first=false;
    });
    ctx.stroke();
    // ── VWAP ──────────────────────────────────────────────────────────────
    ctx.beginPath(); ctx.strokeStyle=CS('--vwap'); ctx.lineWidth=1.3; first=true;
    data.forEach((d,i)=>{
      if(d.vwap==null) return;
      const x=xs(i,n,L,R), y=ys(d.vwap,yMin,yMax,T,B);
      first?ctx.moveTo(x,y):ctx.lineTo(x,y); first=false;
    });
    ctx.stroke();
  }

  // ── Candles ───────────────────────────────────────────────────────────────
  data.forEach((d,i)=>{
    const bull=d.c>=d.o; const color=CS(bull?'--bull':'--bear');
    const x=xs(i,n,L,R);
    const yO=ys(d.o,yMin,yMax,T,B), yC=ys(d.c,yMin,yMax,T,B);
    const yH=ys(d.h,yMin,yMax,T,B), yL=ys(d.l,yMin,yMax,T,B);
    ctx.strokeStyle=color; ctx.lineWidth=1;
    ctx.beginPath(); ctx.moveTo(x,yH); ctx.lineTo(x,yL); ctx.stroke();
    const bTop=Math.min(yO,yC), bH=Math.max(1.5,Math.abs(yO-yC));
    ctx.fillStyle=CS(bull?'--bull-dim':'--bear-dim');
    ctx.fillRect(x-cw/2,bTop,cw,bH);
    ctx.strokeStyle=color; ctx.lineWidth=1;
    ctx.strokeRect(x-cw/2,bTop,cw,bH);
  });

  // ── Last price dashed ─────────────────────────────────────────────────────
  const last=data[data.length-1].c;
  const yL2=ys(last,yMin,yMax,T,B);
  ctx.setLineDash([3,3]); ctx.strokeStyle='rgba(139,148,158,0.35)'; ctx.lineWidth=1;
  ctx.beginPath(); ctx.moveTo(L,yL2); ctx.lineTo(R,yL2); ctx.stroke();
  ctx.setLineDash([]);

  // ── S/R lines — drawn LAST so they overlay candles ───────────────────────
  ctx.font="9px 'JetBrains Mono',monospace";
  for(const sr of DATA.sr_levels) {
    if(sr.price<yMin||sr.price>yMax) continue;
    const y=ys(sr.price,yMin,yMax,T,B);
    const isR=sr.label==='R';
    const lineColor=isR?'rgba(248,81,73,0.75)':'rgba(38,166,65,0.75)';
    const labelColor=isR?'#f85149':'#26a641';
    ctx.setLineDash([5,4]);
    ctx.strokeStyle=lineColor;
    ctx.lineWidth=1;
    ctx.beginPath(); ctx.moveTo(L,y); ctx.lineTo(R,y); ctx.stroke();
    ctx.setLineDash([]);
    const lbl=sr.label+' '+sr.price.toFixed(2);
    const lw=ctx.measureText(lbl).width;
    ctx.fillStyle='rgba(13,17,23,0.82)';
    ctx.fillRect(R+3, y-9, lw+6, 12);
    ctx.fillStyle=labelColor;
    ctx.textAlign='left';
    ctx.fillText(lbl, R+6, y+1);
  }

  return {yMin,yMax};
}

// ── Volume ───────────────────────────────────────────────────────────────
function drawVolume(data, isIntra) {
  const ctx=volC.getContext('2d'); const l=lay(volC); const {L,R,T,B,W,H}=l;
  ctx.clearRect(0,0,W,H); drawGrid(ctx,l,3);
  const vols=data.map(d=>d.v); const vMax=Math.max(...vols)*1.05;
  const n=data.length; const bw=Math.max(1,(R-L)/n*0.68);
  data.forEach((d,i)=>{
    const bull=d.c>=d.o; const x=xs(i,n,L,R);
    const bh=(d.v/vMax)*(B-T);
    ctx.fillStyle=CS(bull?'--vol-bull':'--vol-bear');
    ctx.fillRect(x-bw/2,B-bh,bw,bh);
  });
  if(!isIntra) {
    ctx.beginPath(); ctx.strokeStyle=CS('--vol-avg'); ctx.lineWidth=1; let first=true;
    data.forEach((d,i)=>{
      if(!d.vavg20) return;
      const x=xs(i,n,L,R), y=B-(d.vavg20/vMax)*(B-T);
      first?ctx.moveTo(x,y):ctx.lineTo(x,y); first=false;
    });
    ctx.stroke();
  }
  ctx.fillStyle=CS('--dim'); ctx.font="9px 'JetBrains Mono',monospace"; ctx.textAlign='left';
  ctx.fillText(fmtVol(vMax*0.9),R+4,T+10);
}

// ── RSI ──────────────────────────────────────────────────────────────────
function drawRSI(data) {
  const ctx=subC.getContext('2d'); const l=lay(subC); const {L,R,T,B,W,H}=l;
  ctx.clearRect(0,0,W,H);
  const ys2=(v)=>ys(v,0,100,T,B);
  const y70=ys2(70), y30=ys2(30);
  ctx.fillStyle='rgba(248,81,73,0.05)'; ctx.fillRect(L,T,R-L,y70-T);
  ctx.fillStyle='rgba(38,166,65,0.05)'; ctx.fillRect(L,y30,R-L,B-y30);
  ctx.setLineDash([3,3]);
  for(const [lv,col] of [[70,'rgba(248,81,73,0.3)'],[50,'rgba(139,148,158,0.2)'],[30,'rgba(38,166,65,0.3)']]) {
    const y=ys2(lv);
    ctx.strokeStyle=col; ctx.lineWidth=0.8;
    ctx.beginPath(); ctx.moveTo(L,y); ctx.lineTo(R,y); ctx.stroke();
  }
  ctx.setLineDash([]);
  const n=data.length;
  ctx.beginPath(); ctx.strokeStyle=CS('--rsi-line'); ctx.lineWidth=1.4; let first=true;
  data.forEach((d,i)=>{
    if(d.rsi==null) return;
    const x=xs(i,n,L,R), y=ys2(d.rsi);
    first?ctx.moveTo(x,y):ctx.lineTo(x,y); first=false;
  });
  ctx.stroke();
  // RSI area fill
  ctx.beginPath(); first=true;
  const firstRsiIdx=data.findIndex(d=>d.rsi!=null);
  if(firstRsiIdx>=0){
    ctx.moveTo(xs(firstRsiIdx,n,L,R),B);
    data.forEach((d,i)=>{
      if(d.rsi==null) return;
      ctx.lineTo(xs(i,n,L,R),ys2(d.rsi));
    });
    const lastRsiIdx=[...data].map((d,i)=>d.rsi!=null?i:-1).filter(i=>i>=0).pop();
    ctx.lineTo(xs(lastRsiIdx,n,L,R),B); ctx.closePath();
    ctx.fillStyle='rgba(165,214,255,0.05)'; ctx.fill();
  }
  ctx.fillStyle=CS('--dim'); ctx.font="9px 'JetBrains Mono',monospace"; ctx.textAlign='left';
  ctx.fillText('70',R+4,y70+3); ctx.fillText('50',R+4,ys2(50)+3); ctx.fillText('30',R+4,y30+3);
  // dot on last
  const lastR=[...data].reverse().find(d=>d.rsi!=null);
  if(lastR){const xi=data.indexOf(lastR);ctx.beginPath();ctx.arc(xs(xi,n,L,R),ys2(lastR.rsi),3,0,Math.PI*2);ctx.fillStyle=CS('--rsi-line');ctx.fill();}
  subLbl.textContent='RSI 14';
}

// ── MACD ──────────────────────────────────────────────────────────────────
function drawMACD(data) {
  const ctx=subC.getContext('2d'); const l=lay(subC); const {L,R,T,B,W,H}=l;
  ctx.clearRect(0,0,W,H);
  const n=data.length;
  const vals=[...data.map(d=>d.macd),...data.map(d=>d.macd_sig),...data.map(d=>d.macd_hist)].filter(v=>v!=null);
  if(!vals.length){
    ctx.fillStyle=CS('--dim'); ctx.font="10px 'Inter',sans-serif"; ctx.textAlign='center';
    ctx.fillText('No MACD data',W/2,H/2); subLbl.textContent='MACD(12,26,9)'; return;
  }
  let yMin=Math.min(...vals), yMax=Math.max(...vals);
  const pad=(yMax-yMin)*0.1||0.01; yMin-=pad; yMax+=pad;
  const ys2=v=>ys(v,yMin,yMax,T,B);
  // Zero line
  const y0=ys2(0);
  ctx.setLineDash([3,3]); ctx.strokeStyle='rgba(139,148,158,0.25)'; ctx.lineWidth=0.8;
  ctx.beginPath(); ctx.moveTo(L,y0); ctx.lineTo(R,y0); ctx.stroke(); ctx.setLineDash([]);
  // Histogram bars
  const bw=Math.max(1,(R-L)/n*0.5);
  data.forEach((d,i)=>{
    if(d.macd_hist==null) return;
    const x=xs(i,n,L,R); const yTop=Math.min(ys2(d.macd_hist),y0); const yBot=Math.max(ys2(d.macd_hist),y0);
    ctx.fillStyle=d.macd_hist>=0?CS('--macd-pos'):CS('--macd-neg');
    ctx.fillRect(x-bw/2,yTop,bw,Math.max(1,yBot-yTop));
  });
  // MACD line
  ctx.beginPath(); ctx.strokeStyle=CS('--macd-line'); ctx.lineWidth=1.2; let first=true;
  data.forEach((d,i)=>{
    if(d.macd==null) return;
    const x=xs(i,n,L,R), y=ys2(d.macd);
    first?ctx.moveTo(x,y):ctx.lineTo(x,y); first=false;
  });
  ctx.stroke();
  // Signal line
  ctx.beginPath(); ctx.strokeStyle=CS('--macd-sig'); ctx.lineWidth=1.0; first=true;
  data.forEach((d,i)=>{
    if(d.macd_sig==null) return;
    const x=xs(i,n,L,R), y=ys2(d.macd_sig);
    first?ctx.moveTo(x,y):ctx.lineTo(x,y); first=false;
  });
  ctx.stroke();
  drawYLabels(ctx,l,yMin,yMax,4,v=>v.toFixed(2));
  subLbl.textContent='MACD(12,26,9)';
}

// ── RS chart ─────────────────────────────────────────────────────────────
function drawRS() {
  const ctx=mainC.getContext('2d'); const l=lay(mainC);
  const {L,R,T,B,W,H}=l;
  ctx.clearRect(0,0,W,H);

  const rn=DATA.rs_nifty, rs=DATA.rs_sector;
  if(!rn.length && !rs.length){
    ctx.fillStyle=CS('--dim'); ctx.font="13px 'Inter',sans-serif"; ctx.textAlign='center';
    ctx.fillText('No RS data available',W/2,H/2); return;
  }

  const allVals=[...rn.map(d=>d.rs),...rs.map(d=>d.rs)].filter(v=>v!=null);
  let yMin=Math.min(...allVals), yMax=Math.max(...allVals);
  const pad=(yMax-yMin)*0.08; yMin-=pad; yMax+=pad;
  if(yMin>95) yMin=95; if(yMax<105) yMax=105;

  drawGrid(ctx,l,8); drawYLabels(ctx,l,yMin,yMax,8,v=>v.toFixed(1));

  // Baseline at 100
  const y100=ys(100,yMin,yMax,T,B);
  ctx.setLineDash([4,4]); ctx.strokeStyle='rgba(139,148,158,0.4)'; ctx.lineWidth=0.8;
  ctx.beginPath(); ctx.moveTo(L,y100); ctx.lineTo(R,y100); ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle=CS('--dim'); ctx.font="9px 'JetBrains Mono',monospace"; ctx.textAlign='left';
  ctx.fillText('Base 100', R+4, y100+3);

  // Shading: clip regions where RS is above / below 100 correctly
  // Draw segment-by-segment so crossing 100 mid-bar is handled
  if(rn.length>1) {
    const n=rn.length;
    // Build segments split at 100 crossings
    for(const [above, fillColor] of [[true,'rgba(38,166,65,0.09)'],[false,'rgba(248,81,73,0.09)']]) {
      ctx.beginPath(); let inSeg=false;
      rn.forEach((d,i)=>{
        if(d.rs==null) return;
        const x=xs(i,n,L,R);
        const rsY=ys(d.rs,yMin,yMax,T,B);
        const isAbove=d.rs>=100;
        if((above&&isAbove)||(!above&&!isAbove)) {
          if(!inSeg){ctx.moveTo(x,y100);inSeg=true;}
          ctx.lineTo(x,rsY);
        } else if(inSeg){
          ctx.lineTo(x,y100); ctx.closePath();
          ctx.fillStyle=fillColor; ctx.fill();
          ctx.beginPath(); inSeg=false;
        }
      });
      if(inSeg){ctx.lineTo(xs(n-1,n,L,R),y100);ctx.closePath();ctx.fillStyle=fillColor;ctx.fill();}
    }
  }

  // RS lines
  for(const [arr,color,lw] of [[rn,CS('--rs-nifty'),1.6],[rs,CS('--rs-sector'),1.2]]) {
    if(!arr.length) continue;
    const n=arr.length;
    ctx.beginPath(); ctx.strokeStyle=color; ctx.lineWidth=lw; let first=true;
    arr.forEach((d,i)=>{
      if(d.rs==null) return;
      const x=xs(i,n,L,R), y=ys(d.rs,yMin,yMax,T,B);
      first?ctx.moveTo(x,y):ctx.lineTo(x,y); first=false;
    });
    ctx.stroke();
  }

  // X labels from rs_nifty (or rs_sector if nifty empty)
  const xSrc=rn.length?rn:rs;
  if(xSrc.length){
    const n=xSrc.length; const step=Math.max(1,Math.floor(n/10));
    ctx.fillStyle=CS('--dim'); ctx.font="9px 'JetBrains Mono',monospace"; ctx.textAlign='center';
    for(let i=0;i<n;i+=step){
      const d=new Date(xSrc[i].dt.replace(' ','T').replace('+05:30','+0530'));
      ctx.fillText(d.toLocaleDateString('en-IN',{day:'2-digit',month:'short'}),xs(i,n,L,R),B+14);
    }
  }

  // Current values + end-of-line dots
  const lastN=rn.length?rn[rn.length-1]:null;
  const lastS=rs.length?rs[rs.length-1]:null;
  ctx.font="11px 'JetBrains Mono',monospace"; ctx.textAlign='right';
  if(lastN?.rs!=null){
    const x=xs(rn.length-1,rn.length,L,R);
    const y=ys(lastN.rs,yMin,yMax,T,B);
    ctx.beginPath(); ctx.arc(x,y,4,0,Math.PI*2); ctx.fillStyle=CS('--rs-nifty'); ctx.fill();
    ctx.fillStyle=CS('--rs-nifty');
    ctx.fillText('Nifty: '+(lastN.rs>=100?'▲':'▼')+lastN.rs.toFixed(1),R-4,T+18);
  }
  if(lastS?.rs!=null){
    const n2=rs.length; const x=xs(n2-1,n2,L,R); const y=ys(lastS.rs,yMin,yMax,T,B);
    ctx.beginPath(); ctx.arc(x,y,4,0,Math.PI*2); ctx.fillStyle=CS('--rs-sector'); ctx.fill();
    ctx.fillStyle=CS('--rs-sector');
    ctx.fillText('Sector: '+(lastS.rs>=100?'▲':'▼')+lastS.rs.toFixed(1),R-4,T+34);
  }
}

// ── Crosshair ─────────────────────────────────────────────────────────────
let activeIdx=-1;
function getIdx(e, canvas) {
  const rect=canvas.getBoundingClientRect(); const mx=e.clientX-rect.left;
  const l=lay(canvas);
  const data=currentTab==='daily'?DATA.daily:DATA.intraday;
  const n=data?data.length:0;
  if(!n) return -1;
  return Math.max(0,Math.min(n-1,Math.round((mx-l.L)/(l.R-l.L)*n-0.5)));
}

function drawCrosshair(idx) {
  if(idx<0) return;
  const isIntra=currentTab==='intraday';
  const data=isIntra?DATA.intraday:DATA.daily;
  const d=data[idx]; if(!d) return;
  drawCandles(data,isIntra); drawVolume(data,isIntra);
  if(subMode==='macd') drawMACD(data); else drawRSI(data);
  const n=data.length;
  for(const canvas of [mainC,volC,subC]) {
    const ctx=canvas.getContext('2d'); const l=lay(canvas);
    const x=xs(idx,n,l.L,l.R);
    ctx.strokeStyle=CS('--crosshair'); ctx.lineWidth=0.8; ctx.setLineDash([]);
    ctx.beginPath(); ctx.moveTo(x,l.T); ctx.lineTo(x,l.B); ctx.stroke();
  }
  const bull=d.c>=d.o;
  const rows=[['O',d.o?.toFixed(2)],['H',d.h?.toFixed(2)],['L',d.l?.toFixed(2)],
    ['C',d.c?.toFixed(2),bull],['Vol',fmtVol(d.v)]];
  if(!isIntra){
    if(d.sma20) rows.push(['SMA20',d.sma20?.toFixed(2)]);
    if(d.sma50) rows.push(['SMA50',d.sma50?.toFixed(2)]);
    if(d.sma200) rows.push(['SMA200',d.sma200?.toFixed(2)]);
    if(d.bb_upper) rows.push(['BB↑',d.bb_upper?.toFixed(2)],['BB↓',d.bb_lower?.toFixed(2)]);
    if(d.st) rows.push(['ST',d.st?.toFixed(2)]);
    if(d.macd!=null) rows.push(['MACD',d.macd?.toFixed(3)],['Sig',d.macd_sig?.toFixed(3)]);
  } else {
    if(d.ema9) rows.push(['EMA9',d.ema9?.toFixed(2)]);
    if(d.vwap) rows.push(['VWAP',d.vwap?.toFixed(2)]);
  }
  if(d.rsi!=null) rows.push(['RSI',d.rsi?.toFixed(1)]);
  tt.style.display='block';
  tt.innerHTML=`<div class="tt-date">${fmtDt(d.dt,isIntra)}</div>`+
    rows.map(([l,v,isBull])=>`<div class="tt-row"><span class="tt-lbl">${l}</span><span class="tt-val" style="${isBull===true?'color:var(--bull)':isBull===false?'color:var(--bear)':''}">${v??'—'}</span></div>`).join('');
  const wRect=wrap.getBoundingClientRect(); const mRect=mainC.getBoundingClientRect();
  const lm=lay(mainC); const x=xs(idx,n,lm.L,lm.R);
  let tx=mRect.left-wRect.left+x+14; let ty=mRect.top-wRect.top+18;
  if(tx+145>wrap.clientWidth-10) tx=mRect.left-wRect.left+x-155;
  tt.style.left=tx+'px'; tt.style.top=ty+'px';
}

function hideCross() {
  tt.style.display='none'; activeIdx=-1;
  if(currentTab!=='rs') drawAll();
}

// ── Toggle RSI / MACD sub-panel ───────────────────────────────────────────
function toggleSub() {
  subMode = subMode==='rsi' ? 'macd' : 'rsi';
  const btn=document.getElementById('sub-toggle');
  btn.textContent = subMode==='rsi' ? 'MACD' : 'RSI';
  if(currentTab!=='rs') drawAll();
}

// ── Symbol switcher ───────────────────────────────────────────────────────
function goChart() {
  const sym=document.getElementById('sym-input').value.trim().toUpperCase();
  if(!sym) return;
  const url=window.location.href.replace(/[^\\/]+_chart\\.html/,sym+'_chart.html');
  window.location.href=url;
}
document.getElementById('sym-input').addEventListener('keydown',e=>{ if(e.key==='Enter') goChart(); });

// ── Tab switch ────────────────────────────────────────────────────────────
function switchTab(tab) {
  currentTab=tab;
  document.querySelectorAll('.tab').forEach((t,i)=>{
    t.classList.toggle('active',(['daily','intraday','rs'][i])===tab);
  });
  tt.style.display='none'; activeIdx=-1;
  if(tab==='rs') resizeRS(); else resize();
  buildLegend(tab); drawAll();
}

function drawAll() {
  if(currentTab==='rs'){drawRS(); return;}
  const isIntra=currentTab==='intraday';
  const data=isIntra?DATA.intraday:DATA.daily;
  if(!data||!data.length){
    mainC.getContext('2d').clearRect(0,0,mainC.width/DPR,mainC.height/DPR);
    return;
  }
  drawCandles(data,isIntra); drawVolume(data,isIntra);
  if(subMode==='macd') drawMACD(data); else drawRSI(data);
}

// Events
for(const canvas of [mainC,volC,subC]) {
  canvas.addEventListener('mousemove',e=>{
    if(currentTab==='rs') return;
    const idx=getIdx(e,canvas);
    if(idx>=0 && idx!==activeIdx){activeIdx=idx;drawCrosshair(idx);}
  });
  canvas.addEventListener('mouseleave',hideCross);
}

// ── Init stat bar ─────────────────────────────────────────────────────────
const S=DATA.stats;
const ltpEl=document.getElementById('ltp');
const chgEl=document.getElementById('chg');
ltpEl.textContent=S.last;
ltpEl.className='ltp mono '+(S.chg_pct>=0?'bull':'bear');
chgEl.textContent=(S.chg_pct>=0?'+':'')+S.chg_pct+'%';
chgEl.className='chg mono '+(S.chg_pct>=0?'bull':'bear');
document.getElementById('h52').textContent=S.high52;
document.getElementById('l52').textContent=S.low52;
document.getElementById('s20').textContent=S.sma20??'—';
document.getElementById('s50').textContent=S.sma50??'—';
document.getElementById('s200').textContent=S.sma200??'—';
const rsiEl=document.getElementById('rsi-val');
rsiEl.textContent=S.rsi??'—';
rsiEl.className='sval mono '+(S.rsi<30?'bull':S.rsi>70?'bear':'neutral');
const stEl=document.getElementById('st-badge');
stEl.className=S.supertrend==='BULL'?'st-bull':'st-bear';
stEl.textContent='▲ '+S.supertrend;
document.getElementById('from52h').textContent=S.from_52h+'%';

// ── Sector name ───────────────────────────────────────────────────────────
const snameEl=document.getElementById('sname-el');
snameEl.textContent='NSE'+(DATA.sector_name?' · '+DATA.sector_name:'');

// Start
resize(); buildLegend('daily'); drawAll();
window.addEventListener('resize',()=>{
  if(currentTab==='rs') resizeRS(); else resize();
  drawAll();
});

// ── Command Palette (Cmd+K) ───────────────────────────────────────────────
const PAL_COMMANDS = [
  {name:'equity_chart', desc:'Chart another symbol', tags:['chart'], cli:'python -m terminal.chart_engine SYMBOL'},
  {name:'intraday_alerts', desc:'Live F&O intraday alert scan', tags:['intraday','fno'], cli:'python -m terminal.live_intraday_alerts --cycles 1'},
  {name:'stage2_vcp', desc:'Stage 2 VCP breakout screener', tags:['screener','vcp'], cli:'python nse_agent.py → /screen stage2_vcp'},
  {name:'sector_rotation', desc:'Sector rotation report', tags:['sector'], cli:'python sector_rotation_report.py'},
  {name:'/dashboard', desc:'Full market dashboard', tags:['market'], cli:'python nse_agent.py → /dashboard'},
  {name:'/xray', desc:'Company X-Ray for a symbol', tags:['research'], cli:'python nse_agent.py → /xray SYMBOL'},
  {name:'/options', desc:'Options chain & PCR analysis', tags:['options','derivatives'], cli:'python nse_agent.py → /options SYMBOL'},
  {name:'/scan', desc:'Live intraday scan', tags:['intraday'], cli:'python nse_agent.py → /scan'},
  {name:'/screen', desc:'Run a screener', tags:['screener'], cli:'python nse_agent.py → /screen'},
  {name:'/strategy_council', desc:'Multi-agent strategy council', tags:['strategy'], cli:'python nse_agent.py → /strategy_council SYMBOL'},
  {name:'universe_scoring', desc:'Full NSE universe scoring', tags:['scoring'], cli:'python fixed_nse_universe_analysis.py'},
  {name:'fund_dashboard', desc:'Mutual fund dashboard', tags:['fund'], cli:'python tools/fund_refresh.py'},
  {name:'live_prices', desc:'Live prices dashboard', tags:['live'], cli:'python tools/live_prices.py'},
  {name:'pg_loader', desc:'Load all data into PostgreSQL', tags:['admin'], cli:'python postgres/loader.py'},
  {name:'daily_refresh', desc:'Run full daily pipeline', tags:['admin','pipeline'], cli:'python daily_refresh.py'},
  {name:'voice_briefing', desc:'Generate voice briefing', tags:['voice'], cli:'python generate_voice_briefing.py --no-tts'},
  {name:'launcher', desc:'Open Agent Adda command centre', tags:['tools'], cli:'open reports/latest/launcher.html'},
];

let palActive=-1;
function openPalette(){{document.getElementById('palette-overlay').classList.add('open');document.getElementById('palette-input').value='';document.getElementById('palette-input').focus();palActive=-1;renderPal('');}}
function closePalette(){{document.getElementById('palette-overlay').classList.remove('open');palActive=-1;}}

function palScore(item,q){{
  if(!q) return 1;
  const s=(item.name+' '+item.desc+' '+(item.tags||[]).join(' ')).toLowerCase();
  const terms=q.toLowerCase().split(/\s+/);
  let score=0;
  for(const t of terms){{
    if(s.includes(t)) score+=(item.name.toLowerCase().startsWith(t)?3:1);
    else return 0;
  }}
  return score;
}}

function renderPal(q){{
  const res=document.getElementById('palette-results');
  const scored=PAL_COMMANDS.map(c=>({...c,_s:palScore(c,q)})).filter(c=>c._s>0).sort((a,b)=>b._s-a._s);
  if(!scored.length){{res.innerHTML=`<div style="padding:20px;text-align:center;color:#484f58;font-family:'JetBrains Mono',monospace;font-size:12px">No match for "${{q}}"</div>`;return;}}
  res.innerHTML=scored.map((c,i)=>`
    <div class="pal-item${{i===palActive?' active':''}}" onclick="palSelect(${{i}})" data-idx="${{i}}">
      <div class="pal-name">${{c.name}}</div>
      <div class="pal-desc">${{c.desc}}</div>
      <div class="pal-tags">${{(c.tags||[]).map(t=>`<span class="pal-tag">${{t}}</span>`).join('')}}</div>
      <div class="pal-cli">${{c.cli}}</div>
    </div>`).join('');
  res._scored=scored;
}}

function palSelect(i){{
  const res=document.getElementById('palette-results');
  const scored=res._scored;
  if(!scored||!scored[i]) return;
  navigator.clipboard.writeText(scored[i].cli).then(()=>{{
    const items=res.querySelectorAll('.pal-item');
    if(items[i]){{const n=items[i].querySelector('.pal-name');const orig=n.textContent;n.textContent='✓ Copied!';setTimeout(()=>{{n.textContent=orig;}},1200);}}
  }}).catch(()=>{{}});
}}

document.getElementById('palette-input').addEventListener('input',e=>{{ palActive=-1; renderPal(e.target.value); }});
document.getElementById('palette-input').addEventListener('keydown',e=>{{
  const res=document.getElementById('palette-results');
  const items=res.querySelectorAll('.pal-item');
  if(e.key==='ArrowDown'){{e.preventDefault();palActive=Math.min(palActive+1,items.length-1);}}
  else if(e.key==='ArrowUp'){{e.preventDefault();palActive=Math.max(palActive-1,0);}}
  else if(e.key==='Enter'){{e.preventDefault();if(palActive>=0)palSelect(palActive);else if(items.length)palSelect(0);}}
  else if(e.key==='Escape'){{closePalette();return;}}
  items.forEach((el,i)=>el.classList.toggle('active',i===palActive));
  if(items[palActive]) items[palActive].scrollIntoView({{block:'nearest'}});
}});
document.addEventListener('keydown',e=>{{
  if((e.metaKey||e.ctrlKey)&&e.key==='k'){{e.preventDefault();
    const ov=document.getElementById('palette-overlay');
    ov.classList.contains('open')?closePalette():openPalette();
  }}
  if(e.key==='Escape') closePalette();
}});
</script>
<div id="palette-overlay" onclick="if(event.target===this)closePalette()">
  <div id="palette-box">
    <input id="palette-input" placeholder="Search commands, skills, screeners…" autocomplete="off" spellcheck="false">
    <div id="palette-results"></div>
    <div id="pal-hint">↑↓ navigate · Enter copy command · Esc close · ⌘K open</div>
  </div>
</div>
</body>
</html>"""


# ── Render ────────────────────────────────────────────────────────────────────

def render_chart(data: dict) -> str:
    html = _HTML
    # Template uses {{ }} in CSS to survive future .format() calls — un-escape them first,
    # before inserting the JSON payload (which itself contains { } legitimately).
    html = html.replace("{{", "{").replace("}}", "}")
    html = html.replace("__SYM__", data["symbol"])
    html = html.replace("__DATA_JSON__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    return html


def save_chart(data: dict, out_path: Optional[Path] = None) -> Path:
    html = render_chart(data)
    if out_path is None:
        REPORTS.mkdir(parents=True, exist_ok=True)
        out_path = REPORTS / f"{data['symbol']}_chart.html"
    out_path.write_text(html, encoding="utf-8")
    return out_path


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    import argparse
    ap = argparse.ArgumentParser(description="Generate comprehensive equity chart")
    ap.add_argument("symbol", help="NSE symbol, e.g. NHPC, RELIANCE")
    ap.add_argument("--months",   type=int,  default=6,  help="Daily history months (default 6)")
    ap.add_argument("--intra-days", type=int, default=5, help="Intraday history days (default 5)")
    ap.add_argument("--out",      help="Output HTML path (default: reports/latest/charts/SYMBOL_chart.html)")
    ap.add_argument("--open",     action="store_true", default=True,  help="Open in browser after save (default on)")
    ap.add_argument("--no-open",  action="store_true", dest="no_open",  help="Do not open browser")
    args = ap.parse_args()

    data = build_chart_data(args.symbol, months=args.months, intra_days=args.intra_days)
    out  = save_chart(data, Path(args.out) if args.out else None)
    print(f"\n✅  Chart saved → {out}")
    if args.open and not args.no_open:
        subprocess.Popen(["open", str(out)])


if __name__ == "__main__":
    main()
