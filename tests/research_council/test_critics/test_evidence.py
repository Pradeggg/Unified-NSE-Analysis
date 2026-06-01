from datetime import datetime

from terminal.research_council.critics.evidence import EvidenceCritic
from terminal.research_council.schemas import AgentFinding, CouncilState, Decision


def _state(decision, findings=None):
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


def test_evidence_blocks_unsupported_fno_claim():
    decision = Decision(
        final_label="RESEARCH_LONG",
        confidence=0.8,
        rationale="ok",
        candidates=[{"symbol": "AAA", "fno_claim": "bullish"}],
    )

    review = EvidenceCritic().review(_state(decision))

    assert review.severity_max == "block"
    assert "F&O" in review.findings[0].description


def test_evidence_blocks_unsupported_catalyst_claim():
    decision = Decision(
        final_label="RESEARCH_LONG",
        confidence=0.8,
        rationale="ok",
        candidates=[{"symbol": "AAA", "catalyst_claim": "results"}],
    )

    review = EvidenceCritic().review(_state(decision))

    assert review.severity_max == "block"
    assert "catalyst" in review.findings[0].description


def test_evidence_allows_supported_fno_claim():
    decision = Decision(
        final_label="RESEARCH_LONG",
        confidence=0.8,
        rationale="ok",
        candidates=[{"symbol": "AAA", "fno_claim": "bullish"}],
    )
    findings = {
        "fno_risk": AgentFinding(
            finding_id="fno_1",
            agent="fno_risk",
            stance="supportive",
            confidence=0.7,
            thesis="ok",
            candidates=["AAA"],
        )
    }

    review = EvidenceCritic().review(_state(decision, findings))

    assert review.severity_max == "info"
    assert review.findings == []


def test_evidence_warns_when_sector_quant_lacks_specialist_confirmation():
    decision = Decision(
        final_label="WATCHLIST",
        confidence=0.75,
        rationale="quant supported but confirmation pending",
        candidates=[
            {
                "symbol": "AAA",
                "supporting_agents": ["sector_rotation"],
                "quant_sweep": {"verdict": "SUPPORTED"},
            }
        ],
    )
    findings = {
        "technical": AgentFinding("technical_1", "technical", "neutral", 0.3, "0 actionable technical setups identified."),
        "fundamental": AgentFinding("fund_1", "fundamental", "neutral", 0.3, "0 candidates have supportive quality evidence."),
        "fno_risk": AgentFinding("fno_1", "fno_risk", "unavailable", 0.2, "F&O evidence is unavailable."),
        "catalyst": AgentFinding("cat_1", "catalyst", "absent", 0.25, "No catalyst evidence available."),
    }

    review = EvidenceCritic().review(_state(decision, findings))

    assert review.severity_max == "warn"
    assert {finding.finding_id for finding in review.findings} >= {
        "evidence_technical_confirmation_AAA",
        "evidence_fno_confirmation_AAA",
        "evidence_fundamental_confirmation_AAA",
        "evidence_catalyst_confirmation_AAA",
    }


def test_evidence_warns_when_sector_only_candidate_lacks_specialist_confirmation():
    decision = Decision(
        final_label="WATCHLIST",
        confidence=0.55,
        rationale="sector-only shortlist; quant unavailable",
        candidates=[
            {
                "symbol": "AAA",
                "supporting_branch": "sector_rotation",
                "supporting_agents": ["sector_rotation"],
                "quant_sweep": {"verdict": None, "routes_untestable": 9},
            }
        ],
    )
    findings = {
        "technical": AgentFinding("technical_1", "technical", "neutral", 0.3, "0 actionable technical setups identified."),
        "fundamental": AgentFinding("fund_1", "fundamental", "neutral", 0.3, "0 candidates have supportive quality evidence."),
        "fno_risk": AgentFinding("fno_1", "fno_risk", "unavailable", 0.2, "F&O evidence is unavailable."),
        "catalyst": AgentFinding("cat_1", "catalyst", "absent", 0.25, "No catalyst evidence available."),
    }

    review = EvidenceCritic().review(_state(decision, findings))

    assert review.severity_max == "warn"
    assert any("sector-only" in finding.description for finding in review.findings)
