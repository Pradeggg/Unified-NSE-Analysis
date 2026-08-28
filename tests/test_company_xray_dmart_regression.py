import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from company_intelligence.company_intelligence import run_company_xray


class CompanyXrayDmartRegressionTests(unittest.TestCase):
    def test_dmart_no_result_searches_create_auditable_gaps_not_fabricated_targets(self):
        with TemporaryDirectory() as td:
            db_path = Path(td) / "company_intelligence.db"
            result = run_company_xray(
                "DMART",
                strict=False,
                db_path=db_path,
                output_dir=Path(td) / "reports",
                evidence_records=[
                    {
                        "document_id": "annual-report",
                        "category": "business model",
                        "text": "Avenue Supermarts operates DMart as a value retail store model.",
                        "source_tier": 1,
                        "confidence": 0.9,
                    }
                ],
                search_attempts=[
                    {
                        "source_group": "external_context",
                        "vertical": "broker_research",
                        "query": "Avenue Supermarts broker research",
                        "alias_used": "Avenue Supermarts",
                        "result_count": 0,
                        "urls_found": [],
                        "status": "no_results",
                        "failure_reason": "no accessible broker report",
                    },
                    {
                        "source_group": "external_context",
                        "vertical": "concalls",
                        "query": "Avenue Supermarts concall transcript",
                        "alias_used": "Avenue Supermarts",
                        "result_count": 0,
                        "urls_found": [],
                        "status": "no_results",
                        "failure_reason": "no accessible transcript",
                    },
                ],
            )

            report = Path(result["report_markdown_path"]).read_text()
            self.assertIn("Broker research unavailable", report)
            self.assertIn("No parsed concall transcript found", report)
            self.assertNotIn("price target", report.lower())
            self.assertNotIn("buy recommendation", report.lower())

            with sqlite3.connect(db_path) as conn:
                attempts = conn.execute(
                    "SELECT query, alias_used, status, failure_reason FROM search_attempts ORDER BY attempt_id"
                ).fetchall()

            self.assertEqual(len(attempts), 2)
            self.assertEqual(attempts[0][1], "Avenue Supermarts")
            self.assertEqual(attempts[0][2], "no_results")
            self.assertIn("no accessible", attempts[0][3])


if __name__ == "__main__":
    unittest.main()
