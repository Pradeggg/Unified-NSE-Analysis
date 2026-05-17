import unittest
from unittest.mock import patch

from backtesting.strategy_council.types import (
    BacktestSliceResult,
    CouncilConfig,
    CouncilIteration,
    CouncilResult,
    Critique,
    EvidencePack,
    StrategySpec,
)


class FakeCursor:
    def __init__(self):
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((str(sql), params))

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


def _sample_council_result() -> CouncilResult:
    candidate = StrategySpec(
        "stage2",
        10,
        ("close_above_sma50",),
        ("time_stop",),
        ("risk_1pct",),
        "Stage 2 continuation.",
        params={"min_rs": 70},
        origin="deterministic",
    )
    iteration = CouncilIteration(
        index=1,
        candidates=(candidate,),
        train_results=(
            BacktestSliceResult("train", "stage2", 10, {"total_return_pct": 12.5}, 3),
        ),
        validation_results=(
            BacktestSliceResult("validation", "stage2", 10, {"total_return_pct": 4.2}, 1),
        ),
        critiques=(
            Critique("risk", "pass", issues=("size ok",), required_changes=("none",), confidence_delta=0.1),
        ),
        strategist_revision="keep stage2",
    )
    return CouncilResult(
        config=CouncilConfig(symbol="DMART", iterations=1),
        evidence=EvidencePack(symbol="DMART", as_of="2026-05-15", missing=["news"]),
        iterations=(iteration,),
        locked_strategy=candidate,
        test_results=(
            BacktestSliceResult("test", "stage2", 10, {"total_return_pct": 2.5}, 1),
        ),
        recommendation="TRADE_RESEARCH",
        rationale="Research-only positive validation.",
        report_path="/tmp/report.md",
    )


class StrategyCouncilPostgresStorageTests(unittest.TestCase):
    def test_ensure_schema_creates_council_tables_and_indexes(self):
        from backtesting.strategy_council.postgres_storage import ensure_strategy_council_schema

        conn = FakeConnection()

        ensure_strategy_council_schema(conn)

        sql_text = "\n".join(sql for sql, _ in conn.cursor_obj.executed)
        self.assertIn("CREATE SCHEMA IF NOT EXISTS strategy_council", sql_text)
        self.assertIn("CREATE TABLE IF NOT EXISTS strategy_council.runs", sql_text)
        self.assertIn("CREATE TABLE IF NOT EXISTS strategy_council.iterations", sql_text)
        self.assertIn("CREATE TABLE IF NOT EXISTS strategy_council.candidates", sql_text)
        self.assertIn("CREATE TABLE IF NOT EXISTS strategy_council.critiques", sql_text)
        self.assertIn("CREATE TABLE IF NOT EXISTS strategy_council.split_results", sql_text)
        self.assertIn("idx_strategy_council_runs_symbol_created", sql_text)
        self.assertEqual(conn.commits, 1)

    @patch("backtesting.strategy_council.postgres_storage.execute_values")
    def test_persist_council_result_inserts_run_and_child_rows(self, mock_execute_values):
        from backtesting.strategy_council.postgres_storage import persist_council_result

        conn = FakeConnection()

        persisted = persist_council_result(_sample_council_result(), conn=conn)

        self.assertTrue(persisted["ok"])
        self.assertEqual(persisted["schema"], "strategy_council")
        self.assertEqual(persisted["iterations_inserted"], 1)
        self.assertEqual(persisted["candidates_inserted"], 1)
        self.assertEqual(persisted["critiques_inserted"], 1)
        self.assertEqual(persisted["split_results_inserted"], 3)
        self.assertEqual(conn.commits, 1)
        sql_text = "\n".join(sql for sql, _ in conn.cursor_obj.executed)
        self.assertIn("INSERT INTO strategy_council.runs", sql_text)
        run_insert_params = conn.cursor_obj.executed[-1][1]
        self.assertIsInstance(run_insert_params[0], str)
        self.assertEqual(mock_execute_values.call_count, 4)
        first_child_values = mock_execute_values.call_args_list[0].args[2]
        self.assertIsInstance(first_child_values[0][0], str)
        child_sql = "\n".join(call.args[1] for call in mock_execute_values.call_args_list)
        self.assertIn("INSERT INTO strategy_council.iterations", child_sql)
        self.assertIn("INSERT INTO strategy_council.candidates", child_sql)
        self.assertIn("INSERT INTO strategy_council.critiques", child_sql)
        self.assertIn("INSERT INTO strategy_council.split_results", child_sql)


if __name__ == "__main__":
    unittest.main()
