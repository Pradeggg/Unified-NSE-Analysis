import unittest
from datetime import date, timedelta
from unittest.mock import patch

import pandas as pd

from terminal.agent import _keyword_intent
from terminal.tools import (
    _finalize_stage_snapshot,
    _normalize_index_name,
    get_market_breadth,
    get_sector_context,
    get_symbol_snapshot,
    get_technical_setup,
    get_top_gainers_losers,
)


class OnDemandStockDataTests(unittest.TestCase):
    def test_full_technical_prompt_routes_to_stock_tools_not_market_education(self):
        routed = _keyword_intent(
            "Full technical setup for USHAMART — Weinstein stage, RSI, ADX, MACD, "
            "supertrend direction, position vs 20/50/200 MA, RS rank vs Nifty 50."
        )

        self.assertNotEqual(routed["intent"], "market_knowledge")
        self.assertEqual(routed["intent"], "stock_brief")
        self.assertEqual(routed["plan"][0], ("resolve_symbol", {"query": "USHAMART"}))
        self.assertIn(("get_technical_setup", {"symbol": "USHAMART"}), routed["plan"])

    def test_get_technical_setup_fetches_and_loads_missing_price_history_on_demand(self):
        rows = []
        start = date(2025, 1, 1)
        for i in range(240):
            close = 100 + i * 0.5
            rows.append(
                {
                    "SYMBOL": "NEWMISS",
                    "TIMESTAMP": start + timedelta(days=i),
                    "OPEN": close - 1,
                    "HIGH": close + 2,
                    "LOW": close - 2,
                    "CLOSE": close,
                    "TOTTRDQTY": 100000 + i,
                }
            )
        fetched = pd.DataFrame(rows)

        with (
            patch("terminal.tools._load_price_history", return_value=pd.DataFrame()),
            patch("terminal.tools._fetch_on_demand_price_history", return_value=fetched) as fetch,
            patch("terminal.tools.persist_on_demand_eod_history", return_value={"ok": True, "rows_inserted": 240}) as persist,
        ):
            result = get_technical_setup("NEWMISS")

        fetch.assert_called_once_with("NEWMISS", 400)
        persist.assert_called_once()
        self.assertEqual(result["symbol"], "NEWMISS")
        self.assertEqual(result["data_source"], "on-demand yfinance EOD")
        self.assertEqual(result["postgres_persist"]["rows_inserted"], 240)
        self.assertIsNone(result.get("error"))
        self.assertGreater(result["data_bars"], 200)

    def test_get_technical_setup_reuses_postgres_on_demand_history_before_fetching(self):
        rows = []
        start = date(2025, 1, 1)
        for i in range(240):
            close = 100 + i * 0.5
            rows.append(
                {
                    "SYMBOL": "PGHIST",
                    "TIMESTAMP": start + timedelta(days=i),
                    "OPEN": close - 1,
                    "HIGH": close + 2,
                    "LOW": close - 2,
                    "CLOSE": close,
                    "TOTTRDQTY": 100000 + i,
                }
            )
        pg_cached = pd.DataFrame(rows)

        with (
            patch("terminal.tools._load_price_history", return_value=pd.DataFrame()),
            patch("terminal.tools._load_on_demand_price_history", return_value=pg_cached) as load_pg,
            patch("terminal.tools._fetch_on_demand_price_history") as fetch,
        ):
            result = get_technical_setup("PGHIST")

        load_pg.assert_called_once_with("PGHIST", 400)
        fetch.assert_not_called()
        self.assertEqual(result["data_source"], "PostgreSQL on-demand EOD")
        self.assertGreater(result["data_bars"], 200)

    def test_get_technical_setup_reports_missing_when_on_demand_fetch_fails(self):
        with (
            patch("terminal.tools._load_price_history", return_value=pd.DataFrame()),
            patch("terminal.tools._load_on_demand_price_history", return_value=pd.DataFrame()),
            patch("terminal.tools._fetch_on_demand_price_history", return_value=pd.DataFrame()),
        ):
            result = get_technical_setup("NOHIST")

        self.assertEqual(result["symbol"], "NOHIST")
        self.assertIn("No price history available", result["error"])
        self.assertEqual(result["missing_evidence"], ["price_history"])

    def test_symbol_snapshot_backfills_missing_stage_row_from_on_demand_technicals(self):
        with (
            patch("terminal.tools._latest_snapshot_date", return_value="2026-05-08"),
            patch("terminal.tools._read_stage_snapshot_row", return_value=None),
            patch("terminal.tools._backfill_on_demand_stage_snapshot") as backfill,
        ):
            backfill.return_value = {
                "symbol": "NIVABUPA",
                "company_name": "Niva Bupa Health Insurance Company Limited",
                "stage": "STAGE_2",
                "stage_score": 0.65,
                "price": 83.0,
                "rsi": 65.4,
                "relative_strength": 12.3,
                "technical_score": 85,
                "trading_signal": "BUY",
                "trend_signal": "BULLISH",
                "sector": "General Insurance",
                "market_cap_cat": None,
                "fundamental_score": None,
                "enhanced_fund_score": None,
                "can_slim_score": None,
                "minervini_score": None,
                "missing_evidence": ["fundamental_score", "can_slim_score", "minervini_score"],
                "evidence_coverage": "partial",
                "snapshot_date": "2026-05-08",
                "data_source": "on-demand stage snapshot",
            }

            result = get_symbol_snapshot("NIVABUPA")

        backfill.assert_called_once_with("NIVABUPA", "2026-05-08")
        self.assertEqual(result["stage"], "STAGE_2")
        self.assertEqual(result["data_source"], "on-demand stage snapshot")
        self.assertIn("fundamental_score", result["missing_evidence"])
        self.assertNotIn("error", result)

    def test_symbol_snapshot_does_not_double_scale_relative_strength(self):
        snap = _finalize_stage_snapshot(
            "USHAMART",
            {
                "company_name": "Usha Martin Ltd",
                "stage": "STAGE_2",
                "stage_score": 0.7,
                "investment_score": 70,
                "price": 100,
                "rsi": 55,
                "relative_strength": 18.22,
                "technical_score": 65,
                "trading_signal": "BUY",
                "sector": "Other",
            },
            "2026-05-08",
        )
        with patch("terminal.tools._latest_snapshot_date", return_value="2026-05-08"), patch(
            "terminal.tools._read_stage_snapshot_row", return_value=snap
        ):
            result = get_symbol_snapshot("USHAMART")

        self.assertLessEqual(result["rs_pct"], 100)
        self.assertGreater(result["rs_pct"], 0)
        self.assertIn("missing_evidence", result)

    def test_context_averages_do_not_double_scale_relative_strength(self):
        sector_rows = [
            ("AAA", "AAA Ltd", "STAGE_2", 70, 18.22, 1.0, 2.0, 3.0, 55, "BUY"),
            ("BBB", "BBB Ltd", "STAGE_1", 50, 0.1234, -1.0, 1.0, 2.0, 45, "HOLD"),
        ]
        breadth_rows = [("STAGE_2", 1), ("STAGE_1", 1)]
        breadth_source_rows = [
            ("AAA", 1.0, 2.0, 18.22),
            ("BBB", -1.0, 1.0, 0.1234),
        ]
        with patch("terminal.tools._canonical_symbol", side_effect=lambda s: str(s).upper()), patch(
            "terminal.tools._latest_snapshot_date", return_value="2026-05-08"
        ), patch(
            "terminal.tools._pg_fetchall",
            side_effect=[
                [("Other",)],
                sector_rows,
                breadth_source_rows,
                breadth_rows,
            ],
        ):
            sector = get_sector_context("USHAMART")
            breadth = get_market_breadth()

        self.assertLessEqual(abs(sector["avg_rs_pct"]), 100)
        self.assertLessEqual(abs(breadth["avg_rs_pct"]), 100)

    def test_market_breadth_returns_rs_percentiles_and_distribution(self):
        breadth_source_rows = [
            ("AAA", 1.0, 2.0, -10.0),
            ("BBB", 1.0, 2.0, 0.0),
            ("CCC", -1.0, -2.0, 20.0),
            ("DDD", -1.0, -2.0, 50.0),
            ("EEE", 0.0, 0.0, 100.0),
        ]
        breadth_rows = [("STAGE_1", 1), ("STAGE_2", 2), ("STAGE_3", 1), ("STAGE_4", 1)]

        with patch("terminal.tools._latest_snapshot_date", return_value="2026-05-08"), patch(
            "terminal.tools._pg_fetchall",
            side_effect=[breadth_source_rows, breadth_rows],
        ):
            breadth = get_market_breadth()

        self.assertEqual(breadth["rs_percentiles"]["p25"], 0.0)
        self.assertEqual(breadth["rs_percentiles"]["p50"], 20.0)
        self.assertEqual(breadth["rs_percentiles"]["p75"], 50.0)
        self.assertEqual(breadth["rs_distribution"]["negative"]["count"], 1)
        self.assertEqual(breadth["rs_distribution"]["strong_50_plus"]["count"], 2)

    def test_market_breadth_can_scope_to_index_constituents(self):
        index_rows = [
            ("AAA", 1.0, 2.0, -10.0, "STAGE_1"),
            ("BBB", 0.5, 1.0, 20.0, "STAGE_2"),
            ("CCC", -1.0, -2.0, 50.0, "STAGE_4"),
        ]

        with patch("terminal.tools._latest_snapshot_date", return_value="2026-05-08"), patch(
            "terminal.tools._pg_fetchall",
            side_effect=[
                [(5,)],
                index_rows,
            ],
        ):
            breadth = get_market_breadth(index="NIFTY500")

        self.assertEqual(breadth["scope"], "index")
        self.assertEqual(breadth["index"], "NIFTY 500")
        self.assertEqual(breadth["composition_count"], 5)
        self.assertEqual(breadth["matched_count"], 3)
        self.assertEqual(breadth["total_stocks"], 3)
        self.assertEqual(breadth["advances"], 2)
        self.assertEqual(breadth["declines"], 1)
        self.assertEqual(breadth["stage_distribution"]["STAGE_2"], 1)
        self.assertIn("constituent_score_coverage:3/5", breadth["warnings"])

    def test_market_breadth_index_scope_reports_missing_constituents(self):
        with patch("terminal.tools._latest_snapshot_date", return_value="2026-05-08"), patch(
            "terminal.tools._pg_fetchall",
            return_value=[(0,)],
        ), patch("terminal.tools._load_index_constituents_local", return_value=[]):
            breadth = get_market_breadth(index="NIFTY BANK")

        self.assertEqual(breadth["index"], "NIFTY BANK")
        self.assertIn("Index constituents unavailable", breadth["error"])
        self.assertIn("ref.index_compositions", breadth["missing_evidence"])
        self.assertIn("local_index_constituents", breadth["missing_evidence"])

    def test_market_breadth_midcpnifty_uses_local_constituent_fallback(self):
        index_rows = [
            ("AAA", 1.0, 2.0, 70.0, "STAGE_2"),
            ("BBB", -0.5, 1.0, 40.0, "STAGE_3"),
        ]

        with patch("terminal.tools._latest_snapshot_date", return_value="2026-05-08"), patch(
            "terminal.tools._load_index_constituents_local",
            return_value=["AAA", "BBB", "CCC"],
        ), patch(
            "terminal.tools._pg_fetchall",
            side_effect=[
                [(0,)],
                index_rows,
            ],
        ):
            breadth = get_market_breadth(index="MIDCPNIFTY")

        self.assertEqual(breadth["scope"], "index")
        self.assertEqual(breadth["index"], "NIFTY MIDCAP SELECT")
        self.assertEqual(breadth["composition_count"], 3)
        self.assertEqual(breadth["matched_count"], 2)
        self.assertEqual(breadth["advances"], 1)
        self.assertEqual(breadth["declines"], 1)
        self.assertEqual(breadth["data_source"], "PostgreSQL scores.stage_snapshots + local index constituent CSV")

    def test_nifty500_analysis_routes_breadth_to_nifty500_scope(self):
        routed = _keyword_intent("NIFTY 500 analysis")

        self.assertEqual(routed["intent"], "index_status")
        self.assertIn(("get_index_snapshot", {"index_name": "NIFTY 500"}), routed["plan"])
        self.assertIn(("get_market_breadth", {"index": "NIFTY 500"}), routed["plan"])
        self.assertIn(
            ("get_top_gainers_losers", {"index": "NIFTY 500", "top_n": 10, "direction": "both"}),
            routed["plan"],
        )

    def test_compact_nifty500_look_query_routes_to_index_scope(self):
        routed = _keyword_intent("how does NIFTY500 look like")

        self.assertEqual(routed["intent"], "index_status")
        self.assertIn(("get_index_snapshot", {"index_name": "NIFTY 500"}), routed["plan"])
        self.assertIn(("get_market_breadth", {"index": "NIFTY 500"}), routed["plan"])
        self.assertNotIn(("resolve_symbol", {"query": "NIFTY500"}), routed["plan"])

    def test_nifty200_analysis_routes_breadth_to_nifty200_scope(self):
        routed = _keyword_intent("analyse NIFTY 200 breadth")

        self.assertEqual(routed["intent"], "index_status")
        self.assertIn(("get_index_snapshot", {"index_name": "NIFTY 200"}), routed["plan"])
        self.assertIn(("get_market_breadth", {"index": "NIFTY 200"}), routed["plan"])

    def test_midcpnifty_routes_to_midcap_select_index_scope(self):
        routed = _keyword_intent("MIDCPNIFTY analysis")

        self.assertEqual(routed["intent"], "index_status")
        self.assertIn(("get_index_snapshot", {"index_name": "NIFTY MIDCAP SELECT"}), routed["plan"])
        self.assertIn(("get_market_breadth", {"index": "NIFTY MIDCAP SELECT"}), routed["plan"])
        self.assertNotIn(("resolve_symbol", {"query": "MIDCPNIFTY"}), routed["plan"])

    def test_generic_nifty_midcap_routes_to_midcap_select_not_stock(self):
        routed = _keyword_intent("how does NIFTY MIDCAP look like")

        self.assertEqual(routed["intent"], "index_status")
        self.assertIn(("get_index_snapshot", {"index_name": "NIFTY MIDCAP SELECT"}), routed["plan"])
        self.assertIn(("get_market_breadth", {"index": "NIFTY MIDCAP SELECT"}), routed["plan"])

    def test_midcpnifty_constituent_alias_normalizes_to_midcap_select(self):
        self.assertEqual(_normalize_index_name("MIDCPNIFTY"), "NIFTY MIDCAP SELECT")
        self.assertEqual(_normalize_index_name("NIFTY MIDCAP"), "NIFTY MIDCAP SELECT")

    def test_midcpnifty_top_movers_are_filtered_to_constituents(self):
        def fake_payload(url: str, timeout: int = 10):
            data = [
                {"symbol": "OUTSIDE", "ltp": 10, "perChange": 20.0, "net_price": 2},
                {"symbol": "AAA", "ltp": 100, "perChange": 5.0, "net_price": 5},
                {"symbol": "BBB", "ltp": 90, "perChange": -3.0, "net_price": -3},
            ]
            return {"allSec": {"data": data}}

        with patch("terminal.tools._fetch_nse_index_constituents", return_value=["AAA", "BBB"]), patch(
            "terminal.tools._nse_get_json",
            side_effect=fake_payload,
        ):
            movers = get_top_gainers_losers(index="MIDCPNIFTY", top_n=5, direction="both")

        self.assertEqual(movers["canonical_index"], "NIFTY MIDCAP SELECT")
        self.assertEqual(movers["constituent_count"], 2)
        self.assertEqual([row["symbol"] for row in movers["gainers"]], ["AAA", "BBB"])
        self.assertEqual([row["symbol"] for row in movers["losers"]], ["BBB", "AAA"])
        self.assertNotIn("OUTSIDE", {row["symbol"] for row in movers["gainers"] + movers["losers"]})


if __name__ == "__main__":
    unittest.main()
