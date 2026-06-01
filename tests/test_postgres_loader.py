import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import daily_refresh
from postgres import loader


class FakeCursor:
    def __init__(self):
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))


class PostgresLoaderTests(unittest.TestCase):
    def test_load_equity_eod_reads_all_available_history_csvs(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            (data_dir / "nse-raw").mkdir()
            (data_dir / "data" / "nse-raw").mkdir(parents=True)
            pd.DataFrame(
                [
                    {
                        "SYMBOL": "AAA",
                        "TIMESTAMP": "2025-01-01",
                        "OPEN": 10,
                        "HIGH": 12,
                        "LOW": 9,
                        "CLOSE": 11,
                        "SERIES": "EQ",
                    }
                ]
            ).to_csv(data_dir / "data" / "nse-raw" / "nse_sec_full_data.csv", index=False)
            pd.DataFrame(
                [
                    {
                        "SYMBOL": "AAA",
                        "TIMESTAMP": "2026-05-14",
                        "OPEN": 20,
                        "HIGH": 22,
                        "LOW": 19,
                        "CLOSE": 21,
                        "SERIES": "EQ",
                    },
                ]
            ).to_csv(data_dir / "nse_sec_full_data.csv", index=False)

            captured = {}

            def fake_upsert(cur, table, rows, conflict_cols, update_cols=None):
                captured["table"] = table
                captured["rows"] = rows
                captured["conflict_cols"] = conflict_cols
                return len(rows)

            original_data = loader.DATA
            try:
                loader.DATA = data_dir
                with patch("postgres.loader.upsert", side_effect=fake_upsert):
                    count = loader.load_equity_eod(object())
            finally:
                loader.DATA = original_data

        self.assertEqual(count, 2)
        self.assertEqual(captured["table"], "market.equity_eod")
        self.assertEqual(captured["conflict_cols"], ["trade_date", "symbol", "series"])
        rows_by_date = {row["trade_date"]: row for row in captured["rows"]}
        self.assertEqual(set(rows_by_date), {"2025-01-01", "2026-05-14"})
        self.assertEqual(rows_by_date["2025-01-01"]["close"], 11.0)

    def test_load_equity_eod_nulls_out_unstorable_change_pct(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            pd.DataFrame(
                [
                    {
                        "SYMBOL": "AAA",
                        "TIMESTAMP": "2026-05-14",
                        "OPEN": 100,
                        "HIGH": 110,
                        "LOW": 95,
                        "CLOSE": 10000,
                        "PREVCLOSE": 1,
                        "SERIES": "EQ",
                    },
                ]
            ).to_csv(data_dir / "nse_sec_full_data.csv", index=False)

            captured = {}

            def fake_upsert(cur, table, rows, conflict_cols, update_cols=None):
                captured["rows"] = rows
                return len(rows)

            original_data = loader.DATA
            try:
                loader.DATA = data_dir
                with patch("postgres.loader.upsert", side_effect=fake_upsert):
                    loader.load_equity_eod(object())
            finally:
                loader.DATA = original_data

        self.assertIsNone(captured["rows"][0]["change_pct"])

    def test_load_index_eod_upserts_all_rows_from_index_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            pd.DataFrame(
                [
                    {
                        "SYMBOL": "Nifty 50",
                        "TIMESTAMP": "2026-05-12",
                        "OPEN": 23000,
                        "HIGH": 23500,
                        "LOW": 22800,
                        "CLOSE": 23379.55,
                        "PREVCLOSE": 23800,
                        "TOTTRDQTY": 123456,
                        "TOTTRDVAL": 987654321,
                        "TOTALTRADES": 1000,
                        "HI_52_WK": 26000,
                        "LO_52_WK": 20000,
                    },
                    {
                        "SYMBOL": "Nifty Bank",
                        "TIMESTAMP": "2026-05-12",
                        "OPEN": 53000,
                        "HIGH": 54000,
                        "LOW": 52800,
                        "CLOSE": 53500,
                    },
                ]
            ).to_csv(data_dir / "nse_index_data.csv", index=False)

            captured = {}

            def fake_upsert(cur, table, rows, conflict_cols, update_cols=None):
                captured["table"] = table
                captured["rows"] = rows
                captured["conflict_cols"] = conflict_cols
                captured["update_cols"] = update_cols
                return len(rows)

            original_data = loader.DATA
            try:
                loader.DATA = data_dir
                with patch("postgres.loader.upsert", side_effect=fake_upsert):
                    count = loader.load_index_eod(object())
            finally:
                loader.DATA = original_data

        self.assertEqual(count, 2)
        self.assertEqual(captured["table"], "market.index_eod")
        self.assertEqual(captured["conflict_cols"], ["trade_date", "index_symbol"])
        self.assertEqual(captured["rows"][0]["index_symbol"], "Nifty 50")
        self.assertEqual(captured["rows"][0]["trade_date"], "2026-05-12")
        self.assertAlmostEqual(captured["rows"][0]["turnover_cr"], 98.7654)
        self.assertIn("change_pct", captured["update_cols"])

    def test_load_fno_today_loads_all_cached_bhavcopy_dates(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            cache_dir = data_dir / "_fno_cache"
            cache_dir.mkdir()
            columns = [
                "TradDt",
                "INSTRUMENT",
                "SYMBOL",
                "EXPIRY_DATE",
                "STRIKE_PRICE",
                "OPTION_TYPE",
                "OpnPric",
                "HghPric",
                "LwPric",
                "CLOSE",
                "LastPric",
                "PREV_CLOSE",
                "UndrlygPric",
                "SETTLE_PRICE",
                "OPEN_INTEREST",
                "CHANGE_IN_OI",
                "VOLUME",
                "TtlTrfVal",
                "TtlNbOfTxsExctd",
                "NewBrdLotQty",
            ]
            pd.DataFrame(
                [
                    ["2026-05-21", "STO", "ABCAPITAL", "2026-05-28", 300, "CE", 1, 2, 1, 1.5, 1.45, 1.4, 310, 1.5, 100, 10, 20, 10000000, 4, 3100],
                    ["2026-05-21", "STF", "ABCAPITAL", "2026-05-28", 0, "", 300, 305, 298, 302, 302, 299, 301, 302, 500, 25, 12, 20000000, 3, 3100],
                ],
                columns=columns,
            ).to_csv(cache_dir / "fo_bhav_20260521.csv", index=False)
            pd.DataFrame(
                [
                    ["2026-05-22", "STO", "NIFTY", "2026-05-28", 25000, "PE", 10, 12, 8, 9, 9.5, 10.5, 24900, 9, 200, -5, 40, 30000000, 7, 75],
                ],
                columns=columns,
            ).to_csv(cache_dir / "fo_bhav_20260522.csv", index=False)
            pd.DataFrame([["bad"]], columns=["not_a_bhavcopy"]).to_csv(cache_dir / "fo_bhav_test.csv", index=False)

            captured = {}

            def fake_execute_values(cur, sql, values, page_size=None):
                captured["sql"] = sql
                captured["values"] = values
                captured["page_size"] = page_size

            cur = FakeCursor()
            original_data = loader.DATA
            try:
                loader.DATA = data_dir
                with patch("postgres.loader.execute_values", side_effect=fake_execute_values):
                    count = loader.load_fno_today(cur)
            finally:
                loader.DATA = original_data

        self.assertEqual(count, 3)
        self.assertEqual(len(captured["values"]), 3)
        self.assertIn("ON CONFLICT ON CONSTRAINT fno_eod_pkey DO UPDATE", captured["sql"])
        partition_dates = [params[0] for sql, params in cur.executed if "ensure_fno_monthly_partition" in sql]
        self.assertEqual(partition_dates, ["2026-05-21", "2026-05-22"])
        self.assertTrue(any("FUT" in row for row in captured["values"]))

    def test_daily_refresh_loads_fno_postgres_before_sector_report(self):
        calls = []

        def record(name, result=True):
            def inner(*args, **kwargs):
                calls.append(name)
                return result

            return inner

        with patch.object(daily_refresh, "step_fetch_eod_data", record("fetch_eod")), \
             patch.object(daily_refresh, "step_postgres_eod_load", record("postgres_eod")), \
             patch.object(daily_refresh, "step_fetch_auxiliary", record("fetch_aux", {"F&O OI + PCR": True})), \
             patch.object(daily_refresh, "step_fno_postgres_load", record("fno_postgres")), \
             patch.object(daily_refresh, "step_comprehensive_analysis", record("analysis")), \
             patch.object(daily_refresh, "step_tracker_snapshot", record("tracker")), \
             patch.object(daily_refresh, "step_generate_report", record("html")), \
             patch.object(daily_refresh, "step_sector_rotation_report", record("sector_report")), \
             patch.object(daily_refresh, "step_voice_briefing", record("voice")), \
             patch.object(daily_refresh, "step_postgres_load", record("postgres_full")), \
             patch.object(daily_refresh, "step_refresh_results_feed", record("results_feed")), \
             patch.object(daily_refresh, "datetime") as fake_datetime, \
             patch.object(sys, "argv", ["daily_refresh.py"]):
            fake_datetime.now.return_value.weekday.return_value = 0
            exit_code = daily_refresh.main()

        self.assertEqual(exit_code, 0)
        self.assertIn("fno_postgres", calls)
        self.assertLess(calls.index("fno_postgres"), calls.index("sector_report"))


if __name__ == "__main__":
    unittest.main()
