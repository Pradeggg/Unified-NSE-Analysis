"""Execute the latest compiled council plan."""

from __future__ import annotations

from dataclasses import replace

from terminal.research_council.persistence import save_council_plans, save_execution_results
from terminal.research_council.plan_compiler import compile_plan
from terminal.research_council.plan_executor import PlanExecutor
from terminal.research_council.tool_registry import DEFAULT_REGISTRY, ToolRegistry


def run(state):
    if state.flags.get("dry_run") or not state.plans:
        return state
    plan = compile_plan(state.plans[-1], registry=DEFAULT_REGISTRY)
    save_council_plans([plan], run_id=state.run_id)
    executor = PlanExecutor(
        registry=DEFAULT_REGISTRY,
        run_id=state.run_id,
        result_sink=lambda plan_id, rows: save_execution_results(rows, plan_id=plan_id),
    )
    results = executor.execute(plan)
    execution_results = dict(state.execution_results)
    execution_results[plan.plan_id] = results
    plans = list(state.plans)
    plans[-1] = plan
    return replace(state, plans=plans, execution_results=execution_results)
