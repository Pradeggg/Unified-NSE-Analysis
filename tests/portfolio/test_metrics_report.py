from __future__ import annotations

import json

from portfolio.agents.report_agent import ReportAgent
from datetime import date, datetime

import pytest

from portfolio.engine.audit_log import AuditLog, AuditLogError, AuditRecord, read_audit_log, write_audit_record
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


def test_plain_closed_fill_pair_derives_realized_pnl_when_no_account_or_snapshot_pnl():
    fills = [
        {
            "fill_id": "buy-1",
            "order_id": "order-buy",
            "strategy_id": "plain_strategy",
            "symbol": "AAA",
            "side": "BUY",
            "quantity": 10,
            "price": 100.0,
            "fees": 5.0,
            "timestamp": "2025-01-02",
        },
        {
            "fill_id": "sell-1",
            "order_id": "order-sell",
            "strategy_id": "plain_strategy",
            "symbol": "AAA",
            "side": "SELL",
            "quantity": 10,
            "price": 110.0,
            "fees": 3.0,
            "timestamp": "2025-01-03",
        },
    ]

    metrics = calculate_metrics(starting_equity=10_000.0, fills=fills)

    assert metrics.number_of_fills == 2
    assert metrics.number_of_trades == 1
    assert metrics.winning_trades == 1
    assert metrics.losing_trades == 0
    assert metrics.realized_pnl == 92.0
    assert metrics.invalid_fill_sequences == 0


def test_multi_strategy_same_symbol_plain_fills_use_portfolio_blended_cost():
    fills = [
        {
            "strategy_id": "s1",
            "symbol": "AAA",
            "side": "BUY",
            "quantity": 10,
            "price": 100.0,
            "fees": 0.0,
        },
        {
            "strategy_id": "s2",
            "symbol": "AAA",
            "side": "BUY",
            "quantity": 10,
            "price": 200.0,
            "fees": 0.0,
        },
        {
            "strategy_id": "s1",
            "symbol": "AAA",
            "side": "SELL",
            "quantity": 10,
            "price": 150.0,
            "fees": 0.0,
        },
    ]

    metrics = calculate_metrics(starting_equity=10_000.0, fills=fills)

    assert metrics.number_of_trades == 1
    assert metrics.flat_trades == 1
    assert metrics.realized_pnl == 0.0
    assert metrics.invalid_fill_sequences == 0


def test_unmatched_or_oversold_plain_sell_does_not_count_as_closed_trade():
    standalone_sell = calculate_metrics(
        starting_equity=10_000.0,
        fills=[
            {
                "strategy_id": "s1",
                "symbol": "AAA",
                "side": "SELL",
                "quantity": 10,
                "price": 150.0,
                "fees": 0.0,
            }
        ],
    )
    oversell = calculate_metrics(
        starting_equity=10_000.0,
        fills=[
            {
                "strategy_id": "s1",
                "symbol": "AAA",
                "side": "BUY",
                "quantity": 5,
                "price": 100.0,
                "fees": 0.0,
            },
            {
                "strategy_id": "s1",
                "symbol": "AAA",
                "side": "SELL",
                "quantity": 10,
                "price": 150.0,
                "fees": 0.0,
            },
        ],
    )

    assert standalone_sell.number_of_trades == 0
    assert standalone_sell.realized_pnl == 0.0
    assert standalone_sell.invalid_fill_sequences == 1
    assert oversell.number_of_trades == 0
    assert oversell.realized_pnl == 0.0
    assert oversell.invalid_fill_sequences == 1


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


def test_audit_write_returns_normalized_record_matching_jsonl_readback(tmp_path):
    path = tmp_path / "audit.jsonl"
    record = {
        "timestamp": datetime(2025, 1, 3, 15, 30),
        "date": date(2025, 1, 3),
        "agent": "paper_broker",
        "action": "fill_order",
        "strategy_id": "stage2_fixture_v1",
        "symbol": "AAA",
        "reason": "buy filled at next open",
        "payload": {"when": datetime(2025, 1, 3, 15, 30), "quantity": 95},
    }

    written = write_audit_record(path, record)

    assert written == read_audit_log(path)[0]
    assert written["timestamp"] == "2025-01-03 15:30:00"
    assert written["date"] == "2025-01-03"
    assert written["payload"]["when"] == "2025-01-03 15:30:00"


def test_read_audit_log_raises_domain_error_for_malformed_jsonl(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"agent":"ok"}\n{bad json}\n', encoding="utf-8")

    with pytest.raises(AuditLogError, match="malformed audit log JSON"):
        read_audit_log(path)


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
