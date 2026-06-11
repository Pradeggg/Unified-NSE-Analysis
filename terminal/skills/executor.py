from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping

from terminal.skills.evidence_validator import SkillEvidenceValidation, validate_skill_evidence
from terminal.skills.execution_plan import SkillExecutionPlan
from terminal.skills.sql_runner import run_skill_sql_template
from terminal.skills.telemetry import build_execution_event, log_execution_event


ToolCallFn = Callable[[str, dict[str, Any]], Any]
SQLRunnerFn = Callable[..., Any]
ReportLookupFn = Callable[[str, dict[str, Any]], Any]


@dataclass(frozen=True)
class SkillExecutionResult:
    passed: bool
    evidence: dict[str, Any]
    validation: SkillEvidenceValidation
    execution_id: int | None = None
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", dict(self.evidence or {}))
        object.__setattr__(self, "errors", _string_tuple(self.errors))
        object.__setattr__(self, "warnings", _string_tuple(self.warnings))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "execution_id": self.execution_id,
            "evidence": dict(self.evidence),
            "validation": self.validation.to_dict(),
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


def execute_skill_plan(
    execution_plan: SkillExecutionPlan | Mapping[str, Any],
    *,
    repository: Any | None = None,
    call_tool_fn: ToolCallFn | None = None,
    sql_runner_fn: SQLRunnerFn | None = None,
    report_lookup_fn: ReportLookupFn | None = None,
    available_tools: Iterable[str] | None = None,
    output_contract: Iterable[str] | None = None,
    freshness: Mapping[str, Any] | None = None,
    retrieval_id: int | None = None,
    today: Any | None = None,
) -> SkillExecutionResult:
    started = time.monotonic()
    plan = _normalize_plan(execution_plan)
    repo = repository
    tool_fn = call_tool_fn or _default_call_tool
    sql_fn = sql_runner_fn or run_skill_sql_template
    report_fn = report_lookup_fn or _default_report_lookup
    allowed_tools = set(_strings(available_tools)) if available_tools is not None else None

    evidence: dict[str, Any] = {}
    errors: list[str] = []
    executed_steps: list[dict[str, Any]] = []

    for step in plan["steps"]:
        step_type = str(step.get("step_type") or "")
        step_name = str(step.get("name") or "")
        target = str(step.get("target") or "")
        params = dict(step.get("params") or {})
        if step_type not in {"tool_call", "sql_template", "report_lookup"}:
            raise ValueError(f"unknown execution step type: {step_type}")
        if step_type == "tool_call" and allowed_tools is not None and target.lower() not in allowed_tools:
            raise ValueError(f"unknown tool: {target}")

        executed_record = {
            "step_id": step.get("step_id"),
            "step_type": step_type,
            "name": step_name,
            "target": target,
            "status": "pending",
        }
        try:
            result = _execute_step(
                step,
                tool_fn=tool_fn,
                sql_fn=sql_fn,
                report_fn=report_fn,
            )
            normalized = _normalize_evidence_result(result)
            if normalized.get("error"):
                message = f"step {step_name} failed: {normalized['error']}"
                errors.append(message)
                executed_record["status"] = "failed"
                executed_record["error"] = normalized["error"]
            else:
                evidence[step_name] = normalized
                executed_record["status"] = "passed"
                executed_record["row_count"] = normalized.get("row_count")
        except Exception as exc:
            message = f"step {step_name} failed: {exc}"
            errors.append(message)
            executed_record["status"] = "failed"
            executed_record["error"] = str(exc)
        executed_steps.append(executed_record)

    validation = validate_skill_evidence(
        plan["steps"],
        evidence=evidence,
        output_contract=output_contract,
        freshness=freshness,
        today=today,
    )
    all_errors = tuple([*errors, *validation.errors])
    warnings = tuple(validation.warnings)
    passed = not all_errors and validation.passed
    elapsed_ms = int((time.monotonic() - started) * 1000)
    execution_id = _log_execution(
        repo,
        plan,
        steps=executed_steps,
        validation=validation,
        passed=passed,
        errors=all_errors,
        elapsed_ms=elapsed_ms,
        retrieval_id=retrieval_id,
    )
    return SkillExecutionResult(
        passed=passed,
        evidence=evidence,
        validation=validation,
        execution_id=execution_id,
        errors=all_errors,
        warnings=warnings,
        metadata={"elapsed_ms": elapsed_ms, "steps_executed": len(executed_steps)},
    )


def _execute_step(
    step: dict[str, Any],
    *,
    tool_fn: ToolCallFn,
    sql_fn: SQLRunnerFn,
    report_fn: ReportLookupFn,
) -> Any:
    step_type = str(step.get("step_type") or "")
    target = str(step.get("target") or "")
    params = dict(step.get("params") or {})
    if step_type == "tool_call":
        return tool_fn(target, params)
    if step_type == "sql_template":
        return sql_fn(
            str(step["skill_id"]),
            target,
            params,
            version=int(step.get("skill_version") or 1),
        )
    if step_type == "report_lookup":
        return report_fn(target, params)
    raise ValueError(f"unknown execution step type: {step_type}")


def _normalize_plan(execution_plan: SkillExecutionPlan | Mapping[str, Any]) -> dict[str, Any]:
    if hasattr(execution_plan, "to_dict"):
        payload = execution_plan.to_dict()
    else:
        payload = dict(execution_plan)
    steps = []
    for step in payload.get("steps") or []:
        if hasattr(step, "to_dict"):
            steps.append(step.to_dict())
        elif isinstance(step, Mapping):
            steps.append(dict(step))
        else:
            steps.append(dict(step))
    payload["steps"] = steps
    payload["skill_ids"] = list(payload.get("skill_ids") or [])
    payload["skill_versions"] = dict(payload.get("skill_versions") or {})
    return payload


def _normalize_evidence_result(result: Any) -> dict[str, Any]:
    if hasattr(result, "to_dict"):
        value = result.to_dict()
    elif isinstance(result, Mapping):
        value = dict(result)
    else:
        value = {"rows": result}
    if "error" in value and value.get("error"):
        return {"error": str(value["error"])}
    if "rows" not in value and "data" in value:
        value["rows"] = value["data"]
    if "rows" not in value:
        value["rows"] = []
    if "row_count" not in value:
        rows = value.get("rows") or []
        value["row_count"] = len(rows) if isinstance(rows, list) else 1
    return value


def _log_execution(
    repo: Any,
    plan: dict[str, Any],
    *,
    steps: list[dict[str, Any]],
    validation: SkillEvidenceValidation,
    passed: bool,
    errors: tuple[str, ...],
    elapsed_ms: int,
    retrieval_id: int | None,
) -> int | None:
    if repo is None:
        return None
    log_fn = getattr(repo, "log_execution", None)
    if not callable(log_fn):
        return None
    skill_ids = list(plan.get("skill_ids") or [])
    skill_id = skill_ids[0] if skill_ids else ""
    versions = dict(plan.get("skill_versions") or {})
    return log_execution_event(
        repo,
        build_execution_event(
            retrieval_id=retrieval_id,
            skill_id=skill_id,
            skill_version=versions.get(skill_id, 1),
            steps=steps,
            validation_status="passed" if passed else "failed",
            validation_findings=[*errors, *validation.warnings],
            elapsed_ms=elapsed_ms,
            final_intent="skill_store",
            metadata={"skill_ids": skill_ids, "review_decision": plan.get("review_decision")},
        ),
    )


def _default_call_tool(name: str, params: dict[str, Any]) -> Any:
    from terminal.tools import call_tool

    return call_tool(name, params)


def _default_report_lookup(report_name: str, params: dict[str, Any]) -> Any:
    from terminal.report_context import get_last_report, list_generated_reports, read_report

    if params.get("path"):
        return read_report(str(params["path"]))
    if params.get("latest", True):
        return get_last_report(report_name)
    return list_generated_reports(report_name=report_name)


def _strings(values: Iterable[Any] | Any | None) -> list[str]:
    if values in (None, "", [], {}):
        return []
    if isinstance(values, str):
        items = [values]
    elif isinstance(values, Iterable):
        items = list(values)
    else:
        items = [values]
    return [str(item).strip().lower() for item in items if str(item).strip()]


def _string_tuple(values: Iterable[Any] | Any | None) -> tuple[str, ...]:
    return tuple(_strings(values))
