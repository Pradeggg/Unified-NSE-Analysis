import unittest

from company_intelligence.company_intelligence_analyze import (
    build_deliberation_view,
    score_evidence_coverage,
    strict_mode_passes,
)


class CompanyIntelligenceAnalyzeTests(unittest.TestCase):
    def test_score_evidence_coverage_marks_strengths_and_gaps(self):
        evidence = [
            {"category": "business model", "source_tier": 1, "text": "Official annual report description."},
            {"category": "sector structure", "source_tier": 2, "text": "Internal sector map."},
            {"category": "market share", "source_tier": 3, "text": "Industry article estimate."},
        ]
        attempts = [
            {"source_group": "external_context", "status": "no_results", "failure_reason": "no accessible broker report"},
            {"source_group": "company_ir", "status": "parsed", "failure_reason": ""},
        ]

        coverage = score_evidence_coverage(evidence, attempts)

        self.assertEqual(coverage["official_evidence"], "High")
        self.assertEqual(coverage["company_ir"], "High")
        self.assertEqual(coverage["broker_research"], "Unavailable")
        self.assertIn("Broker research unavailable", coverage["known_gaps"])

    def test_strict_mode_requires_official_business_and_sector_evidence(self):
        weak = {
            "official_evidence": "Low",
            "business_model": "Low",
            "sector_data": "Low",
            "search_audit": "High",
            "known_gaps": [],
        }
        strong = {
            "official_evidence": "High",
            "business_model": "High",
            "sector_data": "Medium",
            "search_audit": "High",
            "known_gaps": [],
        }

        self.assertFalse(strict_mode_passes(weak)[0])
        self.assertTrue(strict_mode_passes(strong)[0])

    def test_build_deliberation_view_contains_cases_and_open_questions(self):
        view = build_deliberation_view(
            "DMART",
            evidence_by_category={
                "business model": [{"text": "Value retail store model."}],
                "competitive advantage": [{"text": "Low-cost procurement and store discipline."}],
                "risks": [{"text": "Competition from quick commerce."}],
            },
            coverage={"known_gaps": ["No accessible concall transcript"]},
            policy_impacts=[{"impact_area": "consumer_demand", "direction": "positive", "rationale": "Tax relief can help demand."}],
        )

        self.assertEqual(view["symbol"], "DMART")
        self.assertIn("bull_case", view)
        self.assertIn("bear_case", view)
        self.assertIn("base_case", view)
        self.assertIn("No accessible concall transcript", view["evidence_gaps"])
        self.assertTrue(view["open_questions"])


if __name__ == "__main__":
    unittest.main()
