import math
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from index_intelligence import (
    build_index_coverage,
    build_index_constituent_data,
    build_stock_metric_frame,
    build_top5_index_stocks,
    breadth_context_html,
    classify_breadth_signal,
    cross_index_breadth,
    infer_smallcap_250_constituents,
    render_breadth_html,
    report_output_paths,
)


class IndexIntelligenceTests(unittest.TestCase):
    def test_classify_breadth_signal_all_buckets(self):
        # STRONG: > 70% above 200DMA AND high A/D ratio
        self.assertEqual(classify_breadth_signal(75.0, 2.0, 2.5), "STRONG")
        # HEALTHY: > 70% above 200DMA but A/D ratio below threshold (was a bug: returned NEUTRAL)
        self.assertEqual(classify_breadth_signal(100.0, 0.0, 1.67), "HEALTHY")
        self.assertEqual(classify_breadth_signal(71.0, 0.0, 1.0), "HEALTHY")
        # HEALTHY: 60–70% band
        self.assertEqual(classify_breadth_signal(65.0, 0.0, 1.0), "HEALTHY")
        # NEUTRAL: 45–59%
        self.assertEqual(classify_breadth_signal(52.0, 0.0, 1.0), "NEUTRAL")
        # WEAK: 30–44%
        self.assertEqual(classify_breadth_signal(40.0, 0.0, 1.0), "WEAK")
        # BEARISH: < 30%
        self.assertEqual(classify_breadth_signal(25.0, 5.0, 0.5), "BEARISH")
        # BEARISH: pct_near_52wl > 15 overrides
        self.assertEqual(classify_breadth_signal(75.0, 20.0, 2.0), "BEARISH")

    def test_cross_index_breadth_scores_dma_proximity_and_ad_ratio(self):
        index_data = {
            "NIFTY 50": pd.DataFrame(
                [
                    {"SYMBOL": "AAA", "CLOSE": 100, "SMA_50": 90, "SMA_200": 80, "HIGH_52W": 102, "LOW_52W": 50, "RET_1D": 1.2},
                    {"SYMBOL": "BBB", "CLOSE": 95, "SMA_50": 90, "SMA_200": 85, "HIGH_52W": 96, "LOW_52W": 50, "RET_1D": 0.4},
                    {"SYMBOL": "CCC", "CLOSE": 70, "SMA_50": 75, "SMA_200": 80, "HIGH_52W": 100, "LOW_52W": 68, "RET_1D": -0.5},
                    {"SYMBOL": "DDD", "CLOSE": 60, "SMA_50": 65, "SMA_200": 70, "HIGH_52W": 100, "LOW_52W": 58, "RET_1D": 0.1},
                ]
            )
        }

        result = cross_index_breadth(index_data).set_index("INDEX_NAME")

        self.assertAlmostEqual(result.loc["NIFTY 50", "pct_above_200dma"], 50.0)
        self.assertAlmostEqual(result.loc["NIFTY 50", "pct_above_50dma"], 50.0)
        self.assertAlmostEqual(result.loc["NIFTY 50", "pct_near_52wh"], 50.0)
        self.assertAlmostEqual(result.loc["NIFTY 50", "pct_near_52wl"], 50.0)
        self.assertAlmostEqual(result.loc["NIFTY 50", "ad_ratio"], 3.0)
        self.assertEqual(result.loc["NIFTY 50", "breadth_signal"], "BEARISH")

    def test_build_stock_metric_frame_calculates_latest_dma_and_52w_levels(self):
        dates = pd.date_range("2026-01-01", periods=205, freq="D")
        stock_history = pd.DataFrame(
            {
                "SYMBOL": ["AAA"] * 205,
                "TIMESTAMP": dates,
                "CLOSE": list(range(100, 305)),
                "HIGH": list(range(101, 306)),
                "LOW": list(range(99, 304)),
                "TOTTRDQTY": list(range(1_000, 1_205)),
            }
        )

        metrics = build_stock_metric_frame(stock_history).set_index("SYMBOL")

        self.assertIn("AAA", metrics.index)
        self.assertAlmostEqual(metrics.loc["AAA", "CLOSE"], 304.0)
        self.assertAlmostEqual(metrics.loc["AAA", "SMA_50"], sum(range(255, 305)) / 50)
        self.assertAlmostEqual(metrics.loc["AAA", "SMA_200"], sum(range(105, 305)) / 200)
        self.assertAlmostEqual(metrics.loc["AAA", "HIGH_52W"], 305.0)
        self.assertAlmostEqual(metrics.loc["AAA", "LOW_52W"], 99.0)
        self.assertAlmostEqual(metrics.loc["AAA", "TOTTRDQTY"], 1204.0)
        self.assertGreater(metrics.loc["AAA", "RET_1D"], 0)

    def test_infer_smallcap_250_constituents_ranks_liquid_non_largecap_symbols(self):
        metrics = pd.DataFrame(
            [
                {"SYMBOL": "AAA", "TOTTRDQTY": 999, "CLOSE": 100},
                {"SYMBOL": "BBB", "TOTTRDQTY": 40, "CLOSE": 100},
                {"SYMBOL": "CCC", "TOTTRDQTY": 300, "CLOSE": 100},
                {"SYMBOL": "DDD", "TOTTRDQTY": 200, "CLOSE": 100},
                {"SYMBOL": "EEE", "TOTTRDQTY": 100, "CLOSE": 100},
            ]
        )
        constituents = {
            "NIFTY 50": ["AAA"],
            "NIFTY MIDCAP 150": ["BBB"],
        }

        inferred = infer_smallcap_250_constituents(metrics, constituents, count=2)

        self.assertEqual(inferred, ["CCC", "DDD"])

    def test_render_breadth_html_contains_dashboard_table_and_signal_badges(self):
        breadth = pd.DataFrame(
            [
                {
                    "INDEX_NAME": "NIFTY 50",
                    "constituents": 50,
                    "pct_above_200dma": 72.0,
                    "pct_above_50dma": 68.0,
                    "pct_near_52wh": 24.0,
                    "pct_near_52wl": 2.0,
                    "ad_ratio": 2.1,
                    "breadth_signal": "STRONG",
                }
            ]
        )

        html = render_breadth_html(breadth, pd.Timestamp("2026-05-02"))

        self.assertIn("Cross-Index Breadth Dashboard", html)
        self.assertIn("NIFTY 50", html)
        self.assertIn("STRONG", html)
        self.assertIn("Above 200DMA", html)
        self.assertIn("Index Coverage", html)
        self.assertIn("Top 5 Investment Stocks", html)

        enriched_html = render_breadth_html(
            breadth,
            pd.Timestamp("2026-05-02"),
            coverage=pd.DataFrame(
                [
                    {
                        "INDEX_NAME": "NIFTY AUTO",
                        "CATEGORY": "Sectoral",
                        "API_SYMBOL": "NIFTY AUTO",
                        "constituent_count": 18,
                        "mapping_status": "Available",
                        "included_in_dashboard": True,
                    }
                ]
            ),
            top5_stocks=pd.DataFrame(
                [
                    {
                        "INDEX_NAME": "NIFTY AUTO",
                        "CATEGORY": "Sectoral",
                        "rank": 1,
                        "SYMBOL": "AAA",
                        "CLOSE": 100,
                        "investment_score": 91.2,
                        "above_200dma": True,
                        "dist_from_52w_high_pct": -2.1,
                        "recovery_from_52w_low_pct": 50.0,
                        "TOTTRDQTY": 1000,
                    }
                ]
            ),
        )
        self.assertIn("NIFTY AUTO", enriched_html)
        self.assertIn("AAA", enriched_html)
        self.assertIn("Available", enriched_html)

        no_data_html = render_breadth_html(
            pd.DataFrame(
                [
                    {
                        "INDEX_NAME": "NIFTY SMALLCAP 250",
                        "constituents": 0,
                        "pct_above_200dma": math.nan,
                        "pct_above_50dma": math.nan,
                        "pct_near_52wh": math.nan,
                        "pct_near_52wl": math.nan,
                        "ad_ratio": math.nan,
                        "breadth_signal": "NO_DATA",
                    }
                ]
            ),
            pd.Timestamp("2026-05-02"),
        )
        self.assertIn("<td class=\"num\">NA</td>", no_data_html)
        self.assertNotIn(">nan<", no_data_html)

    def test_breadth_context_html_summarizes_nifty_and_smallcap_divergence(self):
        breadth = pd.DataFrame(
            [
                {"INDEX_NAME": "NIFTY 50", "breadth_signal": "STRONG", "pct_above_200dma": 74, "ad_ratio": 2.2},
                {"INDEX_NAME": "NIFTY SMALLCAP 250", "breadth_signal": "WEAK", "pct_above_200dma": 38, "ad_ratio": 0.8},
            ]
        )

        html = breadth_context_html(breadth)

        self.assertIn("Breadth", html)
        self.assertIn("Selective rotation", html)
        self.assertIn("NIFTY 50", html)
        self.assertIn("Smallcap", html)

    def test_build_index_constituent_data_keeps_missing_targets_as_empty_frames(self):
        metrics = pd.DataFrame(
            [
                {"SYMBOL": "AAA", "CLOSE": 100, "SMA_50": 90, "SMA_200": 80, "HIGH_52W": 105, "LOW_52W": 60, "RET_1D": 1},
            ]
        )
        constituents = {"NIFTY 50": ["AAA"]}

        result = build_index_constituent_data(metrics, constituents, target_indices=["NIFTY 50", "NIFTY SMALLCAP 250"])

        self.assertEqual(len(result["NIFTY 50"]), 1)
        self.assertIn("NIFTY SMALLCAP 250", result)
        self.assertTrue(result["NIFTY SMALLCAP 250"].empty)

    def test_build_index_constituent_data_uses_smlcap_alias(self):
        metrics = pd.DataFrame(
            [
                {"SYMBOL": "CCC", "CLOSE": 100, "SMA_50": 90, "SMA_200": 80, "HIGH_52W": 105, "LOW_52W": 60, "RET_1D": 1},
            ]
        )
        constituents = {"NIFTY SMLCAP 250": ["CCC"]}

        result = build_index_constituent_data(metrics, constituents, target_indices=["NIFTY SMALLCAP 250"])

        self.assertEqual(result["NIFTY SMALLCAP 250"]["SYMBOL"].tolist(), ["CCC"])

    def test_build_index_coverage_classifies_available_inferred_and_missing_indices(self):
        catalog = pd.DataFrame(
            [
                {"INDEX_NAME": "NIFTY AUTO", "CATEGORY": "Sectoral", "API_SYMBOL": "NIFTY AUTO"},
                {"INDEX_NAME": "NIFTY SMALLCAP 250", "CATEGORY": "Broad market", "API_SYMBOL": "NIFTY SMLCAP 250"},
                {"INDEX_NAME": "NIFTY WAVES", "CATEGORY": "Thematic", "API_SYMBOL": "NIFTY WAVES"},
            ]
        )
        constituents = {"NIFTY AUTO": ["AAA", "BBB"]}
        index_data = {
            "NIFTY AUTO": pd.DataFrame([{"SYMBOL": "AAA"}, {"SYMBOL": "BBB"}]),
            "NIFTY SMALLCAP 250": pd.DataFrame([{"SYMBOL": "CCC"}]),
        }

        coverage = build_index_coverage(catalog, constituents, index_data, target_indices=["NIFTY AUTO"]).set_index("INDEX_NAME")

        self.assertEqual(coverage.loc["NIFTY AUTO", "mapping_status"], "Available")
        self.assertEqual(coverage.loc["NIFTY AUTO", "constituent_count"], 2)
        self.assertTrue(bool(coverage.loc["NIFTY AUTO", "included_in_dashboard"]))
        self.assertEqual(coverage.loc["NIFTY SMALLCAP 250", "mapping_status"], "Inferred")
        self.assertEqual(coverage.loc["NIFTY SMALLCAP 250", "constituent_count"], 1)
        self.assertEqual(coverage.loc["NIFTY WAVES", "mapping_status"], "Missing")

    def test_build_top5_index_stocks_filters_sectoral_thematic_and_ranks_by_strength(self):
        catalog = pd.DataFrame(
            [
                {"INDEX_NAME": "NIFTY AUTO", "CATEGORY": "Sectoral", "API_SYMBOL": "NIFTY AUTO"},
                {"INDEX_NAME": "NIFTY INDIA DEFENCE", "CATEGORY": "Thematic", "API_SYMBOL": "NIFTY IND DEFENCE"},
                {"INDEX_NAME": "NIFTY 50", "CATEGORY": "Listed for derivatives", "API_SYMBOL": "NIFTY 50"},
            ]
        )
        index_data = {
            "NIFTY AUTO": pd.DataFrame(
                [
                    {"SYMBOL": "AAA", "CLOSE": 100, "SMA_50": 90, "SMA_200": 80, "HIGH_52W": 102, "LOW_52W": 50, "RET_1D": 1, "TOTTRDQTY": 1000},
                    {"SYMBOL": "BBB", "CLOSE": 90, "SMA_50": 95, "SMA_200": 100, "HIGH_52W": 120, "LOW_52W": 80, "RET_1D": -1, "TOTTRDQTY": 100},
                    {"SYMBOL": "CCC", "CLOSE": 120, "SMA_50": 110, "SMA_200": 100, "HIGH_52W": 121, "LOW_52W": 60, "RET_1D": 2, "TOTTRDQTY": 1200},
                    {"SYMBOL": "DDD", "CLOSE": 105, "SMA_50": 100, "SMA_200": 90, "HIGH_52W": 130, "LOW_52W": 70, "RET_1D": 0, "TOTTRDQTY": 800},
                    {"SYMBOL": "EEE", "CLOSE": 99, "SMA_50": 98, "SMA_200": 97, "HIGH_52W": 110, "LOW_52W": 90, "RET_1D": 0.5, "TOTTRDQTY": 700},
                    {"SYMBOL": "FFF", "CLOSE": 80, "SMA_50": 82, "SMA_200": 85, "HIGH_52W": 120, "LOW_52W": 75, "RET_1D": -2, "TOTTRDQTY": 600},
                ]
            ),
            "NIFTY INDIA DEFENCE": pd.DataFrame(
                [
                    {"SYMBOL": "DEF", "CLOSE": 50, "SMA_50": 45, "SMA_200": 40, "HIGH_52W": 51, "LOW_52W": 25, "RET_1D": 1, "TOTTRDQTY": 500},
                ]
            ),
            "NIFTY 50": pd.DataFrame(
                [
                    {"SYMBOL": "LARGE", "CLOSE": 200, "SMA_50": 190, "SMA_200": 180, "HIGH_52W": 205, "LOW_52W": 100, "RET_1D": 1, "TOTTRDQTY": 2000},
                ]
            ),
        }

        top5 = build_top5_index_stocks(catalog, index_data, top_n=5)

        self.assertNotIn("NIFTY 50", set(top5["INDEX_NAME"]))
        self.assertIn("NIFTY AUTO", set(top5["INDEX_NAME"]))
        self.assertIn("NIFTY INDIA DEFENCE", set(top5["INDEX_NAME"]))
        self.assertLessEqual(int(top5[top5["INDEX_NAME"].eq("NIFTY AUTO")]["rank"].max()), 5)
        self.assertEqual(top5[top5["INDEX_NAME"].eq("NIFTY AUTO")].iloc[0]["SYMBOL"], "CCC")

    def test_report_output_paths_use_index_intelligence_year_folder_and_latest_aliases(self):
        with TemporaryDirectory() as tmp:
            paths = report_output_paths(pd.Timestamp("2026-05-02 11:00:00"), root=Path(tmp))

            self.assertEqual(paths.html.relative_to(tmp).as_posix(), "reports/index_intelligence/2026/Index_Intelligence_20260502.html")
            self.assertEqual(paths.csv.relative_to(tmp).as_posix(), "reports/index_intelligence/2026/Index_Intelligence_20260502.csv")
            self.assertEqual(paths.latest_html.relative_to(tmp).as_posix(), "reports/latest/index_intelligence.html")
            self.assertEqual(paths.latest_csv.relative_to(tmp).as_posix(), "reports/latest/index_intelligence.csv")
            self.assertEqual(paths.latest_coverage_csv.relative_to(tmp).as_posix(), "reports/latest/index_coverage.csv")
            self.assertEqual(paths.latest_top5_csv.relative_to(tmp).as_posix(), "reports/latest/index_top5_stocks.csv")

    def test_breadth_regime_override_nifty_strong_smallcap_weak_yields_rotation(self):
        from regime_detector import _breadth_regime_override
        import tempfile, os

        breadth_data = pd.DataFrame([
            {"INDEX_NAME": "NIFTY 50",            "breadth_signal": "STRONG"},
            {"INDEX_NAME": "NIFTY SMALLCAP 250",  "breadth_signal": "WEAK"},
        ])
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            breadth_data.to_csv(f, index=False)
            tmp_path = Path(f.name)
        try:
            # BULL_TREND + divergence → override to ROTATION (more defensive)
            self.assertEqual(_breadth_regime_override("BULL_TREND", tmp_path), "ROTATION")
            # ROTATION already → no upgrade needed
            self.assertIsNone(_breadth_regime_override("ROTATION", tmp_path))
            # BEAR_TREND → no upgrade to ROTATION
            self.assertIsNone(_breadth_regime_override("BEAR_TREND", tmp_path))
        finally:
            os.unlink(tmp_path)

    def test_breadth_regime_override_both_bearish_yields_bear_trend(self):
        from regime_detector import _breadth_regime_override
        import tempfile, os

        breadth_data = pd.DataFrame([
            {"INDEX_NAME": "NIFTY 50",            "breadth_signal": "BEARISH"},
            {"INDEX_NAME": "NIFTY SMALLCAP 250",  "breadth_signal": "BEARISH"},
        ])
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            breadth_data.to_csv(f, index=False)
            tmp_path = Path(f.name)
        try:
            self.assertEqual(_breadth_regime_override("BULL_TREND", tmp_path), "BEAR_TREND")
            self.assertEqual(_breadth_regime_override("ROTATION", tmp_path), "BEAR_TREND")
            self.assertIsNone(_breadth_regime_override("BEAR_TREND", tmp_path))
        finally:
            os.unlink(tmp_path)

    def test_breadth_regime_override_missing_file_returns_none(self):
        from regime_detector import _breadth_regime_override
        self.assertIsNone(_breadth_regime_override("BULL_TREND", Path("/nonexistent/file.csv")))


if __name__ == "__main__":
    unittest.main()
