import sqlite3
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from company_intelligence.company_intelligence_db import (
    add_company_alias,
    get_company_aliases,
    init_company_intelligence_db,
    upsert_company,
)


class CompanyIntelligenceDbTests(unittest.TestCase):
    def test_init_company_intelligence_db_creates_required_tables(self):
        with TemporaryDirectory() as td:
            db_path = init_company_intelligence_db(Path(td) / "company_intelligence.db")

            self.assertTrue(db_path.exists())
            with sqlite3.connect(db_path) as conn:
                rows = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()

            tables = {row[0] for row in rows}
            self.assertTrue(
                {
                    "companies",
                    "company_aliases",
                    "source_documents",
                    "search_runs",
                    "search_attempts",
                    "evidence_chunks",
                    "structured_facts",
                    "sector_entities",
                    "macro_policy_events",
                    "impact_assessments",
                    "analysis_runs",
                    "website_crawl_runs",
                    "website_pages",
                    "website_links",
                    "website_page_chunks",
                    "website_search_fts",
                }.issubset(tables)
            )

    def test_upsert_company_inserts_and_updates_company(self):
        with TemporaryDirectory() as td:
            db_path = init_company_intelligence_db(Path(td) / "company_intelligence.db")
            with sqlite3.connect(db_path) as conn:
                upsert_company(conn, "DMART", company_name="Avenue Supermarts", sector="Retail")
                upsert_company(conn, "DMART", company_name="Avenue Supermarts Ltd", sector="Retail", website="https://www.dmartindia.com")
                row = conn.execute(
                    "SELECT symbol, company_name, sector, website FROM companies WHERE symbol = ?",
                    ("DMART",),
                ).fetchone()

            self.assertEqual(row, ("DMART", "Avenue Supermarts Ltd", "Retail", "https://www.dmartindia.com"))

    def test_add_company_alias_deduplicates_and_returns_sorted_aliases(self):
        with TemporaryDirectory() as td:
            db_path = init_company_intelligence_db(Path(td) / "company_intelligence.db")
            with sqlite3.connect(db_path) as conn:
                upsert_company(conn, "DMART", company_name="Avenue Supermarts")
                add_company_alias(conn, "DMART", "Avenue Supermarts", "company_name")
                add_company_alias(conn, "DMART", "AVENUE SUPERMARTS", "bse_name")
                add_company_alias(conn, "DMART", "DMART", "symbol")
                add_company_alias(conn, "DMART", "DMART", "symbol")
                aliases = get_company_aliases(conn, "DMART")

            self.assertEqual(aliases, ["AVENUE SUPERMARTS", "Avenue Supermarts", "DMART"])


if __name__ == "__main__":
    unittest.main()
