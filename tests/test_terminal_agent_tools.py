import sqlite3
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from terminal.agent import _keyword_intent
from terminal import tools
from terminal.agent import _synthesize_no_llm


class TerminalAgentToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.old_db_path = tools.DB_PATH
        tools.DB_PATH = Path(self.tmp.name) / "sector_rotation_tracker.db"

    def tearDown(self):
        tools.DB_PATH = self.old_db_path
        if hasattr(self, "old_global_index_csv"):
            tools.GLOBAL_INDEX_CSV = self.old_global_index_csv
        if hasattr(self, "old_global_CORR_CSV"):
            tools.GLOBAL_CORR_CSV = self.old_global_CORR_CSV
        self.tmp.cleanup()

    def _create_stage_snapshot_db(self):
        conn = sqlite3.connect(tools.DB_PATH)
        conn.execute(
            """
            CREATE TABLE stage_snapshots (
                snapshot_date TEXT,
                symbol TEXT,
                company_name TEXT,
                stage TEXT,
                stage_score REAL,
                investment_score REAL,
                price REAL,
                relative_strength REAL,
                change_1d_pct REAL,
                change_1m_pct REAL,
                rsi REAL,
                trading_signal TEXT,
                sector TEXT,
                supertrend_state TEXT,
                technical_score REAL
            )
            """
        )
        rows = [
            ("2026-05-04", "BRKOUT", "Breakout Ltd", "STAGE_2", 82, 91, 125, 0.42, 4.5, 18.0, 68, "BUY", "Auto", "BUY", 88),
            ("2026-05-04", "WEAK", "Weak Ltd", "STAGE_2", 60, 45, 80, -0.05, -1.0, -4.0, 48, "HOLD", "IT", "SELL", 40),
        ]
        conn.executemany(
            """
            INSERT INTO stage_snapshots
              (snapshot_date, symbol, company_name, stage, stage_score, investment_score,
               price, relative_strength, change_1d_pct, change_1m_pct, rsi,
               trading_signal, sector, supertrend_state, technical_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
        conn.close()

    def _create_intraday_ohlcv_db(self, symbols: tuple[str, ...] = ("RELIANCE",)):
        conn = sqlite3.connect(tools.DB_PATH)
        conn.execute(
            """
            CREATE TABLE intraday_ohlcv (
                symbol TEXT,
                timeframe TEXT,
                timestamp TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER
            )
            """
        )
        rows = []
        base_price = 100.0
        start = datetime(2026, 5, 6, 9, 15)
        for symbol in symbols:
            for i in range(60):
                close = base_price + i * 0.5 if symbol == "RELIANCE" else base_price + 30 - i * 0.35
                rows.append((
                    symbol,
                    "15m",
                    (start + timedelta(minutes=15 * i)).strftime("%Y-%m-%d %H:%M:%S"),
                    close - 0.4,
                    close + 0.8,
                    close - 0.9,
                    close,
                    100000 + i * 1000,
                ))
        conn.executemany(
            """
            INSERT INTO intraday_ohlcv
              (symbol, timeframe, timestamp, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
        conn.close()

    def test_breakout_query_routes_to_breakout_screener(self):
        intent = _keyword_intent("breakout stocks")

        self.assertEqual(intent["intent"], "screener")
        self.assertEqual(intent["plan"], [("run_screener_query", {"screen_type": "breakouts"})])

    def test_intraday_breakout_query_routes_to_sqlite_intraday_screener(self):
        intent = _keyword_intent("breakout stocks", data_mode="intraday")

        self.assertEqual(intent["intent"], "intraday_screener")
        self.assertEqual(intent["plan"], [("run_intraday_screener", {"screen_type": "breakouts"})])

    def test_intraday_stock_setup_routes_to_sqlite_setup_explain(self):
        intent = _keyword_intent("Reliance setup", data_mode="intraday")

        self.assertEqual(intent["intent"], "intraday_setup")
        self.assertEqual(intent["plan"], [("resolve_symbol", {"query": "Reliance"}), ("explain_intraday_setup", {"symbol": "Reliance"})])

    def test_openai_schema_exposes_breakout_screener(self):
        schema = next(
            s for s in tools.openai_tool_schemas()
            if s["function"]["name"] == "run_screener_query"
        )

        enum = schema["function"]["parameters"]["properties"]["screen_type"]["enum"]
        self.assertIn("breakouts", enum)

    def test_breakout_screener_does_not_fall_back_to_stage2(self):
        self._create_stage_snapshot_db()

        result = tools.run_screener_query("breakouts", top_n=10)

        self.assertEqual(result["screen_type"], "breakouts")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["results"][0]["symbol"], "BRKOUT")

    def test_global_query_routes_to_global_market_assessment(self):
        intent = _keyword_intent("global market assessment for India")

        self.assertEqual(intent["intent"], "global_market_assessment")
        self.assertEqual(intent["plan"], [("get_global_market_assessment", {})])

    def test_global_market_assessment_reads_cached_global_data(self):
        self.old_global_index_csv = tools.GLOBAL_INDEX_CSV
        self.old_global_CORR_CSV = tools.GLOBAL_CORR_CSV
        tools.GLOBAL_INDEX_CSV = Path(self.tmp.name) / "global_indices.csv"
        tools.GLOBAL_CORR_CSV = Path(self.tmp.name) / "global_correlations.csv"
        tools.GLOBAL_INDEX_CSV.write_text(
            "Date,S&P 500,Nasdaq,Hang Seng,Nikkei 225,Gold,Crude Oil,Copper,DXY,USDINR\n"
            "2026-05-04,5000,16000,18000,38000,2300,80,4.5,104,83.0\n"
            "2026-05-05,5050,16320,18180,37620,2288,82,4.6,103.5,83.4\n",
            encoding="utf-8",
        )
        tools.GLOBAL_CORR_CSV.write_text(
            "asset,price,corr_30d,corr_60d,change,alert\n"
            "S&P 500,5050,0.62,0.58,0.04,STABLE\n"
            "Crude Oil,82,-0.25,-0.10,-0.15,STABLE\n",
            encoding="utf-8",
        )

        result = tools.get_global_market_assessment()

        self.assertEqual(result["risk_regime"], "RISK_ON")
        self.assertEqual(result["as_of"], "2026-05-05")
        self.assertEqual(result["regions"]["US"]["bias"], "positive")
        self.assertEqual(result["moves"]["Nasdaq"]["pct_change"], 2.0)
        self.assertIn("Crude up", " ".join(result["india_readthrough"]))
        self.assertEqual(result["correlations"][0]["asset"], "S&P 500")

    def test_global_assessment_synthesis_renders_global_section(self):
        answer = _synthesize_no_llm(
            "global_market_assessment",
            [{
                "tool": "get_global_market_assessment",
                "args": {},
                "result": {
                    "risk_regime": "RISK_OFF",
                    "as_of": "2026-05-05",
                    "regions": {"US": {"bias": "negative"}, "Asia": {"bias": "mixed"}},
                    "moves": {"S&P 500": {"pct_change": -1.2}, "DXY": {"pct_change": 0.4}},
                    "india_readthrough": ["Caution for Indian equities due to weak US risk tone."],
                    "watch_items": ["Nifty gap risk", "Bank Nifty follow-through"],
                    "source": "Cached global market CSVs",
                },
            }],
        )

        self.assertIn("GLOBAL MARKET ASSESSMENT", answer)
        self.assertIn("RISK_OFF", answer)
        self.assertIn("Caution for Indian equities", answer)

    def test_intraday_source_health_reads_sqlite_tables(self):
        self._create_intraday_ohlcv_db()

        result = tools.get_intraday_source_health(max_age_minutes=240)

        self.assertEqual(result["data_mode"], "intraday")
        self.assertEqual(result["overall_status"], "FRESH")
        self.assertEqual(result["tables"]["intraday_ohlcv"]["status"], "FRESH")
        self.assertEqual(result["tables"]["intraday_ohlcv"]["rows"], 60)

    def test_intraday_levels_read_from_sqlite_ohlcv(self):
        self._create_intraday_ohlcv_db()

        result = tools.get_intraday_levels("RELIANCE", timeframe="15m")

        self.assertEqual(result["symbol"], "RELIANCE")
        self.assertEqual(result["data_mode"], "intraday")
        self.assertEqual(result["source"], "SQLite intraday_ohlcv")
        self.assertEqual(result["timeframe"], "15m")
        self.assertGreater(result["latest_close"], 100)
        self.assertIn("supports", result)
        self.assertIn("resistances", result)

    def test_openai_schema_exposes_sqlite_intraday_tools(self):
        tool_names = {s["function"]["name"] for s in tools.openai_tool_schemas()}

        self.assertIn("get_intraday_source_health", tool_names)
        self.assertIn("get_intraday_levels", tool_names)

    def test_compute_intraday_indicators_reads_sqlite_ohlcv(self):
        self._create_intraday_ohlcv_db()

        result = tools.compute_intraday_indicators("RELIANCE", timeframe="15m")

        self.assertEqual(result["symbol"], "RELIANCE")
        self.assertEqual(result["data_mode"], "intraday")
        self.assertEqual(result["source"], "SQLite intraday_ohlcv")
        self.assertIn("rsi", result["indicators"])
        self.assertIn("macd_hist", result["indicators"])
        self.assertIn("supertrend_dir", result["indicators"])
        self.assertGreater(result["bars"], 50)

    def test_explain_intraday_setup_returns_research_label_and_levels(self):
        self._create_intraday_ohlcv_db()

        result = tools.explain_intraday_setup("RELIANCE", timeframe="15m")

        self.assertEqual(result["symbol"], "RELIANCE")
        self.assertIn(result["setup_label"], {"LONG_SETUP", "SHORT_SETUP", "WATCH", "AVOID", "SETUP_INVALIDATED"})
        self.assertIn("analyzers", result)
        self.assertIn("levels", result)
        self.assertIn("research and learning only", result["disclaimer"].lower())
        self.assertNotIn("BUY", result["setup_label"])
        self.assertNotIn("SELL", result["setup_label"])

    def test_run_intraday_screener_uses_sqlite_symbols(self):
        self._create_intraday_ohlcv_db(symbols=("RELIANCE", "INFY"))

        result = tools.run_intraday_screener("momentum", timeframe="15m", min_score=0, top_n=5)

        self.assertEqual(result["screen_type"], "momentum")
        self.assertEqual(result["data_mode"], "intraday")
        self.assertEqual(result["source"], "SQLite intraday_ohlcv")
        self.assertGreaterEqual(result["scanned"], 2)
        self.assertGreaterEqual(result["count"], 1)
        self.assertIn("setup_label", result["results"][0])

    def test_openai_schema_exposes_sqlite_intraday_analysis_tools(self):
        tool_names = {s["function"]["name"] for s in tools.openai_tool_schemas()}

        self.assertIn("compute_intraday_indicators", tool_names)
        self.assertIn("explain_intraday_setup", tool_names)
        self.assertIn("run_intraday_screener", tool_names)

    def test_intraday_setup_synthesis_renders_research_only_section(self):
        answer = _synthesize_no_llm(
            "intraday_setup",
            [{
                "tool": "explain_intraday_setup",
                "args": {"symbol": "RELIANCE"},
                "result": {
                    "symbol": "RELIANCE",
                    "timeframe": "15m",
                    "setup_label": "LONG_SETUP",
                    "score": 82,
                    "latest_close": 1295.5,
                    "latest_timestamp": "2026-05-06 10:30:00",
                    "indicators": {"rsi": 62, "macd_hist": 1.2, "supertrend_dir": 1},
                    "levels": {"supports": [1288.0], "resistances": [1310.0]},
                    "invalidation_level": 1288.0,
                    "technical_target_zones": [1310.0],
                    "disclaimer": "Research and learning only.",
                },
            }],
        )

        self.assertIn("INTRADAY SETUP", answer)
        self.assertIn("LONG_SETUP", answer)
        self.assertIn("technical target zones", answer.lower())
        self.assertIn("Not investment advice", answer)


if __name__ == "__main__":
    unittest.main()
