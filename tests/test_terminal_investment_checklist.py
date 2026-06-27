from pathlib import Path
from unittest.mock import patch

import nse_agent


def test_handle_investment_checklist_command_writes_report(monkeypatch, tmp_path):
    from terminal.value_checklist import (
        ValueChecklistEvidence,
        handle_investment_checklist_command,
    )

    evidence = [
        ValueChecklistEvidence(
            symbol="TCS",
            company_name="TCS Ltd",
            sector="IT",
            fundamentals={
                "roe": 24.0,
                "roce": 31.0,
                "opm_pct": 26.0,
                "free_cash_flow_positive": True,
                "debt_to_equity": 0.05,
                "enhanced_fund_score": 82.0,
            },
            valuation={"pe": 24.0, "pb": 5.5, "earnings_yield_pct": 4.2, "valuation_signal": "reasonable"},
            governance={"promoter_pledge_pct": 0.0, "forensic_risk": "low", "insider_signal": "neutral"},
            technical={
                "stage": "STAGE_2",
                "relative_strength": 1.18,
                "rsi": 61.0,
                "technical_score": 78.0,
                "trend_signal": "BULLISH",
                "trading_signal": "BUY",
            },
            latest_results={"status": "ok"},
            source_trail=({"name": "scores.stage_snapshots", "status": "ok"},),
            missing_evidence=(),
            freshness={"stage_snapshot": "2026-06-26"},
        )
    ]

    monkeypatch.setattr("terminal.value_checklist.collect_value_checklist_evidence", lambda symbols: evidence)

    output = handle_investment_checklist_command("/investment-checklist TCS", project_root=tmp_path)

    assert "NSE Investment Checklist Comparison" in output
    assert "TCS" in output
    expected_report_prefix = f"Report: {tmp_path / 'reports' / 'value_checklists' / 'investment_checklist_'}"
    assert expected_report_prefix in output
    assert "Markdown:" in output
    assert "HTML:" in output
    assert "Latest Summary CSV:" in output
    assert (tmp_path / "reports" / "latest" / "investment_checklist.md").exists()
    assert (tmp_path / "reports" / "latest" / "investment_checklist_summary.csv").exists()


def test_investment_checklist_registry_handler_is_registered(monkeypatch):
    registry = nse_agent._build_command_registry()

    assert "investment-checklist" in registry.handler_names

    with patch(
        "terminal.value_checklist.handle_investment_checklist_command",
        return_value="# NSE Investment Checklist Comparison\n\nReport: /tmp/checklist.md\nMarkdown: x\nHTML: y",
    ) as handle, patch("nse_agent.console.print") as printed:
        handled = registry.dispatch("/investment-checklist TCS INFY", agent=None, show_trace=False, mode="single_query")

    assert handled is True
    handle.assert_called_once_with("/investment-checklist TCS INFY")
    assert printed.called


def test_investment_checklist_registry_remembers_report_path():
    registry = nse_agent._build_command_registry()
    previous_report = nse_agent._last_generated_report
    nse_agent._last_generated_report = None
    try:
        with patch(
            "terminal.value_checklist.handle_investment_checklist_command",
            return_value="# NSE Investment Checklist Comparison\n\nReport: /tmp/checklist.md\nMarkdown: x\nHTML: y",
        ), patch("nse_agent.console.print"):
            handled = registry.dispatch("/investment-checklist TCS INFY", agent=None, show_trace=False, mode="single_query")

        assert handled is True
        assert nse_agent._last_generated_report == Path("/tmp/checklist.md")
    finally:
        nse_agent._last_generated_report = previous_report


def test_investment_checklist_is_visible_in_slash_commands_and_help():
    commands = {command for command, _description in nse_agent._SLASH_COMMANDS}

    assert "/investment-checklist" in commands
    assert "/investment-checklist TCS INFY HDFCBANK" in commands
    assert "/investment-checklist" in nse_agent._CMD_CATEGORIES
