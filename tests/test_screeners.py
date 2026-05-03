"""Tests for screeners.py — A1 Stage Analysis and A3 52W Momentum."""
import unittest

import pandas as pd

from screeners import (
    momentum_52w_high_screener,
    build_momentum_screener_tab_html,
    run_stage_screener,
)


def _make_universe(**overrides) -> pd.DataFrame:
    """Build a one-row candidates DataFrame with sensible defaults."""
    defaults = {
        "SYMBOL": "TEST",
        "COMPANY_NAME": "Test Co",
        "SECTOR_NAME": "IT",
        "CLOSE": 100.0,
        "CURRENT_PRICE": 100.0,
        "DIST_FROM_52W_HIGH_PCT": -2.0,   # within 5% of 52W high
        "SMA_50_SLOPE": 0.05,              # positive slope
        "RS_RANK_PCT": 0.85,               # top 25%
        "VOL_RATIO": 1.5,                  # above average volume
        "RSI": 62.0,                       # 50–80 window
        "STAGE": "STAGE_2",
        "RELATIVE_STRENGTH": 10.0,
    }
    defaults.update(overrides)
    return pd.DataFrame([defaults])


class MomentumScreenerTests(unittest.TestCase):
    def test_qualifying_stock_passes_filter_and_gets_score(self):
        df = _make_universe()
        result = momentum_52w_high_screener(df)
        self.assertEqual(len(result), 1)
        self.assertIn("MOMENTUM_SCORE", result.columns)
        self.assertGreater(result.iloc[0]["MOMENTUM_SCORE"], 0)

    def test_stock_too_far_from_52w_high_excluded(self):
        """Dist -10% → outside -5 to +0.5 window → filtered out."""
        df = _make_universe(DIST_FROM_52W_HIGH_PCT=-10.0)
        result = momentum_52w_high_screener(df)
        self.assertTrue(result.empty)

    def test_declining_sma50_slope_excluded(self):
        """Negative SMA50 slope → not in uptrend → excluded."""
        df = _make_universe(SMA_50_SLOPE=-0.02)
        result = momentum_52w_high_screener(df)
        self.assertTrue(result.empty)

    def test_low_rs_rank_excluded(self):
        """RS rank below 75th percentile → excluded."""
        df = _make_universe(RS_RANK_PCT=0.60)
        result = momentum_52w_high_screener(df)
        self.assertTrue(result.empty)

    def test_low_volume_ratio_excluded(self):
        """VOL_RATIO < 1.0 → contracting volume → excluded."""
        df = _make_universe(VOL_RATIO=0.80)
        result = momentum_52w_high_screener(df)
        self.assertTrue(result.empty)

    def test_rsi_above_80_excluded(self):
        """Overbought RSI excluded (too late in the move)."""
        df = _make_universe(RSI=85.0)
        result = momentum_52w_high_screener(df)
        self.assertTrue(result.empty)

    def test_rsi_below_50_excluded(self):
        """RSI below 50 → not yet in confirmed uptrend → excluded."""
        df = _make_universe(RSI=45.0)
        result = momentum_52w_high_screener(df)
        self.assertTrue(result.empty)

    def test_results_sorted_descending_by_momentum_score(self):
        """Multiple qualifying stocks ranked by MOMENTUM_SCORE descending."""
        rows = [
            _make_universe(SYMBOL="AA", RS_RANK_PCT=0.95, VOL_RATIO=2.0, RSI=70, DIST_FROM_52W_HIGH_PCT=-0.5),
            _make_universe(SYMBOL="BB", RS_RANK_PCT=0.76, VOL_RATIO=1.1, RSI=52, DIST_FROM_52W_HIGH_PCT=-4.5),
        ]
        df = pd.concat(rows, ignore_index=True)
        result = momentum_52w_high_screener(df)
        self.assertEqual(len(result), 2)
        self.assertGreater(result.iloc[0]["MOMENTUM_SCORE"], result.iloc[1]["MOMENTUM_SCORE"])
        self.assertEqual(result.iloc[0]["SYMBOL"], "AA")

    def test_fallback_to_volume_ratio_column_name(self):
        """Screener works with VOLUME_RATIO (sector_rotation_report naming convention)."""
        df = _make_universe()
        df = df.rename(columns={"VOL_RATIO": "VOLUME_RATIO"})
        df = df.drop(columns=["VOL_RATIO"], errors="ignore")
        result = momentum_52w_high_screener(df)
        self.assertEqual(len(result), 1)

    def test_empty_input_returns_empty(self):
        result = momentum_52w_high_screener(pd.DataFrame())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertTrue(result.empty)

    def test_html_contains_candidate_symbol_and_score(self):
        df = _make_universe()
        screened = momentum_52w_high_screener(df)
        html = build_momentum_screener_tab_html(screened)
        self.assertIn("TEST", html)
        self.assertIn("52W High Momentum", html)

    def test_html_empty_result_shows_no_candidates_message(self):
        html = build_momentum_screener_tab_html(pd.DataFrame())
        self.assertIn("No stocks matched", html)
        self.assertIn("52W High Momentum", html)


if __name__ == "__main__":
    unittest.main()
