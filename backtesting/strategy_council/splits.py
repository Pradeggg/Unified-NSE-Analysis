"""Time-based train/validation/test split helpers."""

from __future__ import annotations

import pandas as pd


def build_time_splits(
    df: pd.DataFrame,
    *,
    validation_from: str | None = None,
    test_from: str | None = None,
) -> dict[str, pd.DataFrame]:
    data = df.copy()
    if "timestamp" in data.columns and "date" not in data.columns:
        data = data.rename(columns={"timestamp": "date"})
    if "date" not in data.columns:
        data["date"] = pd.NaT
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data = data.dropna(subset=["date"]).sort_values("date")

    if data.empty:
        return {"train": data.copy(), "validation": data.copy(), "test": data.copy()}

    min_date = data["date"].min()
    max_date = data["date"].max()
    validation_cut = pd.Timestamp(validation_from) if validation_from else min_date + (max_date - min_date) * 0.60
    test_cut = pd.Timestamp(test_from) if test_from else min_date + (max_date - min_date) * 0.80

    return {
        "train": data[data["date"] < validation_cut].copy(),
        "validation": data[(data["date"] >= validation_cut) & (data["date"] < test_cut)].copy(),
        "test": data[data["date"] >= test_cut].copy(),
    }

