import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from company_intelligence_db import init_company_intelligence_db
from company_website_indexer import (
    classify_link,
    crawl_company_website,
    discover_sitemap_urls,
    download_company_document,
    extract_links,
    fetch_url,
    normalize_url,
    robots_allows,
    search_company_website,
)


class CompanyWebsiteIndexerTests(unittest.TestCase):
    def test_normalize_url_keeps_same_domain_and_blocks_unsupported_links(self):
        base = "https://www.example.com/investors/"

        self.assertEqual(
            normalize_url(base, "/annual-reports/fy26.pdf"),
            "https://www.example.com/annual-reports/fy26.pdf",
        )
        self.assertEqual(
            normalize_url(base, "results.html"),
            "https://www.example.com/investors/results.html",
        )
        self.assertIsNone(normalize_url(base, "mailto:ir@example.com"))
        self.assertIsNone(normalize_url(base, "tel:+910000000000"))

    def test_extract_links_returns_text_and_normalized_urls(self):
        html = """
        <html><body>
          <a href="/investors/results.html">Quarterly Results</a>
          <a href="https://www.example.com/reports/annual-report-fy26.pdf">Annual Report</a>
        </body></html>
        """

        links = extract_links("https://www.example.com/investors/", html)

        self.assertEqual(
            links,
            [
                {"url": "https://www.example.com/investors/results.html", "text": "Quarterly Results"},
                {"url": "https://www.example.com/reports/annual-report-fy26.pdf", "text": "Annual Report"},
            ],
        )

    def test_classify_link_identifies_company_documents(self):
        cases = {
            "https://x.com/annual-report-fy26.pdf": "annual_report",
            "https://x.com/investor-presentation-q4.pdf": "investor_presentation",
            "https://x.com/financial-results.pdf": "results",
            "https://x.com/concall-transcript.pdf": "concall_transcript",
            "https://x.com/about-us": "html_page",
        }

        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(classify_link(url, ""), expected)

    def test_crawl_company_website_indexes_pages_documents_and_fts_search(self):
        pages = {
            "https://www.example.com/investors/": """
                <html><head><title>Investor Relations</title></head><body>
                  <h1>Investor Relations</h1>
                  <p>DMart focuses on value retail and disciplined store expansion.</p>
                  <a href="/investors/business.html">Business Model</a>
                  <a href="/reports/annual-report-fy26.pdf">Annual Report FY26</a>
                  <a href="https://external.example.com/news">External News</a>
                </body></html>
            """,
            "https://www.example.com/investors/business.html": """
                <html><head><title>Business Model</title></head><body>
                  <p>Same store sales growth, store network, and grocery retail customer base are key operating drivers.</p>
                  <a href="/reports/investor-presentation-q4.pdf">Investor Presentation</a>
                </body></html>
            """,
            "https://www.example.com/reports/annual-report-fy26.pdf": b"%PDF annual report bytes",
            "https://www.example.com/reports/investor-presentation-q4.pdf": b"%PDF investor presentation bytes",
        }

        def fetcher(url):
            value = pages[url]
            if isinstance(value, bytes):
                return {"url": url, "content": value, "content_type": "application/pdf", "status_code": 200}
            return {"url": url, "text": value, "content_type": "text/html", "status_code": 200}

        with TemporaryDirectory() as td:
            db_path = init_company_intelligence_db(Path(td) / "company_intelligence.db")
            with sqlite3.connect(db_path) as conn:
                result = crawl_company_website(
                    conn,
                    "DMART",
                    "https://www.example.com/investors/",
                    fetcher=fetcher,
                    max_pages=5,
                    max_depth=2,
                    include_documents=True,
                )
                hits = search_company_website(conn, "DMART", "store network grocery", limit=5)
                doc_count = conn.execute(
                    "SELECT COUNT(*) FROM website_links WHERE link_type IN ('annual_report', 'investor_presentation')"
                ).fetchone()[0]

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["pages_indexed"], 2)
            self.assertEqual(result["documents_found"], 2)
            self.assertEqual(doc_count, 2)
            self.assertTrue(hits)
            self.assertIn("store network", hits[0]["chunk_text"])

    def test_crawl_downloads_linked_documents_when_document_root_is_supplied(self):
        pages = {
            "https://www.example.com/investors/": """
                <html><head><title>Investor Relations</title></head><body>
                  <a href="/reports/annual-report-fy26.pdf">Annual Report FY26</a>
                </body></html>
            """,
            "https://www.example.com/reports/annual-report-fy26.pdf": b"%PDF annual report bytes",
        }

        def fetcher(url):
            value = pages[url]
            if isinstance(value, bytes):
                return {"url": url, "status": "ok", "content": value, "content_type": "application/pdf", "status_code": 200}
            return {"url": url, "status": "ok", "text": value, "content_type": "text/html", "status_code": 200}

        with TemporaryDirectory() as td:
            db_path = init_company_intelligence_db(Path(td) / "company_intelligence.db")
            with sqlite3.connect(db_path) as conn:
                result = crawl_company_website(
                    conn,
                    "DMART",
                    "https://www.example.com/investors/",
                    fetcher=fetcher,
                    max_pages=5,
                    max_depth=1,
                    include_documents=True,
                    document_root=Path(td) / "documents",
                )
                stored = conn.execute(
                    """
                    SELECT document_type, fetch_status, parse_status, local_path
                    FROM source_documents
                    WHERE symbol = 'DMART'
                    """
                ).fetchone()
                downloaded_exists = Path(stored[3]).exists()

        self.assertEqual(result["documents_found"], 1)
        self.assertEqual(stored[0], "annual_report")
        self.assertEqual(stored[1], "ok")
        self.assertEqual(stored[2], "downloaded")
        self.assertTrue(downloaded_exists)

    def test_fetch_url_returns_text_and_metadata(self):
        class FakeResponse:
            status = 200
            headers = {"Content-Type": "text/html; charset=utf-8"}

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self, size=-1):
                return b"<html><title>IR</title></html>"

        seen = {}

        def fake_urlopen(request, timeout):
            seen["url"] = request.full_url
            seen["user_agent"] = request.headers.get("User-agent")
            seen["timeout"] = timeout
            return FakeResponse()

        with patch("urllib.request.urlopen", fake_urlopen):
            result = fetch_url("https://www.example.com/investors/", timeout=3.0)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["status_code"], 200)
        self.assertEqual(result["content_type"], "text/html; charset=utf-8")
        self.assertEqual(result["text"], "<html><title>IR</title></html>")
        self.assertEqual(seen["url"], "https://www.example.com/investors/")
        self.assertIn("AgentAdda", seen["user_agent"])
        self.assertEqual(seen["timeout"], 3.0)

    def test_fetch_url_rejects_responses_larger_than_max_bytes(self):
        class FakeResponse:
            status = 200
            headers = {"Content-Type": "application/pdf"}

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self, size=-1):
                return b"123456"

        with patch("urllib.request.urlopen", lambda request, timeout: FakeResponse()):
            result = fetch_url("https://www.example.com/report.pdf", max_bytes=5)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["status_code"], 200)
        self.assertIn("exceeds max_bytes", result["error"])

    def test_fetch_url_returns_structured_error_on_request_failure(self):
        with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
            result = fetch_url("https://www.example.com/investors/")

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["status_code"], 0)
        self.assertIn("timed out", result["error"])

    def test_robots_allows_respects_disallow_rules(self):
        def fetcher(url):
            self.assertEqual(url, "https://www.example.com/robots.txt")
            return {
                "url": url,
                "status": "ok",
                "status_code": 200,
                "content_type": "text/plain",
                "text": "User-agent: *\nDisallow: /private\n",
            }

        self.assertTrue(robots_allows("https://www.example.com/investors/", fetcher=fetcher))
        self.assertFalse(robots_allows("https://www.example.com/private/results.html", fetcher=fetcher))

    def test_discover_sitemap_urls_reads_robots_and_sitemap_xml(self):
        sitemap = """
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://www.example.com/investors/</loc></url>
          <url><loc>https://www.example.com/reports/annual-report-fy26.pdf</loc></url>
          <url><loc>https://external.example.com/news</loc></url>
        </urlset>
        """

        def fetcher(url):
            if url == "https://www.example.com/robots.txt":
                return {
                    "url": url,
                    "status": "ok",
                    "status_code": 200,
                    "content_type": "text/plain",
                    "text": "Sitemap: https://www.example.com/sitemap.xml\n",
                }
            if url == "https://www.example.com/sitemap.xml":
                return {
                    "url": url,
                    "status": "ok",
                    "status_code": 200,
                    "content_type": "application/xml",
                    "text": sitemap,
                }
            return {"url": url, "status": "error", "status_code": 404, "error": "not found"}

        urls = discover_sitemap_urls("https://www.example.com/investors/", fetcher=fetcher)

        self.assertEqual(
            urls,
            [
                "https://www.example.com/investors/",
                "https://www.example.com/reports/annual-report-fy26.pdf",
            ],
        )

    def test_crawl_can_seed_from_sitemap_and_respect_robots(self):
        sitemap = """
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://www.example.com/investors/</loc></url>
          <url><loc>https://www.example.com/business-model.html</loc></url>
          <url><loc>https://www.example.com/private/strategy.html</loc></url>
        </urlset>
        """
        pages = {
            "https://www.example.com/robots.txt": "User-agent: *\nDisallow: /private\nSitemap: https://www.example.com/sitemap.xml\n",
            "https://www.example.com/sitemap.xml": sitemap,
            "https://www.example.com/investors/": """
                <html><head><title>IR</title></head><body>
                  <p>Investor relations home page.</p>
                </body></html>
            """,
            "https://www.example.com/business-model.html": """
                <html><head><title>Business Model</title></head><body>
                  <p>Store network and customer base drive operating model.</p>
                </body></html>
            """,
            "https://www.example.com/private/strategy.html": """
                <html><head><title>Private</title></head><body>
                  <p>This disallowed page should not be fetched.</p>
                </body></html>
            """,
        }
        fetched_urls = []

        def fetcher(url):
            fetched_urls.append(url)
            return {
                "url": url,
                "status": "ok",
                "status_code": 200,
                "content_type": "text/html",
                "text": pages[url],
            }

        with TemporaryDirectory() as td:
            db_path = init_company_intelligence_db(Path(td) / "company_intelligence.db")
            with sqlite3.connect(db_path) as conn:
                result = crawl_company_website(
                    conn,
                    "DMART",
                    "https://www.example.com/investors/",
                    fetcher=fetcher,
                    max_pages=5,
                    max_depth=0,
                    include_documents=True,
                    respect_robots=True,
                    seed_sitemap=True,
                )
                stored_urls = [
                    row[0]
                    for row in conn.execute(
                        "SELECT url FROM website_pages WHERE symbol = 'DMART' ORDER BY url"
                    ).fetchall()
                ]

        self.assertEqual(result["pages_indexed"], 2)
        self.assertEqual(
            stored_urls,
            [
                "https://www.example.com/business-model.html",
                "https://www.example.com/investors/",
            ],
        )
        self.assertNotIn("https://www.example.com/private/strategy.html", fetched_urls)

    def test_download_company_document_stores_source_document_and_reuses_cached_copy(self):
        calls = []

        def fetcher(url):
            calls.append(url)
            return {
                "url": url,
                "status": "ok",
                "status_code": 200,
                "content_type": "application/pdf",
                "content": b"%PDF annual report bytes",
            }

        with TemporaryDirectory() as td:
            root_dir = Path(td) / "documents"
            db_path = init_company_intelligence_db(Path(td) / "company_intelligence.db")
            with sqlite3.connect(db_path) as conn:
                first = download_company_document(
                    conn,
                    "DMART",
                    "https://www.example.com/reports/annual-report-fy26.pdf",
                    "annual_report",
                    fetcher=fetcher,
                    root_dir=root_dir,
                )
                second = download_company_document(
                    conn,
                    "DMART",
                    "https://www.example.com/reports/annual-report-fy26.pdf",
                    "annual_report",
                    fetcher=fetcher,
                    root_dir=root_dir,
                )
                stored = conn.execute(
                    """
                    SELECT source_name, document_type, local_path, content_hash, fetch_status, parse_status
                    FROM source_documents
                    WHERE symbol = 'DMART' AND source_url = ?
                    """,
                    ("https://www.example.com/reports/annual-report-fy26.pdf",),
                ).fetchone()
                downloaded_exists = Path(first["local_path"]).exists()
                downloaded_bytes = Path(first["local_path"]).read_bytes()

        self.assertEqual(first["status"], "downloaded")
        self.assertEqual(second["status"], "cached")
        self.assertEqual(calls, ["https://www.example.com/reports/annual-report-fy26.pdf"])
        self.assertTrue(downloaded_exists)
        self.assertEqual(downloaded_bytes, b"%PDF annual report bytes")
        self.assertEqual(stored[0], "company_website")
        self.assertEqual(stored[1], "annual_report")
        self.assertEqual(stored[2], first["local_path"])
        self.assertEqual(stored[3], first["content_hash"])
        self.assertEqual(stored[4], "ok")
        self.assertEqual(stored[5], "downloaded")


if __name__ == "__main__":
    unittest.main()
