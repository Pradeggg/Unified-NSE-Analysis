import unittest

import pandas as pd

from backtesting.patterns import PatternSignal, compute_pattern_features, detect_vcp


class BacktestingPatternTests(unittest.TestCase):
    def test_compute_pattern_features_adds_indicators(self):
        df = pd.DataFrame(
            {
                "date": pd.date_range("2026-01-01", periods=260, freq="D"),
                "open": list(range(260)),
                "high": [x + 2 for x in range(260)],
                "low": [x - 1 for x in range(260)],
                "close": [x + 1 for x in range(260)],
                "volume": [1000 + x for x in range(260)],
            }
        )

        out = compute_pattern_features(df)

        self.assertIn("sma_50", out.columns)
        self.assertIn("sma_200", out.columns)
        self.assertIn("atr_14", out.columns)
        self.assertIn("rsi_14", out.columns)
        self.assertIn("range_pct", out.columns)
        self.assertFalse(out["sma_50"].dropna().empty)

    def test_detect_vcp_returns_rejection_reason_when_ranges_do_not_contract(self):
        df = pd.DataFrame(
            {
                "date": pd.date_range("2026-01-01", periods=80, freq="D"),
                "open": [100] * 80,
                "high": [110] * 80,
                "low": [90] * 80,
                "close": [100] * 79 + [111],
                "volume": [1000] * 80,
            }
        )

        signals = detect_vcp(df, symbol="DMART")

        self.assertTrue(signals)
        self.assertIsInstance(signals[0], PatternSignal)
        self.assertEqual(signals[0].pattern_id, "vcp")
        self.assertIn("range_not_contracting", signals[0].rejection_reasons)

    def test_detect_vcp_emits_high_confidence_for_contraction_breakout(self):
        rows = []
        base_date = pd.Timestamp("2026-01-01")
        ranges = [12] * 20 + [8] * 20 + [5] * 20 + [3] * 19 + [14]
        closes = [100 + min(i, 70) * 0.15 for i in range(80)]
        for i, range_width in enumerate(ranges):
            close = closes[i]
            rows.append(
                {
                    "date": base_date + pd.Timedelta(days=i),
                    "open": close - 0.4,
                    "high": close + range_width / 2,
                    "low": close - range_width / 2,
                    "close": close if i < 79 else max(closes[:-1]) + 4,
                    "volume": 2000 - min(i, 70) * 10 if i < 79 else 2500,
                }
            )
        df = pd.DataFrame(rows)

        signals = detect_vcp(df, symbol="DMART")

        self.assertTrue(signals)
        self.assertGreaterEqual(signals[0].confidence, 70)
        self.assertEqual(signals[0].direction, "bullish")
        self.assertEqual(signals[0].rejection_reasons, [])


if __name__ == "__main__":
    unittest.main()
