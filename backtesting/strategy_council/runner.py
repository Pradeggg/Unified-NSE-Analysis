"""Deterministic Strategy Council candidate runner."""

from __future__ import annotations

import pandas as pd

from backtesting.engine import BacktestConfig, run_backtest
from backtesting.strategy_council.types import BacktestSliceResult, StrategySpec


def run_strategy_spec_on_split(
    df: pd.DataFrame,
    spec: StrategySpec,
    *,
    split_name: str,
    initial_capital: float,
) -> BacktestSliceResult:
    if spec.strategy_id != "stage2":
        metrics = {
            "trade_count": 0,
            "total_return_pct": None,
            "total_pnl": 0,
            "unsupported_strategy": spec.strategy_id,
        }
        return BacktestSliceResult(
            split=split_name,
            strategy_id=spec.strategy_id,
            horizon_days=spec.horizon_days,
            metrics=metrics,
            trade_count=0,
        )

    result = run_backtest(
        df,
        BacktestConfig(strategy_id=spec.strategy_id, initial_capital=initial_capital),
    )
    return BacktestSliceResult(
        split=split_name,
        strategy_id=spec.strategy_id,
        horizon_days=spec.horizon_days,
        metrics=result.metrics,
        trade_count=int(result.metrics.get("trade_count") or 0),
    )

