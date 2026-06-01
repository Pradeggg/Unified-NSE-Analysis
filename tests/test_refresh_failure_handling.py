import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

import daily_refresh
from fixed_nse_universe_analysis import STOCK_RESULT_COLUMNS, analyze_stocks


class RefreshFailureHandlingTests(unittest.TestCase):
    def test_analyze_stocks_empty_when_history_insufficient_keeps_expected_columns(self):
        latest = date(2026, 5, 15)
        stock_data = pd.DataFrame(
            [
                {
                    "SYMBOL": "AAA",
                    "TIMESTAMP": latest,
                    "CLOSE": 150.0,
                    "OPEN": 149.0,
                    "HIGH": 151.0,
                    "LOW": 148.0,
                    "TOTTRDQTY": 200000,
                    "TOTTRDVAL": 30000000,
                }
            ]
        )

        result = analyze_stocks(
            stock_data,
            pd.DataFrame(columns=["SYMBOL", "TIMESTAMP", "CLOSE"]),
            pd.DataFrame(),
            pd.DataFrame(columns=["SYMBOL", "COMPANY_NAME"]),
            latest,
        )

        self.assertTrue(result.empty)
        self.assertEqual(result.columns.tolist(), STOCK_RESULT_COLUMNS)
        self.assertIn("TECHNICAL_SCORE", result.columns)

    def test_postgres_eod_step_attempts_local_start_before_loader(self):
        calls = []

        def fake_run(label, cmd, dry_run=False, cwd=None, env=None):
            calls.append((label, cmd))
            return True

        with patch("daily_refresh.subprocess.run", return_value=SimpleNamespace(returncode=1)), patch(
            "daily_refresh._run", side_effect=fake_run
        ):
            ok = daily_refresh.step_postgres_eod_load(dry_run=False)

        self.assertTrue(ok)
        self.assertEqual(calls[0][0], "Start local PostgreSQL")
        self.assertIn("postgres/loader.py", calls[1][1])
        self.assertIn("--eod-only", calls[1][1])

    def test_portfolio_strategy_lab_step_runs_native_command_then_report(self):
        calls = []

        def fake_run(label, cmd, dry_run=False, cwd=None, env=None):
            calls.append((label, cmd))
            return True

        with patch("daily_refresh.subprocess.run", return_value=SimpleNamespace(returncode=0)), patch(
            "daily_refresh._run", side_effect=fake_run
        ):
            ok = daily_refresh.step_portfolio_strategy_lab(
                dry_run=False,
                output_dir="portfolio/data/nse_pg_strategy_lab/latest",
                top_n=123,
                slippage_bps=4.0,
                brokerage_bps=2.0,
            )

        self.assertTrue(ok)
        self.assertEqual(calls[0][0], "Portfolio strategy-lab replay")
        self.assertEqual(calls[0][1][1:4], ["-m", "portfolio.cli", "strategy-lab"])
        self.assertIn("--top-n", calls[0][1])
        self.assertIn("123", calls[0][1])
        self.assertEqual(calls[1][0], "Agent Adda strategy-lab report")
        self.assertIn("generate_preset_report('strategy-lab','html')", calls[1][1][-1])

    def test_historical_stage_backfill_step_preserves_existing_snapshots_by_default(self):
        calls = []

        def fake_run(label, cmd, dry_run=False, cwd=None, env=None):
            calls.append((label, cmd))
            return True

        with patch("daily_refresh.subprocess.run", return_value=SimpleNamespace(returncode=0)), patch(
            "daily_refresh._run", side_effect=fake_run
        ):
            ok = daily_refresh.step_historical_stage_backfill(dry_run=False)

        self.assertTrue(ok)
        self.assertEqual(calls[0][0], "Historical Stage Snapshots → scores.stage_snapshots")
        self.assertIn("scripts.backfill_historical_stage_snapshots", calls[0][1])
        self.assertNotIn("--replace-existing", calls[0][1])


if __name__ == "__main__":
    unittest.main()
