import unittest
from unittest.mock import patch

import pandas as pd

from terminal import tools
from terminal.agent import Agent, _keyword_intent, _synthesize_no_llm


class TerminalIntradayFallbackTests(unittest.TestCase):
    def test_get_intraday_bars_seeds_postgres_when_pg_empty_and_sqlite_absent(self):
        rows = 40
        df = pd.DataFrame(
            {
                "Open": [100 + i for i in range(rows)],
                "High": [101 + i for i in range(rows)],
                "Low": [99 + i for i in range(rows)],
                "Close": [100.5 + i for i in range(rows)],
                "Volume": [1000 + i for i in range(rows)],
            },
            index=pd.date_range("2026-05-15 09:15:00", periods=rows, freq="15min"),
        )

        with patch.object(tools, "_pg_read_df", return_value=pd.DataFrame()), patch.object(
            tools, "DB_PATH"
        ) as db_path, patch.object(
            tools, "get_intraday_candles", return_value=df
        ) as get_candles, patch(
            "terminal.tools.persist_intraday_bars",
            return_value={"ok": True, "rows_inserted": rows, "schema": "intraday", "table": "ohlcv_bars"},
            create=True,
        ) as persist:
            db_path.exists.return_value = False

            result = tools.get_intraday_bars("GESHIP", timeframe="15m", lookback=30)

        get_candles.assert_called_once_with("GESHIP", "15m")
        persist.assert_called_once()
        self.assertEqual(result["source"], "PostgreSQL intraday.ohlcv_bars seeded from Yahoo Finance (yfinance)")
        self.assertEqual(result["count"], 30)
        self.assertNotIn("error", result)

    def test_get_intraday_bars_formats_postgres_timestamptz_as_ist(self):
        df = pd.DataFrame(
            {
                "timestamp": [pd.Timestamp("2026-05-15 04:15:00", tz="UTC")],
                "open": [100],
                "high": [101],
                "low": [99],
                "close": [100.5],
                "volume": [1000],
            }
        )

        with patch.object(tools, "_pg_read_df", return_value=df):
            result = tools.get_intraday_bars("GESHIP", timeframe="15m", lookback=5)

        self.assertEqual(result["latest_timestamp"], "2026-05-15 09:45:00")

    def test_get_intraday_bars_does_not_read_legacy_sqlite_when_pg_seed_empty(self):
        with patch.object(tools, "_pg_read_df", return_value=pd.DataFrame()), patch.object(
            tools, "get_intraday_candles", return_value=pd.DataFrame()
        ), patch.object(tools, "DB_PATH") as db_path, patch.object(
            tools, "_sqlite_table_exists", return_value=True
        ), patch.object(
            tools, "_db_conn", side_effect=AssertionError("legacy SQLite should not be read")
        ):
            db_path.exists.return_value = True

            result = tools.get_intraday_bars("GESHIP", timeframe="15m", lookback=30)

        self.assertEqual(result["source"], "PostgreSQL intraday.ohlcv_bars")
        self.assertIn("No PostgreSQL intraday.ohlcv_bars", result["error"])
        self.assertNotIn("SQLite", result["error"])

    def test_intraday_source_health_reports_postgres_only_when_pg_empty(self):
        def fake_fetchall(sql, params=None):
            if "information_schema.tables" in sql:
                return [(1,)]
            return [(0, None)]

        with patch.object(tools, "_pg_fetchall", side_effect=fake_fetchall), patch.object(
            tools, "DB_PATH"
        ) as db_path, patch.object(
            tools, "_db_conn", side_effect=AssertionError("legacy SQLite should not be inspected")
        ):
            db_path.exists.return_value = True

            result = tools.get_intraday_source_health()

        self.assertEqual(result["source"], "PostgreSQL intraday schema")
        self.assertEqual(result["overall_status"], "EMPTY")
        self.assertIn("intraday.ohlcv_bars", result["tables"])
        self.assertNotIn("intraday_ohlcv", result["tables"])

    def test_run_intraday_screener_uses_yfinance_fallback_not_legacy_sqlite_when_pg_empty(self):
        with patch.object(tools, "_pg_table_exists", return_value=True), patch.object(
            tools, "_pg_fetchall", return_value=[(0,)]
        ), patch.object(tools, "DB_PATH") as db_path, patch.object(
            tools, "_sqlite_table_exists", return_value=True
        ), patch.object(
            tools, "_db_conn", side_effect=AssertionError("legacy SQLite should not be read")
        ), patch.object(
            tools,
            "scan_intraday_market",
            return_value={"buy_signals": [], "sell_signals": []},
        ) as scan:
            db_path.exists.return_value = True

            result = tools.run_intraday_screener("momentum", timeframe="15m", top_n=5)

        scan.assert_called_once()
        self.assertEqual(result["data_mode"], "live-yfinance-fallback")
        self.assertNotIn("SQLite", " ".join(result["source_priority"]))

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

    def test_intraday_setup_resolves_multi_word_company_name_before_llm(self):
        routed = _keyword_intent("Bajaj finance intraday setup", data_mode="intraday")

        self.assertEqual(routed["intent"], "intraday_setup")
        self.assertEqual(routed["plan"][0], ("resolve_symbol", {"query": "BAJFINANCE"}))
        self.assertIn(("explain_intraday_setup", {"symbol": "BAJFINANCE"}), routed["plan"])

    def test_intraday_index_query_does_not_parse_of_as_symbol(self):
        routed = _keyword_intent("intraday technical analysis of NIFTY50", data_mode="intraday")

        self.assertEqual(routed["intent"], "intraday_setup")
        self.assertNotIn(("resolve_symbol", {"query": "of"}), routed["plan"])
        self.assertIn(("get_nse_intraday_snapshot", {"symbol": "NIFTY50"}), routed["plan"])

    def test_no_llm_response_uses_intraday_fallback_when_postgres_bars_missing(self):
        response = _synthesize_no_llm(
            "intraday_setup",
            [
                {
                    "tool": "explain_intraday_setup",
                    "args": {"symbol": "POLYCAB"},
                    "result": {
                        "symbol": "POLYCAB",
                        "data_mode": "intraday",
                        "source": "PostgreSQL intraday.ohlcv_bars",
                        "error": "No PostgreSQL intraday.ohlcv_bars for POLYCAB at 15m",
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
        self.assertIn("PostgreSQL intraday bars unavailable", response)
        self.assertIn("NSE LIVE SNAPSHOT", response)
        self.assertIn("POLYCAB", response)
        self.assertIn("Yahoo Finance", response)
        self.assertIn("POLYCAB", response)
        self.assertIn("Research-only", response)

    def test_agent_mode_footer_labels_yfinance_fallback_when_postgres_bars_missing(self):
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"
        tool_results = [
            {
                "tool": "resolve_symbol",
                "args": {"query": "GESHIP"},
                "result": {"symbol": "GESHIP", "company_name": "Great Eastern Shipping"},
            },
            {
                "tool": "explain_intraday_setup",
                "args": {"symbol": "GESHIP"},
                "result": {
                    "symbol": "GESHIP",
                    "data_mode": "intraday",
                    "source": "PostgreSQL intraday.ohlcv_bars",
                    "error": "No PostgreSQL intraday.ohlcv_bars for GESHIP at 15m",
                },
            },
            {
                "tool": "get_nse_intraday_snapshot",
                "args": {"symbol": "GESHIP"},
                "result": {
                    "symbol": "GESHIP",
                    "source": "NSE live API (real-time)",
                    "last_price": 1622.0,
                    "day_high": 1634.0,
                    "day_low": 1550.0,
                    "vwap": 1605.84,
                    "pct_change": 9.23,
                    "as_of": "15-May-2026 09:48:17",
                },
            },
            {
                "tool": "get_intraday_analysis",
                "args": {"symbol": "GESHIP"},
                "result": {
                    "symbol": "GESHIP",
                    "interval": "15m",
                    "session": "live",
                    "source": "Yahoo Finance (yfinance)",
                    "close": 1628.6,
                    "bias": "BULLISH",
                    "candles": 103,
                    "key_levels": {"supports": [1597.53], "resistances": [1637.67], "pivot": 1607.87},
                    "indicators": {"rsi": 86.1, "macd_hist": 18.4149, "supertrend_dir": 1},
                    "buy_signals": [],
                    "sell_signals": [],
                    "watch_alerts": [],
                },
            },
        ]

        with patch("terminal.agent._execute_plan", return_value=tool_results):
            result = agent.query("/intraday GESHIP setup")

        self.assertIn("INTRADAY FALLBACK ANALYSIS", result["answer"])
        self.assertIn("Sources: NSE live API snapshot + Yahoo Finance fallback candles", result["answer"])
        self.assertNotIn("Sources: PG intraday.quote_snapshots + SQLite intraday OHLCV", result["answer"])


if __name__ == "__main__":
    unittest.main()
