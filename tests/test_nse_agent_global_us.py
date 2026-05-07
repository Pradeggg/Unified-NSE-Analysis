import unittest
from unittest.mock import patch
import contextlib
import io

import pandas as pd

from nse_agent import _US_INDEX_SYMBOLS, _format_us_global_terminal_summary, _handle_us_global_command, _parse_us_global_command


class NSEAgentGlobalUSTests(unittest.TestCase):
    def test_parse_us_global_commands(self):
        self.assertEqual(_parse_us_global_command("/us")["view"], "summary")
        self.assertEqual(_parse_us_global_command("/us indices")["view"], "indices")
        self.assertEqual(_parse_us_global_command("/us sectors")["view"], "sectors")
        self.assertEqual(_parse_us_global_command("/us stage2")["view"], "stage2")
        self.assertEqual(_parse_us_global_command("/us vcp")["view"], "vcp")
        self.assertEqual(_parse_us_global_command("/global readthrough")["view"], "readthrough")

        stock = _parse_us_global_command("/us stock nvda")
        self.assertEqual(stock["view"], "stock")
        self.assertEqual(stock["stock"], "NVDA")
        self.assertIn("NVDA", stock["symbols"])
        self.assertIn("SPY", stock["symbols"])
        self.assertIsNone(_parse_us_global_command("/global market check"))

    def test_format_us_global_terminal_summary_includes_report_and_sections(self):
        request = {"view": "summary", "label": "US Market Summary"}
        bundle = {
            "metrics": pd.DataFrame(
                [
                    {"SYMBOL": "SPY", "RET_1M": 3.0, "SMA_ALIGNMENT": "BULLISH", "MACD_SIGNAL": "BULLISH"},
                    {"SYMBOL": "QQQ", "RET_1M": 8.0, "SMA_ALIGNMENT": "BULLISH", "MACD_SIGNAL": "BULLISH"},
                ]
            ),
            "stage2": pd.DataFrame([{"SYMBOL": "NVDA", "SCREENER_SCORE": 31.5}]),
            "sector_rotation": pd.DataFrame([{"SYMBOL": "SMH", "ROTATION_SCORE": 40.0}]),
            "india_readthrough": {
                "global_regime": "risk-on",
                "india_sector_implications": [
                    {"nse_sector": "IT & Technology", "stance": "positive", "symbols": ["QQQ"], "confidence": "medium"}
                ],
            },
        }
        report = {"report_path": "reports/global/us_market_report_20260508.html", "latest_path": "reports/latest/us_market_report.html"}

        text = _format_us_global_terminal_summary(request, bundle, report)

        self.assertIn("US Market Summary", text)
        self.assertIn("risk-on", text)
        self.assertIn("NVDA", text)
        self.assertIn("SMH", text)
        self.assertIn("IT & Technology", text)
        self.assertIn("reports/global/us_market_report_20260508.html", text)

    def test_subset_us_command_renders_report_from_full_cache(self):
        load_calls = []
        rendered_prices = []

        class FakeLoader:
            def load(self, symbols=None, force=False, lookback_days=365):
                load_calls.append(symbols)
                label = "full-cache" if symbols is None else "subset-cache"
                return {
                    "status": "ok",
                    "prices": label,
                    "warnings": [],
                    "latest_snapshot": pd.DataFrame(),
                    "source": "cache",
                }

        def fake_build_bundle(prices, warnings=None):
            return {
                "prices_label": prices,
                "stage2": pd.DataFrame(),
                "sector_rotation": pd.DataFrame(),
                "vcp": pd.DataFrame(),
                "india_readthrough": {"global_regime": "neutral", "india_sector_implications": []},
                "risk_dashboard": {"regime": "neutral"},
                "warnings": warnings or [],
            }

        def fake_render_report(bundle):
            rendered_prices.append(bundle["prices_label"])
            return {
                "report_path": "reports/global/us_market_report_20260508.html",
                "latest_path": "reports/latest/us_market_report.html",
            }

        with (
            patch("global_market_intelligence.GlobalMarketDataLoader", FakeLoader),
            patch("global_market_intelligence.build_us_market_bundle", fake_build_bundle),
            patch("global_market_intelligence.render_us_market_report", fake_render_report),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            handled = _handle_us_global_command("/us indices")

        self.assertTrue(handled)
        self.assertEqual(load_calls[0], _US_INDEX_SYMBOLS)
        self.assertIsNone(load_calls[1])
        self.assertEqual(rendered_prices, ["full-cache"])


if __name__ == "__main__":
    unittest.main()
