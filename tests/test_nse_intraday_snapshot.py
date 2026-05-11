import unittest
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
