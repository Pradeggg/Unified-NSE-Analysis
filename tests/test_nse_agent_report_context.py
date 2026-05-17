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
