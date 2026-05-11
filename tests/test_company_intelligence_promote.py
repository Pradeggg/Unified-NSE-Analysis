import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from company_intelligence_db import init_company_intelligence_db
from company_intelligence_extract import list_evidence_by_symbol
from company_intelligence_promote import promote_indexed_company_evidence
from company_website_indexer import crawl_company_website, download_company_document


class CompanyIntelligencePromoteTests(unittest.TestCase):
    def test_promote_indexed_company_evidence_promotes_website_chunks(self):
        pages = {
            "https://www.example.com/investors/": """
                <html><head><title>Investor Relations</title></head><body>
                  <p>DMART operates a value retail business model for grocery customers.</p>
                  <p>Organized retail sector structure includes competitors and peers.</p>
                </body></html>
            """,
        }

        def fetcher(url):
            return {"url": url, "status": "ok", "status_code": 200, "content_type": "text/html", "text": pages[url]}

        with TemporaryDirectory() as td:
            db_path = init_company_intelligence_db(Path(td) / "company_intelligence.db")
            with sqlite3.connect(db_path) as conn:
                crawl_company_website(conn, "DMART", "https://www.example.com/investors/", fetcher=fetcher)

                result = promote_indexed_company_evidence(conn, "DMART", parse_documents=False)
                evidence = list_evidence_by_symbol(conn, "DMART")

        self.assertEqual(result["website_chunks_promoted"], 1)
        self.assertEqual(result["document_chunks_promoted"], 0)
        self.assertEqual(evidence[0]["document_id"].split(":")[0], "website_page")
        self.assertEqual(evidence[0]["source_tier"], 1)
        self.assertIn(evidence[0]["category"], {"business model", "customer base", "sector structure", "competitor list"})
        self.assertIn("value retail business model", evidence[0]["text"])

    def test_promote_indexed_company_evidence_parses_downloaded_documents(self):
        def fetcher(url):
            return {
                "url": url,
                "status": "ok",
                "status_code": 200,
                "content_type": "application/pdf",
                "content": b"%PDF investor presentation",
            }

        def fake_pdf_parser(path):
            return {
                "status": "ok",
                "pages": [
                    {
                        "page_number": 1,
                        "text": "DMART value retail business model serves grocery customers through store network.",
                    },
                    {
                        "page_number": 2,
                        "text": "Competition risk from quick commerce and other organized retail peers.",
                    },
                ],
            }

        with TemporaryDirectory() as td:
            db_path = init_company_intelligence_db(Path(td) / "company_intelligence.db")
            with sqlite3.connect(db_path) as conn:
                downloaded = download_company_document(
                    conn,
                    "DMART",
                    "https://www.example.com/investor-presentation.pdf",
                    "investor_presentation",
                    fetcher=fetcher,
                    root_dir=Path(td) / "documents",
                )

                result = promote_indexed_company_evidence(conn, "DMART", pdf_parser=fake_pdf_parser)
                evidence = list_evidence_by_symbol(conn, "DMART")
                parse_status = conn.execute(
                    "SELECT parse_status FROM source_documents WHERE symbol = 'DMART'"
                ).fetchone()[0]

        self.assertEqual(result["documents_parsed"], 1)
        self.assertEqual(result["document_chunks_promoted"], 2)
        self.assertEqual(parse_status, "parsed")
        self.assertEqual([row["page_number"] for row in evidence], [1, 2])
        self.assertEqual({row["document_id"] for row in evidence}, {downloaded["document_id"]})


if __name__ == "__main__":
    unittest.main()
