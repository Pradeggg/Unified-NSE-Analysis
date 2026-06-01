from terminal.research_council.plan_executor import PlanExecutor, RetryableToolError, evaluate_success_criteria
from terminal.research_council.schemas import Plan, PlanStep, SuccessCriterion, ToolCall
from terminal.research_council.tool_registry import ToolRegistry


def _plan(*steps):
    return Plan(
        plan_id="plan_1",
        run_id="run_1",
        iteration=0,
        central_question="test plan",
        steps=list(steps),
    )


def test_plan_executor_runs_independent_steps_and_returns_results():
    registry = ToolRegistry()
    registry.register("tool.a", lambda **_: {"ok": True, "value": 2})
    registry.register("tool.b", lambda **_: {"ok": True, "value": 3})
    plan = _plan(
        PlanStep(step_id="a", sequence=1, question="a", tool_calls=[ToolCall("tool.a")]),
        PlanStep(step_id="b", sequence=2, question="b", tool_calls=[ToolCall("tool.b")]),
    )

    results = PlanExecutor(registry=registry, run_id="run_1").execute(plan)

    assert set(results) == {"a", "b"}
    assert results["a"].status == "success"
    assert results["a"].outputs == [{"ok": True, "value": 2}]
    assert results["b"].status == "success"


def test_plan_executor_respects_dependencies():
    calls = []
    registry = ToolRegistry()
    registry.register("tool.first", lambda **_: calls.append("first") or {"ok": True})
    registry.register("tool.second", lambda **_: calls.append("second") or {"ok": True})
    plan = _plan(
        PlanStep(step_id="first", sequence=1, question="first", tool_calls=[ToolCall("tool.first")]),
        PlanStep(
            step_id="second",
            sequence=2,
            question="second",
            tool_calls=[ToolCall("tool.second")],
            dependencies=["first"],
        ),
    )

    results = PlanExecutor(registry=registry, run_id="run_1").execute(plan)

    assert calls == ["first", "second"]
    assert results["second"].status == "success"


def test_plan_executor_skips_step_when_dependency_failed_terminal():
    registry = ToolRegistry()
    registry.register("tool.fail", lambda **_: {"ok": False, "error": "bad input"})
    registry.register("tool.later", lambda **_: {"ok": True})
    plan = _plan(
        PlanStep(step_id="first", sequence=1, question="first", tool_calls=[ToolCall("tool.fail")]),
        PlanStep(
            step_id="second",
            sequence=2,
            question="second",
            tool_calls=[ToolCall("tool.later")],
            dependencies=["first"],
        ),
    )

    results = PlanExecutor(registry=registry, run_id="run_1").execute(plan)

    assert results["first"].status == "failed_terminal"
    assert results["second"].status == "deliberate_skip"
    assert "dependency failed" in results["second"].error


def test_plan_executor_retries_retryable_failure_once():
    attempts = {"count": 0}
    registry = ToolRegistry()

    def flaky(**_):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RetryableToolError("temporary")
        return {"ok": True}

    registry.register("tool.flaky", flaky)
    plan = _plan(PlanStep(step_id="a", sequence=1, question="a", tool_calls=[ToolCall("tool.flaky")]))

    results = PlanExecutor(registry=registry, run_id="run_1", retry_attempts=1).execute(plan)

    assert attempts["count"] == 2
    assert results["a"].status == "success"


def test_plan_executor_marks_terminal_when_success_criteria_fail():
    registry = ToolRegistry()
    registry.register("tool.a", lambda **_: {"ok": True, "score": 42})
    plan = _plan(
        PlanStep(
            step_id="a",
            sequence=1,
            question="a",
            tool_calls=[ToolCall("tool.a")],
            success_criteria=[SuccessCriterion(metric="score", operator=">=", value=80)],
        )
    )

    results = PlanExecutor(registry=registry, run_id="run_1").execute(plan)

    assert results["a"].status == "failed_terminal"
    assert "success criteria failed" in results["a"].error


def test_plan_executor_calls_result_sink_after_execution():
    saved = []
    registry = ToolRegistry()
    registry.register("tool.a", lambda **_: {"ok": True})
    plan = _plan(PlanStep(step_id="a", sequence=1, question="a", tool_calls=[ToolCall("tool.a")]))

    results = PlanExecutor(registry=registry, run_id="run_1", result_sink=lambda plan_id, rows: saved.append((plan_id, rows))).execute(plan)

    assert saved == [("plan_1", list(results.values()))]


def test_evaluate_success_criteria_supports_structured_paths():
    outputs = [{"ok": True, "nested": {"value": 10}, "symbols": ["A", "B"]}]

    assert evaluate_success_criteria(
        [
            SuccessCriterion(metric="nested.value", operator=">", value=5),
            SuccessCriterion(metric="symbols", operator="in", value="A"),
            SuccessCriterion(metric="ok", operator="exists"),
        ],
        outputs,
    ) == []
