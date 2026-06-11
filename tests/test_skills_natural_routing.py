from unittest.mock import patch

import nse_agent


def test_natural_skill_router_handles_eps_driver_question():
    with patch("terminal.skills.commands.handle_diagnose_command", return_value="## Fundamental Driver Diagnosis\n\nShort Answer: ok") as handle, \
         patch("nse_agent._print_user") as print_user, \
         patch.object(nse_agent.console, "print") as printed:
        handled = nse_agent._handle_natural_skill_query("Why is EPS of DMART going down?")

    assert handled is True
    handle.assert_called_once_with("/diagnose DMART eps")
    print_user.assert_called_once_with("Why is EPS of DMART going down?")
    assert printed.called


def test_natural_skill_router_does_not_handle_generic_stock_question():
    with patch("terminal.skills.commands.handle_diagnose_command") as handle:
        handled = nse_agent._handle_natural_skill_query("Tell me about DMART")

    assert handled is False
    handle.assert_not_called()


def test_natural_skill_router_ignores_slash_commands():
    with patch("terminal.skills.commands.handle_diagnose_command") as handle:
        handled = nse_agent._handle_natural_skill_query("/diagnose DMART eps")

    assert handled is False
    handle.assert_not_called()
