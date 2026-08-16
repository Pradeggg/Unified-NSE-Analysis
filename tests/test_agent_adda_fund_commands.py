from __future__ import annotations

from pathlib import Path


def test_smallcap_fund_action_view_surfaces_daily_decision_sections() -> None:
    from terminal.fund_commands import build_fund_action_view

    rows = [
        {
            "symbol": "ABC",
            "readiness_overlay_100": "82.0",
            "trigger_state": "TRIGGER_READY_REVIEW",
            "action_bucket": "Trigger review",
            "latest_price": "110",
            "breakout_level": "108",
            "retest_level": "101",
            "initial_stop": "99",
            "target_2r": "124",
            "paper_quantity": "20",
            "paper_position_value": "2200",
            "paper_risk_to_stop": "220",
            "result_status": "Fresh result",
            "external_note": "No adverse filing found",
            "research_action": "Review evidence pack before paper order.",
        },
        {
            "symbol": "XYZ",
            "readiness_overlay_100": "66.0",
            "trigger_state": "WAIT",
            "action_bucket": "Watch trigger",
            "latest_price": "94",
            "breakout_level": "115",
            "retest_level": "105",
            "initial_stop": "95",
            "target_2r": "135",
            "paper_quantity": "10",
            "paper_position_value": "940",
            "paper_risk_to_stop": "0",
            "result_status": "Board event pending",
            "external_note": "Wait for event.",
            "research_action": "Refresh after result.",
        },
    ]
    summary = {
        "total_symbols": 2,
        "paper_order_allowed": True,
        "trigger_review_symbols": ["ABC"],
        "blocked_trigger_symbols": [],
        "top_readiness_symbols": ["ABC", "XYZ"],
    }
    paths = {
        "csv": Path("Mutual Funds/extracted/small.csv"),
        "md": Path("docs/fund_policies/research_updates/small.md"),
        "html": Path("Mutual Funds/reports/small.html"),
    }

    output = build_fund_action_view("smallcap", rows, summary, paths, run_date="20260808")

    assert "Agent Adda Small Cap Portfolio Daily Command" in output
    assert "Paper order allowed: YES - review required" in output
    assert "Buy / New Paper Order Review" in output
    assert "ABC" in output
    assert "Sell / Exit Review" in output
    assert "XYZ <= stop 95" in output
    assert "Increase / Add Review" in output
    assert "Decrease / Trim Review" in output
    assert "Position Size / Stop / Target Map" in output
    assert "News / Result Watch" in output
    assert "Research-only. No live order instruction." in output


def test_midcap_fund_action_view_discloses_missing_trigger_risk_layer() -> None:
    from terminal.fund_commands import build_fund_action_view

    rows = [
        {
            "symbol": "BHEL",
            "overall_score_100": "84.2",
            "decision_bucket": "CORE CANDIDATE",
            "trigger_state": "WAIT",
            "stage": "STAGE_2",
            "stage2_gate": "PASS",
            "growth_gate": "PASS",
            "high_eps_gate": "PASS",
            "yoy_sales_gate": "PASS",
            "freshness_gate": "PASS",
            "latest_price": "300",
            "relative_strength": "45",
            "rsi": "62",
            "blockers": "",
        }
    ]
    summary = {
        "total_symbols": 1,
        "paper_order_allowed": False,
        "core_candidates": ["BHEL"],
        "refresh_first_symbols": [],
        "retest_only_symbols": [],
        "trigger_review_symbols": [],
        "blocked_trigger_symbols": [],
        "top_score_symbols": ["BHEL"],
    }
    paths = {
        "csv": Path("Mutual Funds/extracted/mid.csv"),
        "md": Path("docs/fund_policies/research_updates/mid.md"),
        "html": Path("Mutual Funds/reports/mid.html"),
    }

    output = build_fund_action_view("midcap", rows, summary, paths, run_date="20260808")

    assert "Agent Adda Mid Cap Portfolio Daily Command" in output
    assert "Buy / New Paper Order Review" in output
    assert "BHEL" in output
    assert "Position sizing is policy guidance only" in output
    assert "Stop/target map is pending a midcap trigger-risk layer" in output
    assert "Research-only. No live order instruction." in output


def test_agent_adda_fund_commands_are_registered() -> None:
    import nse_agent

    labels = [label for label, _description in nse_agent._SLASH_COMMANDS]

    assert "/agent-adda-small-cap-fund" in labels
    assert "/agent-adda-mid-cap-fund" in labels
    assert nse_agent._CMD_CATEGORIES["/agent-adda-small-cap-fund"][0] == "Portfolio Funds"
    assert nse_agent._CMD_CATEGORIES["/agent-adda-mid-cap-fund"][0] == "Portfolio Funds"
    assert "agent-adda-fund" in nse_agent._build_command_registry().handler_names
