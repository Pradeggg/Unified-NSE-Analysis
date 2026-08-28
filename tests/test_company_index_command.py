import json
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from company_intelligence.company_index_command import parse_company_index_args, run_company_index
from company_intelligence.company_intelligence_db import init_company_intelligence_db


class CompanyIndexCommandTests(unittest.TestCase):
    def test_parse_company_index_args_supports_backend_options(self):
        args = parse_company_index_args(
            "DMART --max-pages 7 --include-documents --seed-sitemap --respect-robots "
            "--adapter auto --document-limit 3 --website https://www.dmartindia.com/investor-relationship"
        )

        self.assertEqual(args.symbol, "DMART")
        self.assertEqual(args.max_pages, 7)
        self.assertTrue(args.include_documents)
        self.assertTrue(args.seed_sitemap)
        self.assertTrue(args.respect_robots)
        self.assertEqual(args.adapter, "auto")
        self.assertEqual(args.document_limit, 3)
        self.assertEqual(args.website, "https://www.dmartindia.com/investor-relationship")

    def test_run_company_index_uses_dmart_adapter_and_downloads_limited_documents(self):
        api_payload = [
            {
                "contentId": "2",
                "content": {
                    "investorCategoryName": "Investor Updates",
                    "subMenus": [
                        {
                            "name": "2026-2027",
                            "subCategories": [
                                {
                                    "name": "2026-2027",
                                    "files": [
                                        {
                                            "fileId": "presentation-file",
                                            "fileName": "Investor Presentation for the year ended 31st March, 2026",
                                            "fileType": "application/pdf",
                                            "isPublished": True,
                                        },
                                        {
                                            "fileId": "press-file",
                                            "fileName": "Press release dated 2nd May, 2026",
                                            "fileType": "application/pdf",
                                            "isPublished": True,
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                },
            }
        ]
        shell_html = "<html><head><title>DMart</title></head><body><div id='root'></div></body></html>"
        fetched_urls = []

        def fetcher(url):
            fetched_urls.append(url)
            if "robots.txt" in url:
                return {"url": url, "status": "error", "status_code": 404, "error": "not found"}
            if "sitemap.xml" in url:
                return {"url": url, "status": "error", "status_code": 404, "error": "not found"}
            if "corporate/content/v1" in url:
                return {
                    "url": url,
                    "status": "ok",
                    "status_code": 200,
                    "content_type": "application/json",
                    "text": json.dumps(api_payload),
                }
            if "presentation-file" in url:
                return {
                    "url": url,
                    "status": "ok",
                    "status_code": 200,
                    "content_type": "application/pdf",
                    "content": b"%PDF presentation",
                }
            if "press-file" in url:
                return {
                    "url": url,
                    "status": "ok",
                    "status_code": 200,
                    "content_type": "application/pdf",
                    "content": b"%PDF press release",
                }
            return {"url": url, "status": "ok", "status_code": 200, "content_type": "text/html", "text": shell_html}

        with TemporaryDirectory() as td:
            db_path = init_company_intelligence_db(Path(td) / "company_intelligence.db")
            result = run_company_index(
                "DMART",
                db_path=db_path,
                website="https://www.dmartindia.com/investor-relationship",
                max_pages=2,
                include_documents=True,
                respect_robots=True,
                seed_sitemap=True,
                adapter="auto",
                document_limit=1,
                document_root=Path(td) / "documents",
                fetcher=fetcher,
            )
            with sqlite3.connect(db_path) as conn:
                docs = conn.execute(
                    "SELECT document_type, fetch_status, parse_status FROM source_documents WHERE symbol = 'DMART'"
                ).fetchall()
                pages = conn.execute("SELECT COUNT(*) FROM website_pages WHERE symbol = 'DMART'").fetchone()[0]

        self.assertEqual(result["symbol"], "DMART")
        self.assertEqual(result["crawl"]["pages_indexed"], 1)
        self.assertEqual(result["adapter"], "dmart_investor_api")
        self.assertEqual(result["adapter_documents_found"], 1)
        self.assertEqual(result["documents_downloaded"], 1)
        self.assertEqual(docs, [("investor_presentation", "ok", "downloaded")])
        self.assertEqual(pages, 1)
        self.assertTrue(any("corporate/content/v1" in url for url in fetched_urls))


if __name__ == "__main__":
    unittest.main()
