from datetime import date, datetime

from terminal.research_council.schemas import (
    AgentFinding,
    BranchSummary,
    CouncilState,
    CriticFinding,
    CriticReview,
    EvidencePack,
    ExecutionResult,
    MissingEvidence,
    Plan,
    PlanReview,
    PlanStep,
    SourceTrailEntry,
    StewardVerdict,
    SuccessCriterion,
    ToolCall,
)


def test_evidence_pack_roundtrip_to_jsonable_dict():
    pack = EvidencePack(
        pack_id="evidence_20260526_001",
        as_of=date(2026, 5, 26),
        mode="market_council",
        universe_filter="liquid",
        sections={"market": {"regime": "CHOP"}},
        source_trail=[
            SourceTrailEntry(source="market.equity_eod", rows=2465, latest_date="2026-05-26")
        ],
        missing_evidence=[
            MissingEvidence(scope="derivatives", subject="FNO", field="iv_percentile", severity="warn")
        ],
    )

    restored = EvidencePack.from_dict(pack.to_dict())

    assert restored == pack
    assert restored.to_dict()["as_of"] == "2026-05-26"


def test_council_state_roundtrip_contains_nested_artifacts():
    plan = Plan(
        plan_id="plan_1",
        run_id="research_20260526_001",
        iteration=0,
        central_question="Is the tape supportive?",
        steps=[
            PlanStep(
                step_id="ps_001",
                sequence=1,
                question="Check breadth",
                required_evidence=["breadth.market_daily"],
                tool_calls=[ToolCall(tool_name="breadth.summarize", args={"window_days": 20})],
                success_criteria=[
                    SuccessCriterion(metric="breadth.pct_above_50dma", operator=">", value=50)
                ],
            )
        ],
    )
    state = CouncilState(
        run_id="research_20260526_001",
        session_id="session_1",
        created_at=datetime(2026, 5, 26, 21, 30),
        mode="market_council",
        stage="plan_review",
        objective="today swing",
        horizon="swing",
        risk_budget="moderate",
        universe_filter="liquid",
        symbols=[],
        plans=[plan],
        execution_results={
            "plan_1": {
                "ps_001": ExecutionResult(result_id="er_1", step_id="ps_001", status="success")
            }
        },
    )

    restored = CouncilState.from_dict(state.to_dict())

    assert restored.run_id == state.run_id
    assert restored.created_at == state.created_at
    assert restored.plans[0].steps[0].tool_calls[0].tool_name == "breadth.summarize"
    assert restored.execution_results["plan_1"]["ps_001"].status == "success"


def test_agent_and_critic_contracts_are_jsonable():
    finding = AgentFinding(
        finding_id="af_1",
        agent="technical",
        stance="selective",
        confidence=0.7,
        thesis="Two setups are actionable.",
        evidence=["scores.daily_scores"],
        candidates=["ABC"],
        risks=["breadth mixed"],
    )
    branch = BranchSummary(
        summary_id="bs_1",
        branch="momentum_leadership",
        stance="selective",
        supporting_agents=["technical"],
        dissenting_agents=["risk"],
        candidates=["ABC"],
        risks=["event risk"],
    )
    review = CriticReview(
        review_id="cr_1",
        critic="evidence",
        run_id="research_20260526_001",
        iteration=0,
        findings=[
            CriticFinding(
                finding_id="cf_1",
                severity="warn",
                target={"kind": "agent_finding", "id": "af_1"},
                description="Source trail is thin.",
                recommendation="Add exact source table.",
            )
        ],
        severity_max="warn",
        summary="One warning.",
    )
    plan_review = PlanReview(
        plan_id="plan_1",
        advance=True,
        step_verdicts=[{"step_id": "ps_001", "outcome": "success"}],
        advance_rationale="Enough evidence.",
    )

    assert AgentFinding.from_dict(finding.to_dict()) == finding
    assert BranchSummary.from_dict(branch.to_dict()) == branch
    assert CriticReview.from_dict(review.to_dict()) == review
    assert PlanReview.from_dict(plan_review.to_dict()) == plan_review
