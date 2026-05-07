import unittest

import pandas as pd

from nse_agent import _format_us_global_terminal_summary, _parse_us_global_command


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


if __name__ == "__main__":
    unittest.main()
