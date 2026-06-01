import pytest

from terminal.research_council.plan_compiler import PlanCompileError, compile_plan
from terminal.research_council.schemas import Plan, PlanStep, SuccessCriterion, ToolCall
from terminal.research_council.tool_registry import ToolRegistry


def _registry():
    registry = ToolRegistry()
    registry.register("ok.tool", lambda **_: {"ok": True})
    return registry


def test_compile_plan_validates_tool_calls_and_keeps_valid_steps_pending():
    plan = Plan(
        plan_id="plan_1",
        run_id="run_1",
        iteration=0,
        central_question="test",
        steps=[
            PlanStep(
                step_id="ps_1",
                sequence=1,
                question="Run known tool",
                tool_calls=[ToolCall(tool_name="ok.tool")],
                success_criteria=[SuccessCriterion(metric="ok", operator="==", value=True)],
            )
        ],
    )

    compiled = compile_plan(plan, registry=_registry())

    assert compiled.steps[0].status == "pending"


def test_compile_plan_marks_unknown_tool_as_failed_terminal():
    plan = Plan(
        plan_id="plan_1",
        run_id="run_1",
        iteration=0,
        central_question="test",
        steps=[
            PlanStep(
                step_id="ps_1",
                sequence=1,
                question="Run unknown tool",
                tool_calls=[ToolCall(tool_name="missing.tool")],
            )
        ],
    )

    compiled = compile_plan(plan, registry=_registry())

    assert compiled.steps[0].status == "failed_terminal"
    assert compiled.steps[0].result_id == "tool_not_registered:missing.tool"


def test_compile_plan_rejects_dependency_cycles():
    plan = Plan(
        plan_id="plan_1",
        run_id="run_1",
        iteration=0,
        central_question="test",
        steps=[
            PlanStep(step_id="a", sequence=1, question="a", dependencies=["b"]),
            PlanStep(step_id="b", sequence=2, question="b", dependencies=["a"]),
        ],
    )

    with pytest.raises(PlanCompileError):
        compile_plan(plan, registry=_registry())


def test_compile_plan_rejects_unknown_dependencies():
    plan = Plan(
        plan_id="plan_1",
        run_id="run_1",
        iteration=0,
        central_question="test",
        steps=[PlanStep(step_id="a", sequence=1, question="a", dependencies=["missing"])],
    )

    with pytest.raises(PlanCompileError):
        compile_plan(plan, registry=_registry())


def test_compile_plan_validates_structured_success_criteria_without_eval():
    plan = Plan(
        plan_id="plan_1",
        run_id="run_1",
        iteration=0,
        central_question="test",
        steps=[
            PlanStep(
                step_id="a",
                sequence=1,
                question="a",
                success_criteria=[SuccessCriterion(metric="", operator="==", value=True)],
            )
        ],
    )

    with pytest.raises(PlanCompileError):
        compile_plan(plan, registry=_registry())
