"""Plan validation and compilation."""

from __future__ import annotations

from dataclasses import replace

from terminal.research_council.schemas import Plan, PlanStep, SuccessCriterion
from terminal.research_council.tool_registry import DEFAULT_REGISTRY, ToolNotRegistered, ToolRegistry


class PlanCompileError(ValueError):
    pass


def compile_plan(plan: Plan, *, registry: ToolRegistry | None = None) -> Plan:
    registry = registry or DEFAULT_REGISTRY
    _validate_dependencies(plan)
    compiled_steps = []
    for step in plan.steps:
        _validate_success_criteria(step.success_criteria)
        missing = _missing_tool(step, registry)
        if missing:
            compiled_steps.append(replace(step, status="failed_terminal", result_id=f"tool_not_registered:{missing}"))
        else:
            compiled_steps.append(step)
    return replace(plan, steps=compiled_steps)


def _missing_tool(step: PlanStep, registry: ToolRegistry) -> str | None:
    for call in step.tool_calls:
        try:
            registry.resolve(call.tool_name)
        except ToolNotRegistered:
            return call.tool_name
    return None


def _validate_dependencies(plan: Plan) -> None:
    step_ids = {step.step_id for step in plan.steps}
    for step in plan.steps:
        for dep in step.dependencies:
            if dep not in step_ids:
                raise PlanCompileError(f"unknown dependency {dep} for {step.step_id}")
    visiting: set[str] = set()
    visited: set[str] = set()
    deps = {step.step_id: set(step.dependencies) for step in plan.steps}

    def visit(node: str) -> None:
        if node in visited:
            return
        if node in visiting:
            raise PlanCompileError(f"cyclic dependency at {node}")
        visiting.add(node)
        for dep in deps[node]:
            visit(dep)
        visiting.remove(node)
        visited.add(node)

    for step_id in step_ids:
        visit(step_id)


def _validate_success_criteria(criteria: list[SuccessCriterion]) -> None:
    for criterion in criteria:
        if not criterion.metric:
            raise PlanCompileError("success criterion metric cannot be empty")
        if criterion.operator not in {">", ">=", "<", "<=", "==", "!=", "exists", "in"}:
            raise PlanCompileError(f"unsupported success criterion operator {criterion.operator}")
