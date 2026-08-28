import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from company_intelligence.company_intelligence import run_company_xray
from company_intelligence.company_intelligence_db import init_company_intelligence_db
from company_intelligence.company_website_indexer import crawl_company_website


class CompanyIntelligenceOrchestratorTests(unittest.TestCase):
    def test_run_company_xray_permissive_writes_report_with_gaps(self):
        with TemporaryDirectory() as td:
            result = run_company_xray(
                "DMART",
                strict=False,
                db_path=Path(td) / "company_intelligence.db",
                output_dir=Path(td) / "reports",
                evidence_records=[
                    {
                        "document_id": "annual-report",
                        "category": "business model",
                        "text": "DMART operates a value retail store model.",
                        "source_tier": 1,
                        "confidence": 0.9,
                    },
                    {
                        "document_id": "sector-map",
                        "category": "sector structure",
                        "text": "DMART operates in organized grocery retail.",
                        "source_tier": 2,
                        "confidence": 0.7,
                    },
                ],
                search_attempts=[
                    {
                        "source_group": "external_context",
                        "query": "Avenue Supermarts broker research",
                        "alias_used": "Avenue Supermarts",
                        "result_count": 0,
                        "urls_found": [],
                        "status": "no_results",
                        "failure_reason": "no accessible broker report",
                    }
                ],
            )

            self.assertEqual(result["status"], "ok")
            self.assertFalse(result["strict"])
            self.assertTrue(Path(result["report_markdown_path"]).exists())
            self.assertTrue(Path(result["report_html_path"]).exists())
            self.assertIn("Broker research unavailable", result["known_gaps"])

    def test_run_company_xray_strict_blocks_weak_report_and_records_analysis(self):
        with TemporaryDirectory() as td:
            db_path = Path(td) / "company_intelligence.db"
            result = run_company_xray(
                "DMART",
                strict=True,
                db_path=db_path,
                output_dir=Path(td) / "reports",
                evidence_records=[],
                search_attempts=[],
            )

            self.assertEqual(result["status"], "blocked")
            self.assertTrue(result["strict"])
            self.assertTrue(Path(result["report_markdown_path"]).exists())
            self.assertIn("Missing or weak official evidence", result["strict_failures"])

            with sqlite3.connect(db_path) as conn:
                row = conn.execute(
                    "SELECT symbol, workflow, mode, status FROM analysis_runs WHERE symbol = ?",
                    ("DMART",),
                ).fetchone()
            self.assertEqual(row, ("DMART", "company_xray", "strict", "blocked"))

    def test_run_company_xray_uses_indexed_website_evidence(self):
        pages = {
            "https://www.example.com/investors/": """
                <html><head><title>Investor Relations</title></head><body>
                  <p>DMART operates a value retail business model for grocery customers.</p>
                  <p>The organized retail sector structure includes peers and competitors.</p>
                </body></html>
            """,
        }

        def fetcher(url):
            return {"url": url, "status": "ok", "status_code": 200, "content_type": "text/html", "text": pages[url]}

        with TemporaryDirectory() as td:
            db_path = init_company_intelligence_db(Path(td) / "company_intelligence.db")
            with sqlite3.connect(db_path) as conn:
                crawl_company_website(conn, "DMART", "https://www.example.com/investors/", fetcher=fetcher)

            result = run_company_xray(
                "DMART",
                strict=False,
                db_path=db_path,
                output_dir=Path(td) / "reports",
                evidence_records=[],
                search_attempts=[],
            )

            report_text = Path(result["report_markdown_path"]).read_text()

        self.assertEqual(result["coverage"]["official_evidence"], "High")
        self.assertEqual(result["coverage"]["business_model"], "High")
        self.assertIn("value retail business model", report_text)


if __name__ == "__main__":
    unittest.main()
