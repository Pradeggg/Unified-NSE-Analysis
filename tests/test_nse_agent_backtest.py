import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from terminal.backtest import handle_backtest_command


class NSEAgentBacktestTests(unittest.TestCase):
    def test_backtest_list_renders_registered_strategies(self):
        output = handle_backtest_command("/backtest list")

        self.assertIn("stage2", output)
        self.assertIn("vcp", output)
        self.assertIn("head_shoulders", output)

    def test_strategy_lab_validate_reports_readiness(self):
        output = handle_backtest_command("/strategy-lab validate")

        self.assertIn("Strategy Lab", output)
        self.assertIn("EOD", output)
        self.assertTrue("ok" in output.lower() or "blocked" in output.lower())

    def test_unknown_backtest_command_returns_usage(self):
        output = handle_backtest_command("/backtest nonsense")

        self.assertIn("Usage", output)

    @patch("terminal.backtest.load_latest_backtest_report")
    def test_backtest_report_latest_renders_persisted_run(self, mock_latest):
        mock_latest.return_value = {
            "run": {
                "id": 42,
                "strategy_id": "stage2",
                "universe": "fixture",
                "from_date": "2026-01-01",
                "to_date": "2026-01-05",
                "trade_count": 1,
                "total_return_pct": 8.3333,
                "total_pnl": 100.0,
                "created_at": "2026-05-11T08:00:00+05:30",
            },
            "metrics": {"win_rate_pct": 100.0},
            "trades": [
                {
                    "symbol": "AAA",
                    "entry_date": "2026-01-03",
                    "entry_price": 12.0,
                    "exit_date": "2026-01-05",
                    "exit_price": 13.0,
                    "quantity": 100,
                    "pnl": 100.0,
                    "return_pct": 8.3333,
                    "entry_reason": "stage2_entry_next_open",
                    "exit_reason": "stage2_exit_next_open",
                }
            ],
        }

        output = handle_backtest_command("/backtest report latest")

        self.assertIn("Backtest Report: #42", output)
        self.assertIn("stage2", output)
        self.assertIn("AAA", output)
        self.assertIn("8.3333", output)

    def test_backtest_run_stage2_with_data_file_returns_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_path = Path(tmp) / "fixture.csv"
            data_path.write_text(
                "date,symbol,open,high,low,close,volume,stage,relative_strength,sma_50\n"
                "2026-01-01,AAA,10,11,9,10.5,1000,Stage 1,50,10\n"
                "2026-01-02,AAA,11,12,10,11.5,1100,Stage 2,80,10\n"
                "2026-01-03,AAA,12,13,11,13,1200,Stage 2,82,10\n"
                "2026-01-04,AAA,14,15,13,13.5,1300,Stage 1,60,14\n"
                "2026-01-05,AAA,13,14,12,12.5,1400,Stage 1,55,14\n",
                encoding="utf-8",
            )

            output = handle_backtest_command(f"/backtest run stage2 --data {data_path} --capital 1200")

        self.assertIn("Backtest: stage2", output)
        self.assertIn("Trades: 1", output)
        self.assertIn("Total return", output)

    @patch("terminal.backtest.persist_backtest_result")
    def test_backtest_run_persist_reports_postgres_run_id(self, mock_persist):
        mock_persist.return_value = {"run_id": 42, "trades_inserted": 1, "metrics_inserted": 6}
        with tempfile.TemporaryDirectory() as tmp:
            data_path = Path(tmp) / "fixture.csv"
            data_path.write_text(
                "date,symbol,open,high,low,close,volume,stage,relative_strength,sma_50\n"
                "2026-01-01,AAA,10,11,9,10.5,1000,Stage 1,50,10\n"
                "2026-01-02,AAA,11,12,10,11.5,1100,Stage 2,80,10\n"
                "2026-01-03,AAA,12,13,11,13,1200,Stage 2,82,10\n"
                "2026-01-04,AAA,14,15,13,13.5,1300,Stage 1,60,14\n"
                "2026-01-05,AAA,13,14,12,12.5,1400,Stage 1,55,14\n",
                encoding="utf-8",
            )

            output = handle_backtest_command(f"/backtest run stage2 --data {data_path} --persist")

        self.assertIn("PostgreSQL run id: 42", output)
        mock_persist.assert_called_once()

    def test_default_nse_backtest_requires_symbol_or_max_symbols_guardrail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data").mkdir()
            (root / "data" / "nse_sec_full_data.csv").write_text(
                "TIMESTAMP,SYMBOL,OPEN,HIGH,LOW,CLOSE,TOTTRDQTY\n"
                "2026-01-01,AAA,10,11,9,10.5,1000\n",
                encoding="utf-8",
            )

            output = handle_backtest_command("/backtest run stage2", project_root=root)

        self.assertIn("requires --symbol or --max-symbols", output)

    def test_default_nse_backtest_with_symbol_uses_real_data_path_and_computed_features(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data").mkdir()
            rows = ["TIMESTAMP,SYMBOL,OPEN,HIGH,LOW,CLOSE,TOTTRDQTY\n"]
            for i in range(240):
                close = 100 + i
                rows.append(
                    f"2025-01-{(i % 28) + 1:02d},AAA,{close - 1},{close + 1},{close - 2},{close},{1000 + i}\n"
                )
            (root / "data" / "nse_sec_full_data.csv").write_text("".join(rows), encoding="utf-8")

            output = handle_backtest_command(
                "/backtest run stage2 --symbol AAA --capital 100000",
                project_root=root,
            )

        self.assertIn("Backtest: stage2", output)
        self.assertIn("Data: data/nse_sec_full_data.csv", output)
        self.assertIn("Trades:", output)


if __name__ == "__main__":
    unittest.main()
