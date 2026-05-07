import unittest

from terminal.agent import _keyword_intent, _synthesize_no_llm


class TerminalIntradayFallbackTests(unittest.TestCase):
    def test_intraday_stock_query_uses_real_symbol_and_fallback_tool(self):
        routed = _keyword_intent("intraday deep dive Polycab", data_mode="intraday")

        self.assertEqual(routed["intent"], "intraday_setup")
        self.assertEqual(routed["plan"][0], ("resolve_symbol", {"query": "Polycab"}))
        self.assertIn(("explain_intraday_setup", {"symbol": "Polycab"}), routed["plan"])
        self.assertIn(("get_intraday_analysis", {"symbol": "Polycab"}), routed["plan"])

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
        self.assertIn("Yahoo Finance", response)
        self.assertIn("POLYCAB", response)
        self.assertIn("Research-only", response)


if __name__ == "__main__":
    unittest.main()
