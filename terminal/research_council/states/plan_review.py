"""Review plan execution results and decide whether to advance."""

from __future__ import annotations

from dataclasses import replace

from terminal.research_council.schemas import PlanReview


def run(state):
    if state.flags.get("dry_run") or not state.plans:
        return state
    plan = state.plans[-1]
    results = state.execution_results.get(plan.plan_id, {})
    step_verdicts = [_step_verdict(step_id, result) for step_id, result in sorted(results.items())]
    failed = [verdict for verdict in step_verdicts if verdict["status"] != "success"]
    new_questions = [
        f"Resolve failed evidence step {verdict['step_id']}: {verdict['error'] or verdict['status']}"
        for verdict in failed
    ]
    max_iterations = int(state.flags.get("max_plan_iterations", 2))
    cap_hit = plan.iteration >= max_iterations
    flags = dict(state.flags)
    if cap_hit:
        flags["plan_loop_cap_hit"] = True
    degraded = state.steward_verdict is not None and state.steward_verdict.data_status != "usable"
    advance = not failed and not cap_hit
    if degraded and failed:
        advance = False
    rationale = _advance_rationale(advance=advance, failed=failed, cap_hit=cap_hit, degraded=degraded)
    review = PlanReview(
        plan_id=plan.plan_id,
        advance=advance,
        step_verdicts=step_verdicts,
        new_questions=new_questions,
        new_plan_steps=[],
        advance_rationale=rationale,
    )
    return replace(state, flags=flags, plan_reviews=[*state.plan_reviews, review])


def _advance_rationale(*, advance: bool, failed: list[dict], cap_hit: bool, degraded: bool) -> str:
    if cap_hit:
        return "Plan loop cap reached; stop adding new evidence steps."
    if failed:
        if degraded:
            return "Evidence failed while data status is degraded."
        return "One or more evidence steps failed."
    if advance:
        return "All executed plan steps passed."
    return "Plan review did not advance."


def _step_verdict(step_id: str, result) -> dict:
    degraded_error = _degraded_success_error(result)
    if degraded_error:
        return {"step_id": step_id, "status": "degraded", "error": degraded_error}
    return {"step_id": step_id, "status": result.status, "error": result.error}


def _degraded_success_error(result) -> str | None:
    if result.status != "success":
        return None
    for output in result.outputs or []:
        if output.get("routes_tested") == 0 and output.get("routes_untestable", 0) > 0:
            return "quant sweep produced no testable routes"
    return None
