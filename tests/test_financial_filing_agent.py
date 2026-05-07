import json
import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from financial_filing_agent import (
    build_arg_parser,
    detect_document_type,
    ingest_filing_url,
    parse_pdf_filing,
    parse_registered_filing,
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

    def test_parse_pdf_filing_returns_dependency_error_when_backend_missing(self):
        with TemporaryDirectory() as td:
            pdf_path = Path(td) / "sample.pdf"
            pdf_path.write_bytes(b"%PDF sample")

            result = parse_pdf_filing(pdf_path, backend_loader=lambda: None)

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["error_code"], "PDF_BACKEND_MISSING")
            self.assertEqual(result["document_type"], "pdf")
            self.assertEqual(result["source_path"], str(pdf_path))
            self.assertEqual(result["pages"], [])
            self.assertEqual(result["tables"], [])
            self.assertEqual(result["evidence"], [])

    def test_parse_pdf_filing_extracts_page_text_and_evidence_with_backend(self):
        class FakePage:
            def __init__(self, text):
                self.text = text

            def get_text(self, mode):
                return self.text

        class FakeDocument:
            def __init__(self):
                self.pages = [
                    FakePage("Standalone revenue grew 24 percent.\nProfit after tax improved."),
                    FakePage("Segment results show strong electro-mechanical project execution."),
                ]

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def __len__(self):
                return len(self.pages)

            def __iter__(self):
                return iter(self.pages)

        class FakeBackend:
            @staticmethod
            def open(path):
                return FakeDocument()

        with TemporaryDirectory() as td:
            pdf_path = Path(td) / "sample.pdf"
            pdf_path.write_bytes(b"%PDF sample")

            result = parse_pdf_filing(pdf_path, backend_loader=lambda: FakeBackend)

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["page_count"], 2)
            self.assertEqual(result["pages"][0]["page_number"], 1)
            self.assertIn("Standalone revenue", result["pages"][0]["text"])
            self.assertEqual(result["evidence"][0]["source_type"], "pdf_page")
            self.assertEqual(result["evidence"][0]["page_number"], 1)
            self.assertIn("Standalone revenue", result["evidence"][0]["text_excerpt"])

    def test_parse_pdf_filing_extracts_detected_tables_with_cell_evidence(self):
        class FakeTable:
            def extract(self):
                return [
                    ["Particulars", "FY26", "FY25"],
                    ["Revenue from operations", "11,779.23", "11,325.75"],
                    ["Profit after tax", "385.10", "484.90"],
                ]

        class FakeTableFinder:
            tables = [FakeTable()]

        class FakePage:
            def get_text(self, mode):
                return "STANDALONE FINANCIAL RESULTS"

            def find_tables(self):
                return FakeTableFinder()

        class FakeDocument:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def __len__(self):
                return 1

            def __iter__(self):
                return iter([FakePage()])

        class FakeBackend:
            @staticmethod
            def open(path):
                return FakeDocument()

        with TemporaryDirectory() as td:
            pdf_path = Path(td) / "sample.pdf"
            pdf_path.write_bytes(b"%PDF sample")

            result = parse_pdf_filing(pdf_path, backend_loader=lambda: FakeBackend)

            self.assertEqual(result["status"], "ok")
            self.assertEqual(len(result["tables"]), 1)
            self.assertEqual(result["tables"][0]["row_count"], 3)
            self.assertEqual(result["tables"][0]["rows"][1][0], "Revenue from operations")
            table_evidence = [item for item in result["evidence"] if item["source_type"] == "pdf_table_cell"]
            self.assertEqual(table_evidence[0]["row_label"], "Revenue from operations")
            self.assertEqual(table_evidence[0]["column_label"], "FY26")
            self.assertEqual(table_evidence[0]["extracted_value"], "11,779.23")

    def test_parse_pdf_filing_suppresses_backend_table_stdout_noise(self):
        class NoisyPage:
            def get_text(self, mode):
                return "RESULTS"

            def find_tables(self):
                print("backend layout suggestion")

                class Finder:
                    tables = []

                return Finder()

        class FakeDocument:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def __len__(self):
                return 1

            def __iter__(self):
                return iter([NoisyPage()])

        class FakeBackend:
            @staticmethod
            def open(path):
                return FakeDocument()

        with TemporaryDirectory() as td:
            pdf_path = Path(td) / "sample.pdf"
            pdf_path.write_bytes(b"%PDF sample")
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                result = parse_pdf_filing(pdf_path, backend_loader=lambda: FakeBackend)

            self.assertEqual(result["status"], "ok")
            self.assertEqual(stdout.getvalue(), "")

    def test_parse_registered_filing_reads_manifest_and_writes_parsed_json(self):
        with TemporaryDirectory() as td:
            ingest = ingest_filing_url(
                "https://example.com/result.pdf",
                symbol="BLUESTARCO",
                period="FY26_Q4",
                root_dir=Path(td),
                fetcher=lambda url: FakeResponse(content=b"%PDF sample", content_type="application/pdf"),
            )
            parsed_result = {
                "status": "ok",
                "document_type": "pdf",
                "source_path": ingest["local_path"],
                "page_count": 1,
                "pages": [{"page_number": 1, "text": "Revenue grew.", "char_count": 13}],
                "tables": [],
                "evidence": [{"source_type": "pdf_page", "page_number": 1, "text_excerpt": "Revenue grew."}],
                "warnings": [],
            }

            result = parse_registered_filing(Path(ingest["manifest_path"]), parser=lambda path: parsed_result)

            self.assertEqual(result["status"], "ok")
            self.assertTrue(Path(result["parsed_path"]).exists())
            written = json.loads(Path(result["parsed_path"]).read_text())
            self.assertEqual(written["page_count"], 1)
            self.assertEqual(written["evidence"][0]["text_excerpt"], "Revenue grew.")

    def test_build_arg_parser_accepts_parse_command(self):
        parser = build_arg_parser()
        args = parser.parse_args(["parse", "data/filings/BLUESTARCO/FY26_Q4/manifest.json"])

        self.assertEqual(args.command, "parse")
        self.assertEqual(args.manifest_path, "data/filings/BLUESTARCO/FY26_Q4/manifest.json")


if __name__ == "__main__":
    unittest.main()
