import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from company_intelligence.company_intelligence_db import init_company_intelligence_db
from company_intelligence.company_intelligence_policy import (
    assess_policy_impact,
    list_policy_events,
    store_policy_event,
)


class CompanyIntelligencePolicyTests(unittest.TestCase):
    def test_store_and_list_policy_events(self):
        with TemporaryDirectory() as td:
            db_path = init_company_intelligence_db(Path(td) / "company_intelligence.db")
            with sqlite3.connect(db_path) as conn:
                event_id = store_policy_event(
                    conn,
                    event_type="rbi_policy",
                    event_date="2026-04-08",
                    title="RBI cuts repo rate",
                    source_url="https://rbi.org.in/example",
                    summary="Repo rate cut may reduce borrowing costs.",
                )
                rows = list_policy_events(conn, "rbi_policy")

            self.assertGreater(event_id, 0)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["event_type"], "rbi_policy")
            self.assertEqual(rows[0]["title"], "RBI cuts repo rate")

    def test_assess_policy_impact_maps_company_sensitivities(self):
        cases = [
            (
                {"symbol": "ABC", "debt_level": "high", "sector": "capital goods"},
                {"event_type": "rbi_policy", "summary": "repo rate cut"},
                "borrowing_cost",
                "positive",
            ),
            (
                {"symbol": "DMART", "sector": "retail", "demand_drivers": ["consumption"]},
                {"event_type": "union_budget", "summary": "tax relief for households"},
                "consumer_demand",
                "positive",
            ),
            (
                {"symbol": "LT", "sector": "infrastructure", "demand_drivers": ["capex"]},
                {"event_type": "union_budget", "summary": "higher infrastructure capex allocation"},
                "infrastructure_demand",
                "positive",
            ),
            (
                {"symbol": "IMPORTCO", "import_exposure": "high"},
                {"event_type": "macro", "summary": "INR weakness raises import costs"},
                "import_cost",
                "negative",
            ),
        ]

        for profile, event, area, direction in cases:
            with self.subTest(area=area):
                result = assess_policy_impact(profile, event, [])
                self.assertEqual(result["impact_area"], area)
                self.assertEqual(result["direction"], direction)
                self.assertIn(result["magnitude"], {"low", "medium", "high"})
                self.assertGreater(result["confidence"], 0)


if __name__ == "__main__":
    unittest.main()
