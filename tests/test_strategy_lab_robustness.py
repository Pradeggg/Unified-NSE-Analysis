from __future__ import annotations

import json

import pandas as pd


def test_cost_stress_erodes_high_turnover_strategy_and_warns():
    from portfolio.engine.robustness import evaluate_strategy_robustness

    result = evaluate_strategy_robustness(
        {
            "strategy_id": "churn_v1",
            "total_return_pct": 12.0,
            "excess_return_pct": 4.0,
            "max_drawdown_pct": 11.0,
            "profit_factor": 1.3,
            "turnover_pct": 8000.0,
            "cost_drag_pct": 6.0,
            "fills": 250,
            "closed_trades": 80,
        },
        base_slippage_bps=5.0,
        base_brokerage_bps=3.0,
    )

    assert result["cost_scenarios"]["stress"]["adjusted_excess_return_pct"] < 0
    assert result["critic_verdict"] == "WARN"
    assert any("stress" in issue.lower() for issue in result["critic_issues"])


def test_inactive_strategy_is_blocked():
    from portfolio.engine.robustness import evaluate_strategy_robustness

    result = evaluate_strategy_robustness(
        {
            "strategy_id": "inactive_v1",
            "total_return_pct": 0.0,
            "excess_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "profit_factor": 0.0,
            "turnover_pct": 0.0,
            "cost_drag_pct": 0.0,
            "fills": 0,
            "closed_trades": 0,
        },
        base_slippage_bps=5.0,
        base_brokerage_bps=3.0,
    )

    assert result["critic_verdict"] == "BLOCK"
    assert result["robustness_score"] < 50


def test_strategy_lab_summary_attaches_robustness_rows():
    from portfolio.cli import _attach_strategy_lab_robustness

    summary = {
        "slippage_bps": 5.0,
        "brokerage_bps": 3.0,
        "benchmark_id": "Nifty 500",
    }
    leaderboard = pd.DataFrame(
        [
            {
                "rank": 1,
                "strategy_id": "trend_v1",
                "total_return_pct": 18.0,
                "excess_return_pct": 7.0,
                "max_drawdown_pct": 9.0,
                "profit_factor": 1.8,
                "turnover_pct": 500.0,
                "cost_drag_pct": 0.4,
                "fills": 32,
                "closed_trades": 12,
            }
        ]
    )

    enriched = _attach_strategy_lab_robustness(summary, leaderboard)

    assert "robustness" in summary
    assert len(summary["robustness"]["rows"]) == 1
    assert list(enriched["strategy_id"]) == ["trend_v1"]
    assert enriched.loc[0, "critic_verdict"] == "PASS"
    assert "robustness_score" in leaderboard.columns
    assert "critic_verdict" in leaderboard.columns
    assert "cost_stress_excess_return_pct" in leaderboard.columns


def test_cli_strategy_lab_report_includes_robustness_section(tmp_path):
    from portfolio.cli import _write_strategy_lab_report

    summary = _summary_with_robustness()
    path = tmp_path / "strategy_comparison_report.md"

    _write_strategy_lab_report(path, summary)

    text = path.read_text(encoding="utf-8")
    assert "## Robustness Pack" in text
    assert "Cost Stress Excess" in text
    assert "Critic Verdict" in text
    assert "trend_v1" in text


def test_terminal_strategy_lab_renders_robustness_markdown():
    from terminal import reports

    section = reports._strategy_lab_robustness_markdown(_summary_with_robustness())

    assert "## Robustness Pack" in section
    assert "trend_v1" in section
    assert "PASS" in section
    assert "stress-adjusted excess" in section.lower()


def _summary_with_robustness() -> dict:
    row = {
        "rank": 1,
        "strategy_id": "trend_v1",
        "name": "Trend",
        "total_return_pct": 18.0,
        "max_drawdown_pct": 9.0,
        "benchmark_return_pct": 11.0,
        "excess_return_pct": 7.0,
        "profit_factor": 1.8,
        "expectancy": 1200.0,
        "turnover_pct": 500.0,
        "cost_drag_pct": 0.4,
        "fills": 32,
        "closed_trades": 12,
        "win_rate_pct": 58.0,
        "robustness_score": 92.0,
        "critic_verdict": "PASS",
        "critic_issues": json.dumps(["No blocking robustness issues."]),
        "cost_stress_return_pct": 17.25,
        "cost_stress_excess_return_pct": 6.25,
        "cost_severe_return_pct": 16.5,
        "cost_severe_excess_return_pct": 5.5,
    }
    return {
        "run_id": "NSE-PG-STRATEGY-LAB",
        "benchmark_id": "Nifty 500",
        "start_date": "2025-01-01",
        "end_date": "2026-06-25",
        "row_count": 1000,
        "symbol_count": 200,
        "initial_capital": 1_000_000.0,
        "slippage_bps": 5.0,
        "brokerage_bps": 3.0,
        "leaderboard": [dict(row)],
        "robustness": {
            "artifact": "reports/strategy_robustness.csv",
            "base_cost_bps": 8.0,
            "stress_cost_bps": 23.0,
            "severe_cost_bps": 38.0,
            "rows": [dict(row)],
        },
    }
