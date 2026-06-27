from unittest.mock import patch

import nse_agent


class _FakeGovernanceReport:
    symbol = "INFY"

    def to_dict(self):
        return {
            "symbol": "INFY",
            "rating": "WATCH",
            "score": 72.5,
            "missing_evidence": [],
        }


def test_governance_command_defaults_to_cached_markdown(monkeypatch):
    from terminal.governance.commands import handle_governance_command

    calls = []

    def fake_evaluate(symbol, **kwargs):
        calls.append((symbol, kwargs))
        return _FakeGovernanceReport()

    monkeypatch.setattr("terminal.governance.commands.evaluate_governance", fake_evaluate)
    monkeypatch.setattr(
        "terminal.governance.commands.render_markdown",
        lambda report: f"# Governance Evaluation - {report.symbol}",
    )

    output = handle_governance_command("/governance INFY")

    assert output == "# Governance Evaluation - INFY"
    assert calls == [
        (
            "INFY",
            {"use_llm": False, "use_annual_report_llm": False, "refresh_live": False},
        )
    ]


def test_governance_command_supports_alias_live_llm_and_json(monkeypatch):
    from terminal.governance.commands import handle_governance_command

    calls = []

    def fake_evaluate(symbol, **kwargs):
        calls.append((symbol, kwargs))
        return _FakeGovernanceReport()

    monkeypatch.setattr("terminal.governance.commands.evaluate_governance", fake_evaluate)

    output = handle_governance_command("/gov INFY --live --llm --json")

    assert '"symbol": "INFY"' in output
    assert '"rating": "WATCH"' in output
    assert calls == [
        (
            "INFY",
            {"use_llm": True, "use_annual_report_llm": False, "refresh_live": True},
        )
    ]


def test_governance_command_forwards_llm_read_flag(monkeypatch):
    from terminal.governance.commands import handle_governance_command

    calls = []

    def fake_evaluate(symbol, **kwargs):
        calls.append((symbol, kwargs))
        return _FakeGovernanceReport()

    monkeypatch.setattr("terminal.governance.commands.evaluate_governance", fake_evaluate)

    output = handle_governance_command("/governance INFY --live --llm-read --json")

    assert '"symbol": "INFY"' in output
    assert calls == [
        (
            "INFY",
            {"use_llm": False, "use_annual_report_llm": True, "refresh_live": True},
        )
    ]


def test_governance_command_rejects_missing_symbol():
    from terminal.governance.commands import handle_governance_command

    output = handle_governance_command("/governance --json")

    assert "Usage:" in output
    assert "/governance INFY" in output
    assert "--live" in output


def test_governance_registry_handler_is_registered():
    registry = nse_agent._build_command_registry()

    assert "governance" in registry.handler_names

    with patch(
        "terminal.governance.commands.handle_governance_command",
        return_value="# Governance Evaluation - INFY",
    ) as handle, patch("nse_agent.console.print") as printed:
        handled = registry.dispatch("/gov INFY --json", agent=None, show_trace=False, mode="single_query")

    assert handled is True
    handle.assert_called_once_with("/gov INFY --json")
    assert printed.called


def test_governance_is_visible_in_slash_commands_categories_and_help():
    commands = {command for command, _description in nse_agent._SLASH_COMMANDS}

    assert "/governance INFY" in commands
    assert "/gov INFY" in commands
    assert "/governance INFY --live --llm" in commands
    assert "/governance INFY --live --llm-read" in commands
    assert "/governance" in nse_agent._CMD_CATEGORIES

    from terminal.help import SECTIONS

    assert "governance" in SECTIONS
    aliases = SECTIONS["governance"].get("aliases", [])
    assert "governance" in aliases
    assert "gov" in aliases
