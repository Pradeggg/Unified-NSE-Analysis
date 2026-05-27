from __future__ import annotations

import nse_agent

from terminal.research_council.commands import parse_council_command


def test_parse_council_today_command_extracts_mode_and_flags():
    parsed = parse_council_command("/council today --horizon swing --risk moderate")

    assert parsed.action == "today"
    assert parsed.mode == "market_council"
    assert parsed.horizon == "swing"
    assert parsed.risk_budget == "moderate"
    assert parsed.symbols == []
    assert parsed.objective == "/council today --horizon swing --risk moderate"


def test_parse_council_stock_and_compare_commands_extract_symbols():
    stock = parse_council_command("/council stock MODISONLTD --horizon swing")
    compare = parse_council_command("/council compare APOLLO BEL HAL --horizon positional")

    assert stock.action == "stock"
    assert stock.mode == "stock_deep_dive"
    assert stock.symbols == ["MODISONLTD"]
    assert stock.horizon == "swing"
    assert compare.action == "compare"
    assert compare.mode == "stock_deep_dive"
    assert compare.symbols == ["APOLLO", "BEL", "HAL"]
    assert compare.horizon == "positional"


def test_parse_council_strategy_and_intraday_commands():
    strategy = parse_council_command(
        '/council strategy "Stage 2 breakout with volume confirmation" --family stage2_breakout'
    )
    intraday = parse_council_command("/council intraday --scan vwap-reclaim")

    assert strategy.action == "strategy"
    assert strategy.mode == "strategy_build"
    assert strategy.options["family"] == "stage2_breakout"
    assert strategy.options["hypothesis"] == "Stage 2 breakout with volume confirmation"
    assert intraday.action == "intraday"
    assert intraday.mode == "intraday_tactical"
    assert intraday.options["scan"] == "vwap-reclaim"


def test_parse_operational_council_commands():
    examples = {
        "/council sector --date latest": ("sector", "sector_opportunity"),
        "/council review --run latest": ("review", "report_review"),
        "/council review --file /tmp/broken_report.md": ("review", "report_review"),
        "/council report --run latest --format html": ("report", "report_review"),
        "/council resume --run research_1": ("resume", "report_review"),
        "/council steward": ("steward", "market_council"),
        "/council debug --run research_1": ("debug", "report_review"),
        "/council export --run research_1 --format json": ("export", "report_review"),
    }

    for command, expected in examples.items():
        parsed = parse_council_command(command)
        assert (parsed.action, parsed.mode) == expected


def test_parse_council_sector_command_extracts_sector_objective():
    parsed = parse_council_command("/council sector NIFTY AUTO --horizon swing --risk moderate")

    assert parsed.action == "sector"
    assert parsed.mode == "sector_opportunity"
    assert parsed.horizon == "swing"
    assert parsed.risk_budget == "moderate"
    assert parsed.symbols == []
    assert parsed.options["sector"] == "NIFTY AUTO"


def test_shared_command_registry_includes_council_handler():
    registry = nse_agent._build_command_registry()

    assert "council" in registry.handler_names


def test_handle_council_command_dispatches_run_without_duplicate_kwargs(monkeypatch):
    from terminal.research_council import commands

    captured = {}

    def fake_run_research_council(objective, **kwargs):
        captured["objective"] = objective
        captured["kwargs"] = kwargs
        return {
            "ok": True,
            "run_id": "research_test",
            "mode": kwargs["mode"],
            "stage": "persistence",
            "final_label": "WATCHLIST",
            "report_paths": {"markdown": "/tmp/research_test.md", "html": "/tmp/research_test.html"},
        }

    monkeypatch.setattr("terminal.tools.run_research_council", fake_run_research_council)

    output = commands.handle_council_command("/council today --horizon swing --risk moderate")

    assert captured["objective"] == "/council today --horizon swing --risk moderate"
    assert captured["kwargs"]["horizon"] == "swing"
    assert captured["kwargs"]["risk_budget"] == "moderate"
    assert "Run:    research_test" in output


def test_handle_council_sector_command_dispatches_sector_option(monkeypatch):
    from terminal.research_council import commands

    captured = {}

    def fake_run_research_council(objective, **kwargs):
        captured["objective"] = objective
        captured["kwargs"] = kwargs
        return {
            "ok": True,
            "run_id": "research_sector",
            "mode": kwargs["mode"],
            "stage": "persistence",
            "final_label": "WATCHLIST",
            "report_paths": {"markdown": "/tmp/research_sector.md", "html": "/tmp/research_sector.html"},
        }

    monkeypatch.setattr("terminal.tools.run_research_council", fake_run_research_council)

    output = commands.handle_council_command("/council sector NIFTY AUTO --horizon swing --risk moderate")

    assert captured["objective"] == "/council sector NIFTY AUTO --horizon swing --risk moderate"
    assert captured["kwargs"]["mode"] == "sector_opportunity"
    assert captured["kwargs"]["sector"] == "NIFTY AUTO"
    assert captured["kwargs"]["symbols"] == []
    assert "Run:    research_sector" in output


def test_handle_council_review_file_dispatches_report_review_run(monkeypatch):
    from terminal.research_council import commands

    captured = {}

    def fake_run_research_council(objective, **kwargs):
        captured["objective"] = objective
        captured["kwargs"] = kwargs
        return {
            "ok": True,
            "run_id": "research_review",
            "mode": kwargs["mode"],
            "stage": "persistence",
            "final_label": "REVIEW_MANUALLY",
            "report_paths": {},
        }

    monkeypatch.setattr("terminal.tools.run_research_council", fake_run_research_council)

    output = commands.handle_council_command("/council review --file /tmp/broken_report.md")

    assert captured["kwargs"]["mode"] == "report_review"
    assert captured["kwargs"]["report_path"] == "/tmp/broken_report.md"
    assert "Run:    research_review" in output


def test_slash_command_list_includes_research_council():
    labels = [label for label, _description in nse_agent._SLASH_COMMANDS]

    assert "/council" in labels
    assert "/council today" in labels


def test_handle_council_inlines_markdown_report_body(monkeypatch, tmp_path):
    """The terminal output should embed the full council report so the user
    sees the analysis immediately instead of just file paths."""
    from terminal.research_council import commands

    md = tmp_path / "research_inline.md"
    body = (
        "# Research Council Report\n\n"
        "## Candidate Table\n"
        "| Symbol | Score | Label |\n"
        "|---|---|---|\n"
        "| ATHERENERG | 63.55 | WATCHLIST |\n"
    )
    md.write_text(body, encoding="utf-8")

    def fake_run_research_council(objective, **kwargs):
        return {
            "ok": True,
            "run_id": "research_inline",
            "mode": kwargs["mode"],
            "stage": "persistence",
            "final_label": "WATCHLIST",
            "report_paths": {"markdown": str(md)},
        }

    monkeypatch.setattr("terminal.tools.run_research_council", fake_run_research_council)

    output = commands.handle_council_command(
        "/council sector NIFTY AUTO --horizon swing --risk moderate"
    )

    assert "Run:    research_inline" in output
    # Body must be inlined verbatim (header + table)
    assert "# Research Council Report" in output
    assert "| ATHERENERG | 63.55 | WATCHLIST |" in output


def test_handle_council_skips_inline_when_markdown_missing(monkeypatch):
    """A missing markdown file must not break the renderer or surface a
    traceback — it should silently omit the inline body."""
    from terminal.research_council import commands

    def fake_run_research_council(objective, **kwargs):
        return {
            "ok": True,
            "run_id": "research_nofile",
            "mode": kwargs["mode"],
            "stage": "persistence",
            "final_label": "WATCHLIST",
            "report_paths": {"markdown": "/tmp/does_not_exist_research.md"},
        }

    monkeypatch.setattr("terminal.tools.run_research_council", fake_run_research_council)

    output = commands.handle_council_command(
        "/council today --horizon swing --risk moderate"
    )

    assert "Run:    research_nofile" in output
    # No body / separator when file missing
    assert "─" * 78 not in output
