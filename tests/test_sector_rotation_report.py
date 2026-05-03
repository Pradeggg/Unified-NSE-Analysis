import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

import sector_rotation_report
from sector_rotation_report import (
    _generate_rule_based_market_brief,
    _log_signals,
    calculate_peak_resilience,
    classify_consolidation_breakout,
    compute_supertrend,
    merge_fundamental_scores,
    report_output_paths,
    render_html_interactive,
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

    def test_rank_stock_candidates_assigns_action_buckets_from_setup_quality(self):
        stocks = pd.DataFrame(
            [
                {
                    "SYMBOL": "BREAKOUT",
                    "SECTOR_NAME": "Defence",
                    "TECHNICAL_SCORE": 82,
                    "RELATIVE_STRENGTH": 35,
                    "ENHANCED_FUND_SCORE": 74,
                    "TRADING_SIGNAL": "BUY",
                    "PATTERN": "CONSOLIDATION_BREAKOUT",
                    "VOLUME_RATIO": 2.1,
                    "RSI": 63,
                    "RET_5D": 2,
                    "RET_1M": 11,
                    "DRAWDOWN_FROM_52W_HIGH_PCT": -2,
                    "SUPERTREND_STATE": "BULLISH",
                },
                {
                    "SYMBOL": "EXTENDED",
                    "SECTOR_NAME": "Defence",
                    "TECHNICAL_SCORE": 78,
                    "RELATIVE_STRENGTH": 28,
                    "ENHANCED_FUND_SCORE": 68,
                    "TRADING_SIGNAL": "BUY",
                    "PATTERN": "TRENDING_OR_CHOPPY",
                    "VOLUME_RATIO": 1.0,
                    "RSI": 76,
                    "RET_5D": 6,
                    "RET_1M": 20,
                    "DRAWDOWN_FROM_52W_HIGH_PCT": -3,
                    "SUPERTREND_STATE": "BULLISH",
                },
                {
                    "SYMBOL": "WEAK",
                    "SECTOR_NAME": "Defence",
                    "TECHNICAL_SCORE": 45,
                    "RELATIVE_STRENGTH": -8,
                    "ENHANCED_FUND_SCORE": 55,
                    "TRADING_SIGNAL": "SELL",
                    "PATTERN": "TRENDING_OR_CHOPPY",
                    "VOLUME_RATIO": 0.8,
                    "RSI": 42,
                    "RET_5D": -4,
                    "RET_1M": -8,
                    "DRAWDOWN_FROM_52W_HIGH_PCT": -18,
                    "SUPERTREND_STATE": "BEARISH",
                },
            ]
        )

        ranked = rank_stock_candidates(stocks).set_index("SYMBOL")

        self.assertEqual(ranked.loc["BREAKOUT", "SETUP_CLASS"], "LEADER_BREAKOUT")
        self.assertEqual(ranked.loc["BREAKOUT", "ACTION_BUCKET"], "BUY_WATCH")
        self.assertEqual(ranked.loc["EXTENDED", "ACTION_BUCKET"], "WAIT_FOR_PULLBACK")
        self.assertEqual(ranked.loc["WEAK", "ACTION_BUCKET"], "AVOID")
        self.assertTrue(ranked["ACTION_REASON"].str.len().gt(0).all())

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
        self.assertEqual(paths.pdf.relative_to(root).as_posix(), "reports/sector_rotation/2026/Sector_Rotation_Report_20260502.pdf")
        self.assertEqual(paths.latest_markdown.relative_to(root).as_posix(), "reports/latest/sector_rotation.md")
        self.assertEqual(paths.latest_html.relative_to(root).as_posix(), "reports/latest/sector_rotation.html")
        self.assertEqual(paths.latest_pdf.relative_to(root).as_posix(), "reports/latest/sector_rotation.pdf")

    def test_log_signals_persists_insider_alert_context(self):
        candidates = pd.DataFrame(
            [
                {
                    "SYMBOL": "ABC",
                    "SECTOR_NAME": "Defence",
                    "COMPANY_NAME": "ABC Ltd",
                    "TRADING_SIGNAL": "BUY",
                    "SETUP_CLASS": "LEADER_BREAKOUT",
                    "ACTION_BUCKET": "BUY_WATCH",
                    "ACTION_REASON": "Breakout with institutional context",
                    "INVESTMENT_SCORE": 78,
                    "TECHNICAL_SCORE": 82,
                    "RSI": 61,
                    "SUPERTREND_STATE": "BULLISH",
                    "CURRENT_PRICE": 123.45,
                    "INSIDER_ALERT": "PROMOTER_BUYING",
                    "INSIDER_SCORE": 2,
                    "INSIDER_DETAIL": "Promoter Buying: ABC Promoter ₹12.3Cr",
                }
            ]
        )

        original_log = sector_rotation_report._SIGNAL_LOG
        try:
            with TemporaryDirectory() as tmp:
                sector_rotation_report._SIGNAL_LOG = Path(tmp) / "signal_log.csv"
                _log_signals(candidates, pd.Timestamp("2026-05-02"), regime="BULL")
                logged = pd.read_csv(sector_rotation_report._SIGNAL_LOG)
        finally:
            sector_rotation_report._SIGNAL_LOG = original_log

        self.assertEqual(logged.loc[0, "insider_alert"], "PROMOTER_BUYING")
        self.assertEqual(logged.loc[0, "insider_score"], 2)
        self.assertEqual(logged.loc[0, "insider_detail"], "Promoter Buying: ABC Promoter ₹12.3Cr")

    def test_html_includes_insider_alert_candidate_even_below_top_five(self):
        sector_rank = pd.DataFrame(
            [
                {
                    "SYMBOL": "NIFTYDEF",
                    "SECTOR_NAME": "Defence",
                    "CLOSE": 1000,
                    "RET_5D": 1,
                    "RET_1M": 5,
                    "RET_3M": 8,
                    "RET_6M": 10,
                    "RS_1M": 2,
                    "ROTATION_SCORE": 10,
                }
            ]
        )
        candidates = pd.DataFrame(
            [
                {
                    "SYMBOL": f"TOP{i}",
                    "COMPANY_NAME": f"Top {i}",
                    "SECTOR_NAME": "Defence",
                    "CURRENT_PRICE": 100 + i,
                    "TRADING_SIGNAL": "HOLD",
                    "SETUP_CLASS": "NEUTRAL",
                    "ACTION_BUCKET": "WATCHLIST",
                    "INVESTMENT_SCORE": 80 - i,
                    "TECHNICAL_SCORE": 70,
                    "ENHANCED_FUND_SCORE": 60,
                    "RELATIVE_STRENGTH": 10,
                    "RSI": 55,
                    "SUPERTREND_STATE": "BULLISH",
                    "PATTERN": "TRENDING_OR_CHOPPY",
                    "VOLUME_RATIO": 1,
                }
                for i in range(5)
            ]
            + [
                {
                    "SYMBOL": "ALERT",
                    "COMPANY_NAME": "Alert Ltd",
                    "SECTOR_NAME": "Defence",
                    "CURRENT_PRICE": 99,
                    "TRADING_SIGNAL": "HOLD",
                    "SETUP_CLASS": "NEUTRAL",
                    "ACTION_BUCKET": "WATCHLIST",
                    "INVESTMENT_SCORE": 50,
                    "TECHNICAL_SCORE": 55,
                    "ENHANCED_FUND_SCORE": 58,
                    "RELATIVE_STRENGTH": 6,
                    "RSI": 52,
                    "SUPERTREND_STATE": "BULLISH",
                    "PATTERN": "TRENDING_OR_CHOPPY",
                    "VOLUME_RATIO": 1,
                    "INSIDER_ALERT": "PROMOTER_BUYING",
                    "INSIDER_SCORE": 2,
                    "INSIDER_DETAIL": "Promoter Buying: Alert Promoter ₹5.0Cr",
                    "NEXT_EVENT": "RESULT_ANNOUNCEMENT",
                    "NEXT_EVENT_DAYS": 3,
                    "EVENT_DETAIL": "Results in 3d (2026-05-05)",
                }
            ]
        )

        html = render_html_interactive(
            sector_rank,
            candidates,
            pd.DataFrame(),
            Path("source.csv"),
            pd.Timestamp("2026-05-02"),
            {"sectors": {}, "stocks": {}, "market_summary": ""},
        )

        self.assertIn("<strong>ALERT</strong>", html)
        self.assertIn("<th>Signals</th>", html)
        self.assertIn("Promo Buy", html)
        self.assertIn("Agent Adda - Market Intelligence Agent", html)
        self.assertIn("Agent adda logo", html)
        self.assertIn("This report is not investment advice", html)
        self.assertIn("learning journey demonstrating how AI and rules-based agents can be applied", html)
        self.assertIn("print-page-header", html)
        self.assertIn("print-page-footer", html)
        self.assertIn("Full Disclaimer &amp; Use Restrictions", html)
        self.assertIn("Agent Adda is not a SEBI-registered investment adviser", html)
        self.assertIn("must not be replicated or used with any intent of trading or recommendation", html)
        self.assertIn("toggleSignals(this,event)", html)
        self.assertIn("<div class=\"sp-label\">Insider</div>", html)
        self.assertIn("<div class=\"sp-label\">Events</div>", html)
        self.assertIn('data-sector="Defence"', html)
        self.assertIn("Results in 3d (2026-05-05)", html)

    def test_html_includes_economic_cycle_banner_and_candidate_cycle_tag(self):
        sector_rank = pd.DataFrame(
            [
                {
                    "SYMBOL": "NIFTYFMCG",
                    "SECTOR_NAME": "FMCG",
                    "CLOSE": 1000,
                    "RET_5D": 1,
                    "RET_1M": 5,
                    "RET_3M": 8,
                    "RET_6M": 10,
                    "RS_1M": 2,
                    "ROTATION_SCORE": 16,
                    "CYCLE_TAG": "CYCLE_FAVOURED",
                    "CYCLE_ADJUSTMENT": 4,
                }
            ]
        )
        candidates = pd.DataFrame(
            [
                {
                    "SYMBOL": "FMCG",
                    "COMPANY_NAME": "FMCG Ltd",
                    "SECTOR_NAME": "FMCG",
                    "CURRENT_PRICE": 100,
                    "TRADING_SIGNAL": "HOLD",
                    "SETUP_CLASS": "NEUTRAL",
                    "ACTION_BUCKET": "WATCHLIST",
                    "INVESTMENT_SCORE": 73,
                    "TECHNICAL_SCORE": 70,
                    "ENHANCED_FUND_SCORE": 60,
                    "RELATIVE_STRENGTH": 10,
                    "RSI": 55,
                    "SUPERTREND_STATE": "BULLISH",
                    "PATTERN": "TRENDING_OR_CHOPPY",
                    "VOLUME_RATIO": 1,
                    "CYCLE_TAG": "CYCLE_FAVOURED",
                    "CYCLE_ADJUSTMENT": 4,
                }
            ]
        )

        html = render_html_interactive(
            sector_rank,
            candidates,
            pd.DataFrame(),
            Path("source.csv"),
            pd.Timestamp("2026-05-02"),
            {"sectors": {}, "stocks": {}, "market_summary": ""},
            cycle_info={
                "cycle_phase": "SLOWDOWN",
                "confidence": 0.72,
                "regime_cycle_alignment": "ALIGNED_RISK_OFF",
                "preferred_sectors": ["FMCG", "Pharma", "IT"],
                "avoid_sectors": ["Metals", "Auto", "Real Estate"],
                "definition": "Risk-off test cycle",
            },
        )

        self.assertIn("Economic Cycle: SLOWDOWN", html)
        self.assertIn("Cycle +4", html)
        self.assertIn("CYCLE FAVOURED", html)

    def test_rule_based_market_brief_captures_mixed_risk_context(self):
        sector_rank = pd.DataFrame(
            [
                {"SECTOR_NAME": "FMCG & Consumer Goods", "ROTATION_SCORE": 6.5, "RET_1M": 9.6, "RS_1M": 1.3},
                {"SECTOR_NAME": "Pharma & Healthcare", "ROTATION_SCORE": 5.0, "RET_1M": 2.6, "RS_1M": -5.7},
            ]
        )
        candidates = pd.DataFrame(
            [
                {"SYMBOL": "AAA", "SECTOR_NAME": "FMCG & Consumer Goods", "TRADING_SIGNAL": "BUY"},
                {"SYMBOL": "BBB", "SECTOR_NAME": "Pharma & Healthcare", "TRADING_SIGNAL": "HOLD"},
            ]
        )
        breadth = pd.DataFrame(
            [
                {
                    "date": "2026-04-28",
                    "oscillator": 85.9,
                    "signal": "OVERBOUGHT",
                    "trin": 0.39,
                    "trin_signal": "VERY_BULLISH",
                    "divergence": "BULLISH_DIVERGENCE",
                }
            ]
        )

        brief = _generate_rule_based_market_brief(
            sector_rank,
            candidates,
            regime_info={"current_regime": "BEAR_TREND", "confidence": 1.0},
            cycle_info={
                "cycle_phase": "SLOWDOWN",
                "confidence": 0.67,
                "preferred_sectors": ["FMCG", "Pharma", "IT"],
                "avoid_sectors": ["Metals", "Auto", "Real Estate"],
            },
            flow_info={"flow_signal": "DII_ABSORBING", "fii_net_5d": -8048, "dii_net_5d": 3487},
            macro_context="India VIX: 18.5 (rising, +5.9% today); Nifty 50: 23998 (falling, -0.7% today).",
            breadth_history=breadth,
        )

        self.assertIn("market_read", brief)
        self.assertIn("defensive", brief["risk_posture"].lower())
        self.assertIn("BULLISH_DIVERGENCE", brief["market_read"])
        self.assertIn("FMCG", brief["where_to_focus"])

    def test_html_renders_market_brief_sections(self):
        sector_rank = pd.DataFrame(
            [
                {
                    "SYMBOL": "NIFTYFMCG",
                    "SECTOR_NAME": "FMCG",
                    "CLOSE": 1000,
                    "RET_5D": 1,
                    "RET_1M": 5,
                    "RET_3M": 8,
                    "RET_6M": 10,
                    "RS_1M": 2,
                    "ROTATION_SCORE": 16,
                }
            ]
        )
        candidates = pd.DataFrame(
            [
                {
                    "SYMBOL": "AAA",
                    "COMPANY_NAME": "AAA Ltd",
                    "SECTOR_NAME": "FMCG",
                    "CURRENT_PRICE": 100,
                    "TRADING_SIGNAL": "HOLD",
                    "SETUP_CLASS": "NEUTRAL",
                    "ACTION_BUCKET": "WATCHLIST",
                    "INVESTMENT_SCORE": 50,
                    "TECHNICAL_SCORE": 50,
                    "ENHANCED_FUND_SCORE": 50,
                    "RELATIVE_STRENGTH": 0,
                    "RSI": 50,
                    "SUPERTREND_STATE": "BULLISH",
                    "PATTERN": "TRENDING_OR_CHOPPY",
                    "VOLUME_RATIO": 1,
                }
            ]
        )

        html = render_html_interactive(
            sector_rank,
            candidates,
            pd.DataFrame(),
            Path("source.csv"),
            pd.Timestamp("2026-05-02"),
            {
                "sectors": {},
                "stocks": {},
                "market_summary": "",
                "market_brief": {
                    "market_read": "Bear trend with bullish divergence.",
                    "risk_posture": "Defensive, add only on confirmation.",
                    "where_to_focus": "FMCG and Pharma.",
                    "what_would_change_the_view": "Breadth above 50% and regime improves.",
                },
            },
        )

        self.assertIn("Market Brief", html)
        self.assertIn("Market Read", html)
        self.assertIn("Defensive, add only on confirmation.", html)


if __name__ == "__main__":
    unittest.main()
