"""Technical pattern features for EOD strategy backtesting."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Literal

import pandas as pd


@dataclass(frozen=True)
class PatternSignal:
    symbol: str
    pattern_id: str
    signal_date: date | None
    direction: Literal["bullish", "bearish", "neutral"]
    confidence: float
    entry_price: float | None = None
    stop_price: float | None = None
    target_price: float | None = None
    pivot_price: float | None = None
    start_date: date | None = None
    end_date: date | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    rejection_reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    rename = {col: col.strip().lower() for col in df.columns}
    out = df.rename(columns=rename).copy()
    required = {"high", "low", "close"}
    missing = sorted(required - set(out.columns))
    if missing:
        raise ValueError(f"Missing OHLCV columns: {', '.join(missing)}")
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"], errors="coerce")
        out = out.sort_values("date")
    return out.reset_index(drop=True)


def compute_pattern_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add no-lookahead EOD technical features used by pattern detectors."""
    out = _normalize_ohlcv(df)

    close = pd.to_numeric(out["close"], errors="coerce")
    high = pd.to_numeric(out["high"], errors="coerce")
    low = pd.to_numeric(out["low"], errors="coerce")
    volume = pd.to_numeric(out.get("volume", pd.Series([pd.NA] * len(out))), errors="coerce")

    for window in (20, 50, 150, 200):
        out[f"sma_{window}"] = close.rolling(window=window, min_periods=window).mean()

    prev_close = close.shift(1)
    true_range = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    out["atr_14"] = true_range.rolling(window=14, min_periods=14).mean()

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window=14, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).rolling(window=14, min_periods=14).mean()
    rs = gain / loss.replace(0, pd.NA)
    out["rsi_14"] = 100 - (100 / (1 + rs))
    out.loc[(loss == 0) & (gain > 0), "rsi_14"] = 100
    out.loc[(loss == 0) & (gain == 0), "rsi_14"] = 50

    out["range"] = high - low
    out["range_pct"] = out["range"] / close.replace(0, pd.NA)
    out["avg_volume_20"] = volume.rolling(window=20, min_periods=1).mean()
    out["rel_volume"] = volume / out["avg_volume_20"].replace(0, pd.NA)
    out["high_52w"] = high.rolling(window=252, min_periods=20).max()
    out["low_52w"] = low.rolling(window=252, min_periods=20).min()

    ma20 = close.rolling(window=20, min_periods=20).mean()
    std20 = close.rolling(window=20, min_periods=20).std()
    upper = ma20 + (2 * std20)
    lower = ma20 - (2 * std20)
    out["bb_bandwidth"] = (upper - lower) / ma20.replace(0, pd.NA)

    return out


def _date_value(value: Any) -> date | None:
    if pd.isna(value):
        return None
    if hasattr(value, "date"):
        return value.date()
    try:
        return pd.to_datetime(value).date()
    except Exception:
        return None


def detect_vcp(
    df: pd.DataFrame,
    *,
    symbol: str = "",
    as_of: date | None = None,
    min_confidence: float = 70,
) -> list[PatternSignal]:
    """Detect a simple auditable VCP-style contraction breakout.

    This first implementation is intentionally conservative and explainable:
    it looks at completed historical bars up to `as_of`, compares early and
    late ranges before the signal bar, and treats the last bar as the possible
    breakout bar.
    """
    features = compute_pattern_features(df)
    if as_of is not None and "date" in features.columns:
        features = features[features["date"].dt.date <= as_of]

    if len(features) < 40:
        return [
            PatternSignal(
                symbol=symbol,
                pattern_id="vcp",
                signal_date=None,
                direction="neutral",
                confidence=0,
                rejection_reasons=["insufficient_history"],
            )
        ]

    window = features.tail(min(len(features), 80)).copy()
    signal_bar = window.iloc[-1]
    prior = window.iloc[:-1]

    early = prior.head(max(10, len(prior) // 3))
    late = prior.tail(max(10, len(prior) // 3))

    early_range = float(early["range_pct"].mean())
    late_range = float(late["range_pct"].mean())
    range_contracting = pd.notna(early_range) and pd.notna(late_range) and late_range < early_range * 0.75

    if "volume" in window.columns:
        early_volume = float(pd.to_numeric(early["volume"], errors="coerce").mean())
        late_volume = float(pd.to_numeric(late["volume"], errors="coerce").mean())
        volume_contracting = pd.notna(early_volume) and pd.notna(late_volume) and late_volume < early_volume
        breakout_volume = float(signal_bar.get("volume", 0) or 0) > max(late_volume, 0) * 1.1
    else:
        volume_contracting = False
        breakout_volume = False

    pivot = float(prior["high"].tail(30).max())
    close = float(signal_bar["close"])
    low = float(signal_bar["low"])
    breakout = close > pivot

    rejection_reasons: list[str] = []
    if not range_contracting:
        rejection_reasons.append("range_not_contracting")
    if not volume_contracting:
        rejection_reasons.append("volume_not_contracting")
    if not breakout:
        rejection_reasons.append("pivot_not_broken")
    if not breakout_volume:
        rejection_reasons.append("breakout_without_volume")

    confidence = 30.0
    if range_contracting:
        confidence += 30
    if volume_contracting:
        confidence += 15
    if breakout:
        confidence += 15
    if breakout_volume:
        confidence += 10
    if confidence < min_confidence and not rejection_reasons:
        rejection_reasons.append("confidence_below_threshold")

    signal_date = _date_value(signal_bar.get("date")) if "date" in window.columns else None
    start_date = _date_value(window.iloc[0].get("date")) if "date" in window.columns else None

    return [
        PatternSignal(
            symbol=symbol,
            pattern_id="vcp",
            signal_date=signal_date,
            direction="bullish" if breakout else "neutral",
            confidence=round(min(confidence, 100), 2),
            entry_price=close if breakout else None,
            stop_price=round(min(low, pivot * 0.92), 2) if breakout else None,
            target_price=round(close + (close - min(low, pivot * 0.92)) * 2, 2) if breakout else None,
            pivot_price=round(pivot, 2),
            start_date=start_date,
            end_date=signal_date,
            evidence={
                "early_range_pct": round(early_range, 6) if pd.notna(early_range) else None,
                "late_range_pct": round(late_range, 6) if pd.notna(late_range) else None,
                "range_contracting": range_contracting,
                "volume_contracting": volume_contracting,
                "pivot_breakout": breakout,
                "breakout_volume": breakout_volume,
            },
            rejection_reasons=rejection_reasons,
        )
    ]
