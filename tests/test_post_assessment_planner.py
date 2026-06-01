"""Tests for post_assessment_planner + the news-or-results situation branch.

PG-PLAN 2026-05-25: covers
* PlannedAction shape for plan_news_and_results / plan_compare_fundamentals
  / plan_review_setups (dedupe, capping, None on empty).
* The new `_asks_collective_news_or_results` predicate.
* End-to-end: assess_followup on "any news or results for these top gainers"
  returns a run_tool_plan with get_latest_results per symbol +
  get_event_calendar_summary, and synthesis_intent='collective_news_results'.
* Regression: "fundamental analysis for the above stocks" still routes to
  compare_stocks(aspects=['fundamental']) via the planner refactor.
"""

from __future__ import annotations

from terminal.post_assessment_planner import (
    PlannedAction,
    plan_compare_fundamentals,
    plan_news_and_results,
    plan_review_setups,
)
from terminal.situation_assessment import (
    TurnContext,
    _asks_collective_news_or_results,
    assess_followup,
)


# ---------------------------------------------------------------------------
# planner unit tests
# ---------------------------------------------------------------------------


def test_plan_news_and_results_builds_per_symbol_plus_calendar():
    plan = plan_news_and_results(
        ["modisonltd", "PREMEXPLN", "hariompipe", "modisonltd"]
    )
    assert isinstance(plan, PlannedAction)
    assert plan.synthesis_intent == "collective_news_results"
    # Symbols are uppercased + deduped while preserving order.
    assert plan.resolved_entities == ["MODISONLTD", "PREMEXPLN", "HARIOMPIPE"]
    # One get_latest_results per unique symbol, then one calendar call.
    tool_names = [name for name, _ in plan.tool_plan]
    assert tool_names == [
        "get_latest_results",
        "get_latest_results",
        "get_latest_results",
        "get_event_calendar_summary",
    ]
    assert plan.tool_plan[0][1] == {"symbol": "MODISONLTD"}
    assert plan.tool_plan[-1][1]["index"] == "NIFTY 500"
    assert plan.evidence_plan == [
        "get_latest_results",
        "get_event_calendar_summary",
    ]


def test_plan_news_and_results_caps_symbols():
    plan = plan_news_and_results(
        ["A", "B", "C", "D", "E", "F", "G"], max_symbols=3
    )
    assert plan is not None
    # 3 results + 1 calendar tool.
    assert len(plan.tool_plan) == 4
    assert plan.resolved_entities == ["A", "B", "C"]


def test_plan_news_and_results_empty_symbols_returns_none():
    assert plan_news_and_results([]) is None
    assert plan_news_and_results(["", "  ", None]) is None  # type: ignore[list-item]


def test_plan_compare_fundamentals_emits_compare_stocks():
    plan = plan_compare_fundamentals(["aaa", "BBB"])
    assert plan is not None
    assert plan.synthesis_intent == "stock_comparison"
    assert plan.tool_plan == [
        ("compare_stocks", {"symbols": ["AAA", "BBB"], "aspects": ["fundamental"]}),
    ]


def test_plan_review_setups_uses_both_aspects():
    plan = plan_review_setups(["xxx", "yyy"], direction="long")
    assert plan is not None
    assert plan.synthesis_intent == "stock_comparison"
    assert plan.tool_plan == [
        ("compare_stocks", {"symbols": ["XXX", "YYY"], "aspects": ["both"]}),
    ]
    assert "long setups" in plan.user_is_asking


# ---------------------------------------------------------------------------
# predicate
# ---------------------------------------------------------------------------


def test_asks_collective_news_or_results_matches_news_term():
    assert _asks_collective_news_or_results("any news for these top gainers")
    assert _asks_collective_news_or_results("upcoming events for the above")
    assert _asks_collective_news_or_results("any announcements for these")


def test_asks_collective_news_or_results_matches_news_plus_results_pair():
    # Bare "results" is owned by the fundamentals predicate; this returns
    # True only when "news" co-occurs.
    assert _asks_collective_news_or_results(
        "any news or results for these top gainers"
    )
    assert _asks_collective_news_or_results(
        "news and earnings for the above stocks"
    )


def test_asks_collective_news_or_results_rejects_pure_fundamentals():
    # Pure "results" / "earnings" without a news term must NOT match — it
    # belongs to the fundamentals branch.
    assert not _asks_collective_news_or_results("results for the above stocks")
    assert not _asks_collective_news_or_results(
        "fundamental analysis for the above"
    )


# ---------------------------------------------------------------------------
# end-to-end situation_assessment routing
# ---------------------------------------------------------------------------


def _gainers_context(gainers: list[str]) -> TurnContext:
    return TurnContext(
        user_input="top gainers",
        intent="top_movers",
        mode="historical",
        tools=["get_top_gainers_losers", "get_market_breadth"],
        source_label="NSE live API + DB breadth",
        result_type="top_movers",
        result_summary="Top gainers list.",
        symbols=list(gainers),
        result_items=list(gainers),
        result_groups={"gainers": list(gainers)},
    )


def test_news_or_results_followup_routes_via_planner():
    ctx = _gainers_context(["MODISONLTD", "PREMEXPLN", "HARIOMPIPE"])
    asm = assess_followup("any news or results for these top gainers", ctx)

    assert asm.applies is True
    assert asm.decision == "run_tool_plan"
    assert asm.synthesis_intent == "collective_news_results"
    tool_names = [name for name, _ in asm.tool_plan]
    # All 3 prior gainers covered + the event calendar.
    assert tool_names == [
        "get_latest_results",
        "get_latest_results",
        "get_latest_results",
        "get_event_calendar_summary",
    ]
    assert asm.resolved_entities == ["MODISONLTD", "PREMEXPLN", "HARIOMPIPE"]


def test_fundamentals_followup_still_uses_compare_stocks_via_planner():
    ctx = _gainers_context(["AAA", "BBB"])
    asm = assess_followup("fundamental analysis for the above stocks", ctx)

    assert asm.applies is True
    assert asm.decision == "run_tool_plan"
    assert asm.synthesis_intent == "stock_comparison"
    assert asm.tool_plan == [
        ("compare_stocks", {"symbols": ["AAA", "BBB"], "aspects": ["fundamental"]}),
    ]


# ---------------------------------------------------------------------------
# direct-router (first-turn) coverage — explicit ticker list query
# ---------------------------------------------------------------------------


def test_direct_multi_symbol_news_results_routes_via_planner():
    """PG-PLAN 2026-05-25: first-turn query with N>=2 explicit tickers and
    'results / corporate events' must go through plan_news_and_results,
    NOT the single-symbol stock_results branch."""
    from terminal.agent import _keyword_intent

    plan = _keyword_intent(
        "Latest results and upcoming corporate events for "
        "MODISONLTD PREMEXPLN HARIOMPIPE THACKER SAGARDEEP"
    )

    assert plan["intent"] == "collective_news_results"
    tools = [name for name, _ in plan["plan"]]
    # one get_latest_results per symbol + a single calendar summary
    assert tools.count("get_latest_results") == 5
    assert tools.count("get_event_calendar_summary") == 1
    assert tools[-1] == "get_event_calendar_summary"
    syms = [args["symbol"] for name, args in plan["plan"] if name == "get_latest_results"]
    assert syms == ["MODISONLTD", "PREMEXPLN", "HARIOMPIPE", "THACKER", "SAGARDEEP"]


def test_direct_single_symbol_results_still_uses_stock_results():
    """Single-symbol 'latest results for X' must not be hijacked by the new branch."""
    from terminal.agent import _keyword_intent

    plan = _keyword_intent("latest results for MODISONLTD")
    assert plan["intent"] == "stock_results"
    tools = [name for name, _ in plan["plan"]]
    assert "get_latest_results" in tools


def test_collective_news_results_renderer_iterates_all_symbols():
    """The renderer must surface every symbol's results pack — not just the first."""
    from terminal.agent import _synthesize_no_llm

    tool_results = [
        {
            "tool": "get_latest_results",
            "args": {"symbol": "AAA"},
            "result": {
                "symbol": "AAA",
                "status": "ok",
                "period": "Mar 2026",
                "facts": {"revenue": {"value": "100", "period": "Mar 2026"}},
                "source_trail": {},
            },
        },
        {
            "tool": "get_latest_results",
            "args": {"symbol": "BBB"},
            "result": {
                "symbol": "BBB",
                "status": "ok",
                "period": "Mar 2026",
                "facts": {"pat": {"value": "20", "period": "Mar 2026"}},
                "source_trail": {},
            },
        },
        {
            "tool": "get_event_calendar_summary",
            "args": {"index": "NIFTY 500", "days_ahead": 14},
            "result": {
                "index": "NIFTY 500",
                "days_ahead": 14,
                "total_events": 2,
                "event_counts": {"dividend": 1, "results": 1},
                "events": [
                    {"symbol": "AAA", "type": "dividend", "ex_date": "2026-06-01", "detail": "Final 5"},
                    {"symbol": "ZZZ", "type": "results", "ex_date": "2026-06-05", "detail": "Q1 board meet"},
                ],
            },
        },
    ]

    out = _synthesize_no_llm("collective_news_results", tool_results)

    # Header lists both requested symbols
    assert "AAA, BBB" in out
    # Both symbol sections present
    assert "▶ AAA — Latest Results" in out
    assert "▶ BBB — Latest Results" in out
    # Event calendar section present and the matching symbol surfaces (not ZZZ)
    assert "▶ UPCOMING CORPORATE EVENTS" in out
    assert "AAA" in out and "dividend" in out
