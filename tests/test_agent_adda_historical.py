import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path

from agent_adda.data.historical import bootstrap_historical_store


class AgentAddaHistoricalTests(unittest.TestCase):
    def test_bootstrap_loads_daily_prices_from_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            with (source / "sample.csv").open("w", newline="") as fh:
                writer = csv.DictWriter(
                    fh,
                    fieldnames=["SYMBOL", "DATE", "OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "SYMBOL": "RELIANCE",
                        "DATE": "2026-05-04",
                        "OPEN": "1400",
                        "HIGH": "1420",
                        "LOW": "1390",
                        "CLOSE": "1410",
                        "VOLUME": "12345",
                    }
                )
            db_path = root / "market_data.sqlite"
            result = bootstrap_historical_store(db_path, [source])
            self.assertEqual(result.rows_loaded, 1)
            with sqlite3.connect(db_path) as conn:
                rows = conn.execute("select symbol, trade_date, close from daily_prices").fetchall()
            self.assertEqual(rows, [("RELIANCE", "2026-05-04", 1410.0)])


if __name__ == "__main__":
    unittest.main()
