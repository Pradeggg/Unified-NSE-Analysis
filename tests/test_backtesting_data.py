import tempfile
import unittest
from pathlib import Path

from backtesting.data import inspect_backtest_data


class BacktestingDataTests(unittest.TestCase):
    def test_missing_required_eod_file_blocks_backtests(self):
        with tempfile.TemporaryDirectory() as tmp:
            status = inspect_backtest_data(Path(tmp))

        self.assertFalse(status.ok_to_backtest)
        self.assertIn("missing_eod_ohlcv", status.blockers)

    def test_present_minimal_eod_file_allows_technical_only_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data").mkdir()
            (root / "data" / "nse_sec_full_data.csv").write_text(
                "SYMBOL,DATE,OPEN,HIGH,LOW,CLOSE,VOLUME\n"
                "DMART,2026-05-08,1,2,1,2,1000\n",
                encoding="utf-8",
            )

            status = inspect_backtest_data(root)

        self.assertTrue(status.ok_to_backtest)
        self.assertIn("technical-only", status.modes)
        self.assertEqual(status.latest_eod_date, "2026-05-08")
        self.assertEqual(status.symbol_count, 1)

    def test_eod_readiness_scans_beyond_first_large_chunk_for_latest_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data").mkdir()
            rows = ["SYMBOL,DATE,OPEN,HIGH,LOW,CLOSE,VOLUME\n"]
            rows.extend(
                f"AAA,2023-01-01,1,2,1,2,{1000 + i}\n"
                for i in range(100005)
            )
            rows.append("BBB,2026-05-08,1,2,1,2,2000\n")
            (root / "data" / "nse_sec_full_data.csv").write_text("".join(rows), encoding="utf-8")

            status = inspect_backtest_data(root)

        self.assertTrue(status.ok_to_backtest)
        self.assertEqual(status.latest_eod_date, "2026-05-08")
        self.assertEqual(status.symbol_count, 2)


if __name__ == "__main__":
    unittest.main()
