"""Price-history adjustment helpers for technical analysis."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _common_split_multiplier(ratio: float, tolerance: float = 0.20) -> float | None:
    """Return prior-price adjustment multiplier for obvious split/consolidation gaps."""
    try:
        ratio = float(ratio)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(ratio) or ratio <= 0:
        return None

    for split_ratio in (2, 3, 4, 5, 10):
        forward_factor = 1.0 / split_ratio
        if abs(ratio - forward_factor) / forward_factor <= tolerance:
            return forward_factor
        if abs(ratio - split_ratio) / split_ratio <= tolerance:
            return float(split_ratio)
    return None


def adjust_price_history_for_splits(stock_data: pd.DataFrame) -> pd.DataFrame:
    """Forward-adjust prior OHLC prices when NSE PREVCLOSE exposes a split gap."""
    if stock_data is None or stock_data.empty or "CLOSE" not in stock_data.columns:
        return stock_data

    adjusted = stock_data.copy()
    if "TIMESTAMP" in adjusted.columns:
        adjusted = adjusted.sort_values("TIMESTAMP").reset_index(drop=True)

    price_cols = [
        col
        for col in ("OPEN", "HIGH", "LOW", "CLOSE", "LAST", "PREVCLOSE")
        if col in adjusted.columns
    ]
    for col in price_cols:
        adjusted[col] = pd.to_numeric(adjusted[col], errors="coerce")

    for i in range(1, len(adjusted)):
        current_close = adjusted.at[i, "CLOSE"]
        prev_close = adjusted.at[i, "PREVCLOSE"] if "PREVCLOSE" in adjusted.columns else np.nan
        if pd.isna(prev_close) or prev_close <= 0:
            prev_close = adjusted.at[i - 1, "CLOSE"]
        if pd.isna(current_close) or pd.isna(prev_close) or prev_close <= 0:
            continue

        multiplier = _common_split_multiplier(current_close / prev_close)
        if multiplier is None:
            continue

        adjusted.loc[: i - 1, price_cols] = adjusted.loc[: i - 1, price_cols] * multiplier

    return adjusted
