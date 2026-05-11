import unittest

from terminal.agent import _keyword_intent, _synthesize_no_llm


class TerminalIntradayFallbackTests(unittest.TestCase):
    def test_intraday_stock_query_uses_real_symbol_and_fallback_tool(self):
        routed = _keyword_intent("intraday deep dive Polycab", data_mode="intraday")

        self.assertEqual(routed["intent"], "intraday_setup")
        self.assertEqual(routed["plan"][0], ("resolve_symbol", {"query": "Polycab"}))
        self.assertIn(("explain_intraday_setup", {"symbol": "Polycab"}), routed["plan"])
        self.assertLess(
            routed["plan"].index(("get_nse_intraday_snapshot", {"symbol": "Polycab"})),
            routed["plan"].index(("get_intraday_analysis", {"symbol": "Polycab"})),
        )
        self.assertIn(("get_intraday_analysis", {"symbol": "Polycab"}), routed["plan"])

    def test_intraday_index_query_does_not_parse_of_as_symbol(self):
        routed = _keyword_intent("intraday technical analysis of NIFTY50", data_mode="intraday")

        self.assertEqual(routed["intent"], "intraday_setup")
        self.assertNotIn(("resolve_symbol", {"query": "of"}), routed["plan"])
        self.assertIn(("get_nse_intraday_snapshot", {"symbol": "NIFTY50"}), routed["plan"])

    def test_no_llm_response_uses_legacy_intraday_fallback_when_sqlite_missing(self):
        response = _synthesize_no_llm(
            "intraday_setup",
            [
                {
                    "tool": "explain_intraday_setup",
                    "args": {"symbol": "POLYCAB"},
                    "result": {
                        "symbol": "POLYCAB",
                        "data_mode": "intraday",
                        "error": "intraday_ohlcv table not found",
                    },
                },
                {
                    "tool": "get_nse_intraday_snapshot",
                    "args": {"symbol": "POLYCAB"},
                    "result": {
                        "symbol": "POLYCAB",
                        "source": "NSE live API (real-time)",
                        "last_price": 5531.0,
                        "day_high": 5560.0,
                        "day_low": 5488.0,
                        "vwap": 5520.0,
                        "pct_change": 0.4,
                        "as_of": "11-May-2026 09:35:00",
                    },
                },
                {
                    "tool": "get_intraday_analysis",
                    "args": {"symbol": "POLYCAB"},
                    "result": {
                        "symbol": "POLYCAB",
                        "interval": "15m",
                        "session": "live",
                        "source": "Yahoo Finance (yfinance)",
                        "close": 5520.5,
                        "bias": "BULLISH",
                        "candles": 42,
                        "key_levels": {
                            "supports": [5480.0, 5425.0],
                            "resistances": [5580.0, 5650.0],
                            "pivot": 5535.0,
                        },
                        "indicators": {
                            "rsi": 61.2,
                            "macd_hist": 2.34,
                            "supertrend_dir": 1,
                        },
                        "buy_signals": [{"strategy": "MACD", "entry": 5525, "target": 5600, "stoploss": 5480}],
                        "sell_signals": [],
                        "watch_alerts": [],
                    },
                },
            ],
        )

        self.assertIn("INTRADAY FALLBACK ANALYSIS", response)
        self.assertIn("SQLite intraday source unavailable", response)
        self.assertIn("NSE LIVE SNAPSHOT", response)
        self.assertIn("POLYCAB", response)
        self.assertIn("Yahoo Finance", response)
        self.assertIn("POLYCAB", response)
        self.assertIn("Research-only", response)


if __name__ == "__main__":
    unittest.main()
