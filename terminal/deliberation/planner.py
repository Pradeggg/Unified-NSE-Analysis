"""Plan-of-thought planner for executable market research tasks."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any


@dataclass(frozen=True)
class PlanTask:
    id: str
    question: str
    tool: str | None = None
    args: dict[str, Any] = field(default_factory=dict)
    fallback: str = ""
    recovery_plan: str = ""


@dataclass(frozen=True)
class DeliberationPlan:
    query: str
    intent: str
    tasks: list[PlanTask]

    def executable(self) -> list[tuple[str, dict[str, Any]]]:
        return [(task.tool, dict(task.args)) for task in self.tasks if task.tool]


def _symbol_from_query(query: str) -> str | None:
    placeholders = {"SYMBOL", "TICKER", "STOCK", "COMPANY", "NAME", "NSE_SYMBOL"}
    skip = placeholders | {"ASSESS", "ANALYZE", "ANALYSE", "SETUP", "TECHNICAL", "MARKET"}
    for token in re.findall(r"\b[A-Z][A-Z0-9&-]{1,12}\b", query or ""):
        if token.upper() not in skip:
            return token.upper()
    return None


def build_plan(query: str, *, mode: str = "historical") -> DeliberationPlan:
    """Convert a user query into deterministic executable tasks.

    The planner intentionally emits explicit fallback/code-recovery notes for
    missing tools so downstream renderers can show what would be needed instead
    of fabricating conclusions.
    """
    q = (query or "").strip()
    ql = q.lower()
    if any(token in q.upper().split() for token in {"SYMBOL", "TICKER", "NSE_SYMBOL"}):
        return DeliberationPlan(
            query=q,
            intent="placeholder_symbol_request",
            tasks=[
                PlanTask(
                    "collect-real-symbol",
                    "Ask for a real NSE symbol before running market tools.",
                    recovery_plan="Do not execute resolve_symbol on placeholders; prompt for a concrete ticker like RELIANCE or TCS.",
                )
            ],
        )

    if any(term in ql for term in ("market", "breadth", "nifty", "gainers", "losers")):
        tasks = [
            PlanTask("live-tape", "Fetch live index tape and breadth.", "get_live_market_overview"),
            PlanTask("db-breadth", "Fetch DB universe breadth and stage distribution.", "get_market_breadth"),
            PlanTask(
                "movers",
                "Fetch top stock gainers and losers.",
                "get_top_gainers_losers",
                {"index": "NIFTY 500", "top_n": 8, "direction": "both"},
            ),
        ]
        return DeliberationPlan(q, "market_assessment", tasks)

    symbol = _symbol_from_query(q)
    if symbol:
        return DeliberationPlan(
            q,
            "symbol_assessment",
            [
                PlanTask("resolve", "Resolve company name or ticker.", "resolve_symbol", {"query": symbol}),
                PlanTask("snapshot", "Fetch latest symbol snapshot.", "get_symbol_snapshot", {"symbol": symbol}),
                PlanTask("technicals", "Fetch technical setup.", "get_technical_setup", {"symbol": symbol}),
                PlanTask("sector", "Fetch sector context.", "get_sector_context", {"sector_or_symbol": symbol}),
            ],
        )

    return DeliberationPlan(
        q,
        "unknown",
        [
            PlanTask(
                "clarify",
                "Clarify the entity, market scope, and timeframe before executing tools.",
                recovery_plan="Ask for a symbol, sector, index, or timeframe.",
            )
        ],
    )
