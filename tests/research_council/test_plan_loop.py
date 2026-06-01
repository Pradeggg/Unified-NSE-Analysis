from datetime import datetime

from datetime import date

from terminal.research_council.schemas import CouncilState, EvidencePack, ExecutionResult, Plan
from terminal.research_council.states import plan_build, plan_review


def _state(**overrides):
    base = {
        "run_id": "research_20260527_001",
        "session_id": "s1",
        "created_at": datetime(2026, 5, 27, 10, 0),
        "mode": "market_council",
        "stage": "plan_build",
        "objective": "today",
        "horizon": "swing",
        "risk_budget": "moderate",
        "universe_filter": "liquid",
    }
    base.update(overrides)
    return CouncilState(**base)


def test_plan_build_creates_deterministic_market_council_plan():
    updated = plan_build.run(_state())

    assert len(updated.plans) == 1
    plan = updated.plans[0]
    assert plan.plan_id == "research_20260527_001_plan_0"
    assert [step.question for step in plan.steps] == [
        "Is the current market regime supportive for fresh long research?",
        "Which sectors show relative strength and healthy breadth?",
        "Which stocks are Stage 2 or high relative-strength leaders?",
        "Which candidates fail liquidity, extension, or risk filters?",
        "Which candidates need F&O, result, event, or fundamental confirmation?",
    ]
    assert plan.steps[1].dependencies == ["regime"]
    assert plan.steps[2].dependencies == ["sector_leadership"]


def test_plan_build_creates_sector_opportunity_quant_sweep_from_shortlist():
    pack = EvidencePack(
        pack_id="pack_1",
        as_of=date(2026, 5, 27),
        mode="sector_opportunity",
        sections={
            "sector_opportunity": {"requested_sector": "NIFTY AUTO", "resolved_sector": "AUTO"},
            "stocks": {
                "candidates": [
                    {"symbol": "BAJAJ-AUTO"},
                    {"symbol": "EXIDEIND"},
                ]
            },
        },
    )
    state = _state(
        mode="sector_opportunity",
        objective="Analyze NIFTY AUTO and identify best potential stocks",
        evidence_pack=pack,
        route_decision={"sector": "NIFTY AUTO", "coder_quant_policy": "shortlist_only"},
    )

    updated = plan_build.run(state)

    assert len(updated.plans) == 1
    plan = updated.plans[0]
    assert plan.central_question == "Sector opportunity quant sweep for: NIFTY AUTO"
    assert [step.step_id for step in plan.steps] == ["coder_quant_shortlist_sweep"]
    call = plan.steps[0].tool_calls[0]
    assert call.tool_name == "strategy.build"
    assert call.args["sweep"] is True
    assert call.args["symbols"] == ["BAJAJ-AUTO", "EXIDEIND"]
    assert call.args["source_branch"] == "sector_opportunity"
    assert call.args["allowed_horizons"] == [5, 10, 20]


def test_plan_review_advances_when_latest_plan_results_succeed():
    plan = Plan(plan_id="plan_1", run_id="run_1", iteration=0, central_question="test")
    state = _state(
        stage="plan_review",
        plans=[plan],
        execution_results={"plan_1": {"a": ExecutionResult(result_id="r1", step_id="a", status="success")}},
    )

    updated = plan_review.run(state)

    assert updated.plan_reviews[-1].advance is True
    assert updated.plan_reviews[-1].advance_rationale == "All executed plan steps passed."


def test_plan_review_blocks_and_adds_questions_for_failed_steps():
    plan = Plan(plan_id="plan_1", run_id="run_1", iteration=0, central_question="test")
    state = _state(
        stage="plan_review",
        plans=[plan],
        execution_results={
            "plan_1": {
                "a": ExecutionResult(result_id="r1", step_id="a", status="failed_terminal", error="missing fno")
            }
        },
    )

    updated = plan_review.run(state)

    review = updated.plan_reviews[-1]
    assert review.advance is False
    assert review.new_questions == ["Resolve failed evidence step a: missing fno"]
    assert review.step_verdicts == [{"step_id": "a", "status": "failed_terminal", "error": "missing fno"}]


def test_plan_review_does_not_advance_zero_tested_quant_sweep():
    plan = Plan(plan_id="plan_1", run_id="run_1", iteration=0, central_question="test")
    state = _state(
        stage="plan_review",
        mode="sector_opportunity",
        plans=[plan],
        execution_results={
            "plan_1": {
                "coder_quant_shortlist_sweep": ExecutionResult(
                    result_id="r1",
                    step_id="coder_quant_shortlist_sweep",
                    status="success",
                    outputs=[{"ok": True, "routes_tested": 0, "routes_untestable": 9}],
                )
            }
        },
    )

    updated = plan_review.run(state)

    review = updated.plan_reviews[-1]
    assert review.advance is False
    assert review.new_questions == [
        "Resolve failed evidence step coder_quant_shortlist_sweep: quant sweep produced no testable routes"
    ]
    assert review.step_verdicts == [
        {
            "step_id": "coder_quant_shortlist_sweep",
            "status": "degraded",
            "error": "quant sweep produced no testable routes",
        }
    ]


def test_plan_review_enforces_iteration_cap():
    plan = Plan(plan_id="plan_1", run_id="run_1", iteration=3, central_question="test")
    state = _state(
        stage="plan_review",
        plans=[plan],
        execution_results={"plan_1": {"a": ExecutionResult(result_id="r1", step_id="a", status="failed_terminal")}},
        flags={"max_plan_iterations": 3},
    )

    updated = plan_review.run(state)

    assert updated.flags["plan_loop_cap_hit"] is True
    assert updated.plan_reviews[-1].advance is False
