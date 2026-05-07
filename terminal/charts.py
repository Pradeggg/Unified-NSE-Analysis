"""
terminal/charts.py — In-terminal ASCII charts using plotext.

Renders candlestick + volume + indicator panels directly in the terminal
using plotext. No browser required — works in any terminal.

Usage (from nse_agent.py):
    from terminal.charts import render_chart
    output = render_chart("RELIANCE", timeframe="3mo", indicators=["rsi", "macd"])
    print(output)
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import plotext as plt

ROOT = Path(__file__).parent.parent

# ── yfinance symbol helpers ───────────────────────────────────────────────────

_INDEX_MAP = {
    "NIFTY":        "^NSEI",
    "NIFTY 50":     "^NSEI",
    "BANKNIFTY":    "^NSEBANK",
    "NIFTY BANK":   "^NSEBANK",
    "SENSEX":       "^BSESN",
    "FINNIFTY":     "NIFTY_FIN_SERVICE.NS",
}

_TF_PERIOD_MAP = {
    "1d":   ("1d",  "1m"),    # 1 day → 1-min intraday
    "5d":   ("5d",  "15m"),   # 5 days → 15-min bars
    "1w":   ("5d",  "15m"),
    "1mo":  ("1mo", "1d"),
    "3mo":  ("3mo", "1d"),
    "6mo":  ("6mo", "1d"),
    "1y":   ("1y",  "1d"),
    "2y":   ("2y",  "1wk"),
}


def _yf_symbol(symbol: str) -> str:
    sym = symbol.strip().upper()
    if sym in _INDEX_MAP:
        return _INDEX_MAP[sym]
    if not sym.endswith(".NS") and not sym.startswith("^"):
        return sym + ".NS"
    return sym


def _fetch_ohlcv(symbol: str, timeframe: str = "3mo") -> pd.DataFrame:
    """Fetch OHLCV via yfinance. Returns DataFrame with OHLCV columns."""
    try:
        import yfinance as yf
    except ImportError:
        return pd.DataFrame()

    period, interval = _TF_PERIOD_MAP.get(timeframe, ("3mo", "1d"))
    yf_sym = _yf_symbol(symbol)
    try:
        df = yf.download(yf_sym, period=period, interval=interval, progress=False, auto_adjust=True)
        if df.empty:
            return pd.DataFrame()
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        df = df.reset_index()
        date_col = "Datetime" if "Datetime" in df.columns else "Date"
        df = df.rename(columns={date_col: "Date", "Open": "Open", "High": "High",
                                  "Low": "Low", "Close": "Close", "Volume": "Volume"})
        df = df.dropna(subset=["Close"])
        return df
    except Exception:
        return pd.DataFrame()


# ── Indicator calculations ────────────────────────────────────────────────────

def _rsi(closes: list[float], period: int = 14) -> list[float]:
    s = pd.Series(closes)
    delta = s.diff()
    gain = delta.clip(lower=0).ewm(com=period - 1, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(com=period - 1, adjust=False).mean()
    rs   = gain / loss.replace(0, 1e-9)
    rsi  = 100 - 100 / (1 + rs)
    return rsi.tolist()


def _macd(closes: list[float]) -> tuple[list[float], list[float], list[float]]:
    s    = pd.Series(closes)
    ema12 = s.ewm(span=12, adjust=False).mean()
    ema26 = s.ewm(span=26, adjust=False).mean()
    macd  = ema12 - ema26
    sig   = macd.ewm(span=9, adjust=False).mean()
    hist  = macd - sig
    return macd.tolist(), sig.tolist(), hist.tolist()


def _ema(closes: list[float], span: int) -> list[float]:
    return pd.Series(closes).ewm(span=span, adjust=False).mean().tolist()


def _strip_ansi(s: str) -> str:
    return re.sub(r'\x1b\[[0-9;]*m', '', s)


def _date_labels(df: pd.DataFrame, timeframe: str) -> list[str]:
    """Format date strings for plotext (DD/MM/YYYY)."""
    col = df["Date"]
    if hasattr(col.iloc[0], 'strftime'):
        return [d.strftime('%d/%m/%Y') for d in col]
    # Parse string dates
    parsed = pd.to_datetime(col, utc=True).dt.tz_localize(None)
    return [d.strftime('%d/%m/%Y') for d in parsed]


# ── Chart width/height helpers ────────────────────────────────────────────────

def _terminal_width() -> int:
    try:
        import shutil
        return min(shutil.get_terminal_size().columns - 4, 120)
    except Exception:
        return 90


# ── Public API ─────────────────────────────────────────────────────────────────

def render_chart(
    symbol: str,
    timeframe: str = "3mo",
    indicators: Optional[list[str]] = None,
    width: Optional[int] = None,
) -> str:
    """
    Render an ASCII chart for *symbol* using plotext.

    Parameters
    ----------
    symbol     : NSE symbol e.g. 'RELIANCE', 'NIFTY', 'HDFCBANK'
    timeframe  : '1d', '5d', '1mo', '3mo', '6mo', '1y', '2y'  (default '3mo')
    indicators : list of indicator names to add panels — 'rsi', 'macd', 'volume'
                 default: ['volume', 'rsi']
    width      : chart width in chars (default: terminal width)

    Returns
    -------
    str : complete chart output (ANSI stripped for consistent display)
    """
    if indicators is None:
        indicators = ["volume", "rsi"]
    indicators = [i.lower() for i in indicators]

    df = _fetch_ohlcv(symbol, timeframe)
    if df.empty:
        return f"❌  No data found for {symbol} (timeframe: {timeframe})"

    # Limit to last 60 bars for readability
    max_bars = 60
    if len(df) > max_bars:
        df = df.tail(max_bars).reset_index(drop=True)

    dates  = _date_labels(df, timeframe)
    opens  = df["Open"].tolist()
    highs  = df["High"].tolist()
    lows   = df["Low"].tolist()
    closes = df["Close"].tolist()
    vols   = df["Volume"].tolist() if "Volume" in df.columns else []

    w = width or _terminal_width()

    # Determine number of subplots
    n_panels = 1  # candlestick always
    show_volume = "volume" in indicators and vols
    show_rsi    = "rsi" in indicators
    show_macd   = "macd" in indicators
    if show_volume: n_panels += 1
    if show_rsi:    n_panels += 1
    if show_macd:   n_panels += 1

    plt.clf()
    if n_panels > 1:
        plt.subplots(n_panels, 1)

    panel = 1

    # ── Panel 1: Candlestick + EMAs ───────────────────────────────────────────
    if n_panels > 1:
        plt.subplot(panel, 1)
    candle_data = {"Open": opens, "Close": closes, "High": highs, "Low": lows}
    plt.candlestick(dates, candle_data)
    # Overlay EMA 20 and EMA 50 if enough data
    if len(closes) >= 20:
        ema20 = _ema(closes, 20)
        plt.plot(dates, ema20, color="cyan", label="EMA20")
    if len(closes) >= 50:
        ema50 = _ema(closes, 50)
        plt.plot(dates, ema50, color="orange", label="EMA50")
    tf_label = timeframe.upper()
    current_price = closes[-1]
    chg = closes[-1] - closes[-2] if len(closes) >= 2 else 0.0
    chg_pct = 100 * chg / closes[-2] if closes[-2] else 0.0
    sign = "▲" if chg >= 0 else "▼"
    plt.title(f"{symbol.upper()}  ₹{current_price:,.1f}  {sign}{abs(chg_pct):.2f}%  ({tf_label})")
    h_candle = max(18, 26 - 4 * (n_panels - 1))
    plt.plotsize(w, h_candle)
    panel += 1

    # ── Panel 2: Volume ───────────────────────────────────────────────────────
    if show_volume:
        if n_panels > 1:
            plt.subplot(panel, 1)
        colors = ["green" if c >= o else "red" for c, o in zip(closes, opens)]
        plt.bar(dates, vols, color=colors, label="Volume")
        plt.title("Volume")
        plt.plotsize(w, 7)
        panel += 1

    # ── Panel 3: RSI ──────────────────────────────────────────────────────────
    if show_rsi:
        if n_panels > 1:
            plt.subplot(panel, 1)
        rsi_vals = _rsi(closes, 14)
        plt.plot(dates, rsi_vals, color="yellow", label="RSI(14)")
        plt.hline(70, color="red")
        plt.hline(30, color="green")
        plt.hline(50, color="white")
        plt.title("RSI(14)")
        plt.ylim(0, 100)
        plt.plotsize(w, 8)
        panel += 1

    # ── Panel 4: MACD ─────────────────────────────────────────────────────────
    if show_macd:
        if n_panels > 1:
            plt.subplot(panel, 1)
        macd_line, sig_line, hist_vals = _macd(closes)
        plt.plot(dates, macd_line, color="blue",   label="MACD")
        plt.plot(dates, sig_line,  color="orange", label="Signal")
        plt.bar(dates, hist_vals,  color=["green" if h >= 0 else "red" for h in hist_vals],
                label="Hist")
        plt.title("MACD(12,26,9)")
        plt.hline(0, color="white")
        plt.plotsize(w, 8)

    out = plt.build()
    return _strip_ansi(out)


def render_sparkline(symbol: str, days: int = 20) -> str:
    """
    Render a compact one-line sparkline for *symbol* (last *days* closes).
    Suitable for embedding in tables or brief responses.
    """
    df = _fetch_ohlcv(symbol, "1mo")
    if df.empty:
        return "(no data)"
    closes = df["Close"].tail(days).tolist()
    dates  = _date_labels(df.tail(days), "1mo")

    plt.clf()
    plt.plot(dates, closes, color="cyan")
    plt.plotsize(50, 5)
    plt.title(f"{symbol} ({days}d)")
    out = plt.build()
    return _strip_ansi(out)


def chart_summary(symbol: str, timeframe: str = "3mo") -> dict:
    """
    Return chart data summary dict (for use by agent tools / LLM context).
    Includes: current price, change%, RSI, MACD signal, EMA positions, key levels.
    """
    df = _fetch_ohlcv(symbol, timeframe)
    if df.empty:
        return {"error": f"No data for {symbol}"}

    closes = df["Close"].tolist()
    highs  = df["High"].tolist()
    lows   = df["Low"].tolist()
    c = closes[-1]
    prev = closes[-2] if len(closes) >= 2 else c

    rsi_val = _rsi(closes, 14)[-1] if len(closes) >= 15 else None
    macd_line, sig_line, _ = _macd(closes)
    macd_signal = "bullish" if macd_line[-1] > sig_line[-1] else "bearish"

    ema20 = _ema(closes, 20)[-1] if len(closes) >= 20 else None
    ema50 = _ema(closes, 50)[-1] if len(closes) >= 50 else None

    period_high = max(highs)
    period_low  = min(lows)

    return {
        "symbol":        symbol.upper(),
        "timeframe":     timeframe,
        "current_price": round(c, 2),
        "prev_close":    round(prev, 2),
        "change_pct":    round(100 * (c - prev) / prev, 2) if prev else 0,
        "period_high":   round(period_high, 2),
        "period_low":    round(period_low, 2),
        "rsi_14":        round(rsi_val, 1) if rsi_val else None,
        "macd_signal":   macd_signal,
        "ema20":         round(ema20, 2) if ema20 else None,
        "ema50":         round(ema50, 2) if ema50 else None,
        "price_vs_ema20": "above" if ema20 and c > ema20 else "below",
        "price_vs_ema50": "above" if ema50 and c > ema50 else "below",
        "bars":          len(closes),
    }
