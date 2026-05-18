from pathlib import Path
from unittest.mock import patch

import nse_agent


def test_remember_report_path_from_strategy_council_output(tmp_path):
    report = tmp_path / "strategy_council_KIRLOSENG_20260515_142320.md"
    report.write_text("# Strategy Council", encoding="utf-8")

    output = (
        "Strategy Council — KIRLOSENG\n"
        "Recommendation: NO_TRADE\n"
        f"Report: {report}\n"
        "Mode: EOD Strategy Council simulation; research-only, not investment advice."
    )

    nse_agent._last_generated_report = None
    remembered = nse_agent._remember_generated_report(output)

    assert remembered == report
    assert nse_agent._last_generated_report == report


def test_remember_report_path_from_auto_export_output(tmp_path):
    report = tmp_path / "SCHAEFFLER_research_20260517_220217.html"
    report.write_text("<h1>SCHAEFFLER</h1>", encoding="utf-8")

    output = f"📄 Report saved (HTML): {report}\n"
    nse_agent._last_generated_report = None
    remembered = nse_agent._remember_generated_report(output)

    assert remembered == report
    assert nse_agent._last_generated_report == report


def test_remember_terminal_interaction_can_store_report_path(tmp_path):
    from terminal.agent import Agent

    report = tmp_path / "SCHAEFFLER_research.html"
    agent = Agent()

    nse_agent._remember_terminal_interaction(
        agent,
        "/analyze SCHAEFFLER",
        f"Report: {report}",
        intent="generated_report",
        source_label="generated report",
        symbols=["SCHAEFFLER"],
        result_type="report",
        result_items=[str(report)],
    )

    assert agent._last_turn_context is not None
    assert agent._last_turn_context.result_type == "report"
    assert agent._last_turn_context.result_items == [str(report)]
    assert agent._last_turn_context.symbols == ["SCHAEFFLER"]


def test_open_last_report_request_uses_session_report_path(tmp_path):
    report = tmp_path / "strategy_council_KIRLOSENG_20260515_142320.md"
    report.write_text("# Strategy Council", encoding="utf-8")
    nse_agent._last_generated_report = report

    assert nse_agent._is_open_last_report_request("open the report")

    with patch("subprocess.Popen") as popen:
        message = nse_agent._open_last_generated_report()

    popen.assert_called_once_with(["open", str(report)])
    assert str(report) in message
    assert "Opening report" in message


def test_open_last_report_handles_missing_session_context():
    nse_agent._last_generated_report = None

    with patch("subprocess.Popen") as popen:
        message = nse_agent._open_last_generated_report()

    popen.assert_not_called()
    assert "No report has been generated in this session" in message
