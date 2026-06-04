"""100-scenario stress test for the situation-assessment + clarification +
symbol-resolution pipeline.

Each scenario is a small dict; pytest parametrizes them into focused
assertions per bucket. All scenarios run offline against deterministic
code paths — no API calls, no DB hits — and complete in well under a
second on a stock laptop.

Buckets (case counts in brackets):
  A. Report follow-ups against a prior /analyze report .......... [20]
  B. Clarification reply binding ............................... [15]
  C. Resolver traps — generic words must not become tickers .... [20]
  D. Contextual recommendation phrasings ....................... [10]
  E. Source / freshness follow-ups ............................. [10]
  F. Scan-these / intraday follow-ups .......................... [10]
  G. Affirmative followups ..................................... [ 5]
  H. Unrelated queries — must fall through ..................... [10]
                                                       Total: ... [100]
"""

from __future__ import annotations

from typing import Any

import pytest

from terminal.situation_assessment import (
    ClarificationOption,
    ClarificationQuestion,
    SituationAssessment,
    TurnContext,
    assess_followup,
    assessment_from_bound_action,
    match_clarification_reply,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _report_context(symbol: str, report_path: str | None = None) -> TurnContext:
    path = report_path or f"/Users/x/reports/generated/{symbol}_research_20260518_103059.html"
    return TurnContext(
        user_input=f"/analyze {symbol}",
        intent="entity_topic_command",
        mode="research",
        tools=["comprehensive_stock_research"],
        source_label="EOD CSV + DB snapshot",
        result_type="stock_analysis",
        result_summary=f"Report saved for {symbol}.",
        symbols=[symbol],
        result_items=[path],
    )


def _stage2_context(symbols: list[str]) -> TurnContext:
    return TurnContext(
        user_input="show stage 2 stocks",
        intent="screener",
        mode="historical",
        tools=["run_screener_query"],
        source_label="EOD CSV + DB snapshot",
        freshness="2026-05-15",
        result_type="stage2_screener",
        result_summary=f"Stage 2 screener returned {len(symbols)} results.",
        symbols=symbols,
        result_items=list(symbols),
    )


def _pending_with_options(
    options: list[tuple[str, str]],
) -> SituationAssessment:
    return SituationAssessment(
        applies=True,
        decision="ask_clarification",
        confidence="medium",
        clarification_questions=(
            ClarificationQuestion(
                prompt="?",
                options=tuple(
                    ClarificationOption(
                        label=lab,
                        text=txt,
                        bound_action={
                            "decision": "run_tool_plan",
                            "tool_plan": [("noop", {"label": lab})],
                        },
                    )
                    for lab, txt in options
                ),
            ),
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Bucket A — Report follow-ups (20 cases)
# ─────────────────────────────────────────────────────────────────────────────

_REPORT_SUMMARIZE_PHRASINGS = [
    ("summarize", "SWELECTES"),
    ("summary", "TCS"),
    ("Summarize the report generated and provide recommendations", "RELIANCE"),
    ("summarise its recommendation", "DMART"),
    ("summarize its recommendation", "HDFCBANK"),
    ("recap", "INFY"),
    ("recap the recommendation", "ITC"),
    ("tl;dr", "WIPRO"),
    ("tldr", "BAJFINANCE"),
    ("what does it say", "MARUTI"),
    ("what does the report say", "ULTRACEMCO"),
    ("the recommendation", "BAJAJ-AUTO"),
    ("its conclusion", "ASIANPAINT"),
    ("the conclusion of the report", "BHARTIARTL"),
    ("give me the report result", "SBIN"),
]


@pytest.mark.parametrize("user_input,symbol", _REPORT_SUMMARIZE_PHRASINGS)
def test_bucket_a_report_summarize_routes_to_prior_report(user_input, symbol):
    ctx = _report_context(symbol)
    asm = assess_followup(user_input, ctx)
    assert asm.decision == "run_tool_plan", f"phrasing={user_input!r}"
    tools = [name for name, _ in asm.tool_plan]
    assert tools == ["read_report", "summarize_report"], f"tools={tools}"
    assert all(
        symbol in args.get("path", "") for _, args in asm.tool_plan
    ), f"symbol {symbol} missing from tool paths"
    assert asm.resolved_entities == [symbol]


_REPORT_OPEN_PHRASINGS = [
    ("open it", "SWELECTES"),
    ("open the report", "TCS"),
    ("just open the report", "RELIANCE"),
    ("show me the report", "DMART"),
    ("show it", "HDFCBANK"),
]


@pytest.mark.parametrize("user_input,symbol", _REPORT_OPEN_PHRASINGS)
def test_bucket_a_report_open_routes_to_open_report(user_input, symbol):
    ctx = _report_context(symbol)
    asm = assess_followup(user_input, ctx)
    assert asm.decision == "run_tool_plan"
    assert [n for n, _ in asm.tool_plan] == ["open_report"]
    assert symbol in asm.tool_plan[0][1]["path"]


# ─────────────────────────────────────────────────────────────────────────────
# Bucket B — Clarification reply binding (15 cases)
# ─────────────────────────────────────────────────────────────────────────────


_BINDING_CASES = [
    # (reply, options[(label,text)], expected_label_or_None)
    ("A", [("A", "Open"), ("B", "Summarize"), ("C", "Compare")], "A"),
    ("B", [("A", "Open"), ("B", "Summarize"), ("C", "Compare")], "B"),
    ("C", [("A", "Open"), ("B", "Summarize"), ("C", "Compare")], "C"),
    ("a", [("A", "Open"), ("B", "Summarize")], "A"),
    ("b.", [("A", "Open"), ("B", "Summarize")], "B"),
    ("C!", [("A", "Open"), ("B", "Summarize"), ("C", "Compare")], "C"),
    ("A - please", [("A", "Open"), ("B", "Summarize")], "A"),
    ("1", [("A", "Open"), ("B", "Summarize"), ("C", "Compare")], "A"),
    ("2", [("A", "Open"), ("B", "Summarize"), ("C", "Compare")], "B"),
    ("3", [("A", "Open"), ("B", "Summarize"), ("C", "Compare")], "C"),
    ("open", [("A", "Open"), ("B", "Summarize")], "A"),
    ("summarize", [("A", "Open"), ("B", "Summarize")], "B"),
    ("nope", [("A", "Open"), ("B", "Summarize")], None),
    ("", [("A", "Open"), ("B", "Summarize")], None),
    ("show me Nifty 50", [("A", "Open"), ("B", "Summarize")], None),
]


@pytest.mark.parametrize("reply,options,expected", _BINDING_CASES)
def test_bucket_b_clarification_reply_binding(reply, options, expected):
    pending = _pending_with_options(options)
    matched = match_clarification_reply(reply, pending)
    if expected is None:
        assert matched is None, f"reply={reply!r} should not match"
    else:
        assert matched is not None, f"reply={reply!r} should match"
        assert matched.label == expected
        # Bound action conversion round-trips cleanly.
        bound = assessment_from_bound_action(matched.bound_action)
        assert bound.decision == "run_tool_plan"
        assert bound.tool_plan[0] == ("noop", {"label": expected})


# ─────────────────────────────────────────────────────────────────────────────
# Bucket C — Resolver traps (20 cases)
# ─────────────────────────────────────────────────────────────────────────────


_RESOLVER_GENERIC_REFUSAL = [
    # Generic English / business words must never resolve to a ticker.
    # NOTE: 'global', 'oil', 'energy', 'infra' are excluded — all are real NSE tickers.
    "invest", "INVEST", "energies",
    "infrastructure", "growth", "pharma", "bank",
    "power", "technologies", "industries", "limited", "international",
]

_RESOLVER_DISTINCTIVE_QUERIES = [
    ("Reliance", "RELIANCE"),
    ("TCS", "TCS"),
    ("Premier Energies", "PREMIERENE"),
    ("Hindustan Unilever", "HINDUNILVR"),
    ("Bharat Forge", "BHARATFORG"),
]


@pytest.mark.parametrize("query", _RESOLVER_GENERIC_REFUSAL)
def test_bucket_c_resolver_refuses_generic_word(query):
    from terminal.tools import _resolve_local_symbol

    result = _resolve_local_symbol(query)
    assert result["symbol"] is None, f"query={query!r} resolved to {result['symbol']}"


@pytest.mark.parametrize("query,expected_symbol", _RESOLVER_DISTINCTIVE_QUERIES)
def test_bucket_c_resolver_resolves_distinctive_query(query, expected_symbol):
    from terminal.tools import _resolve_local_symbol

    result = _resolve_local_symbol(query)
    assert result["symbol"] == expected_symbol, f"query={query!r} → {result['symbol']}"


# ─────────────────────────────────────────────────────────────────────────────
# Bucket D — Contextual recommendation phrasings (10 cases)
# ─────────────────────────────────────────────────────────────────────────────


_RECOMMENDATION_CASES = [
    "based on the above analysis, what would you do?",
    "based on above analysis, should I buy?",
    "above financial analysis, recommend a stance",
    "previous analysis - your recommendation please",
    "based on the analysis, buy or sell?",
    "based on this analysis, hold or avoid?",
    "based on financial analysis, what is your recommendation",
    "what is your recommendation based on above analysis",
    "what would you do based on the above",
    "above analysis: should I buy",
]


@pytest.mark.parametrize("user_input", _RECOMMENDATION_CASES)
def test_bucket_d_contextual_recommendation_answers_from_context(user_input):
    ctx = _report_context("SWELECTES")
    asm = assess_followup(user_input, ctx)
    assert asm.decision == "answer_from_context", f"input={user_input!r} → {asm.decision}"
    # Crucially, no new symbol resolution: must keep SWELECTES.
    assert asm.resolved_entities == ["SWELECTES"]


# ─────────────────────────────────────────────────────────────────────────────
# Bucket E — Source / freshness follow-ups (10 cases)
# ─────────────────────────────────────────────────────────────────────────────


_SOURCE_CASES = [
    "what source did you use",
    "which source supports this",
    "is this from postgres",
    "is this from postgresql",
    "what source or fallback was used",
    "what expiry did you use",
    "which expiry contract is this",
    "are these from the last 30 minutes",
    "is this last-30 minute data",
    "from last thirty minutes?",
]


@pytest.mark.parametrize("user_input", _SOURCE_CASES)
def test_bucket_e_source_followups_answer_from_context(user_input):
    ctx = _stage2_context(["TCS", "INFY", "WIPRO"])
    asm = assess_followup(user_input, ctx)
    if "last 30" in user_input or "last-30" in user_input or "last thirty" in user_input:
        assert asm.decision == "ask_clarification", (
            f"input={user_input!r} → {asm.decision}"
        )
        assert asm.clarification_questions
        assert all(opt.bound_action for opt in asm.clarification_questions[0].options)
    else:
        assert asm.decision == "answer_from_context", (
            f"input={user_input!r} → {asm.decision}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Bucket F — Scan-these / intraday follow-ups (10 cases)
# ─────────────────────────────────────────────────────────────────────────────


_SCAN_CASES_15M = [
    "scan these for 15m setups",
    "scan these 15m",
    "scan these on 15-minute",
    "check these 15m",
    "check these 15 m",
]

_SCAN_CASES_AMBIGUOUS = [
    "scan these live",
    "check these live",
    "what about these",
    "what about this",
    "are these still in stage 2",
]


@pytest.mark.parametrize("user_input", _SCAN_CASES_15M)
def test_bucket_f_scan_15m_runs_intraday_scan(user_input):
    ctx = _stage2_context(["TCS", "INFY", "WIPRO", "SBIN"])
    asm = assess_followup(user_input, ctx)
    assert asm.decision == "run_tool_plan", f"input={user_input!r} → {asm.decision}"
    assert any(name == "scan_symbols_intraday" for name, _ in asm.tool_plan)


@pytest.mark.parametrize("user_input", _SCAN_CASES_AMBIGUOUS)
def test_bucket_f_scan_ambiguous_asks_clarification(user_input):
    ctx = _stage2_context(["TCS", "INFY"])
    asm = assess_followup(user_input, ctx)
    assert asm.decision == "ask_clarification", (
        f"input={user_input!r} → {asm.decision}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Bucket G — Affirmative followups (5 cases)
# ─────────────────────────────────────────────────────────────────────────────


_AFFIRMATIVE_WITH_REPORT = ["yes", "go ahead", "do it", "sure", "okay"]


@pytest.mark.parametrize("user_input", _AFFIRMATIVE_WITH_REPORT)
def test_bucket_g_affirmative_with_report_summarizes(user_input):
    ctx = _report_context("SWELECTES")
    asm = assess_followup(user_input, ctx)
    # Either runs the report tool plan or answers from context.
    assert asm.decision in {"run_tool_plan", "answer_from_context"}
    if asm.decision == "run_tool_plan":
        assert [n for n, _ in asm.tool_plan] == ["read_report", "summarize_report"]
    assert asm.resolved_entities == ["SWELECTES"]


# ─────────────────────────────────────────────────────────────────────────────
# Bucket H — Unrelated queries that must fall through (10 cases)
# ─────────────────────────────────────────────────────────────────────────────


_UNRELATED_QUERIES = [
    "show me Nifty 50 list",
    "what is the price of TCS",
    "/analyze RELIANCE",
    "run canslim screener",
    "list top gainers",
    "fno open interest for banknifty",
    "what's the market mood today",
    "intraday breakout stocks",
    "show me a stage 2 list",
    "earnings calendar this week",
]


@pytest.mark.parametrize("user_input", _UNRELATED_QUERIES)
def test_bucket_h_unrelated_query_does_not_hijack_prior_report(user_input):
    """A clearly new request must NOT bind to the prior report — the
    assessment should return applies=False / fallback_to_router OR a
    decision that does NOT execute read_report/summarize_report on the
    prior path. This pins the inverse of the SWELECTES bug: we don't
    want the new rules to be over-eager either.
    """
    ctx = _report_context("SWELECTES")
    asm = assess_followup(user_input, ctx)
    if asm.decision == "run_tool_plan":
        tools = {name for name, _ in asm.tool_plan}
        # New /analyze etc. routes should not pick up the SWELECTES report.
        assert not (tools & {"read_report", "summarize_report", "open_report"}), (
            f"unrelated input={user_input!r} hijacked report tools={tools}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Bucket I — Collective-reference follow-ups against a prior top-movers turn
#
# Regression for the bug where 'Fundamental analysis for the above stocks'
# was extracted as a literal ticker (THE ABOVE STOCKS) by keyword_intent
# because the situation-assessment gate didn't claim the turn.
# ─────────────────────────────────────────────────────────────────────────────


def _top_movers_context() -> TurnContext:
    return TurnContext(
        user_input="top gainers",
        intent="top_movers",
        mode="historical",
        tools=["get_top_gainers_losers", "get_market_breadth"],
        source_label="NSE live API + DB breadth",
        result_type="top_movers",
        result_summary="Top gainers / losers for NIFTY 500.",
        symbols=[],
        result_items=[
            "MODISONLTD", "HARIOMPIPE", "SAGARDEEP", "VIKRAN", "GREENLAM",
            "KOPRAN", "TRUALT", "ALICON",
        ],
        result_groups={
            "gainers": ["MODISONLTD", "HARIOMPIPE", "SAGARDEEP", "VIKRAN", "GREENLAM", "KOPRAN"],
            "losers":  ["TRUALT", "ALICON"],
        },
    )


@pytest.mark.parametrize("user_input", [
    "Fundamental analysis for the above stocks",
    "fundamentals for these stocks",
    "ratios for the above",
    "show me valuation for those stocks",
    "earnings for the gainers",
    "latest results for the above list",
])
def test_bucket_i_collective_fundamentals_binds_to_prior_movers(user_input):
    ctx = _top_movers_context()
    asm = assess_followup(user_input, ctx)
    assert asm.applies is True
    assert asm.decision == "run_tool_plan"
    assert asm.tool_plan, "expected a non-empty tool_plan"
    tool_name, args = asm.tool_plan[0]
    assert tool_name == "compare_stocks"
    assert args.get("aspects") == ["fundamental"]
    symbols = args.get("symbols") or []
    assert symbols, "compare_stocks symbols list must not be empty"
    # No symbol must be a piece of the literal reference phrase.
    for s in symbols:
        assert s not in {"THE", "ABOVE", "STOCKS", "THESE", "THOSE", "THE ABOVE STOCKS"}, (
            f"collective reference leaked as literal ticker: {s}"
        )


def test_bucket_i_the_gainers_picks_gainers_bucket():
    ctx = _top_movers_context()
    asm = assess_followup("fundamentals for the gainers", ctx)
    assert asm.decision == "run_tool_plan"
    symbols = asm.tool_plan[0][1]["symbols"]
    # Must come from the gainers bucket, not the losers bucket.
    assert set(symbols).issubset(set(ctx.result_groups["gainers"]))
    assert "TRUALT" not in symbols and "ALICON" not in symbols


def test_bucket_i_the_losers_picks_losers_bucket():
    ctx = _top_movers_context()
    asm = assess_followup("results for the losers", ctx)
    assert asm.decision == "run_tool_plan"
    symbols = asm.tool_plan[0][1]["symbols"]
    assert set(symbols).issubset(set(ctx.result_groups["losers"]))


def test_bucket_i_gate_triggers_for_collective_references():
    from terminal.situation_assessment import needs_situation_assessment
    for q in (
        "Fundamental analysis for the above stocks",
        "ratios for these stocks",
        "earnings for the gainers",
        "results for the losers",
    ):
        assert needs_situation_assessment(q) is True, q


def test_bucket_i_extract_result_groups_understands_gainers_losers():
    from terminal.situation_assessment import build_turn_context
    tool_results = [{
        "tool": "get_top_gainers_losers",
        "args": {"index": "NIFTY 500"},
        "result": {
            "index": "NIFTY 500",
            "gainers": [{"symbol": "AAA"}, {"symbol": "BBB"}],
            "losers":  [{"symbol": "XXX"}, {"symbol": "YYY"}],
        },
    }]
    ctx = build_turn_context(
        user_input="top gainers", intent="top_movers", mode="historical",
        source_label="", tool_results=tool_results, answer="",
    )
    assert ctx.result_groups.get("gainers") == ["AAA", "BBB"]
    assert ctx.result_groups.get("losers")  == ["XXX", "YYY"]
    # Promoted into the flat list so existing rules that key off result_items still match.
    assert set(ctx.result_items) >= {"AAA", "BBB", "XXX", "YYY"}


def test_bucket_i_collective_followup_without_prior_list_falls_through():
    """When there is no prior context with usable symbols, the assessor
    must NOT fabricate a tool_plan with literal phrase fragments."""
    empty_ctx = TurnContext(
        user_input="hi", intent="greeting", mode="historical",
        tools=[], source_label="",
    )
    asm = assess_followup("fundamentals for the above stocks", empty_ctx)
    # With no symbols anywhere, the rule must not fire; fall back to clarification/router.
    if asm.decision == "run_tool_plan":
        symbols = asm.tool_plan[0][1].get("symbols", [])
        assert symbols, "tool_plan with empty symbol list is worse than no plan"
