import tempfile
import unittest
from pathlib import Path

import pandas as pd
from unittest.mock import patch

from backtesting.strategy_council import evidence
from backtesting.strategy_council.evidence import build_evidence_pack


class StrategyCouncilEvidenceTests(unittest.TestCase):
    def test_build_evidence_pack_reads_latest_symbol_eod_and_marks_missing_optional_sources(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "data").mkdir()
            pd.DataFrame(
                [
                    {"SYMBOL": "DMART", "TIMESTAMP": "2026-05-10", "OPEN": 100, "HIGH": 110, "LOW": 95, "CLOSE": 105, "TOTTRDQTY": 1000},
                    {"SYMBOL": "DMART", "TIMESTAMP": "2026-05-11", "OPEN": 105, "HIGH": 112, "LOW": 101, "CLOSE": 111, "TOTTRDQTY": 1200},
                    {"SYMBOL": "TCS", "TIMESTAMP": "2026-05-11", "OPEN": 200, "HIGH": 205, "LOW": 198, "CLOSE": 202, "TOTTRDQTY": 900},
                ]
            ).to_csv(root / "data" / "nse_sec_full_data.csv", index=False)

            with patch.object(
                evidence,
                "_load_symbol_eod_from_postgres",
                return_value=(pd.DataFrame(), "PostgreSQL market.equity_eod: unavailable"),
            ):
                pack = build_evidence_pack("DMART", project_root=root)

        self.assertEqual(pack.symbol, "DMART")
        self.assertEqual(pack.as_of, "2026-05-11")
        self.assertEqual(pack.technical["close"], 111.0)
        self.assertEqual(pack.technical["volume"], 1200.0)
        self.assertIn("fundamentals", pack.missing)
        self.assertIn("news", pack.missing)
        self.assertIn("data/nse_sec_full_data.csv", " ".join(pack.source_trail))

    def test_build_evidence_pack_merges_archived_stock_history_when_live_csv_is_short(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "data" / "data" / "nse-raw").mkdir(parents=True)
            pd.DataFrame(
                [
                    {"SYMBOL": "DMART", "TIMESTAMP": "2026-05-11", "OPEN": 140, "HIGH": 145, "LOW": 138, "CLOSE": 144, "TOTTRDQTY": 2000},
                ]
            ).to_csv(root / "data" / "nse_sec_full_data.csv", index=False)
            pd.DataFrame(
                [
                    {"SYMBOL": "DMART", "TIMESTAMP": f"2026-03-{day:02d}", "OPEN": 100 + day, "HIGH": 102 + day, "LOW": 99 + day, "CLOSE": 101 + day, "TOTTRDQTY": 1000 + day}
                    for day in range(1, 29)
                ]
                + [
                    {"SYMBOL": "DMART", "TIMESTAMP": f"2026-04-{day:02d}", "OPEN": 120 + day, "HIGH": 122 + day, "LOW": 119 + day, "CLOSE": 121 + day, "TOTTRDQTY": 1200 + day}
                    for day in range(1, 11)
                ]
            ).to_csv(root / "data" / "data" / "nse-raw" / "nse_sec_full_data.csv", index=False)

            with patch.object(
                evidence,
                "_load_symbol_eod_from_postgres",
                return_value=(pd.DataFrame(), "PostgreSQL market.equity_eod: unavailable"),
            ):
                pack = build_evidence_pack("DMART", project_root=root)

        self.assertEqual(pack.as_of, "2026-05-11")
        self.assertGreaterEqual(pack.technical["bars"], 39)
        self.assertEqual(pack.technical["close"], 144.0)
        self.assertIn("data/data/nse-raw/nse_sec_full_data.csv", " ".join(pack.source_trail))

    def test_load_symbol_eod_history_prefers_postgres_over_csv(self):
        pg_rows = pd.DataFrame(
            [
                {
                    "symbol": "DMART",
                    "date": f"2025-01-{day:02d}",
                    "open": 100 + day,
                    "high": 101 + day,
                    "low": 99 + day,
                    "close": 100.5 + day,
                    "volume": 1000 + day,
                }
                for day in range(1, 6)
            ]
        )
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "data").mkdir()
            pd.DataFrame(
                [
                    {
                        "SYMBOL": "DMART",
                        "TIMESTAMP": "2026-05-11",
                        "OPEN": 900,
                        "HIGH": 910,
                        "LOW": 890,
                        "CLOSE": 905,
                        "TOTTRDQTY": 1200,
                    }
                ]
            ).to_csv(root / "data" / "nse_sec_full_data.csv", index=False)

            with patch.object(evidence, "_load_symbol_eod_from_postgres", return_value=(pg_rows, "PostgreSQL market.equity_eod: ok")):
                history, trail = evidence.load_symbol_eod_history("DMART", project_root=root)

        self.assertEqual(len(history), 5)
        self.assertEqual(history["close"].iloc[-1], 105.5)
        self.assertIn("PostgreSQL market.equity_eod: ok", trail)
        self.assertNotIn("data/nse_sec_full_data.csv: ok", trail)
