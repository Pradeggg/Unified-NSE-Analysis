import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from postgres import loader


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


if __name__ == "__main__":
    unittest.main()
