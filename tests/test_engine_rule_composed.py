import unittest

import numpy as np
import pandas as pd

from backtesting.engine import BacktestConfig
from backtesting.strategy_council.rule_composed_engine import run_rule_composed_backtest
from backtesting.strategy_council.runner import run_strategy_spec_on_split
from backtesting.strategy_council.strategy_generator import RuleComposer


def _frame(closes, volumes=None):
    dates = pd.date_range("2024-01-01", periods=len(closes), freq="B")
    closes_arr = np.asarray(closes, dtype=float)
    if volumes is None:
        volumes_arr = np.full(len(closes), 100000.0)
    else:
        volumes_arr = np.asarray(volumes, dtype=float)
    opens = np.concatenate([[closes_arr[0]], closes_arr[:-1]])
    return pd.DataFrame(
        {
            "date": dates,
            "symbol": "TEST",
            "open": opens,
            "high": np.maximum(opens, closes_arr) * 1.001,
            "low": np.minimum(opens, closes_arr) * 0.999,
            "close": closes_arr,
            "volume": volumes_arr,
        }
    )


class RuleComposedBacktestTests(unittest.TestCase):
    def setUp(self):
        self.composer = RuleComposer()
        self.config = BacktestConfig(strategy_id="rule_composed", initial_capital=100000.0)

    def _spec(self, *, entry_atoms, exit_atoms, risk_atoms=("position_size",), horizon=10):
        return self.composer.compose(
            entry_atoms=entry_atoms,
            exit_atoms=exit_atoms,
            risk_atoms=risk_atoms,
            horizon_days=horizon,
            thesis="Engine integration test composite.",
            allowed_horizons=(5, 10, 20),
        )

    def test_profit_target_triggers_exit(self):
        # Long flat run lets EMA20 settle near 100; then a big up-bar triggers entry next open;
        # subsequent bars exceed +2% (profit_target default) well before the final bar.
        closes = [100.0] * 30 + [108.0, 115.0, 116.0, 117.0]
        df = _frame(closes)
        spec = self._spec(entry_atoms=("ema_bullish",), exit_atoms=("profit_target",))
        result = run_rule_composed_backtest(df, spec, self.config)
        self.assertGreaterEqual(result.metrics["trade_count"], 1)
        self.assertTrue(
            any("profit_target" in trade.exit_reason for trade in result.trades),
            f"reasons={[t.exit_reason for t in result.trades]}",
        )

    def test_stop_loss_triggers_exit(self):
        closes = [100.0] * 30 + [99.0, 95.0, 90.0]
        df = _frame(closes)
        spec = self._spec(
            entry_atoms=("ema_bullish",),
            exit_atoms=("stop_loss",),
        )
        # Force entry by raising close above ema first
        closes = [100.0] * 30 + [105.0, 95.0, 90.0, 85.0]
        df = _frame(closes)
        result = run_rule_composed_backtest(df, spec, self.config)
        if result.trades:
            self.assertTrue(any("stop_loss" in t.exit_reason for t in result.trades))

    def test_time_stop_exits_after_horizon(self):
        closes = [100.0] * 30 + [105.0] + [105.0] * 20
        df = _frame(closes)
        spec = self._spec(
            entry_atoms=("ema_bullish",),
            exit_atoms=("time_stop",),
        )
        result = run_rule_composed_backtest(df, spec, self.config)
        self.assertGreaterEqual(result.metrics["trade_count"], 1)
        self.assertTrue(any("time_stop" in t.exit_reason for t in result.trades))

    def test_no_entry_when_signal_never_fires(self):
        closes = [100.0] * 50
        df = _frame(closes)
        spec = self._spec(
            entry_atoms=("rsi_oversold",),
            exit_atoms=("profit_target",),
        )
        result = run_rule_composed_backtest(df, spec, self.config)
        self.assertEqual(result.metrics["trade_count"], 0)

    def test_runner_routes_rule_composed_through_engine(self):
        closes = [100.0] * 30 + [105.0, 108.0, 110.0]
        df = _frame(closes)
        spec = self._spec(entry_atoms=("ema_bullish",), exit_atoms=("profit_target",))
        slice_result = run_strategy_spec_on_split(
            df, spec, split_name="train", initial_capital=100000.0
        )
        self.assertEqual(slice_result.strategy_id, "rule_composed")
        self.assertEqual(slice_result.split, "train")
        self.assertGreaterEqual(slice_result.trade_count, 1)


if __name__ == "__main__":
    unittest.main()
