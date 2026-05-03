"""Tests for screeners.py — A1 Stage Analysis and A3 52W Momentum."""
import unittest

import pandas as pd

from screeners import (
    momentum_52w_high_screener,
    build_momentum_screener_tab_html,
    run_stage_screener,
    turnaround_screener,
    compute_max_drawdown_column,
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


class TurnaroundScreenerTests(unittest.TestCase):
    def _make_candidates(self, **overrides) -> pd.DataFrame:
        defaults = {
            "SYMBOL": "TURN",
            "COMPANY_NAME": "Turnaround Co",
            "SECTOR_NAME": "Metal",
            "CLOSE": 70.0,
            "CURRENT_PRICE": 70.0,
            "SMA_50": 65.0,           # price > SMA50 ✓
            "RSI": 48.0,              # 35–58 ✓
            "SUPERTREND_STATE": "BULLISH",
            "STAGE": "STAGE_2",
            "MAX_DRAWDOWN_PCT": -38.0,  # < -30 ✓
            "FIFTY_TWO_WEEK_HIGH": 120.0,
            "FIFTY_TWO_WEEK_LOW": 60.0,
        }
        defaults.update(overrides)
        return pd.DataFrame([defaults])

    def test_qualifying_stock_passes_all_criteria(self):
        df = self._make_candidates()
        result = turnaround_screener(df)
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["TURNAROUND_SIGNAL"], "EARLY_RECOVERY")

    def test_shallow_drawdown_excluded(self):
        """-20% drawdown — not deep enough."""
        df = self._make_candidates(MAX_DRAWDOWN_PCT=-20.0)
        self.assertTrue(turnaround_screener(df).empty)

    def test_price_below_sma50_excluded(self):
        """Still below SMA50 → not in recovery yet."""
        df = self._make_candidates(CLOSE=60.0, CURRENT_PRICE=60.0, SMA_50=65.0)
        self.assertTrue(turnaround_screener(df).empty)

    def test_rsi_too_high_excluded(self):
        """RSI 65 → already in full upswing, not early turnaround."""
        df = self._make_candidates(RSI=65.0)
        self.assertTrue(turnaround_screener(df).empty)

    def test_rsi_too_low_excluded(self):
        """RSI 30 → still in downtrend."""
        df = self._make_candidates(RSI=30.0)
        self.assertTrue(turnaround_screener(df).empty)

    def test_bearish_supertrend_excluded(self):
        df = self._make_candidates(SUPERTREND_STATE="BEARISH")
        self.assertTrue(turnaround_screener(df).empty)

    def test_sorted_by_rsi_ascending(self):
        """Lower RSI (earlier recovery) ranked first."""
        rows = pd.concat([
            self._make_candidates(SYMBOL="AA", RSI=55.0),
            self._make_candidates(SYMBOL="BB", RSI=37.0),
        ], ignore_index=True)
        result = turnaround_screener(rows)
        self.assertEqual(len(result), 2)
        self.assertEqual(result.iloc[0]["SYMBOL"], "BB")

    def test_neutral_supertrend_qualifies(self):
        df = self._make_candidates(SUPERTREND_STATE="NEUTRAL")
        self.assertEqual(len(turnaround_screener(df)), 1)

    def test_compute_max_drawdown_column_from_history(self):
        """compute_max_drawdown_column fills MAX_DRAWDOWN_PCT from price history."""
        from screeners import compute_max_drawdown_column
        import pandas as pd

        # Stock goes from 100 → 50 → 70 over 30 days (drawdown = -50%)
        dates = pd.date_range("2026-01-01", periods=30)
        closes = [100] * 10 + [50] * 10 + [70] * 10
        history = pd.DataFrame({
            "SYMBOL": ["S1"] * 30,
            "TIMESTAMP": dates,
            "CLOSE": closes,
        })
        candidates = pd.DataFrame([{
            "SYMBOL": "S1",
            "FIFTY_TWO_WEEK_HIGH": 100.0,
            "FIFTY_TWO_WEEK_LOW": 50.0,
        }])
        result = compute_max_drawdown_column(candidates, history, lookback_days=30)
        self.assertIn("MAX_DRAWDOWN_PCT", result.columns)
        self.assertAlmostEqual(result.iloc[0]["MAX_DRAWDOWN_PCT"], -50.0, places=0)

    def test_compute_max_drawdown_fallback_without_history(self):
        """Without history, falls back to 52W low/high ratio."""
        from screeners import compute_max_drawdown_column
        candidates = pd.DataFrame([{
            "SYMBOL": "S1",
            "FIFTY_TWO_WEEK_HIGH": 100.0,
            "FIFTY_TWO_WEEK_LOW": 60.0,
        }])
        result = compute_max_drawdown_column(candidates, history=None)
        self.assertAlmostEqual(result.iloc[0]["MAX_DRAWDOWN_PCT"], -40.0, places=0)

    def test_build_turnaround_tab_html_shows_candidates(self):
        from screeners import build_turnaround_tab_html
        df = self._make_candidates()
        result = turnaround_screener(df)
        html = build_turnaround_tab_html(result)
        self.assertIn("TURN", html)
        self.assertIn("Turnaround Detector", html)
        self.assertIn("-38.0%", html)

    def test_build_turnaround_tab_html_empty_shows_no_candidates(self):
        from screeners import build_turnaround_tab_html
        html = build_turnaround_tab_html(pd.DataFrame())
        self.assertIn("No turnaround candidates", html)


if __name__ == "__main__":
    unittest.main()
