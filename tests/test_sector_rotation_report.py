import unittest
from pathlib import Path

import pandas as pd

from sector_rotation_report import (
    calculate_peak_resilience,
    classify_consolidation_breakout,
    compute_supertrend,
    merge_fundamental_scores,
    report_output_paths,
    rank_peak_resilience_stocks,
    rank_rotating_sectors,
    rank_stock_candidates,
)


class SectorRotationReportTests(unittest.TestCase):
    def test_rank_rotating_sectors_prefers_relative_strength_and_positive_short_term_returns(self):
        index_metrics = pd.DataFrame(
            [
                {"SYMBOL": "Nifty Defence", "RET_5D": 2.0, "RET_1M": 20.0, "RET_3M": 15.0, "RET_6M": 10.0},
                {"SYMBOL": "Nifty IT", "RET_5D": -5.0, "RET_1M": -2.0, "RET_3M": -20.0, "RET_6M": -18.0},
                {"SYMBOL": "Nifty 500", "RET_5D": -1.0, "RET_1M": 8.0, "RET_3M": 0.0, "RET_6M": -4.0},
            ]
        )

        ranked = rank_rotating_sectors(index_metrics, benchmark_symbol="Nifty 500")

        self.assertEqual(ranked.iloc[0]["SYMBOL"], "Nifty Defence")
        self.assertGreater(ranked.iloc[0]["ROTATION_SCORE"], ranked.iloc[-1]["ROTATION_SCORE"])
        self.assertAlmostEqual(ranked.iloc[0]["RS_1M"], 12.0)

    def test_compute_supertrend_marks_persistent_uptrend_as_bullish(self):
        prices = pd.DataFrame(
            {
                "HIGH": [10, 11, 12, 13, 14, 15, 16, 17],
                "LOW": [9, 10, 11, 12, 13, 14, 15, 16],
                "CLOSE": [9.5, 10.8, 11.7, 12.8, 13.6, 14.7, 15.8, 16.7],
            }
        )

        result = compute_supertrend(prices, period=3, multiplier=1.5)

        self.assertEqual(result["SUPERTREND_DIRECTION"].iloc[-1], 1)
        self.assertEqual(result["SUPERTREND_STATE"].iloc[-1], "BULLISH")

    def test_classify_consolidation_breakout_identifies_volume_breakout(self):
        history = pd.DataFrame(
            {
                "HIGH": [100, 101, 100.5, 101.2, 101, 102.5],
                "LOW": [98, 98.5, 98.2, 98.7, 98.6, 100.8],
                "CLOSE": [99, 100, 99.8, 100.5, 100.1, 102.2],
                "TOTTRDQTY": [1000, 1050, 950, 980, 1020, 2600],
            }
        )

        pattern = classify_consolidation_breakout(history, lookback=5, width_threshold=0.05, volume_multiplier=1.5)

        self.assertTrue(pattern["IS_CONSOLIDATION_BREAKOUT"])
        self.assertEqual(pattern["PATTERN"], "CONSOLIDATION_BREAKOUT")

    def test_rank_stock_candidates_blends_technical_rs_fundamental_and_pattern(self):
        stocks = pd.DataFrame(
            [
                {
                    "SYMBOL": "AAA",
                    "SECTOR_NAME": "Defence",
                    "TECHNICAL_SCORE": 80,
                    "RELATIVE_STRENGTH": 30,
                    "ENHANCED_FUND_SCORE": 70,
                    "TRADING_SIGNAL": "BUY",
                    "PATTERN": "CONSOLIDATION_BREAKOUT",
                    "SUPERTREND_STATE": "BULLISH",
                },
                {
                    "SYMBOL": "BBB",
                    "SECTOR_NAME": "Defence",
                    "TECHNICAL_SCORE": 60,
                    "RELATIVE_STRENGTH": 5,
                    "ENHANCED_FUND_SCORE": 80,
                    "TRADING_SIGNAL": "HOLD",
                    "PATTERN": "BASE_BUILDING",
                    "SUPERTREND_STATE": "BEARISH",
                },
            ]
        )

        ranked = rank_stock_candidates(stocks)

        self.assertEqual(ranked.iloc[0]["SYMBOL"], "AAA")
        self.assertGreater(ranked.iloc[0]["INVESTMENT_SCORE"], ranked.iloc[1]["INVESTMENT_SCORE"])

    def test_rank_stock_candidates_accepts_pre_enrichment_rows_without_pattern_columns(self):
        stocks = pd.DataFrame(
            [
                {
                    "SYMBOL": "AAA",
                    "SECTOR_NAME": "Defence",
                    "TECHNICAL_SCORE": 70,
                    "RELATIVE_STRENGTH": 20,
                    "ENHANCED_FUND_SCORE": 65,
                    "TRADING_SIGNAL": "BUY",
                }
            ]
        )

        ranked = rank_stock_candidates(stocks)

        self.assertEqual(ranked.iloc[0]["SYMBOL"], "AAA")
        self.assertIn("INVESTMENT_SCORE", ranked.columns)

    def test_merge_fundamental_scores_fills_missing_scores_without_overwriting_existing(self):
        analysis = pd.DataFrame(
            [
                {
                    "SYMBOL": "AAA",
                    "ENHANCED_FUND_SCORE": None,
                    "EARNINGS_QUALITY": None,
                    "SALES_GROWTH": None,
                    "FINANCIAL_STRENGTH": None,
                    "INSTITUTIONAL_BACKING": None,
                },
                {
                    "SYMBOL": "BBB",
                    "ENHANCED_FUND_SCORE": 72.0,
                    "EARNINGS_QUALITY": 70.0,
                    "SALES_GROWTH": 71.0,
                    "FINANCIAL_STRENGTH": 73.0,
                    "INSTITUTIONAL_BACKING": 74.0,
                },
            ]
        )
        fallback = pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "ENHANCED_FUND_SCORE": 61.0,
                    "EARNINGS_QUALITY": 62.0,
                    "SALES_GROWTH": 63.0,
                    "FINANCIAL_STRENGTH": 64.0,
                    "INSTITUTIONAL_BACKING": 65.0,
                },
                {
                    "symbol": "BBB",
                    "ENHANCED_FUND_SCORE": 55.0,
                    "EARNINGS_QUALITY": 56.0,
                    "SALES_GROWTH": 57.0,
                    "FINANCIAL_STRENGTH": 58.0,
                    "INSTITUTIONAL_BACKING": 59.0,
                },
            ]
        )

        merged = merge_fundamental_scores(analysis, fallback)

        self.assertEqual(float(merged.loc[merged["SYMBOL"] == "AAA", "ENHANCED_FUND_SCORE"].iloc[0]), 61.0)
        self.assertEqual(float(merged.loc[merged["SYMBOL"] == "AAA", "SALES_GROWTH"].iloc[0]), 63.0)
        self.assertEqual(float(merged.loc[merged["SYMBOL"] == "BBB", "ENHANCED_FUND_SCORE"].iloc[0]), 72.0)

    def test_calculate_peak_resilience_measures_high_low_recovery_and_speed(self):
        history = pd.DataFrame(
            {
                "TIMESTAMP": pd.date_range("2025-01-01", periods=6, freq="D"),
                "HIGH": [100, 90, 80, 95, 98, 101],
                "LOW": [90, 70, 60, 80, 90, 96],
                "CLOSE": [95, 75, 65, 90, 96, 100],
                "TOTTRDQTY": [1000, 1000, 1000, 1000, 1000, 1000],
            }
        )

        metrics = calculate_peak_resilience(history, lookback=6)

        self.assertAlmostEqual(metrics["DRAWDOWN_FROM_52W_HIGH_PCT"], -0.99, places=2)
        self.assertAlmostEqual(metrics["RECOVERY_FROM_52W_LOW_PCT"], 66.67, places=2)
        self.assertEqual(metrics["DAYS_SINCE_52W_LOW"], 3)
        self.assertTrue(metrics["WITHIN_20PCT_OF_HIGH"])
        self.assertTrue(metrics["NEAR_OR_ABOVE_52W_HIGH"])

    def test_rank_peak_resilience_stocks_filters_for_resilience_and_near_high(self):
        stocks = pd.DataFrame(
            [
                {
                    "SYMBOL": "FAST",
                    "TECHNICAL_SCORE": 75,
                    "RELATIVE_STRENGTH": 20,
                    "ENHANCED_FUND_SCORE": 65,
                    "DRAWDOWN_FROM_52W_HIGH_PCT": -2,
                    "RECOVERY_FROM_52W_LOW_PCT": 90,
                    "DAYS_SINCE_52W_LOW": 10,
                    "RECOVERY_SPEED_SCORE": 9,
                    "NEAR_OR_ABOVE_52W_HIGH": True,
                    "WITHIN_20PCT_OF_HIGH": True,
                },
                {
                    "SYMBOL": "DEEP",
                    "TECHNICAL_SCORE": 90,
                    "RELATIVE_STRENGTH": 40,
                    "ENHANCED_FUND_SCORE": 80,
                    "DRAWDOWN_FROM_52W_HIGH_PCT": -25,
                    "RECOVERY_FROM_52W_LOW_PCT": 95,
                    "DAYS_SINCE_52W_LOW": 10,
                    "RECOVERY_SPEED_SCORE": 9.5,
                    "NEAR_OR_ABOVE_52W_HIGH": False,
                    "WITHIN_20PCT_OF_HIGH": False,
                },
            ]
        )

        ranked = rank_peak_resilience_stocks(stocks)

        self.assertEqual(list(ranked["SYMBOL"]), ["FAST"])
        self.assertIn("PEAK_RESILIENCE_SCORE", ranked.columns)

    def test_report_output_paths_use_sector_rotation_year_folder_and_latest_aliases(self):
        paths = report_output_paths(pd.Timestamp("2026-05-02 01:17:36"))
        root = Path.cwd()

        self.assertEqual(paths.markdown.relative_to(root).as_posix(), "reports/sector_rotation/2026/Sector_Rotation_Report_20260502.md")
        self.assertEqual(paths.html.relative_to(root).as_posix(), "reports/sector_rotation/2026/Sector_Rotation_Report_20260502.html")
        self.assertEqual(paths.latest_markdown.relative_to(root).as_posix(), "reports/latest/sector_rotation.md")
        self.assertEqual(paths.latest_html.relative_to(root).as_posix(), "reports/latest/sector_rotation.html")


if __name__ == "__main__":
    unittest.main()
