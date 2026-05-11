import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from company_xray_command import parse_company_xray_args, run_company_xray_from_args


class CompanyXrayCommandTests(unittest.TestCase):
    def test_parse_company_xray_args_supports_strict_refresh_and_format(self):
        args = parse_company_xray_args("DMART --strict --refresh --format md")

        self.assertEqual(args.symbol, "DMART")
        self.assertTrue(args.strict)
        self.assertTrue(args.refresh)
        self.assertEqual(args.format, "md")

    def test_run_company_xray_from_args_calls_runner_and_returns_summary(self):
        calls = []

        def runner(symbol, **kwargs):
            calls.append((symbol, kwargs))
            return {
                "symbol": symbol,
                "status": "ok",
                "strict": kwargs["strict"],
                "refresh": kwargs["refresh"],
                "coverage": {
                    "official_evidence": "High",
                    "business_model": "High",
                    "sector_data": "Medium",
                    "known_gaps": ["No parsed concall transcript found"],
                },
                "known_gaps": ["No parsed concall transcript found"],
                "strict_failures": [],
                "report_markdown_path": str(Path(kwargs["output_dir"]) / "company_xray_DMART.md"),
                "report_html_path": str(Path(kwargs["output_dir"]) / "company_xray_DMART.html"),
                "indexed_promotion": {"website_chunks_promoted": 1, "document_chunks_promoted": 2},
            }

        with TemporaryDirectory() as td:
            result = run_company_xray_from_args(
                "DMART --strict --refresh",
                db_path=Path(td) / "company_intelligence.db",
                output_dir=Path(td) / "reports",
                runner=runner,
            )

        self.assertEqual(calls[0][0], "DMART")
        self.assertTrue(calls[0][1]["strict"])
        self.assertTrue(calls[0][1]["refresh"])
        self.assertEqual(result["symbol"], "DMART")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["coverage_summary"]["official_evidence"], "High")
        self.assertEqual(result["indexed_promotion"]["document_chunks_promoted"], 2)


if __name__ == "__main__":
    unittest.main()
