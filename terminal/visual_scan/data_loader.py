"""Evidence loading for visual scan reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

try:
    from terminal.recommendation_report import RecommendationReportOptions, load_recommendation_input_data
except Exception:  # pragma: no cover - optional during isolated imports
    RecommendationReportOptions = None
    load_recommendation_input_data = None


@dataclass
class VisualScanInput:
    daily: pd.DataFrame = field(default_factory=pd.DataFrame)
    benchmark: pd.DataFrame = field(default_factory=pd.DataFrame)
    snapshot: dict[str, Any] = field(default_factory=dict)
    sector_context: dict[str, Any] = field(default_factory=dict)
    mtf: dict[str, Any] = field(default_factory=dict)


@dataclass
class LoadedVisualScanInput:
    symbol: str
    daily: pd.DataFrame
    weekly: pd.DataFrame
    benchmark: pd.DataFrame
    snapshot: dict[str, Any]
    sector_context: dict[str, Any]
    mtf: dict[str, Any]
    source_trail: dict[str, Any]
    missing_evidence: list[str]


def _normalize_ohlcv(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["trade_date", "open", "high", "low", "close", "volume"])
    df = frame.copy()
    df.columns = [str(col).lower().strip() for col in df.columns]
    if "date" in df.columns and "trade_date" not in df.columns:
        df = df.rename(columns={"date": "trade_date"})
    if "trade_date" not in df.columns or "close" not in df.columns:
        return pd.DataFrame(columns=["trade_date", "open", "high", "low", "close", "volume"])
    df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
    for col in ("open", "high", "low", "close", "volume"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["trade_date", "close"]).sort_values("trade_date").reset_index(drop=True)
    for col in ("open", "high", "low"):
        if col not in df.columns:
            df[col] = df["close"]
    if "volume" not in df.columns:
        df["volume"] = 0
    return df


def resample_weekly(daily: pd.DataFrame) -> pd.DataFrame:
    df = _normalize_ohlcv(daily)
    if df.empty:
        return pd.DataFrame(columns=["trade_date", "open", "high", "low", "close", "volume"])
    indexed = df.set_index("trade_date")
    weekly = indexed.resample("W-FRI").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )
    return weekly.dropna(subset=["close"]).reset_index()


def _symbol_key(value: str) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def _filter_history_frame(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    cols = {str(col).lower(): col for col in frame.columns}
    sym_col = cols.get("symbol") or cols.get("index_symbol")
    if not sym_col:
        return pd.DataFrame()
    wanted = _symbol_key(symbol)
    aliases = {wanted}
    if wanted == "NIFTYBANK":
        aliases.add("BANKNIFTY")
    if wanted == "BANKNIFTY":
        aliases.add("NIFTYBANK")
    series = frame[sym_col].astype(str)
    mask = series.map(_symbol_key).isin(aliases)
    return frame[mask].copy()


def _load_daily_from_market(symbol: str) -> pd.DataFrame:
    if load_recommendation_input_data is None or RecommendationReportOptions is None:
        return pd.DataFrame()
    try:
        data = load_recommendation_input_data(RecommendationReportOptions())
        equity = _filter_history_frame(getattr(data, "equity_history", pd.DataFrame()), symbol)
        if not equity.empty:
            return equity
        return _filter_history_frame(getattr(data, "index_history", pd.DataFrame()), symbol)
    except Exception:
        return pd.DataFrame()


def load_visual_scan_input(symbol: str, input_data: VisualScanInput | None = None) -> LoadedVisualScanInput:
    sym = str(symbol or "").strip().upper()
    source_trail: dict[str, Any] = {}
    missing: list[str] = []
    if input_data is not None:
        daily = _normalize_ohlcv(input_data.daily)
        source_trail["daily"] = {"status": "injected" if not daily.empty else "degraded", "rows": len(daily)}
        if daily.empty:
            source_trail["daily"]["reason"] = "injected frame did not contain usable trade_date and close data"
    else:
        daily = _normalize_ohlcv(_load_daily_from_market(sym))
        source_trail["daily"] = {"status": "loaded" if not daily.empty else "missing", "rows": len(daily)}
    if daily.empty:
        missing.append("daily_history")
    weekly = resample_weekly(daily)
    if weekly.empty:
        missing.append("weekly_history")
    source_trail["weekly"] = {"status": "derived" if not weekly.empty else "missing", "rows": len(weekly)}
    injected = input_data or VisualScanInput()
    return LoadedVisualScanInput(
        symbol=sym,
        daily=daily,
        weekly=weekly,
        benchmark=_normalize_ohlcv(injected.benchmark),
        snapshot=dict(injected.snapshot),
        sector_context=dict(injected.sector_context),
        mtf=dict(injected.mtf),
        source_trail=source_trail,
        missing_evidence=missing,
    )
