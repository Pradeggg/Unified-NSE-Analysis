from datetime import datetime

from terminal.research_council.schemas import CouncilState, Plan, PlanStep, ToolCall
from terminal.research_council.states import plan_execute


def _state(plan):
    return CouncilState(
        run_id="research_20260527_001",
        session_id="s1",
        created_at=datetime(2026, 5, 27, 10, 0),
        mode="market_council",
        stage="plan_execute",
        objective="today",
        horizon="swing",
        risk_budget="moderate",
        universe_filter="liquid",
        plans=[plan],
    )


def test_plan_execute_runs_latest_plan_and_attaches_results(monkeypatch):
    saved = []
    saved_plans = []
    registry = plan_execute.ToolRegistry()
    registry.register("tool.a", lambda **_: {"ok": True})
    monkeypatch.setattr(plan_execute, "DEFAULT_REGISTRY", registry)
    monkeypatch.setattr(plan_execute, "save_execution_results", lambda results, **kwargs: saved.append((kwargs["plan_id"], results)))
    monkeypatch.setattr(plan_execute, "save_council_plans", lambda plans, **kwargs: saved_plans.extend(plan.plan_id for plan in plans))
    plan = Plan(
        plan_id="plan_1",
        run_id="research_20260527_001",
        iteration=0,
        central_question="test",
        steps=[PlanStep(step_id="a", sequence=1, question="a", tool_calls=[ToolCall("tool.a")])],
    )

    updated = plan_execute.run(_state(plan))

    assert updated.execution_results["plan_1"]["a"].status == "success"
    assert saved_plans == ["plan_1"]
    assert saved[0][0] == "plan_1"


def test_plan_execute_skips_work_in_dry_run(monkeypatch):
    state = _state(Plan(plan_id="plan_1", run_id="run_1", iteration=0, central_question="test"))
    data = state.to_dict()
    data["flags"] = {"dry_run": True}
    dry_state = CouncilState.from_dict(data)
    monkeypatch.setattr(plan_execute, "save_execution_results", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("called")))
    monkeypatch.setattr(plan_execute, "save_council_plans", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("called")))

    assert plan_execute.run(dry_state) == dry_state
