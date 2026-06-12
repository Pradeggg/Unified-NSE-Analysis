import nse_agent


def test_broker_commands_are_registered_in_catalog():
    commands = dict(nse_agent._SLASH_COMMANDS)

    assert "/broker-sources" in commands
    assert "/broker-index" in commands
    assert "/broker-fetch" in commands
    assert "/broker-research" in commands
    assert "/deep-research" in commands
    assert "/report broker" in commands
