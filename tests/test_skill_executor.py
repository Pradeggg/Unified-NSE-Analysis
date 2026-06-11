from __future__ import annotations

import datetime as dt

import pytest


class FakeRepository:
    def __init__(self):
        self.events = []

    def log_execution(self, event):
        self.events.append(event)
        return 77


def _step(step_type, name, target=None, **overrides):
    from terminal.skills.execution_plan import SkillExecutionStep

    value = {
        "step_id": f"skill_v1:1:{step_type}:{name}",
        "step_type": step_type,
        "skill_id": "skill_v1",
        "skill_version": 1,
        "name": name,
        "target": target or name,
        "params": {},
        "required_params": (),
        "metadata": {},
    }
    value.update(overrides)
    return SkillExecutionStep(**value)


def _plan(steps):
    from terminal.skills.execution_plan import SkillExecutionPlan

    return SkillExecutionPlan(
        skill_ids=("skill_v1",),
        skill_versions={"skill_v1": 1},
        steps=tuple(steps),
        review_decision="select",
    )


def test_executor_runs_tool_sql_and_report_steps_then_validates_and_logs():
    from terminal.skills.executor import execute_skill_plan

    repo = FakeRepository()
    calls = []

    def fake_tool(name, params):
        calls.append(("tool", name, params))
        return {"rows": [{"as_of_date": "2026-06-05", "signal": "ok"}], "row_count": 1, "as_of_date": "2026-06-05"}

    def fake_sql(skill_id, template_name, params, **kwargs):
        calls.append(("sql", skill_id, template_name, params, kwargs.get("version")))
        return {"rows": [{"as_of_date": "2026-06-05", "symbol": "ABC"}], "row_count": 1, "as_of_date": "2026-06-05"}

    def fake_report(report_name, params):
        calls.append(("report", report_name, params))
        return {"rows": [{"as_of_date": "2026-06-05", "report": report_name}], "row_count": 1, "as_of_date": "2026-06-05"}

    plan = _plan(
        [
            _step("tool_call", "market_context", target="get_live_market_overview", params={"mode": "eod"}),
            _step("sql_template", "index_returns", target="index_returns", params={"limit": 100}),
            _step("report_lookup", "top_picks_report", target="top_picks", params={"latest": True}),
        ]
    )

    result = execute_skill_plan(
        plan,
        repository=repo,
        call_tool_fn=fake_tool,
        sql_runner_fn=fake_sql,
        report_lookup_fn=fake_report,
        output_contract=["market_context", "index_returns", "top_picks_report"],
        today=dt.date(2026, 6, 6),
    )

    assert result.passed is True
    assert result.execution_id == 77
    assert set(result.evidence) == {"market_context", "index_returns", "top_picks_report"}
    assert calls == [
        ("tool", "get_live_market_overview", {"mode": "eod"}),
        ("sql", "skill_v1", "index_returns", {"limit": 100}, 1),
        ("report", "top_picks", {"latest": True}),
    ]
    assert repo.events[0]["validation_status"] == "passed"
    assert repo.events[0]["skill_id"] == "skill_v1"
    assert result.to_dict()["validation"]["passed"] is True


def test_executor_blocks_unknown_tool_before_execution():
    from terminal.skills.executor import execute_skill_plan

    with pytest.raises(ValueError, match="unknown tool: get_live_market_overview"):
        execute_skill_plan(
            _plan([_step("tool_call", "market_context", target="get_live_market_overview")]),
            available_tools={"get_symbol_snapshot"},
            call_tool_fn=lambda name, params: {"rows": []},
        )


def test_executor_blocks_unknown_step_type():
    from terminal.skills.executor import execute_skill_plan

    step = {
        "step_id": "bad",
        "step_type": "python",
        "skill_id": "skill_v1",
        "skill_version": 1,
        "name": "run_python",
        "target": "python",
        "params": {},
        "metadata": {},
    }

    with pytest.raises(ValueError, match="unknown execution step type: python"):
        execute_skill_plan(
            {"skill_ids": ["skill_v1"], "skill_versions": {"skill_v1": 1}, "steps": [step]},
            call_tool_fn=lambda name, params: {},
        )


def test_executor_surfaces_tool_error_as_execution_failure_and_logs():
    from terminal.skills.executor import execute_skill_plan

    repo = FakeRepository()

    result = execute_skill_plan(
        _plan([_step("tool_call", "market_context", target="get_live_market_overview")]),
        repository=repo,
        call_tool_fn=lambda name, params: {"error": "boom"},
        output_contract=["market_context"],
    )

    assert result.passed is False
    assert "step market_context failed: boom" in result.errors
    assert repo.events[0]["validation_status"] == "failed"


def test_validation_failure_prevents_success_claim():
    from terminal.skills.executor import execute_skill_plan

    result = execute_skill_plan(
        _plan([_step("sql_template", "index_returns", target="index_returns")]),
        sql_runner_fn=lambda *args, **kwargs: {"rows": [], "row_count": 0, "as_of_date": "2026-06-05"},
        output_contract=["index_returns"],
        today=dt.date(2026, 6, 6),
    )

    assert result.passed is False
    assert "required result set empty: index_returns" in result.validation.errors


def test_executor_result_serializes_to_plain_dict():
    from terminal.skills.evidence_validator import SkillEvidenceValidation
    from terminal.skills.executor import SkillExecutionResult

    result = SkillExecutionResult(
        passed=False,
        evidence={"x": {"row_count": 0}},
        validation=SkillEvidenceValidation(passed=False, errors=("bad",)),
        execution_id=12,
        errors=("bad",),
        warnings=("warn",),
        metadata={"elapsed_ms": 1},
    )

    assert result.to_dict() == {
        "passed": False,
        "execution_id": 12,
        "evidence": {"x": {"row_count": 0}},
        "validation": {
            "passed": False,
            "errors": ["bad"],
            "warnings": [],
            "missing_evidence": [],
            "metadata": {},
        },
        "errors": ["bad"],
        "warnings": ["warn"],
        "metadata": {"elapsed_ms": 1},
    }
