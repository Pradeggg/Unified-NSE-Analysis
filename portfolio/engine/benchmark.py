from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import pandas as pd


@dataclass(frozen=True)
class BenchmarkComparison:
    benchmark_id: str
    portfolio_return_pct: float
    benchmark_return_pct: float
    excess_return_pct: float
    portfolio_max_drawdown_pct: float
    benchmark_max_drawdown_pct: float
    observation_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "benchmark_id": self.benchmark_id,
            "portfolio_return_pct": float(self.portfolio_return_pct),
            "benchmark_return_pct": float(self.benchmark_return_pct),
            "excess_return_pct": float(self.excess_return_pct),
            "portfolio_max_drawdown_pct": float(self.portfolio_max_drawdown_pct),
            "benchmark_max_drawdown_pct": float(self.benchmark_max_drawdown_pct),
            "observation_count": int(self.observation_count),
        }


def compare_to_benchmark(
    nav_history: Iterable[Any],
    benchmark_data: pd.DataFrame,
    benchmark_id: str,
) -> BenchmarkComparison:
    nav_frame = _nav_frame(nav_history)
    benchmark_frame = _benchmark_frame(benchmark_data)
    if nav_frame.empty or benchmark_frame.empty:
        return _empty_comparison(benchmark_id)

    aligned = nav_frame.merge(benchmark_frame, on="date", how="inner").sort_values("date")
    if aligned.empty:
        return _empty_comparison(benchmark_id)

    portfolio_values = aligned["equity"].tolist()
    benchmark_values = aligned["close"].tolist()
    portfolio_return_pct = _pct_return(portfolio_values[0], portfolio_values[-1])
    benchmark_return_pct = _pct_return(benchmark_values[0], benchmark_values[-1])

    return BenchmarkComparison(
        benchmark_id=str(benchmark_id),
        portfolio_return_pct=portfolio_return_pct,
        benchmark_return_pct=benchmark_return_pct,
        excess_return_pct=round(portfolio_return_pct - benchmark_return_pct, 4),
        portfolio_max_drawdown_pct=_max_drawdown_pct(portfolio_values),
        benchmark_max_drawdown_pct=_max_drawdown_pct(benchmark_values),
        observation_count=int(len(aligned)),
    )


def _empty_comparison(benchmark_id: str) -> BenchmarkComparison:
    return BenchmarkComparison(
        benchmark_id=str(benchmark_id),
        portfolio_return_pct=0.0,
        benchmark_return_pct=0.0,
        excess_return_pct=0.0,
        portfolio_max_drawdown_pct=0.0,
        benchmark_max_drawdown_pct=0.0,
        observation_count=0,
    )


def _nav_frame(nav_history: Iterable[Any]) -> pd.DataFrame:
    rows = []
    for entry in nav_history:
        timestamp = _field(entry, "timestamp")
        equity = _number(_field(entry, "equity"))
        date = _date_key(timestamp)
        if date is not None and equity is not None:
            rows.append({"date": date, "equity": equity})
    if not rows:
        return pd.DataFrame(columns=["date", "equity"])
    return pd.DataFrame(rows).drop_duplicates(subset=["date"], keep="last")


def _benchmark_frame(benchmark_data: pd.DataFrame) -> pd.DataFrame:
    if not {"date", "close"}.issubset(benchmark_data.columns):
        return pd.DataFrame(columns=["date", "close"])

    rows = []
    for row in benchmark_data[["date", "close"]].itertuples(index=False):
        close = _number(row.close)
        date = _date_key(row.date)
        if date is not None and close is not None:
            rows.append({"date": date, "close": close})
    if not rows:
        return pd.DataFrame(columns=["date", "close"])
    return pd.DataFrame(rows).drop_duplicates(subset=["date"], keep="last")


def _field(entry: Any, name: str) -> Any:
    if isinstance(entry, dict):
        return entry.get(name)
    return getattr(entry, name, None)


def _date_key(value: Any) -> Any:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed or parsed in {float("inf"), float("-inf")}:
        return None
    return parsed


def _pct_return(starting: float, ending: float) -> float:
    if starting == 0:
        return 0.0
    return round((ending - starting) / starting * 100.0, 4)


def _max_drawdown_pct(values: list[float]) -> float:
    if not values:
        return 0.0
    peak = values[0]
    max_drawdown = 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - value) / peak * 100.0)
    return round(max_drawdown, 4)
