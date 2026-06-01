"""Persist final Research Council artifacts."""

from __future__ import annotations

from terminal.research_council.persistence import save_council_plans, save_council_run_metadata, save_evidence_pack


def run(state):
    if state.flags.get("dry_run"):
        return state
    if state.evidence_pack:
        save_evidence_pack(state.evidence_pack)
    if state.plans:
        save_council_plans(state.plans, run_id=state.run_id)
    save_council_run_metadata(state)
    return state
