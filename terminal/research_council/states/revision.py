"""Revision and convergence state."""

from __future__ import annotations

from dataclasses import replace

from terminal.research_council.mode_profiles import load_mode_profile
from terminal.research_council.schemas import RevisionResult


CONFIDENCE_SHIFT_THRESHOLD = 0.05


def run(state):
    if state.flags.get("dry_run"):
        return state
    iteration = len(state.revision_history)
    unresolved_blocks = _unresolved_blocks(state)
    confidence_shift = float(state.flags.get("max_confidence_shift") or 0)
    new_hypothesis = state.flags.get("new_testable_hypothesis")
    cap = int(state.flags.get("revision_cap", load_mode_profile(state.mode).revision_cap))
    cap_hit = iteration >= cap
    converged = not unresolved_blocks and confidence_shift <= CONFIDENCE_SHIFT_THRESHOLD and not new_hypothesis
    notes = []
    flags = dict(state.flags)
    if cap_hit:
        flags["revision_cap_hit"] = True
        if unresolved_blocks:
            flags["requires_manual_review"] = True
            flags["decision_pressure"] = "downgrade"
            notes.append("revision cap reached with unresolved blocks")
        else:
            converged = True
            notes.append("cap reached without unresolved blocks")
    if new_hypothesis:
        notes.append(f"new hypothesis requires testing: {new_hypothesis}")
    if confidence_shift > CONFIDENCE_SHIFT_THRESHOLD:
        notes.append(f"confidence shift {confidence_shift:.2f} exceeds threshold")
    flags["converged"] = converged
    result = RevisionResult(
        iteration=iteration,
        converged=converged,
        notes=notes,
        unresolved_blocks=unresolved_blocks,
    )
    return replace(state, flags=flags, revision_history=[*state.revision_history, result])


def _unresolved_blocks(state) -> list[str]:
    resolved = set(state.flags.get("resolved_critic_blocks") or [])
    unresolved = []
    for review_group in state.critic_reviews:
        for review in review_group:
            for finding in review.findings:
                if finding.severity == "block" and finding.finding_id not in resolved:
                    unresolved.append(finding.finding_id)
    return unresolved
