import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from company_intelligence_db import init_company_intelligence_db
from company_intelligence_extract import (
    classify_evidence_text,
    list_evidence_by_symbol,
    store_evidence_chunk,
)


class CompanyIntelligenceExtractTests(unittest.TestCase):
    def test_store_and_list_evidence_chunk(self):
        with TemporaryDirectory() as td:
            db_path = init_company_intelligence_db(Path(td) / "company_intelligence.db")
            with sqlite3.connect(db_path) as conn:
                chunk_id = store_evidence_chunk(
                    conn,
                    document_id="doc-1",
                    symbol="DMART",
                    category="business model",
                    text="DMART operates a value retail model with store-led distribution.",
                    source_tier=1,
                    confidence=0.9,
                    page_number=3,
                    table_id="",
                    evidence_date="2026-03-31",
                )
                rows = list_evidence_by_symbol(conn, "DMART")

            self.assertGreater(chunk_id, 0)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["symbol"], "DMART")
            self.assertEqual(rows[0]["category"], "business model")
            self.assertEqual(rows[0]["source_tier"], 1)
            self.assertEqual(rows[0]["page_number"], 3)

    def test_classify_evidence_text_maps_business_categories(self):
        cases = {
            "same store sales growth and new store additions": "operating model",
            "customers include BFSI and retail clients": "customer base",
            "market share increased in organized grocery retail": "market share",
            "repo rate cut may reduce borrowing costs": "RBI monetary policy sensitivity",
            "budget capex allocation supports infrastructure demand": "Union Budget sensitivity",
        }

        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertIn(expected, classify_evidence_text(text))


if __name__ == "__main__":
    unittest.main()
