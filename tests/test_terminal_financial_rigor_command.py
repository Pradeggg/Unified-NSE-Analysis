from unittest.mock import patch

import nse_agent


def test_audit_report_command_renders_markdown_sample(tmp_path):
    from terminal.financial_rigor.commands import handle_audit_report_command

    report = tmp_path / "investment_checklist.md"
    report.write_text("Revenue: Rs 1,200 cr\nROE: 24%\nPE: 20x\n", encoding="utf-8")

    output = handle_audit_report_command(f"/audit-report {report} --ratio 1 --seed 1")

    assert "# NSE Report Data Audit" in output
    assert "Total data points: 3" in output
    assert "Revenue" in output
    assert "Research only. Not investment advice." in output


def test_audit_report_command_supports_json(tmp_path):
    from terminal.financial_rigor.commands import handle_audit_report_command

    report = tmp_path / "report.md"
    report.write_text("Revenue: Rs 1,200 cr\n", encoding="utf-8")

    output = handle_audit_report_command(f"/audit-report {report} --json")

    assert '"total_points": 1' in output
    assert '"label": "Revenue"' in output


def test_audit_report_command_rejects_missing_path():
    from terminal.financial_rigor.commands import handle_audit_report_command

    output = handle_audit_report_command("/audit-report")

    assert "Usage:" in output
    assert "/audit-report reports/latest/investment_checklist.md" in output


def test_financial_rigor_command_renders_single_symbol(monkeypatch):
    from terminal.financial_rigor.commands import handle_financial_rigor_command

    def fake_cache(symbol, max_age_hours=None):
        return {
            "ratios": {
                "Current Price": "2,400",
                "Stock P/E": "24",
                "Book Value": "300",
                "EPS": "100",
                "Dividend Yield": "1%",
            },
            "_cache_age_hours": 1,
        }

    monkeypatch.setattr("terminal.financial_rigor.screener_payload_from_cache", fake_cache)

    output = handle_financial_rigor_command("/financial-rigor INFY")

    assert "# NSE Financial Rigor - INFY" in output
    assert "PE" in output
    assert "24.00" in output
    assert "Earnings Yield" in output


def test_valuation_check_command_compares_multiple_symbols(monkeypatch):
    from terminal.financial_rigor.commands import handle_valuation_check_command

    payloads = {
        "INFY": {
            "ratios": {"Current Price": "2,400", "Stock P/E": "24", "Book Value": "300", "EPS": "100"},
            "_cache_age_hours": 1,
        },
        "TCS": {
            "ratios": {"Current Price": "4,000", "Stock P/E": "32", "Book Value": "250", "EPS": "125"},
            "_cache_age_hours": 2,
        },
    }

    monkeypatch.setattr(
        "terminal.financial_rigor.screener_payload_from_cache",
        lambda symbol, max_age_hours=None: payloads.get(symbol),
    )

    output = handle_valuation_check_command("/valuation-check INFY TCS")

    assert "# NSE Valuation Check" in output
    assert "| INFY | ok | 24.00 |" in output
    assert "| TCS | ok | 32.00 |" in output


def test_financial_rigor_registry_handlers_are_registered():
    registry = nse_agent._build_command_registry()

    assert "audit-report" in registry.handler_names
    assert "financial-rigor" in registry.handler_names
    assert "valuation-check" in registry.handler_names

    with patch(
        "terminal.financial_rigor.commands.handle_audit_report_command",
        return_value="# NSE Report Data Audit",
    ) as audit, patch("nse_agent.console.print") as printed:
        handled = registry.dispatch("/audit-report reports/latest/top_picks.md", agent=None, show_trace=False, mode="single_query")

    assert handled is True
    audit.assert_called_once_with("/audit-report reports/latest/top_picks.md")
    assert printed.called


def test_financial_rigor_commands_visible_in_slash_commands_categories_and_help():
    commands = {command for command, _description in nse_agent._SLASH_COMMANDS}

    assert "/audit-report reports/latest/investment_checklist.md" in commands
    assert "/financial-rigor INFY" in commands
    assert "/valuation-check INFY TCS HDFCBANK" in commands
    assert "/audit-report" in nse_agent._CMD_CATEGORIES
    assert "/financial-rigor" in nse_agent._CMD_CATEGORIES
    assert "/valuation-check" in nse_agent._CMD_CATEGORIES

    from terminal.help import SECTIONS

    assert "financial-rigor" in SECTIONS
    aliases = SECTIONS["financial-rigor"].get("aliases", [])
    assert "audit-report" in aliases
    assert "valuation-check" in aliases
