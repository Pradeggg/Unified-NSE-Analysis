import unittest

import pandas as pd

from backtesting.engine import BacktestConfig, compute_stage2_features, run_backtest


class BacktestingEngineTests(unittest.TestCase):
    def test_stage2_backtest_enters_and_exits_on_next_open_without_lookahead(self):
        df = pd.DataFrame(
            {
                "date": pd.date_range("2026-01-01", periods=5, freq="D"),
                "symbol": ["AAA"] * 5,
                "open": [10.0, 11.0, 12.0, 14.0, 13.0],
                "high": [11.0, 12.0, 13.0, 15.0, 14.0],
                "low": [9.0, 10.0, 11.0, 13.0, 12.0],
                "close": [10.5, 11.5, 13.0, 13.5, 12.5],
                "volume": [1000, 1100, 1200, 1300, 1400],
                "stage": ["Stage 1", "Stage 2", "Stage 2", "Stage 1", "Stage 1"],
                "relative_strength": [50, 80, 82, 60, 55],
                "sma_50": [10, 10, 10, 14, 14],
            }
        )

        result = run_backtest(
            df,
            BacktestConfig(strategy_id="stage2", initial_capital=1200, allocation_pct=1.0),
        )

        self.assertEqual(len(result.trades), 1)
        trade = result.trades[0]
        self.assertEqual(trade.symbol, "AAA")
        self.assertEqual(trade.entry_date.isoformat(), "2026-01-03")
        self.assertEqual(trade.entry_price, 12.0)
        self.assertEqual(trade.exit_date.isoformat(), "2026-01-05")
        self.assertEqual(trade.exit_price, 13.0)
        self.assertEqual(trade.entry_reason, "stage2_entry_next_open")
        self.assertEqual(trade.exit_reason, "stage2_exit_next_open")
        self.assertAlmostEqual(result.metrics["total_return_pct"], 8.3333, places=3)

    def test_unknown_strategy_is_rejected(self):
        df = pd.DataFrame(
            {
                "date": pd.date_range("2026-01-01", periods=2, freq="D"),
                "symbol": ["AAA", "AAA"],
                "open": [10.0, 11.0],
                "high": [11.0, 12.0],
                "low": [9.0, 10.0],
                "close": [10.5, 11.5],
                "volume": [1000, 1100],
            }
        )

        with self.assertRaisesRegex(ValueError, "Available strategies"):
            run_backtest(df, BacktestConfig(strategy_id="unknown"))

    def test_compute_stage2_features_creates_stage_inputs_from_raw_ohlcv(self):
        rows = []
        for i in range(240):
            close = 100 + i
            rows.append(
                {
                    "TIMESTAMP": pd.Timestamp("2025-01-01") + pd.Timedelta(days=i),
                    "SYMBOL": "AAA",
                    "OPEN": close - 1,
                    "HIGH": close + 1,
                    "LOW": close - 2,
                    "CLOSE": close,
                    "TOTTRDQTY": 1000 + i,
                }
            )
        df = pd.DataFrame(rows)

        features = compute_stage2_features(df)
        latest = features.iloc[-1]

        self.assertIn("sma_50", features.columns)
        self.assertIn("sma_150", features.columns)
        self.assertIn("sma_200", features.columns)
        self.assertIn("relative_strength", features.columns)
        self.assertIn("stage", features.columns)
        self.assertEqual(latest["stage"], "Stage 2")
        self.assertGreaterEqual(latest["relative_strength"], 70)

    def test_stage2_backtest_runs_when_stage_features_are_missing_but_ohlcv_exists(self):
        rows = []
        for i in range(240):
            close = 100 + i
            rows.append(
                {
                    "TIMESTAMP": pd.Timestamp("2025-01-01") + pd.Timedelta(days=i),
                    "SYMBOL": "AAA",
                    "OPEN": close - 1,
                    "HIGH": close + 1,
                    "LOW": close - 2,
                    "CLOSE": close,
                    "TOTTRDQTY": 1000 + i,
                }
            )
        df = pd.DataFrame(rows)

        result = run_backtest(df, BacktestConfig(strategy_id="stage2", initial_capital=100000))

        self.assertGreaterEqual(result.metrics["trade_count"], 1)
        self.assertEqual(result.trades[0].entry_reason, "stage2_entry_next_open")


if __name__ == "__main__":
    unittest.main()
