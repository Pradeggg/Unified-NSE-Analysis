from datetime import datetime

from terminal.research_council.schemas import AgentFinding, CouncilState
from terminal.research_council.states import branch_deliberation


def _state():
    findings = {
        "technical": AgentFinding(
            finding_id="technical_1",
            agent="technical",
            stance="selective",
            confidence=0.7,
            thesis="AAA is actionable.",
            candidates=["AAA"],
            risks=["some setups are extended"],
            body={"setups": [{"symbol": "AAA", "setup_bucket": "ACTIONABLE"}]},
        ),
        "sector_rotation": AgentFinding(
            finding_id="sector_1",
            agent="sector_rotation",
            stance="constructive",
            confidence=0.75,
            thesis="Capital Goods leads.",
            candidates=["AAA", "BBB"],
            risks=["sector breadth divergence"],
            body={"leader_sectors": [{"sector": "Capital Goods", "top_stocks": ["AAA", "BBB"]}]},
        ),
        "fundamental": AgentFinding(
            finding_id="fund_1",
            agent="fundamental",
            stance="supportive",
            confidence=0.6,
            thesis="AAA quality supportive.",
            candidates=["AAA"],
            rejects=["CCC"],
            risks=[],
        ),
    }
    return CouncilState(
        run_id="research_20260527_001",
        session_id="s1",
        created_at=datetime(2026, 5, 27, 10, 0),
        mode="market_council",
        stage="branch_deliberation",
        objective="today",
        horizon="swing",
        risk_budget="moderate",
        universe_filter="liquid",
        specialist_findings=findings,
    )


def test_branch_deliberation_creates_six_public_branches(monkeypatch):
    saved = []
    monkeypatch.setattr(branch_deliberation, "save_branch_summaries", lambda summaries, **_: saved.extend(summaries))

    updated = branch_deliberation.run(_state())

    assert [summary.branch for summary in updated.branch_summaries] == [
        "momentum_leadership",
        "minervini_stage2",
        "sector_rotation",
        "earnings_catalyst",
        "fno_positioning",
        "defensive_no_trade",
    ]
    assert len(saved) == 6
    sector = next(summary for summary in updated.branch_summaries if summary.branch == "sector_rotation")
    assert sector.supporting_agents == ["sector_rotation"]
    assert sector.candidates == ["AAA", "BBB"]
    assert "private" not in str(sector.to_dict()).lower()


def test_branch_deliberation_skips_work_in_dry_run(monkeypatch):
    state = _state()
    data = state.to_dict()
    data["flags"] = {"dry_run": True}
    dry_state = CouncilState.from_dict(data)
    monkeypatch.setattr(branch_deliberation, "save_branch_summaries", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("called")))

    assert branch_deliberation.run(dry_state) == dry_state
