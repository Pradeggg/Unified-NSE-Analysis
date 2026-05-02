import math
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from index_intelligence import (
    build_index_constituent_data,
    build_stock_metric_frame,
    breadth_context_html,
    cross_index_breadth,
    render_breadth_html,
    report_output_paths,
)


class IndexIntelligenceTests(unittest.TestCase):
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
            }
        )

        metrics = build_stock_metric_frame(stock_history).set_index("SYMBOL")

        self.assertIn("AAA", metrics.index)
        self.assertAlmostEqual(metrics.loc["AAA", "CLOSE"], 304.0)
        self.assertAlmostEqual(metrics.loc["AAA", "SMA_50"], sum(range(255, 305)) / 50)
        self.assertAlmostEqual(metrics.loc["AAA", "SMA_200"], sum(range(105, 305)) / 200)
        self.assertAlmostEqual(metrics.loc["AAA", "HIGH_52W"], 305.0)
        self.assertAlmostEqual(metrics.loc["AAA", "LOW_52W"], 99.0)
        self.assertGreater(metrics.loc["AAA", "RET_1D"], 0)

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

    def test_report_output_paths_use_index_intelligence_year_folder_and_latest_aliases(self):
        with TemporaryDirectory() as tmp:
            paths = report_output_paths(pd.Timestamp("2026-05-02 11:00:00"), root=Path(tmp))

            self.assertEqual(paths.html.relative_to(tmp).as_posix(), "reports/index_intelligence/2026/Index_Intelligence_20260502.html")
            self.assertEqual(paths.csv.relative_to(tmp).as_posix(), "reports/index_intelligence/2026/Index_Intelligence_20260502.csv")
            self.assertEqual(paths.latest_html.relative_to(tmp).as_posix(), "reports/latest/index_intelligence.html")
            self.assertEqual(paths.latest_csv.relative_to(tmp).as_posix(), "reports/latest/index_intelligence.csv")


if __name__ == "__main__":
    unittest.main()
