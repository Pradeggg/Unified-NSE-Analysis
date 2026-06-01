from types import SimpleNamespace

import terminal.research_council.engine as engine
from terminal.research_council.engine import STATE_SEQUENCE, TERMINAL_STATES, run_council


def test_dry_run_walks_all_non_terminal_states_to_persistence():
    state = run_council("/council today --horizon swing --risk moderate", dry_run=True)

    assert state.stage == "persistence"
    assert [event["stage"] for event in state.events] == list(STATE_SEQUENCE)
    assert state.mode == "market_council"
    assert state.horizon == "swing"
    assert state.risk_budget == "moderate"
    assert state.run_id.startswith("research_")


def test_evidence_only_stops_after_evidence_pack_and_renders():
    state = run_council(
        "/council today --evidence-only --horizon swing --risk moderate",
        dry_run=True,
        evidence_only=True,
    )

    assert state.stage == "persistence"
    assert [event["stage"] for event in state.events] == [
        "intake",
        "route",
        "data_steward",
        "market_state",
        "render_html",
        "persistence",
    ]
    assert state.decision is None


def test_run_council_allows_explicit_mode_and_symbols():
    state = run_council(
        "review MODISONLTD",
        mode="stock_deep_dive",
        symbols=["MODISONLTD"],
        horizon="positional",
        risk_budget="conservative",
        dry_run=True,
    )

    assert state.mode == "stock_deep_dive"
    assert state.symbols == ["MODISONLTD"]
    assert state.horizon == "positional"
    assert state.risk_budget == "conservative"


def test_run_council_budget_abort_terminal_state():
    state = run_council("today", dry_run=True, max_wall_clock_s=0)

    assert state.stage == "abort_budget"
    assert state.stage in TERMINAL_STATES
    assert state.flags["budget_abort"] == "wall_clock_s"


def test_engine_cli_accepts_sector_flags_and_prints_run_summary(monkeypatch, capsys):
    captured = {}

    def fake_run_council(objective, **flags):
        captured["objective"] = objective
        captured["flags"] = flags
        return SimpleNamespace(
            events=[{"stage": "route", "objective": objective}],
            stage="persistence",
            mode="sector_opportunity",
            horizon="swing",
            risk_budget="moderate",
            flags={
                "markdown_report_path": "reports/research_council/research_1.md",
                "html_report_path": "reports/research_council/research_1.html",
            },
            decision=SimpleNamespace(
                final_label="WATCHLIST",
                confidence=0.72,
                candidates=[
                    {"symbol": "AAA", "research_score": 88.2},
                    {"symbol": "BBB", "research_score": 74.0},
                ],
            ),
        )

    monkeypatch.setattr(engine, "run_council", fake_run_council)
    monkeypatch.setattr(
        "sys.argv",
        [
            "research-council",
            "--sector",
            "NIFTY AUTO",
            "--mode",
            "sector_opportunity",
            "--horizon",
            "swing",
            "--risk",
            "moderate",
            "--format",
            "html",
        ],
    )

    engine.main()

    output = capsys.readouterr().out
    assert captured["objective"] == "/council sector NIFTY AUTO --horizon swing --risk moderate"
    assert captured["flags"]["sector"] == "NIFTY AUTO"
    assert captured["flags"]["mode"] == "sector_opportunity"
    assert captured["flags"]["risk_budget"] == "moderate"
    assert "status: persistence" in output
    assert "markdown_report: reports/research_council/research_1.md" in output
    assert "html_report: reports/research_council/research_1.html" in output
    assert "1. AAA score=88.2" in output


def test_engine_cli_print_report_streams_markdown(monkeypatch, capsys, tmp_path):
    report = tmp_path / "research_1.md"
    report.write_text("# Research Council Report\n\n## Candidate Table\nAAA\n", encoding="utf-8")

    def fake_run_council(objective, **flags):
        return SimpleNamespace(
            events=[],
            stage="persistence",
            mode="sector_opportunity",
            horizon="swing",
            risk_budget="moderate",
            flags={"markdown_report_path": str(report)},
            decision=SimpleNamespace(final_label="WATCHLIST", confidence=0.72, candidates=[]),
        )

    monkeypatch.setattr(engine, "run_council", fake_run_council)
    monkeypatch.setattr(
        "sys.argv",
        ["research-council", "--sector", "NIFTY AUTO", "--print-report"],
    )

    engine.main()

    output = capsys.readouterr().out
    assert "markdown_report:" in output
    assert "----- BEGIN RESEARCH COUNCIL REPORT -----" in output
    assert "# Research Council Report" in output
    assert "## Candidate Table" in output
    assert "----- END RESEARCH COUNCIL REPORT -----" in output
