"""Synthesize final Research Council decision."""

from __future__ import annotations

from dataclasses import replace

from terminal.research_council.agents.hedge_fund_owner import DEFAULT_CHAIR


def run(state):
    if state.flags.get("dry_run"):
        return state
    decision = DEFAULT_CHAIR.synthesize_decision(state)
    return replace(state, decision=decision)
