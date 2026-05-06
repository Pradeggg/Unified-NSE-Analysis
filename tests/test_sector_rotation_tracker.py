import sqlite3
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sector_rotation_tracker as tracker


class SectorRotationTrackerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.old_db_path = tracker.DB_PATH
        tracker.DB_PATH = Path(self.tmp.name) / "tracker.db"

    def tearDown(self):
        tracker.DB_PATH = self.old_db_path
        self.tmp.cleanup()

    def _insert_snapshot(self, conn: sqlite3.Connection, snap_date: str, symbol: str, stage: str, price: float, live_price=None):
        conn.execute(
            """
            INSERT INTO stage_snapshots
              (snapshot_date, symbol, company_name, stage, stage_score, price, live_price,
               technical_score, rsi, trading_signal, trend_signal, relative_strength,
               change_1d_pct, change_1w_pct, change_1m_pct, market_cap_cat, source_csv)
            VALUES (?, ?, ?, ?, ?, ?, ?, 70, 60, 'HOLD', 'BULLISH', 0.2, 1, 2, 3, 'MID', 'fixture.csv')
            """,
            (snap_date, symbol, f"{symbol} Ltd", stage, 0.8, price, live_price),
        )

    def test_build_change_report_refreshes_cached_change_live_prices(self):
        conn = tracker.get_conn()
        self._insert_snapshot(conn, "2026-05-02", "TEST", "STAGE_1", 100.0)
        self._insert_snapshot(conn, "2026-05-04", "TEST", "STAGE_2", 110.0)
        conn.commit()
        conn.close()

        first = tracker.build_change_report(snap_date="2026-05-04", vs_date="2026-05-02")
        self.assertIsNone(first["new_stage2"][0]["live_price"])

        conn = tracker.get_conn()
        conn.execute(
            "UPDATE stage_snapshots SET live_price=125 WHERE snapshot_date='2026-05-04' AND symbol='TEST'"
        )
        conn.commit()
        conn.close()

        refreshed = tracker.build_change_report(snap_date="2026-05-04", vs_date="2026-05-02")

        self.assertEqual(refreshed["new_stage2"][0]["live_price"], 125.0)
        self.assertEqual(refreshed["new_stage2"][0]["live_vs_prev_pct"], 25.0)

    def test_rule_based_change_summary_mentions_stage_changes_and_names(self):
        report = {
            "snap_date": "2026-05-04",
            "prev_date": "2026-05-02",
            "week_snap": "2026-04-28",
            "summary": {
                "total_stage2": 159,
                "new_entrants_day": 2,
                "exits_day": 1,
                "stage_changes_day": 3,
                "stage_counts": {"STAGE_1": 400, "STAGE_2": 159, "STAGE_3": 200, "STAGE_4": 160},
            },
            "new_stage2": [{"symbol": "AAA"}, {"symbol": "BBB"}],
            "exit_stage2": [{"symbol": "CCC"}],
            "week_new_stage2": [{"symbol": "AAA"}],
            "week_exit_stage2": [],
            "trend": {"sectors": [{"sector": "Banking", "count": 12}, {"sector": "Pharma", "count": 10}]},
        }

        summary = tracker.generate_change_summary(report, llm_func=lambda _prompt: None)

        self.assertEqual(summary["source"], "rules")
        text = " ".join([summary["headline"], *summary["bullets"]])
        self.assertIn("159", text)
        self.assertIn("AAA", text)
        self.assertIn("CCC", text)
        self.assertIn("Banking", text)

    def test_change_summary_uses_valid_llm_result(self):
        report = {
            "snap_date": "2026-05-04",
            "prev_date": "2026-05-02",
            "summary": {"total_stage2": 159, "new_entrants_day": 7, "exits_day": 7},
            "new_stage2": [],
            "exit_stage2": [],
            "week_new_stage2": [],
            "week_exit_stage2": [],
            "trend": {"sectors": []},
        }

        summary = tracker.generate_change_summary(
            report,
            llm_func=lambda _prompt: {
                "headline": "Leadership stayed balanced while churn remained active.",
                "bullets": ["Stage 2 breadth held at 159 names.", "Entrants and exits were evenly matched."],
            },
        )

        self.assertEqual(summary["source"], "llm")
        self.assertEqual(summary["headline"], "Leadership stayed balanced while churn remained active.")
        self.assertEqual(len(summary["bullets"]), 2)


if __name__ == "__main__":
    unittest.main()
