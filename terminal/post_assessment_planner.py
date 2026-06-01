"""First-class planner invoked AFTER situation_assessment.

PG-PLAN 2026-05-25: Decouples "what is the user asking for" from
"which tools should run + how do we synthesize". Each `plan_*` function
maps a semantic follow-up intent + entities + previous_context into a
``PlannedAction`` containing:

* ``tool_plan``        — concrete ``(tool_name, args)`` tuples to execute.
* ``synthesis_intent`` — label the universal claim-gate uses to pick
                         required-tools for the rendered answer.
* ``evidence_plan``    — short list of tool names for the assessment
                         block / observability.
* ``narrative``        — short bullets shown in the assessment block.
* ``user_is_asking``   — one-line restatement of the user's request.

Before this module, every situation_assessment rule hardcoded a
``tool_plan=[...]`` inline and relied on the agent's synthesis dispatcher
to guess a synthesis_intent from the first tool. Adding a new follow-up
shape (e.g. "news or results for these top gainers") required touching
multiple files. With the planner:

* New shapes only need a new ``plan_*`` function here + one branch in
  ``situation_assessment.py`` that calls it.
* The required-tool contract is co-located with the plan that produces
  the tools (single source of truth).
* The agent's post-assessment dispatch stays a thin executor.

Tag: PG-PLAN.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


@dataclass(frozen=True)
class PlannedAction:
    """A concrete plan handed from the planner to the executor."""

    synthesis_intent: str
    evidence_plan: list[str] = field(default_factory=list)
    tool_plan: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    narrative: list[str] = field(default_factory=list)
    user_is_asking: str = ""
    resolved_entities: list[str] = field(default_factory=list)


def _dedupe_symbols(symbols: Iterable[str], limit: int) -> list[str]:
    """Uppercase + dedupe while preserving order, then cap at ``limit``."""
    seen: dict[str, None] = {}
    for s in symbols:
        if not s:
            continue
        sym = str(s).strip().upper()
        if not sym or sym in seen:
            continue
        seen[sym] = None
    return list(seen)[:limit]


# ---------------------------------------------------------------------------
# Planners — each builds a PlannedAction from semantic inputs.
# ---------------------------------------------------------------------------


def plan_news_and_results(
    symbols: Iterable[str],
    *,
    max_symbols: int = 5,
    index_hint: str = "NIFTY 500",
    days_ahead: int = 14,
) -> PlannedAction | None:
    """Build a plan for "news / earnings / results for these symbols".

    Concrete tools:
      * ``get_latest_results(symbol=S)`` for each of up to ``max_symbols``.
      * ``get_event_calendar_summary(index=index_hint, days_ahead=...)``
        — surfaces upcoming dividends / splits / bonuses / board meetings
        / results for the chosen index; the renderer filters to the
        requested symbols.

    Returns ``None`` when no usable symbols were supplied so callers can
    fall back to a clarification instead of running an empty plan.
    """
    syms = _dedupe_symbols(symbols, max_symbols)
    if not syms:
        return None
    tool_plan: list[tuple[str, dict[str, Any]]] = [
        ("get_latest_results", {"symbol": s}) for s in syms
    ]
    tool_plan.append(
        (
            "get_event_calendar_summary",
            {"index": index_hint, "days_ahead": days_ahead},
        )
    )
    return PlannedAction(
        synthesis_intent="collective_news_results",
        evidence_plan=["get_latest_results", "get_event_calendar_summary"],
        tool_plan=tool_plan,
        narrative=[
            f"Bind the reply to the prior result list ({len(syms)} symbols).",
            "Fetch latest reported results per symbol.",
            f"Fetch the {index_hint} event calendar ({days_ahead}d ahead) "
            "for upcoming dividends, splits, bonuses, board meetings, and "
            "results; the renderer filters to the requested symbols.",
            "Do not resolve reference phrases like 'these top gainers' "
            "as a new ticker.",
        ],
        user_is_asking=(
            f"Latest results and upcoming corporate events for "
            f"{', '.join(syms)}."
        ),
        resolved_entities=syms,
    )


def plan_compare_fundamentals(
    symbols: Iterable[str],
    *,
    max_symbols: int = 5,
) -> PlannedAction | None:
    """Build a plan for "fundamental analysis for these symbols"."""
    syms = _dedupe_symbols(symbols, max_symbols)
    if not syms:
        return None
    return PlannedAction(
        synthesis_intent="stock_comparison",
        evidence_plan=["compare_stocks"],
        tool_plan=[
            ("compare_stocks", {"symbols": syms, "aspects": ["fundamental"]}),
        ],
        narrative=[
            f"Bind the reply to the prior result list ({len(syms)} symbols).",
            "Run compare_stocks on those symbols across fundamental ratios "
            "(P/E, P/B, ROE, ROCE, debt/equity).",
            "Do not resolve the phrase 'the above stocks' as a new ticker.",
        ],
        user_is_asking=(
            f"Fundamental analysis for the prior result list "
            f"({', '.join(syms)})."
        ),
        resolved_entities=syms,
    )


def plan_review_setups(
    symbols: Iterable[str],
    direction: str,
    *,
    max_symbols: int = 10,
) -> PlannedAction | None:
    """Build a plan for "review the long / short / all setups"."""
    syms = _dedupe_symbols(symbols, max_symbols)
    if not syms:
        return None
    label = (
        "long setups"
        if direction == "long"
        else "short setups"
        if direction == "short"
        else "setups"
    )
    return PlannedAction(
        synthesis_intent="stock_comparison",
        evidence_plan=["compare_stocks"],
        tool_plan=[
            ("compare_stocks", {"symbols": syms, "aspects": ["both"]}),
        ],
        narrative=[
            f"Bind the reply to the prior scan's {label} ({len(syms)} symbols).",
            "Run compare_stocks on those symbols across technical + "
            "fundamental aspects.",
            "Do not resolve a new symbol from the reply text; the binding "
            "is authoritative.",
        ],
        user_is_asking=f"Deep-dive review of the prior intraday scan's {label}.",
        resolved_entities=syms,
    )
