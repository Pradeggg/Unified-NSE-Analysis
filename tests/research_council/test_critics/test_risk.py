from datetime import datetime

from terminal.research_council.critics.risk import RiskCritic
from terminal.research_council.schemas import AgentFinding, CouncilState, Decision


def _state(decision=None, findings=None):
    return CouncilState(
        run_id="run_1",
        session_id="s1",
        created_at=datetime(2026, 5, 27, 10, 0),
        mode="market_council",
        stage="critic_review",
        objective="today",
        horizon="swing",
        risk_budget="moderate",
        universe_filter="liquid",
        decision=decision,
        specialist_findings=findings or {},
    )


def test_risk_blocks_position_concentration():
    decision = Decision(
        final_label="RESEARCH_LONG",
        confidence=0.8,
        rationale="ok",
        candidates=[{"symbol": "AAA", "position_weight_pct": 25}],
    )

    review = RiskCritic().review(_state(decision=decision))

    assert review.severity_max == "block"
    assert "concentration" in review.findings[0].description


def test_risk_warns_on_low_liquidity():
    decision = Decision(
        final_label="WATCHLIST",
        confidence=0.6,
        rationale="ok",
        candidates=[{"symbol": "AAA", "liquidity_value_cr": 3}],
    )

    review = RiskCritic().review(_state(decision=decision))

    assert review.severity_max == "warn"


def test_risk_blocks_high_impact_event_risk():
    findings = {
        "catalyst": AgentFinding(
            finding_id="catalyst_1",
            agent="catalyst",
            stance="wait_for_confirmation",
            confidence=0.7,
            thesis="event risk",
            risks=["high-impact event within 5 trading days"],
        )
    }

    review = RiskCritic().review(_state(findings=findings))

    assert review.severity_max == "block"
    assert review.findings[0].target == {"kind": "agent_finding", "id": "catalyst"}
