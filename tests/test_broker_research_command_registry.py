import nse_agent


def test_broker_commands_are_registered_in_catalog():
    commands = dict(nse_agent._SLASH_COMMANDS)

    assert "/broker-sources" in commands
    assert "/broker-index" in commands
    assert "/broker-fetch" in commands
    assert "/broker-research" in commands
    assert "/deep-research" in commands
    assert "/report broker" in commands
    assert "/broker-crawl" in commands


def test_broker_index_failure_is_handled_without_falling_through(monkeypatch):
    def raise_pg_error(query):
        raise RuntimeError("postgres unavailable")

    monkeypatch.setattr(
        "broker_research.commands.handle_broker_index_command",
        raise_pg_error,
    )

    registry = nse_agent._build_command_registry()

    assert registry.dispatch(
        "/broker-index BEL --broker icici",
        agent=None,
        show_trace=False,
        mode="interactive",
    )
