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


def test_helpfile_catalog_loads_commands_prompts_and_email_piping_section():
    from terminal.helpfile import load_helpfile_catalog

    catalog = load_helpfile_catalog()

    assert any(row.command == "/email" for row in catalog.commands)
    assert any("/ric sherlock DMART" in row.command and "/email" in row.command for row in catalog.commands)
    assert any(row.shortcut == "p85" and "Company Xray" in row.title for row in catalog.prompts)
    assert "reports/generated/piped_" in catalog.section_text("email piping")


def test_help_pipe_renders_detailed_email_piping_guide():
    from io import StringIO

    from rich.console import Console
    from terminal.help import print_help

    console = Console(file=StringIO(), force_terminal=False, width=140)
    print_help(console, "pipe")

    output = console.file.getvalue()
    assert "Email Piping" in output
    assert "reports/generated/piped_" in output
    assert "--dry-run" in output


def test_completer_uses_helpfile_for_help_sections_and_pipe_email_flags():
    from prompt_toolkit.document import Document

    import nse_agent

    completer = nse_agent._AgentCompleter()

    help_completions = list(completer.get_completions(Document("/help em"), None))
    assert any("email piping" in str(item.display).lower() for item in help_completions)

    pipe_completions = list(completer.get_completions(Document("/screen stage2 | /email --"), None))
    labels = {item.text for item in pipe_completions}
    assert "--to" in labels
    assert "--dry-run" in labels


def test_single_query_help_pipe_uses_help_renderer(monkeypatch):
    from io import StringIO

    from rich.console import Console

    import nse_agent

    fake_console = Console(file=StringIO(), force_terminal=False, width=140)
    monkeypatch.setattr(nse_agent, "console", fake_console)

    nse_agent._single_query(object(), "/help pipe", show_trace=False)

    output = fake_console.file.getvalue()
    assert "Email Piping" in output
    assert "reports/generated/piped_" in output
    assert "HELP (HELP)" not in output


def test_help_surfaces_mode_command_via_section_and_search():
    """`/mode` (runtime permission mode) should be discoverable via the
    help system: as its own section, via the `permission`/`plan` keyword
    search, and from the high-traffic `session` section."""
    from io import StringIO

    from rich.console import Console
    from terminal.help import SECTIONS, print_help

    assert "permissions" in SECTIONS
    perm_entries = [cmd for cmd, _ in SECTIONS["permissions"]["entries"]]
    assert "/mode" in perm_entries
    assert "/mode plan" in perm_entries
    assert "/mode bypassPermissions" in perm_entries

    console = Console(file=StringIO(), force_terminal=False, width=140)
    for query in ("permissions", "permission", "plan mode", "bypass"):
        console.file = StringIO()
        print_help(console, query)
        out = console.file.getvalue()
        assert "/mode" in out, f"/mode missing from help output for query={query!r}"

    session_entries = [cmd for cmd, _ in SECTIONS["session"]["entries"]]
    assert "/mode" in session_entries
