import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from company_intelligence_report import (
    render_company_xray_html,
    render_company_xray_markdown,
    write_company_xray_report,
)


class CompanyIntelligenceReportTests(unittest.TestCase):
    def sample_model(self):
        return {
            "symbol": "DMART",
            "company_name": "Avenue Supermarts Ltd",
            "coverage": {
                "official_evidence": "High",
                "company_ir": "High",
                "broker_research": "Unavailable",
                "business_model": "High",
                "sector_data": "Medium",
                "known_gaps": ["Broker research unavailable", "No parsed concall transcript found"],
            },
            "sections": {
                "business_model": ["Value retail store model."],
                "customer_base": ["Retail household customers."],
                "sector_structure": ["Organized grocery retail."],
                "market_share": ["Market share requires validation."],
                "competitors": ["Reliance Retail", "Spencer's"],
                "rbi_impact": ["Lower rates may support demand and financing costs."],
                "budget_impact": ["Tax relief may support consumption."],
            },
            "deliberation": {
                "bull_case": ["Efficient operating model."],
                "bear_case": ["Quick commerce competition."],
                "base_case": ["Store-led growth continues with margin discipline."],
                "open_questions": ["What is the latest verified market share?"],
            },
            "evidence": [
                {
                    "category": "business model",
                    "source_tier": 1,
                    "text": "Annual report describes value retail model.",
                    "evidence_date": "2026-03-31",
                }
            ],
        }

    def test_render_company_xray_markdown_contains_required_sections(self):
        md = render_company_xray_markdown(self.sample_model())

        for expected in [
            "Company X-Ray: DMART",
            "Evidence Coverage",
            "Business Model",
            "Customer Base",
            "Sector Structure",
            "Market Share",
            "Competitor Map",
            "RBI Monetary Policy Impact",
            "Union Budget Impact",
            "Bull Case",
            "Bear Case",
            "Base Case",
            "Open Questions",
            "Evidence Table",
            "Not investment advice",
        ]:
            self.assertIn(expected, md)

    def test_render_company_xray_html_contains_sections_and_disclaimer(self):
        html = render_company_xray_html(self.sample_model())

        self.assertIn("<html", html)
        self.assertIn("Company X-Ray: DMART", html)
        self.assertIn("Evidence Coverage", html)
        self.assertIn("Not investment advice", html)

    def test_write_company_xray_report_writes_markdown_and_html(self):
        with TemporaryDirectory() as td:
            model = self.sample_model()
            md = render_company_xray_markdown(model)
            html = render_company_xray_html(model)
            paths = write_company_xray_report("DMART", md, html, Path(td))

            self.assertTrue(Path(paths["markdown"]).exists())
            self.assertTrue(Path(paths["html"]).exists())
            self.assertIn("company_xray_DMART", Path(paths["markdown"]).name)


if __name__ == "__main__":
    unittest.main()
