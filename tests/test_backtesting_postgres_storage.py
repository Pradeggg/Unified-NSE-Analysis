import unittest
from unittest.mock import patch

import pandas as pd

from backtesting.engine import BacktestConfig, run_backtest
from backtesting.storage import ensure_backtest_schema, load_latest_backtest_report, persist_backtest_result


class FakeCursor:
    def __init__(self):
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((str(sql), params))

    def fetchone(self):
        return (42,)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeConnection:
    def __init__(self):
        self.cursor_obj = FakeCursor()
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


class FakeLatestCursor(FakeCursor):
    def __init__(self):
        super().__init__()
        self._last_sql = ""

    def execute(self, sql, params=None):
        self._last_sql = str(sql)
        super().execute(sql, params)

    def fetchone(self):
        if "FROM backtesting.backtest_runs" in self._last_sql:
            return (
                42,
                "stage2",
                "fixture",
                "2026-01-01",
                "2026-01-05",
                1200,
                1,
                8.3333,
                100.0,
                {"strategy_id": "stage2"},
                {"ok_to_backtest": True},
                "2026-05-11T08:00:00+05:30",
            )
        return None

    def fetchall(self):
        if "FROM backtesting.backtest_trades" in self._last_sql:
            return [
                (
                    "AAA",
                    "2026-01-03",
                    12.0,
                    "2026-01-05",
                    13.0,
                    100,
                    100.0,
                    8.3333,
                    "stage2_entry_next_open",
                    "stage2_exit_next_open",
                )
            ]
        if "FROM backtesting.backtest_metrics" in self._last_sql:
            return [
                ("trade_count", 1, "1"),
                ("total_return_pct", 8.3333, "8.3333"),
                ("total_pnl", 100.0, "100.0"),
            ]
        return []


class FakeLatestConnection(FakeConnection):
    def __init__(self):
        super().__init__()
        self.cursor_obj = FakeLatestCursor()


def _sample_result():
    df = pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=5, freq="D"),
            "symbol": ["AAA"] * 5,
            "open": [10.0, 11.0, 12.0, 14.0, 13.0],
            "high": [11.0, 12.0, 13.0, 15.0, 14.0],
            "low": [9.0, 10.0, 11.0, 13.0, 12.0],
            "close": [10.5, 11.5, 13.0, 13.5, 12.5],
            "volume": [1000, 1100, 1200, 1300, 1400],
            "stage": ["Stage 1", "Stage 2", "Stage 2", "Stage 1", "Stage 1"],
            "relative_strength": [50, 80, 82, 60, 55],
            "sma_50": [10, 10, 10, 14, 14],
        }
    )
    config = BacktestConfig(strategy_id="stage2", initial_capital=1200, allocation_pct=1.0)
    return config, run_backtest(df, config)


class BacktestingPostgresStorageTests(unittest.TestCase):
    def test_ensure_schema_creates_backtesting_tables_and_indexes(self):
        conn = FakeConnection()

        ensure_backtest_schema(conn)

        sql_text = "\n".join(sql for sql, _ in conn.cursor_obj.executed)
        self.assertIn("CREATE SCHEMA IF NOT EXISTS backtesting", sql_text)
        self.assertIn("CREATE TABLE IF NOT EXISTS backtesting.backtest_runs", sql_text)
        self.assertIn("CREATE TABLE IF NOT EXISTS backtesting.backtest_trades", sql_text)
        self.assertIn("CREATE INDEX IF NOT EXISTS idx_backtest_runs_strategy_created", sql_text)
        self.assertEqual(conn.commits, 1)

    @patch("backtesting.storage.execute_values")
    def test_persist_backtest_result_inserts_run_trades_and_metrics(self, mock_execute_values):
        conn = FakeConnection()
        config, result = _sample_result()

        persisted = persist_backtest_result(
            result,
            config,
            conn=conn,
            universe="fixture",
            data_readiness={"ok_to_backtest": True},
        )

        self.assertEqual(persisted["run_id"], 42)
        self.assertEqual(persisted["trades_inserted"], 1)
        self.assertGreaterEqual(persisted["metrics_inserted"], 1)
        self.assertEqual(conn.commits, 1)
        run_sql = "\n".join(sql for sql, _ in conn.cursor_obj.executed)
        self.assertIn("INSERT INTO backtesting.backtest_runs", run_sql)
        self.assertEqual(mock_execute_values.call_count, 2)

    def test_load_latest_backtest_report_reads_run_trades_and_metrics(self):
        conn = FakeLatestConnection()

        report = load_latest_backtest_report(conn=conn)

        self.assertEqual(report["run"]["id"], 42)
        self.assertEqual(report["run"]["strategy_id"], "stage2")
        self.assertEqual(report["metrics"]["total_return_pct"], 8.3333)
        self.assertEqual(len(report["trades"]), 1)
        self.assertEqual(report["trades"][0]["symbol"], "AAA")


if __name__ == "__main__":
    unittest.main()
