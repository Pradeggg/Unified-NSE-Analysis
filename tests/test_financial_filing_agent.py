import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from financial_filing_agent import (
    build_arg_parser,
    detect_document_type,
    ingest_filing_url,
    safe_path_part,
)


class FakeResponse:
    def __init__(self, content: bytes, content_type: str = "application/octet-stream", status_code: int = 200):
        self.content = content
        self.status_code = status_code
        self.headers = {"content-type": content_type}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FinancialFilingAgentTests(unittest.TestCase):
    def test_detect_document_type_from_url_content_type_and_bytes(self):
        self.assertEqual(detect_document_type("https://example.com/result.pdf", "application/pdf", b"%PDF"), "pdf")
        self.assertEqual(detect_document_type("https://example.com/result.xml", "text/xml", b"<xbrli:xbrl></xbrli:xbrl>"), "xbrl")
        self.assertEqual(
            detect_document_type("https://example.com/result.html", "text/html", b"<html><ix:nonFraction>1</ix:nonFraction></html>"),
            "ixbrl",
        )
        self.assertEqual(detect_document_type("https://example.com/result.zip", "application/zip", b"PK\x03\x04"), "zip")
        self.assertEqual(detect_document_type("https://example.com/result.bin", "application/octet-stream", b"abc"), "unknown")

    def test_safe_path_part_blocks_path_traversal_and_keeps_meaningful_name(self):
        self.assertEqual(safe_path_part("../Blue Star FY26/Q4"), "BLUE_STAR_FY26_Q4")
        self.assertEqual(safe_path_part(""), "UNKNOWN")

    def test_ingest_filing_url_writes_raw_file_and_manifest(self):
        with TemporaryDirectory() as td:
            response = FakeResponse(content=b"%PDF sample", content_type="application/pdf")
            result = ingest_filing_url(
                "https://example.com/bslbmoutcome06052026.pdf",
                symbol="BLUESTARCO",
                period="FY26_Q4",
                root_dir=Path(td),
                fetcher=lambda url: response,
            )

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["symbol"], "BLUESTARCO")
            self.assertEqual(result["period"], "FY26_Q4")
            self.assertEqual(result["document_type"], "pdf")
            self.assertTrue(Path(result["local_path"]).exists())
            self.assertTrue(Path(result["manifest_path"]).exists())

            manifest = json.loads(Path(result["manifest_path"]).read_text())
            self.assertEqual(manifest["source_url"], "https://example.com/bslbmoutcome06052026.pdf")
            self.assertEqual(manifest["sha256"], result["sha256"])

    def test_ingest_filing_url_returns_structured_error_on_fetch_failure(self):
        with TemporaryDirectory() as td:
            def failing_fetcher(url):
                raise TimeoutError("network timeout")

            result = ingest_filing_url(
                "https://example.com/result.pdf",
                root_dir=Path(td),
                fetcher=failing_fetcher,
            )

            self.assertEqual(result["status"], "error")
            self.assertIn("network timeout", result["error"])
            self.assertEqual(result["document_type"], "pdf")

    def test_ingest_filing_url_is_idempotent_without_force(self):
        with TemporaryDirectory() as td:
            calls = []

            def fetcher(url):
                calls.append(url)
                return FakeResponse(content=b"%PDF sample", content_type="application/pdf")

            first = ingest_filing_url("https://example.com/result.pdf", root_dir=Path(td), fetcher=fetcher)
            second = ingest_filing_url("https://example.com/result.pdf", root_dir=Path(td), fetcher=fetcher)

            self.assertEqual(first["status"], "ok")
            self.assertEqual(second["status"], "ok")
            self.assertEqual(first["sha256"], second["sha256"])
            self.assertEqual(len(calls), 1)

    def test_build_arg_parser_accepts_ingest_command(self):
        parser = build_arg_parser()
        args = parser.parse_args([
            "ingest",
            "https://example.com/result.pdf",
            "--symbol",
            "BLUESTARCO",
            "--period",
            "FY26_Q4",
        ])

        self.assertEqual(args.command, "ingest")
        self.assertEqual(args.url, "https://example.com/result.pdf")
        self.assertEqual(args.symbol, "BLUESTARCO")
        self.assertEqual(args.period, "FY26_Q4")


if __name__ == "__main__":
    unittest.main()
