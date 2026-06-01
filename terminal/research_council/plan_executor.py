"""Execute compiled Research Council plans."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from terminal.research_council.schemas import ExecutionResult, Plan, PlanStep, SuccessCriterion
from terminal.research_council.tool_registry import DEFAULT_REGISTRY, ToolNotRegistered, ToolRegistry


class RetryableToolError(RuntimeError):
    """Raised by adapters when retrying the same tool call may succeed."""


class PlanExecutor:
    def __init__(
        self,
        *,
        registry: ToolRegistry | None = None,
        run_id: str | None = None,
        max_parallel: int = 4,
        retry_attempts: int = 1,
        result_sink: Callable[[str, list[ExecutionResult]], object] | None = None,
    ) -> None:
        self.registry = registry or DEFAULT_REGISTRY
        self.run_id = run_id
        self.max_parallel = max(1, max_parallel)
        self.retry_attempts = max(0, retry_attempts)
        self.result_sink = result_sink

    def execute(self, plan: Plan) -> dict[str, ExecutionResult]:
        results: dict[str, ExecutionResult] = {}
        steps_by_id = {step.step_id: step for step in plan.steps}
        for level in _dependency_levels(plan.steps):
            runnable = []
            for step in sorted(level, key=lambda item: item.sequence):
                failed_dep = _first_failed_dependency(step, results)
                if failed_dep:
                    results[step.step_id] = ExecutionResult(
                        result_id=f"{plan.plan_id}:{step.step_id}",
                        step_id=step.step_id,
                        status="deliberate_skip",
                        error=f"dependency failed: {failed_dep}",
                        elapsed_ms=0,
                    )
                elif step.status in {"failed_terminal", "deliberate_skip"}:
                    results[step.step_id] = ExecutionResult(
                        result_id=step.result_id or f"{plan.plan_id}:{step.step_id}",
                        step_id=step.step_id,
                        status=step.status,
                        error=step.result_id,
                        elapsed_ms=0,
                    )
                else:
                    runnable.append(step)
            if runnable:
                workers = min(self.max_parallel, len(runnable))
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futures = {pool.submit(self._execute_step, plan.plan_id, step): step for step in runnable}
                    for future in as_completed(futures):
                        step = futures[future]
                        results[step.step_id] = future.result()
            if set(results) == set(steps_by_id):
                break
        if self.result_sink:
            self.result_sink(plan.plan_id, list(results.values()))
        return results

    def _execute_step(self, plan_id: str, step: PlanStep) -> ExecutionResult:
        start = time.monotonic()
        outputs: list[dict[str, Any]] = []
        try:
            for call in step.tool_calls:
                adapter = self.registry.resolve(call.tool_name)
                outputs.append(_compact_output(self._call_with_retry(adapter, call.args)))
            failures = evaluate_success_criteria(step.success_criteria, outputs)
            if failures:
                return _result(plan_id, step, "failed_terminal", outputs, f"success criteria failed: {'; '.join(failures)}", start)
            if _tool_reported_terminal_failure(outputs):
                return _result(plan_id, step, "failed_terminal", outputs, _first_output_error(outputs), start)
            return _result(plan_id, step, "success", outputs, None, start)
        except RetryableToolError as exc:
            return _result(plan_id, step, "failed_retryable", outputs, str(exc), start)
        except ToolNotRegistered as exc:
            return _result(plan_id, step, "failed_terminal", outputs, exc.to_result()["error"], start)
        except Exception as exc:
            return _result(plan_id, step, "failed_terminal", outputs, str(exc), start)

    def _call_with_retry(self, adapter: Callable[..., object], args: dict[str, Any]) -> object:
        attempts = 0
        while True:
            try:
                return adapter(**args)
            except RetryableToolError:
                if attempts >= self.retry_attempts:
                    raise
                attempts += 1


def evaluate_success_criteria(criteria: list[SuccessCriterion], outputs: list[dict[str, Any]]) -> list[str]:
    failures = []
    merged = _merge_outputs(outputs)
    for criterion in criteria:
        found, actual = _path_get(merged, criterion.metric)
        if criterion.operator == "exists":
            passed = found
        elif not found:
            passed = False
        else:
            passed = _compare(actual, criterion.operator, criterion.value)
        if criterion.required and not passed:
            failures.append(f"{criterion.metric} {criterion.operator} {criterion.value!r}")
    return failures


def _dependency_levels(steps: list[PlanStep]) -> list[list[PlanStep]]:
    remaining = {step.step_id: step for step in steps}
    completed: set[str] = set()
    levels: list[list[PlanStep]] = []
    while remaining:
        ready = [
            step
            for step in remaining.values()
            if all(dep in completed for dep in step.dependencies)
        ]
        if not ready:
            raise ValueError("plan has cyclic or unresolved dependencies")
        levels.append(ready)
        for step in ready:
            completed.add(step.step_id)
            remaining.pop(step.step_id)
    return levels


def _first_failed_dependency(step: PlanStep, results: dict[str, ExecutionResult]) -> str | None:
    for dependency in step.dependencies:
        result = results.get(dependency)
        if result and result.status != "success":
            return dependency
    return None


def _result(
    plan_id: str,
    step: PlanStep,
    status: str,
    outputs: list[dict[str, Any]],
    error: str | None,
    start: float,
) -> ExecutionResult:
    return ExecutionResult(
        result_id=f"{plan_id}:{step.step_id}",
        step_id=step.step_id,
        status=status,  # type: ignore[arg-type]
        outputs=outputs,
        error=error,
        elapsed_ms=int((time.monotonic() - start) * 1000),
    )


def _compact_output(output: object) -> dict[str, Any]:
    if isinstance(output, dict):
        return output
    return {"ok": True, "value": output}


def _tool_reported_terminal_failure(outputs: list[dict[str, Any]]) -> bool:
    return any(output.get("ok") is False for output in outputs)


def _first_output_error(outputs: list[dict[str, Any]]) -> str:
    for output in outputs:
        if output.get("ok") is False:
            return str(output.get("error") or "tool reported failure")
    return "tool reported failure"


def _merge_outputs(outputs: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for output in outputs:
        merged.update(output)
    return merged


def _path_get(payload: dict[str, Any], path: str) -> tuple[bool, Any]:
    current: Any = payload
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return False, None
    return True, current


def _compare(actual: Any, operator: str, expected: Any) -> bool:
    if operator == "==":
        return actual == expected
    if operator == "!=":
        return actual != expected
    if operator == ">":
        return actual > expected
    if operator == ">=":
        return actual >= expected
    if operator == "<":
        return actual < expected
    if operator == "<=":
        return actual <= expected
    if operator == "in":
        return expected in actual
    return False
