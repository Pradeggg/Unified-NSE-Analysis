"""Grounded EOD recommendation report generation."""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = ROOT / "reports" / "recommendations"
PG_DSN = (
    os.environ.get("AGENT_ADDA_PG_DSN")
    or os.environ.get("PG_DSN")
    or "dbname=nse_market user=nse_admin host=/tmp"
)


@dataclass
class TechnicalProfile:
    subject: str
    latest_date: str = ""
    latest_close: float | None = None
    ret_1w: float | None = None
    ret_1m: float | None = None
    ret_3m: float | None = None
    ret_6m: float | None = None
    rs_1m: float | None = None
    rs_3m: float | None = None
    sma20: float | None = None
    sma50: float | None = None
    sma200: float | None = None
    price_above_sma20: bool | None = None
    price_above_sma50: bool | None = None
    price_above_sma200: bool | None = None
    rsi14: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_hist: float | None = None
    volume_ratio_20d: float | None = None
    high_52w: float | None = None
    low_52w: float | None = None
    drawdown_from_52w_high_pct: float | None = None
    support: float | None = None
    resistance: float | None = None
    trend_label: str = "neutral"
    conflicts: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)


def _num(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        number = float(value)
        return None if math.isnan(number) else number
    except Exception:
        return None


def _round(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(float(value), digits)


def _prep_ohlcv(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()

    df = frame.copy()
    df.columns = [
        re.sub(r"_+", "_", re.sub(r"[^0-9a-zA-Z]+", "_", str(col).strip().lower())).strip("_")
        for col in df.columns
    ]
    if "timestamp" in df.columns and "trade_date" not in df.columns:
        df = df.rename(columns={"timestamp": "trade_date"})
    if "date" in df.columns and "trade_date" not in df.columns:
        df = df.rename(columns={"date": "trade_date"})

    required = {"trade_date", "close"}
    if not required.issubset(df.columns):
        return pd.DataFrame()

    df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
    for col in ("open", "high", "low", "close", "volume"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["trade_date", "close"]).sort_values("trade_date")
    return df.reset_index(drop=True)


def pct_change_from_lookback(
    frame: pd.DataFrame,
    latest_date: str | pd.Timestamp,
    *,
    days: int,
) -> float | None:
    df = _prep_ohlcv(frame)
    if df.empty:
        return None

    latest_ts = pd.to_datetime(latest_date)
    latest_rows = df[df["trade_date"] <= latest_ts]
    if latest_rows.empty:
        return None

    latest = latest_rows.iloc[-1]
    target_ts = latest_ts - pd.Timedelta(days=days)
    prior_rows = df[df["trade_date"] <= target_ts]
    if prior_rows.empty:
        return None

    prior = prior_rows.iloc[-1]
    prior_close = _num(prior.get("close"))
    latest_close = _num(latest.get("close"))
    if prior_close in (None, 0) or latest_close is None:
        return None

    return _round(((latest_close / prior_close) - 1.0) * 100.0)


def _rsi(close: pd.Series, period: int = 14) -> float | None:
    if len(close) <= period:
        return None

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    latest_gain = _num(gain.iloc[-1])
    latest_loss = _num(loss.iloc[-1])
    if latest_gain is None or latest_loss is None:
        return None
    if latest_loss == 0:
        return 100.0 if latest_gain > 0 else 50.0

    rs = latest_gain / latest_loss
    return _round(100 - (100 / (1 + rs)))


def _macd(close: pd.Series) -> tuple[float | None, float | None, float | None]:
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal
    return _round(_num(macd.iloc[-1])), _round(_num(signal.iloc[-1])), _round(_num(hist.iloc[-1]))


def _trend_label(
    latest: float | None,
    sma20: float | None,
    sma50: float | None,
    sma200: float | None,
    rsi14: float | None,
    macd_hist: float | None,
) -> str:
    if latest is None:
        return "neutral"

    positives = 0
    positives += int(sma20 is not None and latest > sma20)
    positives += int(sma50 is not None and latest > sma50)
    positives += int(sma200 is not None and latest > sma200)
    positives += int(rsi14 is not None and rsi14 >= 55)
    positives += int(macd_hist is not None and macd_hist > 0)
    if positives >= 4:
        return "bullish"
    if positives == 3:
        return "constructive"
    if positives == 2:
        return "neutral"
    if positives == 1:
        return "weak"
    return "bearish"


def build_technical_profile(
    subject: str,
    frame: pd.DataFrame,
    benchmark_frame: pd.DataFrame | None = None,
) -> TechnicalProfile:
    df = _prep_ohlcv(frame)
    if df.empty:
        return TechnicalProfile(subject=subject.upper(), missing_evidence=["eod_price_history"])

    missing: list[str] = []
    latest = df.iloc[-1]
    latest_close = _num(latest.get("close"))
    latest_date = str(latest["trade_date"].date())
    close = df["close"]

    sma20 = _round(_num(close.tail(20).mean())) if len(close) >= 20 else None
    sma50 = _round(_num(close.tail(50).mean())) if len(close) >= 50 else None
    sma200 = _round(_num(close.tail(200).mean())) if len(close) >= 200 else None
    if sma20 is None:
        missing.append("sma20_history")
    if sma50 is None:
        missing.append("sma50_history")
    if sma200 is None:
        missing.append("sma200_history")

    rsi14 = _rsi(close) if len(close) >= 15 else None
    if rsi14 is None:
        missing.append("rsi14_history")

    macd, macd_signal, macd_hist = _macd(close) if len(close) >= 35 else (None, None, None)
    if macd_hist is None:
        missing.append("macd_history")

    high_52w = (
        _round(_num(df["high"].tail(252).max()))
        if "high" in df.columns
        else _round(_num(close.tail(252).max()))
    )
    low_52w = (
        _round(_num(df["low"].tail(252).min()))
        if "low" in df.columns
        else _round(_num(close.tail(252).min()))
    )
    drawdown = _round(((latest_close / high_52w) - 1.0) * 100.0) if latest_close and high_52w else None

    volume_ratio = None
    if "volume" in df.columns and len(df) >= 20:
        avg_volume = _num(df["volume"].tail(20).mean())
        latest_volume = _num(latest.get("volume"))
        volume_ratio = (
            _round(latest_volume / avg_volume)
            if latest_volume is not None and avg_volume not in (None, 0)
            else None
        )
    else:
        missing.append("volume_ratio")

    benchmark = _prep_ohlcv(benchmark_frame) if benchmark_frame is not None else pd.DataFrame()
    ret_1m = pct_change_from_lookback(df, latest["trade_date"], days=30)
    ret_3m = pct_change_from_lookback(df, latest["trade_date"], days=90)
    b_ret_1m = (
        pct_change_from_lookback(benchmark, latest["trade_date"], days=30)
        if not benchmark.empty
        else None
    )
    b_ret_3m = (
        pct_change_from_lookback(benchmark, latest["trade_date"], days=90)
        if not benchmark.empty
        else None
    )

    conflicts: list[str] = []
    if rsi14 is not None and rsi14 >= 75 and sma50 is not None and latest_close is not None and latest_close > sma50:
        conflicts.append("trend constructive but RSI extended")
    if ret_1m is not None and ret_3m is not None and ret_1m < 0 < ret_3m:
        conflicts.append("short-term momentum weak against medium-term trend")

    return TechnicalProfile(
        subject=subject.upper(),
        latest_date=latest_date,
        latest_close=_round(latest_close),
        ret_1w=pct_change_from_lookback(df, latest["trade_date"], days=7),
        ret_1m=ret_1m,
        ret_3m=ret_3m,
        ret_6m=pct_change_from_lookback(df, latest["trade_date"], days=180),
        rs_1m=_round(ret_1m - b_ret_1m) if ret_1m is not None and b_ret_1m is not None else None,
        rs_3m=_round(ret_3m - b_ret_3m) if ret_3m is not None and b_ret_3m is not None else None,
        sma20=sma20,
        sma50=sma50,
        sma200=sma200,
        price_above_sma20=latest_close > sma20 if latest_close is not None and sma20 is not None else None,
        price_above_sma50=latest_close > sma50 if latest_close is not None and sma50 is not None else None,
        price_above_sma200=latest_close > sma200 if latest_close is not None and sma200 is not None else None,
        rsi14=rsi14,
        macd=macd,
        macd_signal=macd_signal,
        macd_hist=macd_hist,
        volume_ratio_20d=volume_ratio,
        high_52w=high_52w,
        low_52w=low_52w,
        drawdown_from_52w_high_pct=drawdown,
        support=_round(_num(df["low"].tail(20).min())) if "low" in df.columns else None,
        resistance=_round(_num(df["high"].tail(20).max())) if "high" in df.columns else None,
        trend_label=_trend_label(latest_close, sma20, sma50, sma200, rsi14, macd_hist),
        conflicts=conflicts,
        missing_evidence=missing,
    )


__all__ = [
    "PG_DSN",
    "REPORT_DIR",
    "ROOT",
    "TechnicalProfile",
    "build_technical_profile",
    "pct_change_from_lookback",
]
