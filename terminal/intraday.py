"""
terminal/intraday.py — Intraday screening engine for Agent Adda.

Data source: yfinance (5m / 15m / 30m / 1h OHLCV for NSE stocks).
Indicators: MACD, RSI, Supertrend, Bollinger Bands, EMA stack, OBV,
            VCP detection, Support/Resistance (pivots + swing levels).
Signals:    BUY / SELL with entry, target, stoploss, R:R ratio.
"""

from __future__ import annotations

import math
import os
import contextlib
import warnings
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)


def _quiet_yf_download(yf, *args, **kwargs) -> pd.DataFrame:
    """Run yfinance download while suppressing its noisy failed-ticker output."""
    with open(os.devnull, "w") as devnull:
        with contextlib.redirect_stdout(devnull), contextlib.redirect_stderr(devnull):
            return yf.download(*args, **kwargs)


def _f(v: Any, digits: int = 2) -> float | None:
    """Convert numpy scalars to plain Python floats, return None for NaN."""
    if v is None:
        return None
    try:
        fv = float(v)
        return None if math.isnan(fv) else round(fv, digits)
    except (TypeError, ValueError):
        return None

# ── Interval map ─────────────────────────────────────────────────────────────
_INTERVAL_PERIOD: dict[str, str] = {
    "1m":  "1d",
    "5m":  "5d",
    "15m": "5d",
    "30m": "60d",
    "1h":  "60d",
    "1d":  "1y",
}

# Minimum usable candles per interval
_MIN_CANDLES: dict[str, int] = {
    "1m": 30, "5m": 20, "15m": 10, "30m": 8, "1h": 8, "1d": 20,
}

# Fallback interval chain when data is thin
_INTERVAL_FALLBACK: dict[str, str] = {
    "5m": "15m", "15m": "30m", "30m": "1h", "1h": "1h",
}

def _market_context() -> dict:
    """Return current IST time and whether NSE market is open."""
    now  = datetime.now()
    hour = now.hour + now.minute / 60
    # NSE: Mon–Fri 09:15–15:30 IST
    is_weekday = now.weekday() < 5
    is_open    = is_weekday and 9.25 <= hour <= 15.5
    if not is_weekday:
        session = "weekend"
    elif hour < 9.25:
        session = "pre-market"
    elif hour > 15.5:
        session = "post-market"
    else:
        session = "live"
    return {"session": session, "is_open": is_open,
            "time_ist": now.strftime("%H:%M IST")}

# ── Candle fetch ─────────────────────────────────────────────────────────────

def get_intraday_candles(
    symbol: str,
    interval: str = "15m",
    period: str | None = None,
) -> pd.DataFrame:
    """Fetch OHLCV candles from Yahoo Finance for an NSE stock.

    Tries NSE (.NS) first, then BSE (.BO) if NSE returns too few candles.
    If the requested interval is too granular, auto-upgrades to the next
    coarser interval.

    Returns DataFrame with DatetimeIndex and columns: Open, High, Low, Close, Volume.
    Empty DataFrame on error.
    """
    import yfinance as yf

    sym   = symbol.strip().upper()
    per   = period or _INTERVAL_PERIOD.get(interval, "5d")
    min_c = _MIN_CANDLES.get(interval, 10)

    def _fetch(ticker: str, ivl: str, prd: str) -> pd.DataFrame:
        try:
            df = _quiet_yf_download(
                yf,
                ticker,
                period=prd,
                interval=ivl,
                progress=False,
                auto_adjust=True,
                prepost=False,
            )
            if df.empty:
                return pd.DataFrame()
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df.index = pd.to_datetime(df.index)
            if df.index.tzinfo is not None:
                df.index = df.index.tz_convert("Asia/Kolkata").tz_localize(None)
            df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
            return df
        except Exception:
            return pd.DataFrame()

    # Try NSE first
    df = _fetch(f"{sym}.NS", interval, per)

    # BSE fallback if NSE thin
    if df.empty or len(df) < min_c:
        df_bse = _fetch(f"{sym}.BO", interval, per)
        if len(df_bse) > len(df):
            df = df_bse

    # Auto-upgrade interval if still insufficient
    fallback_ivl = _INTERVAL_FALLBACK.get(interval)
    if (df.empty or len(df) < min_c) and fallback_ivl:
        fallback_per = _INTERVAL_PERIOD.get(fallback_ivl, "60d")
        df2 = _fetch(f"{sym}.NS", fallback_ivl, fallback_per)
        if df2.empty or len(df2) < _MIN_CANDLES.get(fallback_ivl, 8):
            df2 = _fetch(f"{sym}.BO", fallback_ivl, fallback_per)
        if len(df2) >= _MIN_CANDLES.get(fallback_ivl, 8):
            df = df2  # return with upgraded interval noted in caller

    return df


def get_multi_candles(
    symbols: list[str],
    interval: str = "15m",
    period: str | None = None,
) -> dict[str, pd.DataFrame]:
    """Fetch candles for multiple symbols. Returns {symbol: DataFrame}."""
    return {sym: get_intraday_candles(sym, interval, period) for sym in symbols}


# ── Indicator library ─────────────────────────────────────────────────────────

def _ema(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(span=n, adjust=False).mean()


def compute_macd(
    df: pd.DataFrame,
    fast: int = 12, slow: int = 26, signal: int = 9,
) -> pd.DataFrame:
    """Add MACD, MACD_signal, MACD_hist columns."""
    close = df["Close"]
    fast_ema   = _ema(close, fast)
    slow_ema   = _ema(close, slow)
    macd_line  = fast_ema - slow_ema
    signal_line = _ema(macd_line, signal)
    df = df.copy()
    df["MACD"]        = macd_line
    df["MACD_signal"] = signal_line
    df["MACD_hist"]   = macd_line - signal_line
    return df


def compute_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Add RSI column."""
    delta = df["Close"].diff()
    gain  = delta.clip(lower=0)
    loss  = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, adjust=False).mean()
    rs  = avg_gain / avg_loss.replace(0, np.nan)
    df  = df.copy()
    df["RSI"] = 100 - (100 / (1 + rs))
    return df


def compute_supertrend(
    df: pd.DataFrame, period: int = 10, multiplier: float = 3.0,
) -> pd.DataFrame:
    """Add Supertrend, Supertrend_dir (1=bull, -1=bear) columns."""
    hl2   = (df["High"] + df["Low"]) / 2
    tr    = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - df["Close"].shift()).abs(),
        (df["Low"]  - df["Close"].shift()).abs(),
    ], axis=1).max(axis=1)
    atr   = tr.ewm(com=period - 1, adjust=False).mean()
    upper = hl2 + multiplier * atr
    lower = hl2 - multiplier * atr

    st  = [0.0] * len(df)
    dir_= [1]   * len(df)

    for i in range(1, len(df)):
        if df["Close"].iloc[i] > upper.iloc[i - 1]:
            dir_[i] = 1
        elif df["Close"].iloc[i] < lower.iloc[i - 1]:
            dir_[i] = -1
        else:
            dir_[i] = dir_[i - 1]

        if dir_[i] == 1:
            st[i] = max(lower.iloc[i], st[i - 1]) if dir_[i - 1] == 1 else lower.iloc[i]
        else:
            st[i] = min(upper.iloc[i], st[i - 1]) if dir_[i - 1] == -1 else upper.iloc[i]

    df = df.copy()
    df["Supertrend"]     = st
    df["Supertrend_dir"] = dir_
    return df


def compute_bollinger(
    df: pd.DataFrame, period: int = 20, std_dev: float = 2.0,
) -> pd.DataFrame:
    """Add BB_upper, BB_mid, BB_lower, BB_width, BB_pct columns."""
    close   = df["Close"]
    mid     = close.rolling(period).mean()
    std     = close.rolling(period).std()
    df      = df.copy()
    df["BB_upper"] = mid + std_dev * std
    df["BB_mid"]   = mid
    df["BB_lower"] = mid - std_dev * std
    df["BB_width"] = (df["BB_upper"] - df["BB_lower"]) / mid
    df["BB_pct"]   = (close - df["BB_lower"]) / (df["BB_upper"] - df["BB_lower"])
    return df


def compute_ema_stack(df: pd.DataFrame) -> pd.DataFrame:
    """Add EMA9, EMA21, EMA50, EMA200 columns."""
    df = df.copy()
    for n in (9, 21, 50, 200):
        df[f"EMA{n}"] = _ema(df["Close"], n)
    return df


def compute_obv(df: pd.DataFrame) -> pd.DataFrame:
    """Add OBV (On-Balance Volume) column."""
    direction = np.sign(df["Close"].diff()).fillna(0)
    df = df.copy()
    df["OBV"] = (df["Volume"] * direction).cumsum()
    return df


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Add ATR (Average True Range) column."""
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - df["Close"].shift()).abs(),
        (df["Low"]  - df["Close"].shift()).abs(),
    ], axis=1).max(axis=1)
    df = df.copy()
    df["ATR"] = tr.ewm(com=period - 1, adjust=False).mean()
    return df


def compute_all(df: pd.DataFrame) -> pd.DataFrame:
    """Run all indicator computations on a single DataFrame."""
    df = compute_macd(df)
    df = compute_rsi(df)
    df = compute_supertrend(df)
    df = compute_bollinger(df)
    df = compute_ema_stack(df)
    df = compute_obv(df)
    df = compute_atr(df)
    return df


# ── Support / Resistance ──────────────────────────────────────────────────────

def pivot_levels(df: pd.DataFrame) -> dict[str, float]:
    """Compute classic pivot point levels from the previous session.

    Uses the last completed candle as 'previous day' for intraday timeframes.
    """
    if len(df) < 2:
        return {}
    prev  = df.iloc[-2]
    H, L, C = prev["High"], prev["Low"], prev["Close"]
    P  = (H + L + C) / 3
    R1 = 2 * P - L
    R2 = P + (H - L)
    R3 = H + 2 * (P - L)
    S1 = 2 * P - H
    S2 = P - (H - L)
    S3 = L - 2 * (H - P)
    return {
        "PP": round(P, 2),
        "R1": round(R1, 2), "R2": round(R2, 2), "R3": round(R3, 2),
        "S1": round(S1, 2), "S2": round(S2, 2), "S3": round(S3, 2),
    }


def swing_levels(df: pd.DataFrame, window: int = 5) -> dict[str, list[float]]:
    """Find recent swing high and low levels using a rolling window."""
    highs = df["High"]
    lows  = df["Low"]

    sw_highs = highs[
        (highs == highs.rolling(window, center=True).max()) &
        (highs.shift(1) < highs) & (highs.shift(-1) < highs)
    ].tail(5).round(2).tolist()

    sw_lows = lows[
        (lows == lows.rolling(window, center=True).min()) &
        (lows.shift(1) > lows) & (lows.shift(-1) > lows)
    ].tail(5).round(2).tolist()

    return {"swing_highs": sorted(sw_highs, reverse=True),
            "swing_lows":  sorted(sw_lows)}


def key_levels(df: pd.DataFrame) -> dict[str, Any]:
    """Combine pivot points, swing levels, and EMA levels into key S/R levels."""
    pivots  = pivot_levels(df)
    swings  = swing_levels(df)
    close   = df["Close"].iloc[-1]
    ema9    = _ema(df["Close"], 9).iloc[-1]
    ema21   = _ema(df["Close"], 21).iloc[-1]
    ema50   = _ema(df["Close"], 50).iloc[-1]
    ema200  = _ema(df["Close"], 200).iloc[-1]

    resistances = sorted(set(
        [v for k, v in pivots.items() if k.startswith("R") and v > close] +
        [h for h in swings["swing_highs"] if h > close] +
        [round(e, 2) for e in [ema9, ema21, ema50, ema200] if e > close]
    ))

    supports = sorted(set(
        [v for k, v in pivots.items() if k.startswith("S") and v < close] +
        [l for l in swings["swing_lows"] if l < close] +
        [round(e, 2) for e in [ema9, ema21, ema50, ema200] if e < close]
    ), reverse=True)

    return {
        "close":       round(close, 2),
        "pivot":       pivots.get("PP"),
        "resistances": resistances[:4],
        "supports":    supports[:4],
        "ema9":        round(ema9,   2),
        "ema21":       round(ema21,  2),
        "ema50":       round(ema50,  2),
        "ema200":      round(ema200, 2),
        "pivot_levels": pivots,
    }


# ── Signal generators ─────────────────────────────────────────────────────────

def _rr(entry: float, target: float, sl: float) -> float:
    """Risk:Reward ratio."""
    risk   = abs(entry - sl)
    reward = abs(target - entry)
    return round(reward / risk, 2) if risk > 0 else 0


def signal_macd(df: pd.DataFrame) -> dict | None:
    """MACD crossover signal on the latest completed candle.

    BUY : MACD crosses above signal line + histogram positive + above EMA21
    SELL: MACD crosses below signal line + histogram negative + below EMA21
    """
    if len(df) < 30:
        return None
    df = compute_macd(compute_ema_stack(compute_atr(df)))
    last  = df.iloc[-1]
    prev  = df.iloc[-2]
    close = last["Close"]
    atr   = last["ATR"]

    cross_up   = prev["MACD"] < prev["MACD_signal"] and last["MACD"] > last["MACD_signal"]
    cross_down = prev["MACD"] > prev["MACD_signal"] and last["MACD"] < last["MACD_signal"]
    hist_pos   = last["MACD_hist"] > 0
    hist_neg   = last["MACD_hist"] < 0
    above_ema21 = close > last["EMA21"]

    if cross_up and hist_pos:
        entry  = round(close, 2)
        sl     = round(close - 1.5 * atr, 2)
        target = round(close + 2.5 * atr, 2)
        return {
            "strategy":  "MACD Crossover",
            "direction": "BUY",
            "entry":     entry,
            "target":    target,
            "stoploss":  sl,
            "rr":        _rr(entry, target, sl),
            "strength":  "Strong" if above_ema21 else "Moderate",
            "note":      "MACD bullish crossover" + (" above EMA21" if above_ema21 else ""),
            "indicator": {"macd": round(last["MACD"], 4), "signal": round(last["MACD_signal"], 4),
                          "hist": round(last["MACD_hist"], 4)},
        }
    if cross_down and hist_neg:
        entry  = round(close, 2)
        sl     = round(close + 1.5 * atr, 2)
        target = round(close - 2.5 * atr, 2)
        return {
            "strategy":  "MACD Crossover",
            "direction": "SELL",
            "entry":     entry,
            "target":    target,
            "stoploss":  sl,
            "rr":        _rr(entry, target, sl),
            "strength":  "Strong" if not above_ema21 else "Moderate",
            "note":      "MACD bearish crossover" + (" below EMA21" if not above_ema21 else ""),
            "indicator": {"macd": round(last["MACD"], 4), "signal": round(last["MACD_signal"], 4),
                          "hist": round(last["MACD_hist"], 4)},
        }
    return None


def signal_rsi(df: pd.DataFrame) -> dict | None:
    """RSI extreme reversal signal.

    BUY : RSI crosses above 30 (from oversold) — potential bounce
    SELL: RSI crosses below 70 (from overbought) — potential reversal
    Also flags RSI divergence if detectable.
    """
    if len(df) < 20:
        return None
    df    = compute_rsi(compute_atr(compute_ema_stack(df)))
    last  = df.iloc[-1]
    prev  = df.iloc[-2]
    close = last["Close"]
    atr   = last["ATR"]
    rsi   = last["RSI"]

    cross_above_30 = prev["RSI"] < 30 and last["RSI"] >= 30
    cross_below_70 = prev["RSI"] > 70 and last["RSI"] <= 70
    deep_oversold  = rsi < 25
    deep_overbought = rsi > 75

    if cross_above_30 or deep_oversold:
        entry  = round(close, 2)
        sl     = round(close - 1.5 * atr, 2)
        target = round(close + 2.0 * atr, 2)
        return {
            "strategy":  "RSI Reversal",
            "direction": "BUY",
            "entry":     entry,
            "target":    target,
            "stoploss":  sl,
            "rr":        _rr(entry, target, sl),
            "strength":  "Strong" if cross_above_30 else "Moderate (deeply oversold)",
            "note":      f"RSI={round(rsi,1)} — {'crossing above 30' if cross_above_30 else 'deeply oversold'}",
            "indicator": {"rsi": round(rsi, 1)},
        }
    if cross_below_70 or deep_overbought:
        entry  = round(close, 2)
        sl     = round(close + 1.5 * atr, 2)
        target = round(close - 2.0 * atr, 2)
        return {
            "strategy":  "RSI Reversal",
            "direction": "SELL",
            "entry":     entry,
            "target":    target,
            "stoploss":  sl,
            "rr":        _rr(entry, target, sl),
            "strength":  "Strong" if cross_below_70 else "Moderate (deeply overbought)",
            "note":      f"RSI={round(rsi,1)} — {'crossing below 70' if cross_below_70 else 'deeply overbought'}",
            "indicator": {"rsi": round(rsi, 1)},
        }
    return None


def signal_supertrend(df: pd.DataFrame) -> dict | None:
    """Supertrend direction change signal.

    BUY : Price crosses above Supertrend (direction flips to bullish)
    SELL: Price crosses below Supertrend (direction flips to bearish)
    """
    if len(df) < 15:
        return None
    df    = compute_supertrend(compute_atr(df))
    last  = df.iloc[-1]
    prev  = df.iloc[-2]
    close = last["Close"]
    atr   = last["ATR"]

    flip_bull = prev["Supertrend_dir"] == -1 and last["Supertrend_dir"] == 1
    flip_bear = prev["Supertrend_dir"] ==  1 and last["Supertrend_dir"] == -1
    bull_trend = last["Supertrend_dir"] == 1
    bear_trend = last["Supertrend_dir"] == -1

    if flip_bull:
        entry  = round(close, 2)
        sl     = round(last["Supertrend"] - 0.5 * atr, 2)
        target = round(close + 2.5 * atr, 2)
        return {
            "strategy":  "Supertrend",
            "direction": "BUY",
            "entry":     entry,
            "target":    target,
            "stoploss":  sl,
            "rr":        _rr(entry, target, sl),
            "strength":  "Strong",
            "note":      f"Price crossed above Supertrend ({round(last['Supertrend'],2)})",
            "indicator": {"supertrend": round(last["Supertrend"], 2), "direction": "BULLISH"},
        }
    if flip_bear:
        entry  = round(close, 2)
        sl     = round(last["Supertrend"] + 0.5 * atr, 2)
        target = round(close - 2.5 * atr, 2)
        return {
            "strategy":  "Supertrend",
            "direction": "SELL",
            "entry":     entry,
            "target":    target,
            "stoploss":  sl,
            "rr":        _rr(entry, target, sl),
            "strength":  "Strong",
            "note":      f"Price crossed below Supertrend ({round(last['Supertrend'],2)})",
            "indicator": {"supertrend": round(last["Supertrend"], 2), "direction": "BEARISH"},
        }
    # Continuation signal (already in trend)
    if bull_trend:
        st_val = round(last["Supertrend"], 2)
        entry  = round(close, 2)
        # SL: use supertrend if below close by at least 0.5×ATR; else use ATR buffer
        st_sl  = st_val if (close - st_val) >= 0.5 * atr else round(close - 1.5 * atr, 2)
        sl     = round(min(st_sl, close - 0.5 * atr), 2)
        target = round(close + 2.0 * atr, 2)
        if sl >= entry:
            return None
        return {
            "strategy":  "Supertrend",
            "direction": "BUY",
            "entry":     entry,
            "target":    target,
            "stoploss":  sl,
            "rr":        _rr(entry, target, sl),
            "strength":  "Moderate (in uptrend)",
            "note":      f"Supertrend bullish — support at {st_val}",
            "indicator": {"supertrend": st_val, "direction": "BULLISH"},
        }
    if bear_trend:
        st_val = round(last["Supertrend"], 2)
        entry  = round(close, 2)
        # SL: use supertrend if above close by at least 0.5×ATR; else use ATR buffer
        st_sl  = st_val if (st_val - close) >= 0.5 * atr else round(close + 1.5 * atr, 2)
        sl     = round(max(st_sl, close + 0.5 * atr), 2)
        target = round(close - 2.0 * atr, 2)
        if sl <= entry:
            return None
        return {
            "strategy":  "Supertrend",
            "direction": "SELL",
            "entry":     entry,
            "target":    target,
            "stoploss":  sl,
            "rr":        _rr(entry, target, sl),
            "strength":  "Moderate (in downtrend)",
            "note":      f"Supertrend bearish — resistance at {st_val}",
            "indicator": {"supertrend": st_val, "direction": "BEARISH"},
        }
    return None


def signal_bollinger(df: pd.DataFrame) -> dict | None:
    """Bollinger Band squeeze and bounce signals.

    BUY : Price touches/bounces off lower band + BB_pct < 0.2 + RSI < 50
    SELL: Price touches/bounces off upper band + BB_pct > 0.8 + RSI > 50
    Squeeze: BB_width in bottom 20% of recent range → breakout pending.
    """
    if len(df) < 25:
        return None
    df    = compute_bollinger(compute_rsi(compute_atr(df)))
    last  = df.iloc[-1]
    prev  = df.iloc[-2]
    close = last["Close"]
    atr   = last["ATR"]
    pct   = last["BB_pct"]
    rsi   = last["RSI"]
    width = last["BB_width"]
    avg_width = df["BB_width"].rolling(20).mean().iloc[-1]

    squeeze    = width < 0.6 * avg_width if not pd.isna(avg_width) else False
    lower_touch = prev["Close"] <= prev["BB_lower"] * 1.005
    upper_touch = prev["Close"] >= prev["BB_upper"] * 0.995
    bounce_up   = lower_touch and close > prev["BB_lower"]
    bounce_down = upper_touch and close < prev["BB_upper"]

    if bounce_up and pct < 0.35 and rsi < 55:
        entry  = round(close, 2)
        sl     = round(last["BB_lower"] - 0.3 * atr, 2)
        target = round(last["BB_mid"], 2)
        return {
            "strategy":  "Bollinger Band Bounce",
            "direction": "BUY",
            "entry":     entry,
            "target":    target,
            "stoploss":  sl,
            "rr":        _rr(entry, target, sl),
            "strength":  "Strong" if squeeze else "Moderate",
            "note":      ("BB lower-band bounce" + (" in squeeze — breakout imminent" if squeeze else "")),
            "indicator": {"bb_pct": round(pct, 2), "bb_width": round(width, 4), "rsi": round(rsi, 1)},
        }
    if bounce_down and pct > 0.65 and rsi > 45:
        entry  = round(close, 2)
        sl     = round(last["BB_upper"] + 0.3 * atr, 2)
        target = round(last["BB_mid"], 2)
        return {
            "strategy":  "Bollinger Band Bounce",
            "direction": "SELL",
            "entry":     entry,
            "target":    target,
            "stoploss":  sl,
            "rr":        _rr(entry, target, sl),
            "strength":  "Strong" if squeeze else "Moderate",
            "note":      "BB upper-band rejection" + (" in squeeze" if squeeze else ""),
            "indicator": {"bb_pct": round(pct, 2), "bb_width": round(width, 4), "rsi": round(rsi, 1)},
        }
    if squeeze:
        return {
            "strategy":  "Bollinger Squeeze",
            "direction": "WATCH",
            "entry":     round(close, 2),
            "target":    None,
            "stoploss":  None,
            "rr":        None,
            "strength":  "Alert",
            "note":      f"BB squeeze — volatility contraction, breakout pending. Width={round(width,4)}",
            "indicator": {"bb_pct": round(pct, 2), "bb_width": round(width, 4)},
        }
    return None


def signal_ema_crossover(df: pd.DataFrame) -> dict | None:
    """EMA 9/21 crossover signal (Golden/Death cross on intraday).

    BUY : EMA9 crosses above EMA21 with price above EMA50
    SELL: EMA9 crosses below EMA21 with price below EMA50
    """
    if len(df) < 55:
        return None
    df    = compute_ema_stack(compute_atr(df))
    last  = df.iloc[-1]
    prev  = df.iloc[-2]
    close = last["Close"]
    atr   = last["ATR"]

    cross_up   = prev["EMA9"] < prev["EMA21"] and last["EMA9"] > last["EMA21"]
    cross_down = prev["EMA9"] > prev["EMA21"] and last["EMA9"] < last["EMA21"]

    if cross_up and close > last["EMA50"]:
        entry  = round(close, 2)
        sl     = round(last["EMA21"] - 0.5 * atr, 2)
        target = round(close + 2.0 * atr, 2)
        return {
            "strategy":  "EMA Crossover (9/21)",
            "direction": "BUY",
            "entry":     entry,
            "target":    target,
            "stoploss":  sl,
            "rr":        _rr(entry, target, sl),
            "strength":  "Strong",
            "note":      f"EMA9 crossed above EMA21. Price above EMA50={round(last['EMA50'],2)}",
            "indicator": {"ema9": round(last["EMA9"],2), "ema21": round(last["EMA21"],2),
                          "ema50": round(last["EMA50"],2)},
        }
    if cross_down and close < last["EMA50"]:
        entry  = round(close, 2)
        sl     = round(last["EMA21"] + 0.5 * atr, 2)
        target = round(close - 2.0 * atr, 2)
        return {
            "strategy":  "EMA Crossover (9/21)",
            "direction": "SELL",
            "entry":     entry,
            "target":    target,
            "stoploss":  sl,
            "rr":        _rr(entry, target, sl),
            "strength":  "Strong",
            "note":      f"EMA9 crossed below EMA21. Price below EMA50={round(last['EMA50'],2)}",
            "indicator": {"ema9": round(last["EMA9"],2), "ema21": round(last["EMA21"],2),
                          "ema50": round(last["EMA50"],2)},
        }
    return None


def signal_vcp(df: pd.DataFrame, lookback: int = 20) -> dict | None:
    """VCP (Volatility Contraction Pattern) detection.

    Looks for:
    1. Prior uptrend (price above EMA50)
    2. Series of contracting price swings (each high-to-low range < previous)
    3. Declining volume during contraction
    4. Current price near pivot (within 3% of last swing high)
    """
    if len(df) < lookback + 10:
        return None

    df   = compute_ema_stack(compute_atr(df))
    last = df.iloc[-1]
    close = last["Close"]
    atr  = last["ATR"]

    # Require prior uptrend
    in_uptrend = close > last["EMA50"]
    if not in_uptrend:
        return None

    # Measure last 3 range contractions (using rolling windows)
    recent = df.tail(lookback)
    n      = len(recent)
    thirds = n // 3
    if thirds < 3:
        return None

    seg1 = recent.iloc[:thirds]
    seg2 = recent.iloc[thirds:2*thirds]
    seg3 = recent.iloc[2*thirds:]

    range1 = (seg1["High"].max() - seg1["Low"].min()) / seg1["Close"].mean()
    range2 = (seg2["High"].max() - seg2["Low"].min()) / seg2["Close"].mean()
    range3 = (seg3["High"].max() - seg3["Low"].min()) / seg3["Close"].mean()

    contracting = range1 > range2 > range3

    # Volume declining during contraction
    vol1 = seg1["Volume"].mean()
    vol3 = seg3["Volume"].mean()
    vol_declining = vol3 < vol1

    # Near pivot (within 5% of recent high)
    recent_high = recent["High"].max()
    near_pivot  = close >= recent_high * 0.95

    score = sum([contracting, vol_declining, near_pivot, in_uptrend])
    if score < 3:
        return None

    entry  = round(recent_high * 1.01, 2)   # buy on breakout above pivot
    sl     = round(recent["Low"].min(), 2)
    target = round(entry + 2.5 * atr, 2)

    return {
        "strategy":  "VCP (Volatility Contraction Pattern)",
        "direction": "BUY",
        "entry":     entry,
        "target":    target,
        "stoploss":  sl,
        "rr":        _rr(entry, target, sl),
        "strength":  "Strong" if score == 4 else "Moderate",
        "note":      (
            f"VCP detected — contracting range ({round(range1,3)}→{round(range3,3)})"
            f", {'volume declining' if vol_declining else ''}"
            f", pivot at {round(recent_high,2)}"
        ),
        "indicator": {
            "range_contraction": contracting,
            "vol_declining":     vol_declining,
            "near_pivot":        near_pivot,
            "pivot_high":        round(recent_high, 2),
        },
    }


def signal_volume_spike(df: pd.DataFrame) -> dict | None:
    """Volume spike with price confirmation.

    BUY : Volume > 2× 20-period average AND price up > 1% from open
    SELL: Volume > 2× 20-period average AND price down > 1% from open
    """
    if len(df) < 22:
        return None
    df   = compute_atr(compute_ema_stack(df))
    last = df.iloc[-1]
    close = last["Close"]
    open_ = last["Open"]
    atr   = last["ATR"]
    vol   = last["Volume"]
    avg_vol = df["Volume"].rolling(20).mean().iloc[-1]

    if pd.isna(avg_vol) or avg_vol == 0:
        return None

    vol_ratio   = vol / avg_vol
    price_move  = (close - open_) / open_ * 100

    if vol_ratio >= 2.0 and price_move > 0.8:
        entry  = round(close, 2)
        sl     = round(close - 1.5 * atr, 2)
        target = round(close + 2.0 * atr, 2)
        return {
            "strategy":  "Volume Spike",
            "direction": "BUY",
            "entry":     entry,
            "target":    target,
            "stoploss":  sl,
            "rr":        _rr(entry, target, sl),
            "strength":  "Strong" if vol_ratio > 3 else "Moderate",
            "note":      f"Volume spike {round(vol_ratio,1)}× average, price +{round(price_move,1)}%",
            "indicator": {"vol_ratio": round(vol_ratio,1), "price_move_pct": round(price_move,1)},
        }
    if vol_ratio >= 2.0 and price_move < -0.8:
        entry  = round(close, 2)
        sl     = round(close + 1.5 * atr, 2)
        target = round(close - 2.0 * atr, 2)
        return {
            "strategy":  "Volume Spike",
            "direction": "SELL",
            "entry":     entry,
            "target":    target,
            "stoploss":  sl,
            "rr":        _rr(entry, target, sl),
            "strength":  "Strong" if vol_ratio > 3 else "Moderate",
            "note":      f"Volume spike {round(vol_ratio,1)}× average, price {round(price_move,1)}%",
            "indicator": {"vol_ratio": round(vol_ratio,1), "price_move_pct": round(price_move,1)},
        }
    return None



# ── New signal generators ──────────────────────────────────────────────────────

def signal_orb(df: pd.DataFrame, orb_bars: int = 3) -> dict | None:
    """Opening Range Breakout (ORB).

    Identifies when price breaks above/below the first N-bar range with volume.
    BUY : Close > ORB high AND volume confirms (≥ 1.5× average)
    SELL: Close < ORB low  AND volume confirms
    """
    if len(df) < orb_bars + 5:
        return None
    df   = compute_atr(compute_ema_stack(df))
    last = df.iloc[-1]
    atr  = last["ATR"]
    close = last["Close"]

    orb_high = df.iloc[:orb_bars]["High"].max()
    orb_low  = df.iloc[:orb_bars]["Low"].min()
    avg_vol  = df["Volume"].rolling(20).mean().iloc[-1]
    vol_ok   = (not pd.isna(avg_vol)) and last["Volume"] >= 1.5 * avg_vol

    if close > orb_high and vol_ok:
        sl     = round(orb_high - 0.5 * atr, 2)
        target = round(close + 2.0 * (close - sl), 2)
        return {
            "strategy":  "ORB Breakout",
            "direction": "BUY",
            "entry":     round(close, 2),
            "target":    target,
            "stoploss":  sl,
            "rr":        _rr(close, target, sl),
            "strength":  "Strong" if close > orb_high * 1.003 else "Moderate",
            "note":      f"Price broke above ORB high {round(orb_high,2)} with volume",
            "indicator": {"orb_high": round(orb_high,2), "orb_low": round(orb_low,2)},
        }
    if close < orb_low and vol_ok:
        sl     = round(orb_low + 0.5 * atr, 2)
        target = round(close - 2.0 * (sl - close), 2)
        return {
            "strategy":  "ORB Breakdown",
            "direction": "SELL",
            "entry":     round(close, 2),
            "target":    target,
            "stoploss":  sl,
            "rr":        _rr(close, target, sl),
            "strength":  "Strong" if close < orb_low * 0.997 else "Moderate",
            "note":      f"Price broke below ORB low {round(orb_low,2)} with volume",
            "indicator": {"orb_high": round(orb_high,2), "orb_low": round(orb_low,2)},
        }
    return None


def signal_gap(df: pd.DataFrame) -> dict | None:
    """Gap and Go continuation play.

    BUY : Gap up > 0.5% from prior close AND first candle bullish AND MACD positive
    SELL: Gap down > 0.5% AND first candle bearish AND MACD negative
    """
    if len(df) < 30:
        return None
    df    = compute_macd(compute_ema_stack(compute_atr(df)))
    last  = df.iloc[-1]
    prev  = df.iloc[-2]
    close = last["Close"]
    atr   = last["ATR"]

    # Gap = today's open vs prior candle's close
    gap_pct = (df.iloc[0]["Open"] - prev["Close"]) / prev["Close"] * 100

    first_bull = df.iloc[0]["Close"] > df.iloc[0]["Open"]
    first_bear = df.iloc[0]["Close"] < df.iloc[0]["Open"]

    if gap_pct > 0.5 and first_bull and last["MACD_hist"] > 0:
        entry  = round(close, 2)
        sl     = round(close - 1.5 * atr, 2)
        target = round(close + 2.5 * atr, 2)
        return {
            "strategy":  "Gap and Go",
            "direction": "BUY",
            "entry":     entry,
            "target":    target,
            "stoploss":  sl,
            "rr":        _rr(entry, target, sl),
            "strength":  "Strong" if gap_pct > 1.0 else "Moderate",
            "note":      f"Gap up +{round(gap_pct,1)}%, bullish continuation + MACD positive",
            "indicator": {"gap_pct": round(gap_pct,2)},
        }
    if gap_pct < -0.5 and first_bear and last["MACD_hist"] < 0:
        entry  = round(close, 2)
        sl     = round(close + 1.5 * atr, 2)
        target = round(close - 2.5 * atr, 2)
        return {
            "strategy":  "Gap and Go",
            "direction": "SELL",
            "entry":     entry,
            "target":    target,
            "stoploss":  sl,
            "rr":        _rr(entry, target, sl),
            "strength":  "Strong" if gap_pct < -1.0 else "Moderate",
            "note":      f"Gap down {round(gap_pct,1)}%, bearish continuation + MACD negative",
            "indicator": {"gap_pct": round(gap_pct,2)},
        }
    return None


def signal_vwap(df: pd.DataFrame) -> dict | None:
    """VWAP reclaim / loss signal using EMA9 as VWAP proxy.

    BUY : Price crosses above EMA9 (VWAP proxy) with RSI 40–65 range
    SELL: Price crosses below EMA9 with RSI 35–60 range
    Also checks EMA21 alignment for trend filter.
    """
    if len(df) < 25:
        return None
    df    = compute_rsi(compute_ema_stack(compute_atr(df)))
    last  = df.iloc[-1]
    prev  = df.iloc[-2]
    close = last["Close"]
    atr   = last["ATR"]
    rsi   = last["RSI"]
    vwap  = last["EMA9"]   # proxy

    cross_above = prev["Close"] < prev["EMA9"] and close > vwap
    cross_below = prev["Close"] > prev["EMA9"] and close < vwap

    if cross_above and 38 <= rsi <= 68 and close > last["EMA21"]:
        entry  = round(close, 2)
        sl     = round(vwap - 0.5 * atr, 2)
        target = round(close + 2.0 * (close - sl), 2)
        return {
            "strategy":  "VWAP Reclaim",
            "direction": "BUY",
            "entry":     entry,
            "target":    target,
            "stoploss":  sl,
            "rr":        _rr(entry, target, sl),
            "strength":  "Strong" if close > last["EMA21"] * 1.002 else "Moderate",
            "note":      f"Price reclaimed VWAP proxy {round(vwap,2)}, RSI={round(rsi,1)}",
            "indicator": {"vwap_proxy": round(vwap,2), "rsi": round(rsi,1)},
        }
    if cross_below and 32 <= rsi <= 62 and close < last["EMA21"]:
        entry  = round(close, 2)
        sl     = round(vwap + 0.5 * atr, 2)
        target = round(close - 2.0 * (sl - close), 2)
        return {
            "strategy":  "VWAP Loss",
            "direction": "SELL",
            "entry":     entry,
            "target":    target,
            "stoploss":  sl,
            "rr":        _rr(entry, target, sl),
            "strength":  "Strong" if close < last["EMA21"] * 0.998 else "Moderate",
            "note":      f"Price lost VWAP proxy {round(vwap,2)}, RSI={round(rsi,1)}",
            "indicator": {"vwap_proxy": round(vwap,2), "rsi": round(rsi,1)},
        }
    return None


def signal_engulfing(df: pd.DataFrame) -> dict | None:
    """Bullish/Bearish Engulfing candlestick pattern.

    BUY : Bullish engulfing (small red candle followed by larger green that covers it)
          at or near a support level (EMA21 or recent swing low)
    SELL: Bearish engulfing (small green → larger red) near resistance
    """
    if len(df) < 25:
        return None
    df   = compute_rsi(compute_ema_stack(compute_atr(df)))
    last = df.iloc[-1]
    prev = df.iloc[-2]
    atr  = last["ATR"]
    close = last["Close"]

    last_bull = last["Close"] > last["Open"]
    last_bear = last["Close"] < last["Open"]
    prev_bull = prev["Close"] > prev["Open"]
    prev_bear = prev["Close"] < prev["Open"]

    last_body = abs(last["Close"] - last["Open"])
    prev_body = abs(prev["Close"] - prev["Open"])

    bull_engulf = (last_bull and prev_bear and
                   last["Open"] <= prev["Close"] and
                   last["Close"] >= prev["Open"] and
                   last_body > prev_body * 1.1)
    bear_engulf = (last_bear and prev_bull and
                   last["Open"] >= prev["Close"] and
                   last["Close"] <= prev["Open"] and
                   last_body > prev_body * 1.1)

    rsi = last["RSI"]

    if bull_engulf and close > last["EMA21"] * 0.995 and rsi < 65:
        entry  = round(close, 2)
        sl     = round(prev["Low"] - 0.2 * atr, 2)
        target = round(close + 2.5 * (close - sl), 2)
        return {
            "strategy":  "Bullish Engulfing",
            "direction": "BUY",
            "entry":     entry,
            "target":    target,
            "stoploss":  sl,
            "rr":        _rr(entry, target, sl),
            "strength":  "Strong" if rsi < 50 else "Moderate",
            "note":      f"Bullish engulfing near EMA21={round(last['EMA21'],2)}, RSI={round(rsi,1)}",
            "indicator": {"rsi": round(rsi,1), "candle_ratio": round(last_body/max(prev_body,0.01),2)},
        }
    if bear_engulf and close < last["EMA21"] * 1.005 and rsi > 35:
        entry  = round(close, 2)
        sl     = round(prev["High"] + 0.2 * atr, 2)
        target = round(close - 2.5 * (sl - close), 2)
        return {
            "strategy":  "Bearish Engulfing",
            "direction": "SELL",
            "entry":     entry,
            "target":    target,
            "stoploss":  sl,
            "rr":        _rr(entry, target, sl),
            "strength":  "Strong" if rsi > 50 else "Moderate",
            "note":      f"Bearish engulfing near EMA21={round(last['EMA21'],2)}, RSI={round(rsi,1)}",
            "indicator": {"rsi": round(rsi,1), "candle_ratio": round(last_body/max(prev_body,0.01),2)},
        }
    return None


def signal_ema_ribbon(df: pd.DataFrame) -> dict | None:
    """EMA Ribbon alignment — all fast EMAs aligned in same direction.

    BUY : EMA9 > EMA21 > EMA50 all stacked (perfect bull ribbon) + price above all
    SELL: EMA9 < EMA21 < EMA50 all stacked (perfect bear ribbon) + price below all
    Also requires RSI in momentum zone (50–75 BUY, 25–50 SELL).
    """
    if len(df) < 55:
        return None
    df   = compute_rsi(compute_ema_stack(compute_atr(df)))
    last = df.iloc[-1]
    prev = df.iloc[-2]
    close = last["Close"]
    atr   = last["ATR"]
    rsi   = last["RSI"]

    bull_ribbon = last["EMA9"] > last["EMA21"] > last["EMA50"] and close > last["EMA9"]
    bear_ribbon = last["EMA9"] < last["EMA21"] < last["EMA50"] and close < last["EMA9"]

    # Ribbon just aligned (wasn't aligned last bar)
    prev_bull = prev["EMA9"] > prev["EMA21"] > prev["EMA50"]
    prev_bear = prev["EMA9"] < prev["EMA21"] < prev["EMA50"]

    if bull_ribbon and not prev_bull and 48 <= rsi <= 78:
        entry  = round(close, 2)
        sl     = round(last["EMA21"] - 0.3 * atr, 2)
        target = round(close + 2.5 * (close - sl), 2)
        return {
            "strategy":  "EMA Ribbon Bull",
            "direction": "BUY",
            "entry":     entry,
            "target":    target,
            "stoploss":  sl,
            "rr":        _rr(entry, target, sl),
            "strength":  "High",
            "note":      f"EMA 9/21/50 just stacked bullish. RSI={round(rsi,1)}",
            "indicator": {"ema9": round(last["EMA9"],2), "ema21": round(last["EMA21"],2),
                          "ema50": round(last["EMA50"],2), "rsi": round(rsi,1)},
        }
    if bear_ribbon and not prev_bear and 22 <= rsi <= 52:
        entry  = round(close, 2)
        sl     = round(last["EMA21"] + 0.3 * atr, 2)
        target = round(close - 2.5 * (sl - close), 2)
        return {
            "strategy":  "EMA Ribbon Bear",
            "direction": "SELL",
            "entry":     entry,
            "target":    target,
            "stoploss":  sl,
            "rr":        _rr(entry, target, sl),
            "strength":  "High",
            "note":      f"EMA 9/21/50 just stacked bearish. RSI={round(rsi,1)}",
            "indicator": {"ema9": round(last["EMA9"],2), "ema21": round(last["EMA21"],2),
                          "ema50": round(last["EMA50"],2), "rsi": round(rsi,1)},
        }
    return None


def signal_multi_confirm(df: pd.DataFrame) -> dict | None:
    """Multi-indicator confluence — requires 3+ indicators agreeing on direction.

    BUY : MACD bull + EMA cross bull + RSI 45–68 + Volume above average
          → High-confidence entry; all four signals aligned
    SELL: MACD bear + EMA cross bear + RSI 32–55 + Volume above average
    """
    if len(df) < 55:
        return None
    df   = compute_rsi(compute_macd(compute_ema_stack(compute_atr(df))))
    last = df.iloc[-1]
    prev = df.iloc[-2]
    close = last["Close"]
    atr   = last["ATR"]
    rsi   = last["RSI"]

    avg_vol = df["Volume"].rolling(20).mean().iloc[-1]
    vol_ok  = (not pd.isna(avg_vol)) and last["Volume"] >= 1.2 * avg_vol

    macd_bull   = last["MACD"] > last["MACD_signal"] and last["MACD_hist"] > 0
    macd_bear   = last["MACD"] < last["MACD_signal"] and last["MACD_hist"] < 0
    ema_bull    = last["EMA9"] > last["EMA21"] and close > last["EMA21"]
    ema_bear    = last["EMA9"] < last["EMA21"] and close < last["EMA21"]
    rsi_bull    = 45 <= rsi <= 70
    rsi_bear    = 30 <= rsi <= 55

    bull_count = sum([macd_bull, ema_bull, rsi_bull, vol_ok])
    bear_count = sum([macd_bear, ema_bear, rsi_bear, vol_ok])

    if bull_count >= 3:
        entry  = round(close, 2)
        sl     = round(last["EMA21"] - 0.5 * atr, 2)
        target = round(close + 3.0 * (close - sl), 2)
        return {
            "strategy":  "Multi-Confirm BUY",
            "direction": "BUY",
            "entry":     entry,
            "target":    target,
            "stoploss":  sl,
            "rr":        _rr(entry, target, sl),
            "strength":  "High" if bull_count == 4 else "Strong",
            "note":      f"{bull_count}/4 signals aligned bullish: "
                         f"{'MACD ' if macd_bull else ''}{'EMA ' if ema_bull else ''}"
                         f"{'RSI ' if rsi_bull else ''}{'Vol' if vol_ok else ''}",
            "indicator": {"macd_bull": macd_bull, "ema_bull": ema_bull,
                          "rsi": round(rsi,1), "vol_above_avg": vol_ok},
        }
    if bear_count >= 3:
        entry  = round(close, 2)
        sl     = round(last["EMA21"] + 0.5 * atr, 2)
        target = round(close - 3.0 * (sl - close), 2)
        return {
            "strategy":  "Multi-Confirm SELL",
            "direction": "SELL",
            "entry":     entry,
            "target":    target,
            "stoploss":  sl,
            "rr":        _rr(entry, target, sl),
            "strength":  "High" if bear_count == 4 else "Strong",
            "note":      f"{bear_count}/4 signals aligned bearish: "
                         f"{'MACD ' if macd_bear else ''}{'EMA ' if ema_bear else ''}"
                         f"{'RSI ' if rsi_bear else ''}{'Vol' if vol_ok else ''}",
            "indicator": {"macd_bear": macd_bear, "ema_bear": ema_bear,
                          "rsi": round(rsi,1), "vol_above_avg": vol_ok},
        }
    return None


def signal_rsi_divergence(df: pd.DataFrame) -> dict | None:
    """RSI divergence — price and RSI disagree (hidden strength or weakness).

    Bullish divergence: Price making lower lows but RSI making higher lows
    Bearish divergence: Price making higher highs but RSI making lower highs
    Lookback: compare last 3 swing points
    """
    if len(df) < 30:
        return None
    df    = compute_rsi(compute_ema_stack(compute_atr(df)))
    closes = df["Close"].values
    rsis   = df["RSI"].values
    last   = df.iloc[-1]
    atr    = last["ATR"]
    close  = closes[-1]
    rsi    = rsis[-1]

    # Compare current bar vs 5 bars ago and 10 bars ago
    c5 = closes[-6]; r5 = rsis[-6]
    c10= closes[-11]; r10= rsis[-11]

    # Bullish divergence: price lower, RSI higher
    bull_div = close < c5 < c10 and rsi > r5 and rsi > r10
    # Bearish divergence: price higher, RSI lower
    bear_div = close > c5 > c10 and rsi < r5 and rsi < r10

    if bull_div and rsi < 50:
        entry  = round(close, 2)
        sl     = round(close - 2.0 * atr, 2)
        target = round(close + 3.0 * atr, 2)
        return {
            "strategy":  "RSI Bullish Divergence",
            "direction": "BUY",
            "entry":     entry,
            "target":    target,
            "stoploss":  sl,
            "rr":        _rr(entry, target, sl),
            "strength":  "High",
            "note":      f"Price making lower lows but RSI rising ({round(r10,1)}→{round(r5,1)}→{round(rsi,1)})",
            "indicator": {"rsi_trend": f"{round(r10,1)}→{round(r5,1)}→{round(rsi,1)}",
                          "price_trend": f"{round(c10,1)}→{round(c5,1)}→{round(close,1)}"},
        }
    if bear_div and rsi > 50:
        entry  = round(close, 2)
        sl     = round(close + 2.0 * atr, 2)
        target = round(close - 3.0 * atr, 2)
        return {
            "strategy":  "RSI Bearish Divergence",
            "direction": "SELL",
            "entry":     entry,
            "target":    target,
            "stoploss":  sl,
            "rr":        _rr(entry, target, sl),
            "strength":  "High",
            "note":      f"Price making higher highs but RSI falling ({round(r10,1)}→{round(r5,1)}→{round(rsi,1)})",
            "indicator": {"rsi_trend": f"{round(r10,1)}→{round(r5,1)}→{round(rsi,1)}",
                          "price_trend": f"{round(c10,1)}→{round(c5,1)}→{round(close,1)}"},
        }
    return None


# ── All-strategy signal runner ────────────────────────────────────────────────

_STRATEGIES = {
    "macd":           signal_macd,
    "rsi":            signal_rsi,
    "supertrend":     signal_supertrend,
    "bollinger":      signal_bollinger,
    "ema":            signal_ema_crossover,
    "vcp":            signal_vcp,
    "volume":         signal_volume_spike,
    # ── New strategies ──────────────────────────────────────────────────────
    "orb":            signal_orb,
    "gap":            signal_gap,
    "vwap":           signal_vwap,
    "engulfing":      signal_engulfing,
    "ema_ribbon":     signal_ema_ribbon,
    "multi_confirm":  signal_multi_confirm,
    "rsi_divergence": signal_rsi_divergence,
}


def run_all_signals(df: pd.DataFrame, strategies: list[str] | None = None) -> list[dict]:
    """Run all (or selected) signal generators on a DataFrame.

    Returns a list of signal dicts (one per triggering strategy).
    """
    fns = {k: v for k, v in _STRATEGIES.items()
           if strategies is None or k in strategies}
    signals = []
    for name, fn in fns.items():
        try:
            sig = fn(df.copy())
            if sig:
                sig["strategy_key"] = name
                signals.append(sig)
        except Exception:
            pass
    return signals


# ── Public tool functions ─────────────────────────────────────────────────────

def get_intraday_analysis(
    symbol: str,
    interval: str = "15m",
    strategies: list[str] | None = None,
) -> dict:
    """Deep intraday analysis of a single stock.

    Returns: signals (BUY/SELL with entry/target/SL/R:R), key S/R levels,
    current indicator readings, ATR, and trading context.

    Args:
        symbol:     NSE ticker, e.g. 'TCS'.
        interval:   '5m', '15m', '30m', '1h'.
        strategies: List of strategies to run; None = all.
    """
    ctx   = _market_context()
    sym   = symbol.strip().upper()
    df    = get_intraday_candles(sym, interval)

    # ── Insufficient data path ────────────────────────────────────────────
    if df.empty or len(df) < 10:
        reason = (
            "Market is pre-open — intraday candles not yet available for today."
            if ctx["session"] == "pre-market"
            else (
                "Post-market: using last session's candles is less reliable."
                if ctx["session"] == "post-market"
                else f"Symbol {sym} has insufficient intraday data on Yahoo Finance."
            )
        )
        # Try fetching daily candles as a fallback to at least show S/R
        df_daily = get_intraday_candles(sym, "1d")
        if not df_daily.empty and len(df_daily) >= 5:
            last_d  = df_daily.iloc[-1]
            prev_d  = df_daily.iloc[-2]
            hi_20   = _f(df_daily["High"].tail(20).max())
            lo_20   = _f(df_daily["Low"].tail(20).min())
            atr_eod = _f((df_daily["High"] - df_daily["Low"]).tail(14).mean())
            return {
                "symbol":      sym,
                "interval":    interval,
                "as_of":       ctx["time_ist"],
                "session":     ctx["session"],
                "data_source": "EOD daily candles (intraday unavailable)",
                "reason":      reason,
                "close":       _f(last_d["Close"]),
                "prev_close":  _f(prev_d["Close"]),
                "day_range":   f"{_f(last_d['Low'])} – {_f(last_d['High'])}",
                "atr_daily":   atr_eod,
                "approx_levels": {
                    "resistance_20d_high": hi_20,
                    "support_20d_low":     lo_20,
                    "prev_day_high":       _f(prev_d["High"]),
                    "prev_day_low":        _f(prev_d["Low"]),
                    "prev_day_close":      _f(prev_d["Close"]),
                    "approx_target":       _f(last_d["Close"] + atr_eod * 1.5) if atr_eod else None,
                    "approx_stoploss":     _f(last_d["Close"] - atr_eod) if atr_eod else None,
                },
                "note": "Use these daily levels for swing/positional context. Re-run after 09:30 IST for live intraday setup.",
                "signals": [], "buy_signals": [], "sell_signals": [], "watch_alerts": [],
            }
        return {
            "symbol": sym, "interval": interval,
            "session": ctx["session"], "reason": reason,
            "error": f"No data available for {sym}. {reason}",
        }

    df_ind = compute_all(df)
    last   = df_ind.iloc[-1]
    close  = last["Close"]
    atr    = last["ATR"] if not pd.isna(last["ATR"]) else 0

    signals    = run_all_signals(df_ind, strategies)
    kl         = key_levels(df_ind)
    buy_sigs   = [s for s in signals if s["direction"] == "BUY"]
    sell_sigs  = [s for s in signals if s["direction"] == "SELL"]
    watch_sigs = [s for s in signals if s["direction"] == "WATCH"]

    # Aggregate bias
    if len(buy_sigs) > len(sell_sigs):
        bias = "BULLISH"
    elif len(sell_sigs) > len(buy_sigs):
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"

    # Confluence: strategies that agree on direction
    confluence_buy  = [s["strategy"] for s in buy_sigs]
    confluence_sell = [s["strategy"] for s in sell_sigs]

    return {
        "symbol":       sym,
        "interval":     interval,
        "session":      ctx["session"],
        "as_of":        ctx["time_ist"],
        "close":        _f(close),
        "atr":          _f(atr),
        "pct_change":   _f((close - df["Close"].iloc[0]) / df["Close"].iloc[0] * 100),
        "bias":         bias,
        "signals":      signals,
        "buy_signals":  buy_sigs,
        "sell_signals": sell_sigs,
        "watch_alerts": watch_sigs,
        "confluence_buy":  confluence_buy,
        "confluence_sell": confluence_sell,
        "key_levels": {
            "close":       _f(kl["close"]),
            "pivot":       _f(kl.get("pivot")),
            "resistances": [_f(v) for v in kl.get("resistances", [])],
            "supports":    [_f(v) for v in kl.get("supports",    [])],
            "ema9":        _f(kl.get("ema9")),
            "ema21":       _f(kl.get("ema21")),
            "ema50":       _f(kl.get("ema50")),
            "ema200":      _f(kl.get("ema200")),
            "pivot_levels": {k: _f(v) for k, v in kl.get("pivot_levels", {}).items()},
        },
        "indicators": {
            "rsi":           _f(last["RSI"], 1),
            "macd":          _f(last["MACD"], 4),
            "macd_signal":   _f(last["MACD_signal"], 4),
            "macd_hist":     _f(last["MACD_hist"], 4),
            "supertrend":    _f(last["Supertrend"]),
            "supertrend_dir": int(last["Supertrend_dir"]),
            "ema9":          _f(last["EMA9"]),
            "ema21":         _f(last["EMA21"]),
            "ema50":         _f(last["EMA50"]),
            "ema200":        _f(last["EMA200"]),
            "bb_pct":        _f(last["BB_pct"]),
            "bb_width":      _f(last["BB_width"], 4),
            "atr":           _f(last["ATR"]),
        },
        "candles":  len(df),
        "source":   "Yahoo Finance (yfinance)",
    }


def run_intraday_screener(
    symbols: list[str],
    interval: str = "15m",
    strategies: list[str] | None = None,
    direction_filter: str = "all",
    min_rr: float = 1.5,
) -> dict:
    """Scan multiple stocks for intraday signals.

    Args:
        symbols:          List of NSE tickers to scan.
        interval:         Candle interval: '5m', '15m', '30m', '1h'.
        strategies:       Strategies to check; None = all.
        direction_filter: 'buy', 'sell', or 'all'.
        min_rr:           Minimum R:R ratio to include a signal (default 1.5).

    Returns dict with:
        buy_signals, sell_signals, watch_alerts — sorted by R:R
        summary stats
    """
    all_buy: list[dict]   = []
    all_sell: list[dict]  = []
    all_watch: list[dict] = []
    scanned = 0
    errors  = []

    for sym in symbols:
        df = get_intraday_candles(sym, interval)
        if df.empty or len(df) < 10:
            errors.append(sym)
            continue
        scanned += 1
        sigs = run_all_signals(df, strategies)
        for sig in sigs:
            sig["symbol"] = sym
            if sig["direction"] == "BUY"  and (sig.get("rr") or 0) >= min_rr:
                all_buy.append(sig)
            elif sig["direction"] == "SELL" and (sig.get("rr") or 0) >= min_rr:
                all_sell.append(sig)
            elif sig["direction"] == "WATCH":
                all_watch.append(sig)

    # Sort by R:R descending
    all_buy.sort(key=lambda x: x.get("rr") or 0, reverse=True)
    all_sell.sort(key=lambda x: x.get("rr") or 0, reverse=True)

    result: dict = {
        "interval":      interval,
        "strategies":    strategies or list(_STRATEGIES.keys()),
        "as_of":         datetime.now().strftime("%Y-%m-%d %H:%M"),
        "scanned":       scanned,
        "errors":        errors,
        "min_rr":        min_rr,
        "buy_signals":   all_buy  if direction_filter in ("buy",  "all") else [],
        "sell_signals":  all_sell if direction_filter in ("sell", "all") else [],
        "watch_alerts":  all_watch,
        "summary": {
            "total_buy":   len(all_buy),
            "total_sell":  len(all_sell),
            "total_watch": len(all_watch),
            "top_buy":     all_buy[:3],
            "top_sell":    all_sell[:3],
        },
    }
    return result
