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

    def test_run_strategy_spec_adds_symbol_attribution_for_multi_symbol_stage2(self):
        dates = list(pd.date_range("2024-01-01", periods=80, freq="D")) * 2
        df = pd.DataFrame(
            {
                "date": dates,
                "symbol": ["AAA"] * 80 + ["BBB"] * 80,
                "open": list(range(100, 180)) + list(range(200, 280)),
                "high": list(range(101, 181)) + list(range(201, 281)),
                "low": list(range(99, 179)) + list(range(199, 279)),
                "close": list(range(101, 181)) + list(range(201, 281)),
                "volume": [1000] * 160,
                "stage": ["Stage 2"] * 160,
                "relative_strength": [90] * 160,
                "sma_50": list(range(90, 170)) + list(range(190, 270)),
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

        result = run_strategy_spec_on_split(df, spec, split_name="validation", initial_capital=100000)

        attribution = result.metrics["symbol_attribution"]
        self.assertEqual(set(attribution), {"AAA", "BBB"})
        self.assertGreaterEqual(attribution["AAA"]["trade_count"], 1)
        self.assertIn("return_pct", attribution["AAA"])

    def test_run_strategy_spec_executes_52w_high_breakout(self):
        closes = [100.0] * 60 + [101.0 + i * 0.2 for i in range(40)] + [112.0, 115.0, 118.0, 121.0, 124.0]
        df = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=len(closes), freq="D"),
                "symbol": ["AAA"] * len(closes),
                "open": closes,
                "high": [value + 1.0 for value in closes],
                "low": [value - 1.0 for value in closes],
                "close": closes,
                "volume": [1000] * 100 + [2500, 2600, 2700, 2800, 2900],
            }
        )
        spec = StrategySpec(
            strategy_id="52w_high",
            horizon_days=3,
            entry_rules=("near_52w_high", "volume_expansion"),
            exit_rules=("time_stop",),
            risk_rules=("max_position_pct=10",),
            thesis="52 week high breakout.",
        )

        result = run_strategy_spec_on_split(df, spec, split_name="validation", initial_capital=100000)

        self.assertEqual(result.strategy_id, "52w_high")
        self.assertGreaterEqual(result.trade_count, 1)
        self.assertNotIn("unsupported_strategy", result.metrics)
        self.assertIn("sharpe", result.metrics)
        self.assertIn("profit_factor", result.metrics)
        self.assertIn("max_drawdown_pct", result.metrics)
        self.assertIn("symbol_attribution", result.metrics)

    def test_run_strategy_spec_executes_vcp_breakout(self):
        rows = []
        start = pd.Timestamp("2024-01-01")
        for i in range(30):
            rows.append(
                {
                    "date": start + pd.Timedelta(days=i),
                    "symbol": "AAA",
                    "open": 100.0,
                    "high": 110.0,
                    "low": 90.0,
                    "close": 100.0,
                    "volume": 3000,
                }
            )
        for i in range(30, 59):
            rows.append(
                {
                    "date": start + pd.Timedelta(days=i),
                    "symbol": "AAA",
                    "open": 104.0,
                    "high": 106.0,
                    "low": 102.0,
                    "close": 104.0,
                    "volume": 1000,
                }
            )
        rows.append(
            {
                "date": start + pd.Timedelta(days=59),
                "symbol": "AAA",
                "open": 107.0,
                "high": 112.0,
                "low": 106.0,
                "close": 111.0,
                "volume": 2000,
            }
        )
        for i in range(60, 65):
            rows.append(
                {
                    "date": start + pd.Timedelta(days=i),
                    "symbol": "AAA",
                    "open": 112.0 + (i - 60),
                    "high": 114.0 + (i - 60),
                    "low": 111.0 + (i - 60),
                    "close": 113.0 + (i - 60),
                    "volume": 1600,
                }
            )
        df = pd.DataFrame(rows)
        spec = StrategySpec(
            strategy_id="vcp",
            horizon_days=3,
            entry_rules=("range_contracting", "volume_contracting", "pivot_breakout"),
            exit_rules=("time_stop",),
            risk_rules=("max_position_pct=10",),
            thesis="VCP breakout.",
        )

        result = run_strategy_spec_on_split(df, spec, split_name="validation", initial_capital=100000)

        self.assertEqual(result.strategy_id, "vcp")
        self.assertGreaterEqual(result.trade_count, 1)
        self.assertNotIn("unsupported_strategy", result.metrics)
        self.assertIn("symbol_attribution", result.metrics)
