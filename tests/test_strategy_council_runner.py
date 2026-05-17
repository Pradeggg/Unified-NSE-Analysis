import unittest

import pandas as pd

from backtesting.strategy_council.runner import run_strategy_spec_on_split
from backtesting.strategy_council.splits import build_time_splits
from backtesting.strategy_council.types import StrategySpec


class StrategyCouncilRunnerTests(unittest.TestCase):
    def test_build_time_splits_keeps_test_data_separate(self):
        df = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=600, freq="D"),
                "symbol": ["DMART"] * 600,
                "open": range(600),
                "high": range(1, 601),
                "low": range(600),
                "close": range(1, 601),
                "volume": [1000] * 600,
            }
        )

        splits = build_time_splits(df, validation_from="2025-01-01", test_from="2025-06-01")

        self.assertLess(splits["train"]["date"].max(), pd.Timestamp("2025-01-01"))
        self.assertLess(splits["validation"]["date"].max(), pd.Timestamp("2025-06-01"))
        self.assertGreaterEqual(splits["test"]["date"].min(), pd.Timestamp("2025-06-01"))


class StrategyCouncilSpecRunnerTests(unittest.TestCase):
    def test_run_strategy_spec_returns_metrics_without_exposing_test_when_split_is_train(self):
        df = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=260, freq="D"),
                "symbol": ["DMART"] * 260,
                "open": [100 + i for i in range(260)],
                "high": [102 + i for i in range(260)],
                "low": [99 + i for i in range(260)],
                "close": [101 + i for i in range(260)],
                "volume": [1000] * 260,
            }
        )
        spec = StrategySpec(
            strategy_id="stage2",
            horizon_days=10,
            entry_rules=("stage == Stage 2",),
            exit_rules=("close < sma_50",),
            risk_rules=("max_position_pct=10",),
            thesis="Stage 2 continuation.",
        )

        result = run_strategy_spec_on_split(df, spec, split_name="train", initial_capital=100000)

        self.assertEqual(result.split, "train")
        self.assertEqual(result.strategy_id, "stage2")
        self.assertIn("total_return_pct", result.metrics)
        self.assertEqual(result.horizon_days, 10)
