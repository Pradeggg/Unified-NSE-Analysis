from __future__ import annotations


def test_help_sections_cover_every_registered_command_family():
    import nse_agent
    from terminal.help import SECTIONS

    help_tokens: set[str] = set()
    for key, section in SECTIONS.items():
        help_tokens.add(key)
        help_tokens.update(str(alias).lstrip("/") for alias in section.get("aliases", []))
        for command, _description in section.get("entries", []):
            if command.startswith("/"):
                help_tokens.add(command.split()[0].lstrip("/"))

    missing = sorted(
        {
            command.split()[0].lstrip("/")
            for command, _description in nse_agent._SLASH_COMMANDS
        }
        - help_tokens
    )

    assert missing == []


def test_help_search_finds_newer_operational_and_research_commands():
    from io import StringIO

    from rich.console import Console
    from terminal.help import print_help

    console = Console(file=StringIO(), force_terminal=False, width=140)

    for query, expected in (
        ("doctor", "/doctor"),
        ("strategy council", "/strategy-council"),
        ("data coverage", "/data-coverage"),
        ("latest results", "/results-feed"),
        ("backtest", "/backtest"),
        ("report", "/report"),
    ):
        console.file = StringIO()
        print_help(console, query)
        output = console.file.getvalue()
        assert expected in output


def test_help_search_includes_every_registered_prompt_variant():
    from io import StringIO

    import nse_agent
    from rich.console import Console
    from terminal.help import print_help

    prompt_commands = [
        command for command, _description in nse_agent._SLASH_COMMANDS
        if command.startswith("/prompts")
    ]
    console = Console(file=StringIO(), force_terminal=False, width=140)

    print_help(console, "prompts")
    output = console.file.getvalue()

    for command in prompt_commands:
        assert command in output


def test_help_keyword_search_can_find_exact_registered_command_variants():
    from io import StringIO

    from rich.console import Console
    from terminal.help import print_help

    console = Console(file=StringIO(), force_terminal=False, width=140)
    print_help(console, "BANKNIFTY iron_condor")

    assert "/strategy BANKNIFTY iron_condor" in console.file.getvalue()
