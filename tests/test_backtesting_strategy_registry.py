import unittest

from backtesting.strategy_registry import get_strategy, list_strategies


class StrategyRegistryTests(unittest.TestCase):
    def test_core_and_pattern_strategies_are_registered(self):
        ids = {strategy.id for strategy in list_strategies()}

        self.assertIn("stage2", ids)
        self.assertIn("canslim", ids)
        self.assertIn("minervini", ids)
        self.assertIn("supertrend_continuation", ids)
        self.assertIn("rsi_pullback_stage2", ids)
        self.assertIn("vcp", ids)
        self.assertIn("head_shoulders", ids)

    def test_unknown_strategy_reports_available_choices(self):
        with self.assertRaisesRegex(ValueError, "Available strategies"):
            get_strategy("unknown")

    def test_pattern_strategies_are_marked_experimental(self):
        strategy = get_strategy("head_shoulders")

        self.assertEqual(strategy.status, "experimental")
        self.assertIn("close", strategy.required_fields)
        self.assertIn("volume", strategy.required_fields)


if __name__ == "__main__":
    unittest.main()
