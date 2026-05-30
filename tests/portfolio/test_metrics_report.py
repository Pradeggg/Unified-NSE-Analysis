from __future__ import annotations

import json

from portfolio.agents.report_agent import ReportAgent
from portfolio.engine.audit_log import AuditLog, AuditRecord, read_audit_log, write_audit_record
from portfolio.engine.event_loop import ReplayConfig, run_replay
from portfolio.engine.metrics import calculate_metrics
from tests.portfolio.fixtures import sample_ohlcv, valid_strategy_spec


def _replay_result():
    return run_replay(
        sample_ohlcv(),
        [valid_strategy_spec()],
        ReplayConfig(initial_capital=100_000.0),
    )


def test_metrics_from_fixture_replay_include_pnl_drawdown_and_trade_counts():
    result = _replay_result()

    metrics = calculate_metrics(result)

    assert metrics.starting_equity == 100_000.0
    assert metrics.ending_equity == 99_620.0
    assert metrics.total_return_pct == -0.38
    assert metrics.max_drawdown_pct == 0.9446
    assert metrics.number_of_fills == 1
    assert metrics.number_of_trades == 0
    assert metrics.realized_pnl == 0.0
    assert metrics.winning_trades == 0
    assert metrics.losing_trades == 0
    assert metrics.open_positions_count == 1
    assert metrics.as_dict()["strategy_ids"] == ["stage2_fixture_v1"]


def test_empty_metrics_behavior_is_stable_for_missing_inputs():
    metrics = calculate_metrics(starting_equity=50_000.0)

    assert metrics.starting_equity == 50_000.0
    assert metrics.ending_equity == 50_000.0
    assert metrics.total_return_pct == 0.0
    assert metrics.max_drawdown_pct == 0.0
    assert metrics.number_of_fills == 0
    assert metrics.number_of_trades == 0
    assert metrics.realized_pnl == 0.0
    assert metrics.open_positions_count == 0


def test_jsonl_audit_writing_and_readback_is_deterministic(tmp_path):
    path = tmp_path / "nested" / "audit.jsonl"
    record = AuditRecord(
        timestamp="2025-01-03T00:00:00",
        date="2025-01-03",
        agent="paper_broker",
        action="fill_order",
        strategy_id="stage2_fixture_v1",
        symbol="AAA",
        reason="buy filled at next open",
        payload={"fill_id": "ord_000001-fill-1", "quantity": 95},
    )

    written = write_audit_record(path, record)
    AuditLog(path).append(
        timestamp="2025-01-04T00:00:00",
        date="2025-01-04",
        agent="report_agent",
        action="write_report",
        strategy_id="stage2_fixture_v1",
        symbol=None,
        reason="daily report generated",
        payload={"report": "paper_report.md"},
    )

    assert written == record.as_dict()
    assert path.parent.exists()
    lines = path.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0]) == record.as_dict()
    assert read_audit_log(path) == [
        record.as_dict(),
        {
            "timestamp": "2025-01-04T00:00:00",
            "date": "2025-01-04",
            "agent": "report_agent",
            "action": "write_report",
            "strategy_id": "stage2_fixture_v1",
            "symbol": None,
            "reason": "daily report generated",
            "payload": {"report": "paper_report.md"},
        },
    ]


def test_markdown_report_contains_key_pnl_trade_and_audit_sections(tmp_path):
    result = _replay_result()
    metrics = calculate_metrics(result)
    audit_path = tmp_path / "audit" / "paper.jsonl"
    report_path = tmp_path / "reports" / "daily.md"

    report = ReportAgent().write_markdown_report(
        report_path,
        replay_result=result,
        metrics=metrics,
        audit_log_path=audit_path,
        title="Fixture Paper Report",
    )

    assert report == report_path
    markdown = report_path.read_text(encoding="utf-8")
    assert "# Fixture Paper Report" in markdown
    assert "## Summary" in markdown
    assert "Starting equity | 100000.00" in markdown
    assert "Ending equity | 99620.00" in markdown
    assert "Total return | -0.380%" in markdown
    assert "Max drawdown | 0.945%" in markdown
    assert "## Strategy Metrics" in markdown
    assert "stage2_fixture_v1" in markdown
    assert "## Open Positions" in markdown
    assert "| AAA | 95 | 105.00 |" in markdown
    assert "## Fills / Trades" in markdown
    assert "| 2025-01-03 | stage2_fixture_v1 | AAA | BUY | 95 | 105.00 |" in markdown
    assert "## Audit / Log References" in markdown
    assert str(audit_path) in markdown
