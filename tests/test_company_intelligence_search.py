import json
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from company_intelligence_db import init_company_intelligence_db
from company_intelligence_search import (
    build_search_queries,
    complete_search_run,
    log_search_attempt,
    start_search_run,
)


class CompanyIntelligenceSearchTests(unittest.TestCase):
    def test_search_run_and_attempts_are_auditable(self):
        with TemporaryDirectory() as td:
            db_path = init_company_intelligence_db(Path(td) / "company_intelligence.db")
            with sqlite3.connect(db_path) as conn:
                run_id = start_search_run(conn, "DMART", ["analyst_coverage", "concalls"], "permissive")
                attempt_id = log_search_attempt(
                    conn,
                    run_id,
                    source_group="external_context",
                    query="Avenue Supermarts concall transcript",
                    alias_used="Avenue Supermarts",
                    result_count=0,
                    urls_found=[],
                    status="no_results",
                    failure_reason="search returned no accessible transcript",
                )
                complete_search_run(conn, run_id, "completed", "No accessible concall transcript found.")

                run = conn.execute(
                    "SELECT symbol, verticals, mode, status, summary FROM search_runs WHERE search_run_id = ?",
                    (run_id,),
                ).fetchone()
                attempt = conn.execute(
                    "SELECT source_group, query, alias_used, result_count, urls_found, status, failure_reason FROM search_attempts WHERE attempt_id = ?",
                    (attempt_id,),
                ).fetchone()

            self.assertEqual(run[0], "DMART")
            self.assertEqual(json.loads(run[1]), ["analyst_coverage", "concalls"])
            self.assertEqual(run[2], "permissive")
            self.assertEqual(run[3], "completed")
            self.assertIn("No accessible", run[4])
            self.assertEqual(attempt[0], "external_context")
            self.assertEqual(attempt[1], "Avenue Supermarts concall transcript")
            self.assertEqual(attempt[2], "Avenue Supermarts")
            self.assertEqual(attempt[3], 0)
            self.assertEqual(json.loads(attempt[4]), [])
            self.assertEqual(attempt[5], "no_results")
            self.assertIn("no accessible", attempt[6])

    def test_build_search_queries_expands_dmart_aliases_across_verticals(self):
        queries = build_search_queries(
            "DMART",
            ["DMART", "Avenue Supermarts", "Avenue Supermarts Ltd", "AVENUE SUPERMARTS"],
            ["analyst_coverage", "broker_research", "concalls"],
        )

        query_text = {row["query"] for row in queries}
        self.assertIn("Avenue Supermarts concall transcript", query_text)
        self.assertIn("DMART broker research", query_text)
        self.assertIn("Avenue Supermarts analyst coverage", query_text)
        self.assertIn("AVENUE SUPERMARTS investor presentation", query_text)
        for row in queries:
            self.assertIn(row["vertical"], {"analyst_coverage", "broker_research", "concalls"})
            self.assertIn("alias", row)

    def test_build_search_queries_broadens_company_and_policy_verticals(self):
        queries = build_search_queries(
            "DMART",
            ["Avenue Supermarts"],
            ["company_website", "investor_relations", "market_share", "competitors", "rbi_impact", "budget_impact"],
        )

        by_query = {row["query"]: row for row in queries}
        self.assertEqual(by_query["DMART business model site:company_website"]["source_group"], "website_index")
        self.assertEqual(by_query["DMART investor relations annual report"]["source_group"], "website_index")
        self.assertEqual(by_query["Avenue Supermarts market share"]["source_group"], "external_context")
        self.assertEqual(by_query["Avenue Supermarts competitors peers"]["source_group"], "external_context")
        self.assertEqual(by_query["DMART RBI monetary policy impact"]["source_group"], "official_policy")
        self.assertEqual(by_query["DMART Union Budget impact"]["source_group"], "official_policy")


if __name__ == "__main__":
    unittest.main()
