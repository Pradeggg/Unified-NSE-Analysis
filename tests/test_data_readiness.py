import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import terminal.data_readiness as data_readiness
from terminal.data_readiness import (
    append_readiness_metadata,
    execute_refresh_plan,
    handle_data_readiness_command,
    inspect_data_readiness,
    plan_refresh,
    render_readiness_panel,
)


def _create_stage_db(root: Path, rows: list[tuple]) -> Path:
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "sector_rotation_tracker.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE stage_snapshots (
            snapshot_date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            company_name TEXT,
            stage TEXT,
            stage_score REAL,
            technical_score REAL,
            rsi REAL,
            relative_strength REAL,
            trading_signal TEXT,
            supertrend_state TEXT,
            price REAL,
            price_date TEXT,
            enhanced_fund_score REAL,
            earnings_quality REAL,
            sales_growth REAL,
            financial_strength REAL,
            institutional_backing REAL,
            can_slim_score REAL,
            investment_score REAL,
            source_csv TEXT,
            PRIMARY KEY (snapshot_date, symbol)
        )
        """
    )
    conn.executemany(
        """
        INSERT INTO stage_snapshots (
            snapshot_date, symbol, company_name, stage, stage_score,
            technical_score, rsi, relative_strength, trading_signal,
            supertrend_state, price, price_date, enhanced_fund_score,
            earnings_quality, sales_growth, financial_strength,
            institutional_backing, can_slim_score, investment_score, source_csv
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()
    return db_path


class DataReadinessTests(unittest.TestCase):
    def setUp(self):
        self._env_patch = patch.dict(
            "os.environ",
            {"AGENT_ADDA_ENABLE_SQLITE_FALLBACKS": "1"},
        )
        self._pg_patch = patch.object(data_readiness, "PG_DSN", "invalid readiness test dsn")
        self._env_patch.start()
        self._pg_patch.start()

    def tearDown(self):
        self._pg_patch.stop()
        self._env_patch.stop()

    def test_fresh_db_reports_technical_and_fundamental_coverage(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            rows = [
                (
                    "2026-05-14",
                    f"AAA{i}",
                    "AAA",
                    "STAGE_2",
                    80,
                    75,
                    60,
                    12,
                    "BUY",
                    "BUY",
                    100,
                    "2026-05-14",
                    70 if i < 4 else None,
                    60,
                    10,
                    80 if i < 4 else None,
                    50,
                    65 if i < 4 else None,
                    70,
                    "fixture.csv",
                )
                for i in range(10)
            ]
            _create_stage_db(root, rows)

            status = inspect_data_readiness(root, today="2026-05-15")

        self.assertEqual(status.latest_snapshot_date, "2026-05-14")
        self.assertEqual(status.row_count, 10)
        self.assertEqual(status.technical_covered, 10)
        self.assertEqual(status.fundamental_covered, 4)
        self.assertEqual(status.status, "fresh_trading_day")
        self.assertEqual(status.fundamental_status, "ready")
        self.assertFalse(status.needs_refresh)

    def test_missing_db_plans_refresh(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            status = inspect_data_readiness(root, today="2026-05-15")
            plan = plan_refresh(status, project_root=root)

        self.assertEqual(status.status, "missing")
        self.assertTrue(status.needs_refresh)
        self.assertEqual(plan.action, "run_refresh")
        self.assertIn("daily_refresh.py", " ".join(plan.command))

    def test_stale_db_plans_refresh(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _create_stage_db(
                root,
                [
                    (
                        "2026-05-01",
                        "AAA",
                        "AAA",
                        "STAGE_2",
                        80,
                        75,
                        60,
                        12,
                        "BUY",
                        "BUY",
                        100,
                        "2026-05-01",
                        70,
                        60,
                        10,
                        80,
                        50,
                        65,
                        70,
                        "fixture.csv",
                    )
                ],
            )

            status = inspect_data_readiness(root, today="2026-05-15")

        self.assertEqual(status.status, "stale")
        self.assertTrue(status.needs_refresh)

    def test_execute_refresh_plan_uses_injected_runner_and_rechecks(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            status = inspect_data_readiness(root, today="2026-05-15")
            refresh_plan = plan_refresh(status, project_root=root)
            calls = []

            def runner(command, cwd):
                calls.append((command, cwd))
                _create_stage_db(
                    root,
                    [
                        (
                            "2026-05-14",
                            "AAA",
                            "AAA",
                            "STAGE_2",
                            80,
                            75,
                            60,
                            12,
                            "BUY",
                            "BUY",
                            100,
                            "2026-05-14",
                            70,
                            60,
                            10,
                            80,
                            50,
                            65,
                            70,
                            "fixture.csv",
                        )
                    ],
                )
                return 0

            result = execute_refresh_plan(
                refresh_plan,
                project_root=root,
                runner=runner,
                today="2026-05-15",
            )

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.status.status, "fresh_trading_day")
        self.assertEqual(len(calls), 1)

    def test_render_and_command_output_show_counts_and_action(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _create_stage_db(
                root,
                [
                    (
                        "2026-05-14",
                        "AAA",
                        "AAA",
                        "STAGE_2",
                        80,
                        75,
                        60,
                        12,
                        "BUY",
                        "BUY",
                        100,
                        "2026-05-14",
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        "fixture.csv",
                    )
                ],
            )

            panel = render_readiness_panel(inspect_data_readiness(root, today="2026-05-15"))
            command_output = handle_data_readiness_command(
                "/data-status",
                project_root=root,
                today="2026-05-15",
            )

        self.assertIn("Data Readiness", panel)
        self.assertIn("Technical DB: 2026-05-14", command_output)
        self.assertIn("0/1 enhanced fundamentals", command_output)
        self.assertIn("Action: run", command_output)

    def test_refresh_command_can_check_without_running_refresh(self):
        with tempfile.TemporaryDirectory() as td:
            output = handle_data_readiness_command(
                "/refresh-data --check",
                project_root=Path(td),
                today="2026-05-15",
            )

        self.assertIn("Status: missing", output)
        self.assertIn("Action: run", output)

    def test_append_readiness_metadata_adds_explicit_stale_warning(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _create_stage_db(
                root,
                [
                    (
                        "2026-05-01",
                        "AAA",
                        "AAA",
                        "STAGE_2",
                        80,
                        None,
                        None,
                        None,
                        None,
                        None,
                        100,
                        "2026-05-01",
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        "fixture.csv",
                    )
                ],
            )

            answer = append_readiness_metadata("Base answer", project_root=root, today="2026-05-15")

        self.assertIn("Base answer", answer)
        self.assertIn("Data Freshness:", answer)
        self.assertIn("not found in DB", answer)


if __name__ == "__main__":
    unittest.main()
