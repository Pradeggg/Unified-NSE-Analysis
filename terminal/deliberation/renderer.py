"""Persona-specific final answer rendering."""

from __future__ import annotations

from .evaluator import EvidenceScore
from .hypothesis import Hypothesis
from .planner import DeliberationPlan


def render_final_answer(
    plan: DeliberationPlan,
    hypotheses: list[Hypothesis],
    evidence: EvidenceScore,
    *,
    persona: str = "agent_adda",
) -> str:
    lines = [f"━━━ Deliberation Plan: {plan.intent} ━━━"]
    for task in plan.tasks:
        tool = task.tool or "manual/clarify"
        lines.append(f"- {task.id}: {tool} — {task.question}")
    if hypotheses:
        lines.append("\n▶ HYPOTHESES")
        for hyp in hypotheses:
            lines.append(f"- {hyp.label}: {hyp.thesis}")
    lines.append("\n▶ EVIDENCE SCORE")
    lines.append(f"- usable={evidence.usable} missing={evidence.missing} freshness={evidence.freshness}")
    if evidence.errors:
        lines.append("\n▶ MISSING EVIDENCE")
        lines.extend(f"- {err}" for err in evidence.errors)
    if persona == "concise":
        return "\n".join(lines[:8])
    return "\n".join(lines)
