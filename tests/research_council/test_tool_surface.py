from __future__ import annotations

from datetime import datetime

from terminal.research_council.schemas import CouncilState, Decision


PUBLIC_RESEARCH_COUNCIL_TOOLS = {
    "build_research_evidence_pack",
    "run_research_council",
    "run_data_steward_check",
    "compose_plan",
    "execute_plan",
    "review_plan_execution",
    "run_critic_review",
    "apply_revision_round",
    "synthesize_council_decision",
    "render_research_council_report",
    "persist_research_council_run",
    "resume_council_run",
}


def _minimal_state() -> CouncilState:
    return CouncilState(
        run_id="research_test",
        session_id="s1",
        created_at=datetime(2026, 5, 27, 10, 0),
        mode="market_council",
        stage="persistence",
        objective="/council today",
        horizon="swing",
        risk_budget="moderate",
        universe_filter="liquid",
        decision=Decision(
            final_label="WATCHLIST",
            confidence=0.72,
            rationale="Fixture decision",
            candidates=[{"symbol": "AAA"}],
        ),
        flags={
            "markdown_report_path": "reports/research_council/research_test.md",
            "html_report_path": "reports/research_council/research_test.html",
        },
    )


def test_research_council_public_tools_are_registered():
    from terminal.tools import TOOL_REGISTRY

    assert PUBLIC_RESEARCH_COUNCIL_TOOLS.issubset(set(TOOL_REGISTRY))


def test_run_research_council_wrapper_returns_compact_state(monkeypatch):
    import terminal.research_council.engine as engine
    from terminal.tools import run_research_council

    monkeypatch.setattr(engine, "run_council", lambda objective, **flags: _minimal_state())

    result = run_research_council("/council today --horizon swing --risk moderate", dry_run=True)

    assert result["ok"] is True
    assert result["run_id"] == "research_test"
    assert result["final_label"] == "WATCHLIST"
    assert result["report_paths"]["markdown"].endswith("research_test.md")
    assert result["report_paths"]["html"].endswith("research_test.html")


def test_run_data_steward_check_wrapper_returns_verdict(monkeypatch):
    from terminal.research_council.schemas import StewardVerdict
    from terminal.research_council.states import data_steward
    from terminal.tools import run_data_steward_check

    monkeypatch.setattr(
        data_steward,
        "run_check",
        lambda **_: StewardVerdict(
            as_of=datetime(2026, 5, 27).date(),
            data_status="usable",
            universe={"total_symbols": 10},
        ),
    )

    result = run_data_steward_check(mode="market_council")

    assert result["ok"] is True
    assert result["verdict"]["data_status"] == "usable"
    assert result["verdict"]["universe"]["total_symbols"] == 10
