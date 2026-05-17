"""Tree-of-thought hypothesis branching for market reads."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Hypothesis:
    label: str
    thesis: str
    required_evidence: tuple[str, ...]


def build_hypotheses(intent: str) -> list[Hypothesis]:
    if intent == "market_assessment":
        return [
            Hypothesis("risk_on", "Breadth and leadership support risk-taking.", ("live-tape", "db-breadth", "movers")),
            Hypothesis("risk_off", "Index weakness and poor breadth favor defense.", ("live-tape", "db-breadth")),
            Hypothesis("selective", "Mixed tape; only leader pockets deserve attention.", ("live-tape", "movers")),
        ]
    if intent == "symbol_assessment":
        return [
            Hypothesis("bullish_setup", "Trend, RS, and sector context are aligned.", ("snapshot", "technicals", "sector")),
            Hypothesis("avoid_setup", "Evidence is weak, stale, or contradictory.", ("snapshot", "technicals")),
            Hypothesis("watchlist_only", "Setup needs a trigger or data confirmation.", ("snapshot", "sector")),
        ]
    return [Hypothesis("needs_clarification", "The request needs more context before analysis.", tuple())]
