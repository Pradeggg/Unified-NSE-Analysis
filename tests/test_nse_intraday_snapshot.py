import unittest
from unittest.mock import patch

import pandas as pd

from terminal import tools


class NSEIntradaySnapshotTests(unittest.TestCase):
    def test_stock_snapshot_uses_nse_live_quote(self):
        quote = {
            "symbol": "RELIANCE",
            "last_price": 1430.5,
            "source": "NSE live API (real-time)",
        }

        with (
            patch.object(tools, "get_live_quote", return_value=quote) as live,
            patch.object(tools, "persist_intraday_snapshot", return_value={"ok": True, "rows_inserted": 1}),
        ):
            result = tools.get_nse_intraday_snapshot("RELIANCE")

        live.assert_called_once_with("RELIANCE")
        self.assertEqual(result["symbol"], "RELIANCE")
        self.assertEqual(result["source_priority"][0], "NSE website live quote")
        self.assertEqual(result["last_price"], 1430.5)

    def test_stock_snapshot_persists_to_intraday_schema(self):
        quote = {
            "symbol": "RELIANCE",
            "last_price": 1430.5,
            "as_of": "11-May-2026 09:26:33",
            "source": "NSE live API (real-time)",
        }

        with (
            patch.object(tools, "get_live_quote", return_value=quote),
            patch.object(tools, "persist_intraday_snapshot", return_value={"ok": True, "rows_inserted": 1}) as persist,
        ):
            result = tools.get_nse_intraday_snapshot("RELIANCE")

        persist.assert_called_once()
        self.assertEqual(result["postgres_persist"]["schema"], "intraday")
        self.assertEqual(result["postgres_persist"]["rows_inserted"], 1)

    def test_index_snapshot_uses_nse_all_indices(self):
        overview = {
            "indices": {
                "NIFTY 50": {
                    "last": 24600.0,
                    "change": 50.0,
                    "pct_change": 0.2,
                    "day_high": 24650.0,
                    "day_low": 24500.0,
                }
            },
            "source": "NSE live API",
        }

        with (
            patch.object(tools, "get_live_market_overview", return_value=overview) as live,
            patch.object(tools, "persist_intraday_snapshot", return_value={"ok": True, "rows_inserted": 1}),
        ):
            result = tools.get_nse_intraday_snapshot("NIFTY50")

        live.assert_called_once()
        self.assertEqual(result["symbol"], "NIFTY 50")
        self.assertEqual(result["last_price"], 24600.0)
        self.assertEqual(result["source"], "NSE live API")

    def test_stock_snapshot_falls_back_to_yfinance_when_nse_quote_forbidden(self):
        candles = pd.DataFrame(
            {
                "Open": [8500.0, 8525.0],
                "High": [8560.0, 8580.0],
                "Low": [8475.0, 8510.0],
                "Close": [8520.0, 8575.0],
                "Volume": [1000, 1500],
            },
            index=pd.to_datetime(["2026-05-25 09:15:00", "2026-05-25 09:30:00"]),
        )

        with (
            patch.object(
                tools,
                "get_live_quote",
                return_value={"symbol": "BAJAJ-AUTO", "error": "403 Client Error: Forbidden"},
            ),
            patch.object(
                tools,
                "_playwright_nse_quote_snapshot",
                return_value={"symbol": "BAJAJ-AUTO", "error": "Playwright page unavailable"},
            ),
            patch.object(tools, "get_intraday_candles", return_value=candles) as yf_candles,
            patch.object(tools, "persist_intraday_snapshot", return_value={"ok": True, "rows_inserted": 1}),
        ):
            result = tools.get_nse_intraday_snapshot("BAJAJ-AUTO")

        yf_candles.assert_called_once_with("BAJAJ-AUTO", "15m")
        self.assertEqual(result["symbol"], "BAJAJ-AUTO")
        self.assertEqual(result["last_price"], 8575.0)
        self.assertEqual(result["source"], "Yahoo Finance (yfinance) fallback")
        self.assertTrue(result["degraded"])
        self.assertIn("NSE live quote unavailable", result["fallback_reason"])
        self.assertIn("Playwright page unavailable", result["fallback_reason"])
        self.assertNotIn("error", result)

    def test_stock_snapshot_uses_playwright_before_yfinance_when_requests_forbidden(self):
        browser_quote = {
            "symbol": "EICHERMOT",
            "name": "Eicher Motors Limited",
            "last_price": 7360.5,
            "day_high": 7390.0,
            "day_low": 7290.0,
            "pct_change": 1.2,
            "as_of": "2026-05-25 09:45:00",
            "source": "NSE browser quote page",
        }

        with (
            patch.object(
                tools,
                "get_live_quote",
                return_value={"symbol": "EICHERMOT", "error": "403 Client Error: Forbidden"},
            ),
            patch.object(tools, "_playwright_nse_quote_snapshot", return_value=browser_quote) as browser_fetch,
            patch.object(tools, "get_intraday_candles", side_effect=AssertionError("yfinance should not run")),
            patch.object(tools, "persist_intraday_snapshot", return_value={"ok": True, "rows_inserted": 1}),
        ):
            result = tools.get_nse_intraday_snapshot("EICHERMOT")

        browser_fetch.assert_called_once_with("EICHERMOT")
        self.assertEqual(result["source"], "NSE browser quote page")
        self.assertEqual(result["last_price"], 7360.5)
        self.assertNotIn("error", result)


if __name__ == "__main__":
    unittest.main()
