"""Tests for screeners.py — A3 Momentum, A6 Turnaround, A2 Darvas Box."""
import sys
import os
import unittest
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from screeners import (
    momentum_52w_high_screener,
    build_momentum_screener_tab_html,
    compute_max_drawdown_column,
    turnaround_screener,
    build_turnaround_tab_html,
    _compute_darvas_for_symbol,
    run_darvas_screener,
    build_darvas_tab_html,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _momentum_row(**kwargs) -> dict:
    """Return a single-row dict with sane momentum defaults, overridden by kwargs."""
    base = {
        "SYMBOL": "TEST",
        "COMPANY_NAME": "Test Corp",
        "SECTOR_NAME": "Finance",
        "CURRENT_PRICE": 100.0,
        "DIST_FROM_52W_HIGH_PCT": -2.0,
        "SMA_50_SLOPE": 0.5,
        "RS_RANK_PCT": 0.80,
        "VOL_RATIO": 1.2,
        "RSI": 60.0,
        "STAGE": "STAGE_2",
    }
    base.update(kwargs)
    return base


def _momentum_df(*rows, **single_kwargs) -> pd.DataFrame:
    """Single default row when called with no args; kwargs override defaults; or pass dicts."""
    if rows:
        return pd.DataFrame([_momentum_row(**r) for r in rows])
    return pd.DataFrame([_momentum_row(**single_kwargs)])


def _turnaround_row(**kwargs) -> dict:
    base = {
        "SYMBOL": "TEST",
        "COMPANY_NAME": "Test Corp",
        "SECTOR_NAME": "Finance",
        "CURRENT_PRICE": 55.0,
        "SMA_50": 50.0,
        "RSI": 45.0,
        "SUPERTREND_STATE": "BULLISH",
        "MAX_DRAWDOWN_PCT": -40.0,
        "STAGE": "STAGE_1",
    }
    base.update(kwargs)
    return base


def _turnaround_df(*rows, **single_kwargs) -> pd.DataFrame:
    """Single default row when called with no args; kwargs override defaults; or pass dicts."""
    if rows:
        return pd.DataFrame([_turnaround_row(**r) for r in rows])
    return pd.DataFrame([_turnaround_row(**single_kwargs)])


def _darvas_hist(
    n_pre: int = 10,
    peak: float = 100.0,
    post_prices=None,
    last_close: float | None = None,
    last_vol: float = 10_000.0,
    extra_high_after_peak: bool = False,
) -> pd.DataFrame:
    """Build a minimal price-history DataFrame for Darvas tests.

    Structure
    ---------
    - n_pre rows rising from ~90 → peak (historical, before the box peak)
    - post_prices rows forming the consolidation (historical)
    - 1 row = today (last_close / last_vol)
    """
    pre = list(np.linspace(90.0, peak, n_pre))
    if post_prices is None:
        post_prices = [97.5, 98.0, 97.0, 98.5, 97.8, 98.2, 97.3, 97.9, 97.6]  # 9 days
    if extra_high_after_peak:
        post_prices = list(post_prices)
        post_prices[2] = peak * 1.01  # inject a new high to invalidate box

    hist_closes = pre + list(post_prices)
    today_close = last_close if last_close is not None else post_prices[-1]
    all_closes = hist_closes + [today_close]

    n = len(all_closes)
    normal_vol = 10_000.0
    vols = [normal_vol] * (n - 1) + [last_vol]

    return pd.DataFrame({
        "SYMBOL": ["SYM"] * n,
        "TIMESTAMP": pd.date_range("2024-01-01", periods=n),
        "CLOSE": all_closes,
        "TOTTRDQTY": vols,
    })


# ---------------------------------------------------------------------------
# A3 — Momentum Screener
# ---------------------------------------------------------------------------

class MomentumScreenerTests(unittest.TestCase):

    def test_empty_candidates_returns_empty(self):
        result = momentum_52w_high_screener(pd.DataFrame())
        self.assertTrue(result.empty)

    def test_stock_within_5pct_included(self):
        df = _momentum_df(DIST_FROM_52W_HIGH_PCT=-2.0)
        result = momentum_52w_high_screener(df)
        self.assertEqual(len(result), 1)

    def test_stock_more_than_5pct_below_high_excluded(self):
        df = _momentum_df(DIST_FROM_52W_HIGH_PCT=-6.0)
        result = momentum_52w_high_screener(df)
        self.assertTrue(result.empty)

    def test_negative_sma50_slope_excluded(self):
        df = _momentum_df(SMA_50_SLOPE=-0.1)
        result = momentum_52w_high_screener(df)
        self.assertTrue(result.empty)

    def test_low_rs_rank_excluded(self):
        df = _momentum_df(RS_RANK_PCT=0.50)
        result = momentum_52w_high_screener(df)
        self.assertTrue(result.empty)

    def test_low_volume_excluded(self):
        df = _momentum_df(VOL_RATIO=0.9)
        result = momentum_52w_high_screener(df)
        self.assertTrue(result.empty)

    def test_rsi_below_50_excluded(self):
        df = _momentum_df(RSI=48.0)
        result = momentum_52w_high_screener(df)
        self.assertTrue(result.empty)

    def test_rsi_above_80_excluded(self):
        df = _momentum_df(RSI=82.0)
        result = momentum_52w_high_screener(df)
        self.assertTrue(result.empty)

    def test_momentum_score_in_range(self):
        df = _momentum_df()
        result = momentum_52w_high_screener(df)
        self.assertFalse(result.empty)
        score = result.iloc[0]["MOMENTUM_SCORE"]
        self.assertGreater(score, 0)
        self.assertLessEqual(score, 1.0)

    def test_sorted_by_score_descending(self):
        df = _momentum_df(
            {"SYMBOL": "A", "RS_RANK_PCT": 0.95},
            {"SYMBOL": "B", "RS_RANK_PCT": 0.76},
        )
        result = momentum_52w_high_screener(df)
        if len(result) == 2:
            self.assertGreaterEqual(
                result.iloc[0]["MOMENTUM_SCORE"],
                result.iloc[1]["MOMENTUM_SCORE"],
            )

    def test_volume_ratio_fallback_column(self):
        row = _momentum_row()
        del row["VOL_RATIO"]
        row["VOLUME_RATIO"] = 1.5
        df = pd.DataFrame([row])
        result = momentum_52w_high_screener(df)
        self.assertEqual(len(result), 1)

    def test_html_renders_string(self):
        df = _momentum_df()
        result_df = momentum_52w_high_screener(df)
        html = build_momentum_screener_tab_html(result_df)
        self.assertIsInstance(html, str)
        self.assertIn("Momentum", html)

    def test_html_empty_fallback(self):
        html = build_momentum_screener_tab_html(pd.DataFrame())
        self.assertIn("No stocks matched", html)


# ---------------------------------------------------------------------------
# A6 — Turnaround Detector
# ---------------------------------------------------------------------------

class TurnaroundScreenerTests(unittest.TestCase):

    def test_empty_returns_empty(self):
        result = turnaround_screener(pd.DataFrame())
        self.assertTrue(result.empty)

    def test_valid_candidate_included(self):
        df = _turnaround_df()
        result = turnaround_screener(df)
        self.assertEqual(len(result), 1)

    def test_shallow_drawdown_excluded(self):
        df = _turnaround_df(MAX_DRAWDOWN_PCT=-20.0)
        result = turnaround_screener(df)
        self.assertTrue(result.empty)

    def test_price_below_sma50_excluded(self):
        df = _turnaround_df(CURRENT_PRICE=45.0, SMA_50=50.0)
        result = turnaround_screener(df)
        self.assertTrue(result.empty)

    def test_rsi_too_low_excluded(self):
        df = _turnaround_df(RSI=30.0)
        result = turnaround_screener(df)
        self.assertTrue(result.empty)

    def test_rsi_too_high_excluded(self):
        df = _turnaround_df(RSI=62.0)
        result = turnaround_screener(df)
        self.assertTrue(result.empty)

    def test_bearish_supertrend_excluded(self):
        df = _turnaround_df(SUPERTREND_STATE="BEARISH")
        result = turnaround_screener(df)
        self.assertTrue(result.empty)

    def test_neutral_supertrend_included(self):
        df = _turnaround_df(SUPERTREND_STATE="NEUTRAL")
        result = turnaround_screener(df)
        self.assertEqual(len(result), 1)

    def test_sorted_by_rsi_ascending(self):
        df = _turnaround_df(
            {"SYMBOL": "A", "RSI": 55.0},
            {"SYMBOL": "B", "RSI": 37.0},
        )
        result = turnaround_screener(df)
        self.assertEqual(len(result), 2)
        self.assertLessEqual(result.iloc[0]["RSI"], result.iloc[1]["RSI"])

    def test_turnaround_signal_set(self):
        df = _turnaround_df()
        result = turnaround_screener(df)
        self.assertEqual(result.iloc[0]["TURNAROUND_SIGNAL"], "EARLY_RECOVERY")

    def test_compute_max_drawdown_no_history_fallback(self):
        df = pd.DataFrame([{
            "SYMBOL": "TEST",
            "FIFTY_TWO_WEEK_HIGH": 100.0,
            "FIFTY_TWO_WEEK_LOW": 60.0,
        }])
        result = compute_max_drawdown_column(df, history=None)
        self.assertIn("MAX_DRAWDOWN_PCT", result.columns)
        self.assertAlmostEqual(result.iloc[0]["MAX_DRAWDOWN_PCT"], -40.0, places=0)

    def test_html_renders_string(self):
        df = _turnaround_df()
        result_df = turnaround_screener(df)
        html = build_turnaround_tab_html(result_df)
        self.assertIsInstance(html, str)
        self.assertIn("Turnaround", html)

    def test_html_empty_fallback(self):
        html = build_turnaround_tab_html(pd.DataFrame())
        self.assertIn("No turnaround candidates", html)


# ---------------------------------------------------------------------------
# A2 — Darvas Box Screener
# ---------------------------------------------------------------------------

class DarvasBoxTests(unittest.TestCase):

    def test_empty_history_returns_none(self):
        result = _compute_darvas_for_symbol(pd.DataFrame())
        self.assertIsNone(result)

    def test_too_short_history_returns_none(self):
        hist = _darvas_hist(n_pre=5, post_prices=[97.0, 98.0, 97.5])
        # 5 pre + 3 post + 1 today = 9 rows → < 11 → None
        result = _compute_darvas_for_symbol(hist)
        self.assertIsNone(result)

    def test_valid_box_returns_in_box(self):
        hist = _darvas_hist(last_close=97.0)  # today inside the box
        result = _compute_darvas_for_symbol(hist)
        self.assertIsNotNone(result)
        self.assertEqual(result["DARVAS_STATUS"], "IN_BOX")

    def test_breakout_confirmed_when_last_close_above_box_top(self):
        # today closes 1.5% above box_top=100 with 50% volume surge
        hist = _darvas_hist(last_close=101.5, last_vol=15_000.0)
        result = _compute_darvas_for_symbol(hist)
        self.assertIsNotNone(result)
        self.assertEqual(result["DARVAS_STATUS"], "BREAKOUT")
        self.assertTrue(result["BREAKOUT_CONFIRMED"])

    def test_near_top_within_2pct(self):
        # today within 2% below box_top but not above it
        hist = _darvas_hist(last_close=98.5, last_vol=10_000.0)
        result = _compute_darvas_for_symbol(hist)
        self.assertIsNotNone(result)
        self.assertEqual(result["DARVAS_STATUS"], "NEAR_TOP")

    def test_peak_too_recent_returns_none(self):
        # If the peak is in the last 3 positions of hist_closes (<3 consolidation days) → None.
        # Build hist where closes rise monotonically right up to the last historical bar.
        n = 13  # 10 pre + 2 surging + 1 today
        closes = list(np.linspace(90.0, 102.0, n))
        df = pd.DataFrame({
            "SYMBOL": ["SYM"] * n,
            "TIMESTAMP": pd.date_range("2024-01-01", periods=n),
            "CLOSE": closes,
            "TOTTRDQTY": [10_000.0] * n,
        })
        # hist_closes = closes[:-1] (12 rows); argmax at index 11; 11 >= 12-3=9 → None
        result = _compute_darvas_for_symbol(df)
        self.assertIsNone(result)

    def test_box_too_wide_rejected(self):
        # post_prices drop 35% below peak → width > 30%
        post = [65.0, 66.0, 65.5, 66.5, 65.8]
        hist = _darvas_hist(post_prices=post, last_close=66.0)
        result = _compute_darvas_for_symbol(hist)
        self.assertIsNone(result)

    def test_box_too_narrow_rejected(self):
        # post_prices within 0.3% of peak → width < 0.5%
        post = [99.8, 99.9, 99.85, 99.82, 99.88]
        hist = _darvas_hist(post_prices=post, last_close=99.8)
        result = _compute_darvas_for_symbol(hist)
        self.assertIsNone(result)

    def test_run_darvas_screener_returns_dataframe(self):
        hist = _darvas_hist(last_close=97.0)
        hist["SYMBOL"] = "SYM"
        candidates = pd.DataFrame([{
            "SYMBOL": "SYM",
            "COMPANY_NAME": "Test Co",
            "SECTOR_NAME": "Tech",
            "CURRENT_PRICE": 97.0,
            "HI_52_WK": 102.0,
            "INVESTMENT_SCORE": 70,
        }])
        result = run_darvas_screener(candidates, hist)
        self.assertIsInstance(result, pd.DataFrame)
        if not result.empty:
            self.assertIn("DARVAS_STATUS", result.columns)

    def test_html_renders_string(self):
        candidates = pd.DataFrame([{
            "SYMBOL": "SYM",
            "DARVAS_STATUS": "IN_BOX",
            "BOX_TOP": 100.0,
            "BOX_BOTTOM": 97.0,
            "BOX_WIDTH_PCT": 3.09,
            "DAYS_IN_BOX": 9,
            "BREAKOUT_CONFIRMED": False,
            "NEAR_BOX_TOP": False,
            "VS_TOP_PCT": -3.0,
            "BOX_STOP_LOSS": 96.0,
            "HI_52_WK": 102.0,
            "INVESTMENT_SCORE": 65,
            "COMPANY_NAME": "Test Co",
            "SECTOR": "Tech",
            "CURRENT_PRICE": 97.0,
        }])
        html = build_darvas_tab_html(candidates)
        self.assertIsInstance(html, str)
        self.assertIn("Darvas Box", html)

    def test_html_empty_fallback(self):
        html = build_darvas_tab_html(pd.DataFrame())
        self.assertIn("No Darvas boxes detected", html)


if __name__ == "__main__":
    unittest.main()
