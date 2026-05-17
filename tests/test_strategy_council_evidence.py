import tempfile
import unittest
from pathlib import Path

import pandas as pd
from unittest.mock import patch

from backtesting.strategy_council import evidence
from backtesting.strategy_council.evidence import (
    build_evidence_pack,
    build_strategy_council_evidence_pack,
    enrich_strategy_council_evidence,
    score_strategy_data_readiness,
    validate_strategy_council_evidence,
)


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

    def test_enrich_strategy_council_evidence_adds_optional_sources(self):
        pack = evidence.EvidencePack(symbol="DMART", as_of="2026-05-15", technical={"close": 100, "bars": 300})
        pack.missing = ["fundamentals", "market_breadth", "news", "latest_results"]

        with patch.object(evidence, "_fetch_symbol_snapshot", return_value={"symbol": "DMART", "fundamental_score": 72, "sector": "Retail"}), \
             patch.object(evidence, "_fetch_market_breadth", return_value={"advances": 500, "declines": 420}), \
             patch.object(evidence, "_fetch_latest_catalysts", return_value={"results": [{"title": "DMART update"}]}), \
             patch.object(evidence, "_fetch_latest_results", return_value={"status": "ok", "facts": {"revenue": {"value": "14000"}}}):
            enriched = enrich_strategy_council_evidence(pack)

        self.assertEqual(enriched.fundamental["snapshot"]["fundamental_score"], 72)
        self.assertEqual(enriched.market["breadth"]["advances"], 500)
        self.assertEqual(enriched.news[0]["title"], "DMART update")
        self.assertEqual(enriched.fundamental["latest_results"]["status"], "ok")
        self.assertNotIn("fundamentals", enriched.missing)
        self.assertIn("get_latest_results: ok", enriched.source_trail)

    def test_validate_strategy_council_evidence_reports_missing_attempts(self):
        pack = evidence.EvidencePack(symbol="DMART", as_of="2026-05-15", missing=["fundamentals"])
        pack.technical = {}

        result = validate_strategy_council_evidence(pack)

        self.assertEqual(result["status"], "insufficient")
        self.assertIn("technical_eod", result["missing_mandatory"])
        self.assertIn("fundamentals", result["missing_optional"])

    def test_score_strategy_data_readiness_drops_when_optional_evidence_absent(self):
        complete = evidence.EvidencePack(symbol="DMART", as_of="2026-05-15", technical={"close": 100, "bars": 300})
        complete.fundamental["snapshot"] = {"fundamental_score": 70}
        complete.market["breadth"] = {"advances": 500}
        complete.news = [{"title": "news"}]
        complete.fundamental["latest_results"] = {"status": "ok"}

        partial = evidence.EvidencePack(symbol="DMART", as_of="2026-05-15", technical={"close": 100, "bars": 300}, missing=["fundamentals", "news"])

        self.assertGreater(score_strategy_data_readiness(complete)["score"], score_strategy_data_readiness(partial)["score"])

    def test_build_strategy_council_evidence_pack_enriches_base_pack(self):
        base = evidence.EvidencePack(symbol="DMART", as_of="2026-05-15", technical={"close": 100, "bars": 300})
        with patch.object(evidence, "build_evidence_pack", return_value=base), \
             patch.object(evidence, "enrich_strategy_council_evidence", return_value=base) as enrich:
            result = build_strategy_council_evidence_pack("DMART")

        self.assertEqual(result.symbol, "DMART")
        enrich.assert_called_once()
