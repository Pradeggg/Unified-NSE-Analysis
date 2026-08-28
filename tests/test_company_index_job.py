import sqlite3
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from company_intelligence.company_index_job import run_company_index_job
from company_intelligence.company_intelligence_db import init_company_intelligence_db


class CompanyIndexJobTests(unittest.TestCase):
    def test_run_company_index_job_selects_stale_and_skips_fresh_symbols(self):
        calls = []

        def runner(symbol, **kwargs):
            calls.append(symbol)
            return {"symbol": symbol, "crawl": {"pages_indexed": 1}, "documents_downloaded": 0}

        with TemporaryDirectory() as td:
            db_path = init_company_intelligence_db(Path(td) / "company_intelligence.db")
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO website_crawl_runs
                        (symbol, base_url, started_at, completed_at, status, pages_seen, pages_indexed)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "FRESH",
                        "https://fresh.example.com",
                        _days_ago(1),
                        _days_ago(1),
                        "completed",
                        1,
                        1,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO website_crawl_runs
                        (symbol, base_url, started_at, completed_at, status, pages_seen, pages_indexed)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "STALE",
                        "https://stale.example.com",
                        _days_ago(45),
                        _days_ago(45),
                        "completed",
                        1,
                        1,
                    ),
                )
                conn.commit()

            result = run_company_index_job(
                ["FRESH", "STALE", "NEWCO"],
                db_path=db_path,
                stale_days=30,
                max_companies=10,
                index_runner=runner,
            )

        self.assertEqual(calls, ["STALE", "NEWCO"])
        self.assertEqual(result["processed"], 2)
        self.assertEqual(result["skipped"], ["FRESH"])
        self.assertEqual(result["succeeded"], ["STALE", "NEWCO"])

    def test_run_company_index_job_respects_max_companies(self):
        calls = []

        def runner(symbol, **kwargs):
            calls.append(symbol)
            return {"symbol": symbol, "crawl": {"pages_indexed": 1}, "documents_downloaded": 0}

        with TemporaryDirectory() as td:
            db_path = init_company_intelligence_db(Path(td) / "company_intelligence.db")
            result = run_company_index_job(
                ["A", "B", "C"],
                db_path=db_path,
                stale_days=30,
                max_companies=2,
                index_runner=runner,
            )

        self.assertEqual(calls, ["A", "B"])
        self.assertEqual(result["processed"], 2)
        self.assertEqual(result["deferred"], ["C"])

    def test_run_company_index_job_records_failure_and_continues(self):
        def runner(symbol, **kwargs):
            if symbol == "FAIL":
                raise RuntimeError("crawl failed")
            return {"symbol": symbol, "crawl": {"pages_indexed": 1}, "documents_downloaded": 0}

        with TemporaryDirectory() as td:
            db_path = init_company_intelligence_db(Path(td) / "company_intelligence.db")
            result = run_company_index_job(
                ["FAIL", "OKAY"],
                db_path=db_path,
                stale_days=30,
                max_companies=10,
                index_runner=runner,
            )
            with sqlite3.connect(db_path) as conn:
                row = conn.execute(
                    """
                    SELECT status, failure_reason
                    FROM website_crawl_runs
                    WHERE symbol = 'FAIL'
                    ORDER BY crawl_run_id DESC
                    LIMIT 1
                    """
                ).fetchone()

        self.assertEqual(result["processed"], 2)
        self.assertEqual(result["succeeded"], ["OKAY"])
        self.assertEqual(result["failed"], [{"symbol": "FAIL", "error": "crawl failed"}])
        self.assertEqual(row, ("failed", "crawl failed"))


def _days_ago(days: int) -> str:
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


if __name__ == "__main__":
    unittest.main()
