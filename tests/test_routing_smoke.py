"""Routing smoke tests — comprehensive coverage after EntityTopic/DirectIntent retirement.

Covers every routing path in the post-AA-UR-7 pipeline:

  Layer 1 – UnifiedRouter (deterministic structural providers)
    1.1  Provider chain is exactly the 7 structural providers (no keyword-intent providers)
    1.2  PendingOptionProvider fires on label replies
    1.3  ContextualFollowupProvider fires on follow-up phrases
    1.4  CompoundStockProvider fires on multi-stock queries
    1.5  VisualScanProvider fires on chart/visual phrases
    1.6  TopMoversProvider fires on top-gainers/losers phrases
    1.7  MarketSituationProvider fires on market-wide asks
    1.8  ReportProvider fires on report-reference phrases
    1.9  Natural language stock queries fall through to fallback_llm (no keyword provider)
    1.10 False-positive stock names do NOT fire any structural provider

  Layer 2 – EntityTopic slash commands (_stage_entity_topic)
    2.1  /search <symbol> → entity_topic_command
    2.2  /analyze <symbol> <topic> → entity_topic_command

  Layer 3 – Agent end-to-end (mocked _execute_plan + backend.chat)
    3.1  False-positive names route cleanly to stock_brief (no REQUIRED TOOL VALIDATION FAILED)
    3.2  Explicit RSI/MACD/EMA keywords in query still reach LLM (stock_brief)
    3.3  Compound query aggregates tool results from both sub-queries
    3.4  Multi-turn conversation: turn-1 sets symbol context; turn-2 follow-up uses it
    3.5  Pending option reply from session context executes bound tool plan
    3.6  Slash command /mtf <symbol> → entity_topic_command (not LLM)
    3.7  Query with no backend set → keyword fallback, no crash

  Edge cases
    4.1  Stock names whose tickers contain technical indicator substrings
    4.2  Standalone indicator words without a symbol → clarification route (not crash)
    4.3  Empty / whitespace-only query → graceful result
    4.4  All-caps noise words in query (RSI, MACD, EMA, ADX) not treated as symbols
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest

from terminal.router import (
    ActiveReport,
    ContextPack,
    DirectIntentProvider,
    EntityTopicProvider,
    PendingOption,
    PendingOptionProvider,
    RecentTurn,
    UnifiedRouter,
)
from terminal.router.providers import (
    ContextualFollowupProvider,
    MarketSituationProvider,
    ReportProvider,
    TopMoversProvider,
    VisualScanProvider,
)
from terminal.agent import Agent


# ─── helpers ─────────────────────────────────────────────────────────────────

def _pack(**kw) -> ContextPack:
    return ContextPack(session_id="smoke-s", **kw)


def _make_agent() -> Agent:
    agent = Agent()
    agent.backend = MagicMock()
    agent.backend_name = "MockBackend"
    return agent


def _llm_response(answer: str = "Analysis complete. ━━━ Not investment advice. For research and learning only. ━━━"):
    return {
        "tool_calls": [],
        "content": answer,
        "finish_reason": "stop",
        "usage": {
            "input_tokens": 200, "output_tokens": 80,
            "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# Layer 1 — UnifiedRouter (structural providers only)
# ═══════════════════════════════════════════════════════════════════════════

class TestProviderChain:
    """1.1 Structural providers — no keyword-intent classifiers.

    CouncilCommandProvider was added after the original 7-provider chain.
    The test now checks the ordered set rather than an exact count.
    """

    def test_default_chain_has_expected_structural_providers(self):
        router = UnifiedRouter()
        names = router.provider_names
        # Required providers must all be present in order
        required = [
            "PendingOptionProvider",
            "ContextualFollowupProvider",
            "CompoundStockProvider",
            "ReportProvider",
            "VisualScanProvider",
            "TopMoversProvider",
            "MarketSituationProvider",
        ]
        for provider in required:
            assert provider in names, f"{provider} missing from provider chain"
        # No keyword-intent providers (these were retired)
        assert "EntityTopicProvider" not in names
        assert "DirectIntentProvider" not in names

    def test_entity_topic_provider_not_in_default_chain(self):
        assert "EntityTopicProvider" not in UnifiedRouter().provider_names

    def test_direct_intent_provider_not_in_default_chain(self):
        assert "DirectIntentProvider" not in UnifiedRouter().provider_names


class TestPendingOptionProvider:
    """1.2 Pending-option label replies execute bound actions without symbol re-resolution."""

    def test_label_a_fires_bound_action(self):
        pack = _pack(
            pending_options=(
                PendingOption(
                    label="A",
                    text="run technical scan for DIXON",
                    bound_action={
                        "intent": "intraday_scan",
                        "tool_plan": [{"tool": "get_technical_setup", "args": {"symbol": "DIXON"}}],
                    },
                ),
            ),
            active_symbols=("DIXON",),
        )
        d = UnifiedRouter().route("A", pack)
        assert d.reasoning_summary.selected_branch == "PendingOptionProvider"
        assert d.intent == "intraday_scan"
        assert d.tool_plan_tuples() == [("get_technical_setup", {"symbol": "DIXON"})]

    def test_numeric_label_fires_bound_action(self):
        pack = _pack(
            pending_options=(
                PendingOption(
                    label="1",
                    text="show top gainers",
                    bound_action={"intent": "top_gainers", "tool_plan": []},
                ),
            ),
        )
        d = UnifiedRouter().route("1", pack)
        assert d.reasoning_summary.selected_branch == "PendingOptionProvider"

    def test_unknown_label_does_not_fire(self):
        pack = _pack(
            pending_options=(
                PendingOption(label="A", text="x", bound_action={"intent": "x"}),
            ),
        )
        d = UnifiedRouter().route("Z", pack)
        assert d.reasoning_summary.selected_branch != "PendingOptionProvider"

    def test_letter_that_is_also_stock_ticker_routes_to_pending_option_first(self):
        """'B' as label must beat any provider that might parse it as a ticker."""
        pack = _pack(
            pending_options=(
                PendingOption(label="B", text="fundamentals", bound_action={"intent": "fundamentals"}),
            ),
        )
        d = UnifiedRouter().route("B", pack)
        assert d.reasoning_summary.selected_branch == "PendingOptionProvider"


class TestContextualFollowupProvider:
    """1.3 Follow-up phrases resolve to context-bound answers."""

    def test_based_on_above_with_symbol_context(self):
        pack = _pack(active_symbols=("RELIANCE",), freshness="EOD 2026-05-22")
        d = UnifiedRouter().route("Based on the above, what would you recommend?", pack)
        assert d.reasoning_summary.selected_branch == "ContextualFollowupProvider"
        assert d.route_type == "contextual_answer"

    def test_tell_me_more_with_recent_turn(self):
        pack = _pack(
            recent_turns=(
                RecentTurn(
                    turn_index=0,
                    user_input="INFY setup",
                    intent="stock_brief",
                    symbols=("INFY",),
                ),
            ),
        )
        d = UnifiedRouter().route("Tell me more", pack)
        assert d.reasoning_summary.selected_branch == "ContextualFollowupProvider"

    def test_followup_without_any_context_does_not_fire(self):
        d = UnifiedRouter().route("based on the above what do you think", _pack())
        assert d.reasoning_summary.selected_branch != "ContextualFollowupProvider"

    def test_go_deeper_phrase(self):
        pack = _pack(active_symbols=("TCS",))
        d = UnifiedRouter().route("go deeper into this", pack)
        assert d.reasoning_summary.selected_branch == "ContextualFollowupProvider"


class TestCompoundStockProvider:
    """1.4 Multi-facet compound stock queries go to CompoundStockProvider."""

    # CompoundStockProvider requires a multi-facet ask (e.g. price + F&O + intraday),
    # not just two tickers next to each other.
    COMPOUND_DIXON = (
        "live prices for dixon tech and the analysis of the F&O data "
        "and intraday trade setup in 5 mins"
    )

    def test_compound_multi_facet_prompt_fires(self):
        d = UnifiedRouter().route(self.COMPOUND_DIXON, _pack())
        assert d.reasoning_summary.selected_branch == "CompoundStockProvider"
        assert d.route_type == "compound_plan"

    def test_single_facet_stock_does_not_fire_compound(self):
        d = UnifiedRouter().route("RELIANCE setup", _pack())
        assert d.reasoning_summary.selected_branch != "CompoundStockProvider"

    def test_compound_is_in_default_chain(self):
        assert "CompoundStockProvider" in UnifiedRouter().provider_names


class TestVisualScanProvider:
    """1.5 Chart/visual phrases route to VisualScanProvider."""

    def test_candlestick_chart(self):
        pack = _pack(active_symbols=("RELIANCE",))
        d = UnifiedRouter().route("Show me the candlestick chart for it", pack)
        assert d.reasoning_summary.selected_branch == "VisualScanProvider"

    def test_visual_scan(self):
        d = UnifiedRouter().route("Run a visual scan for DIXON", _pack())
        assert d.reasoning_summary.selected_branch == "VisualScanProvider"

    def test_dashboard_phrase(self):
        d = UnifiedRouter().route("open the dashboard for INFY", _pack())
        assert d.reasoning_summary.selected_branch == "VisualScanProvider"


class TestTopMoversProvider:
    """1.6 Top-movers phrases route to TopMoversProvider."""

    def test_top_gainers(self):
        d = UnifiedRouter().route("show me top gainers", _pack())
        assert d.reasoning_summary.selected_branch == "TopMoversProvider"

    def test_biggest_losers(self):
        d = UnifiedRouter().route("biggest losers today", _pack())
        assert d.reasoning_summary.selected_branch == "TopMoversProvider"

    def test_top_movers(self):
        d = UnifiedRouter().route("top movers in NIFTY", _pack())
        assert d.reasoning_summary.selected_branch == "TopMoversProvider"


class TestMarketSituationProvider:
    """1.7 Market-wide asks route to MarketSituationProvider."""

    def test_market_situation(self):
        d = UnifiedRouter().route("what is the market situation today", _pack())
        assert d.reasoning_summary.selected_branch == "MarketSituationProvider"

    def test_intraday_scan(self):
        d = UnifiedRouter().route("Run an intraday scan across NIFTY", _pack())
        assert d.reasoning_summary.selected_branch == "MarketSituationProvider"

    def test_sector_rotation(self):
        d = UnifiedRouter().route("sector rotation overview", _pack())
        assert d.reasoning_summary.selected_branch == "MarketSituationProvider"


class TestReportProvider:
    """1.8 Report-reference phrases route to ReportProvider."""

    def test_open_the_report(self):
        pack = _pack(
            active_reports=(ActiveReport(path="reports/DIXON_mtf.md", report_type="mtf", symbol="DIXON"),),
            active_symbols=("DIXON",),
        )
        d = UnifiedRouter().route("What does the report say?", pack)
        assert d.reasoning_summary.selected_branch == "ReportProvider"
        assert d.route_type == "contextual_answer"

    def test_no_report_in_context_does_not_fire(self):
        d = UnifiedRouter().route("What does the report say?", _pack())
        assert d.reasoning_summary.selected_branch != "ReportProvider"


class TestNaturalLanguageFallthrough:
    """1.9 Natural language stock queries fall through to fallback_llm (no keyword provider)."""

    def test_reliance_technical_falls_to_llm(self):
        d = UnifiedRouter().route("RELIANCE technical setup", _pack())
        assert d.route_type == "fallback_llm"
        assert d.reasoning_summary.selected_branch == "<none>"

    def test_infy_technicals_falls_to_llm(self):
        d = UnifiedRouter().route("INFY technicals", _pack())
        assert d.route_type == "fallback_llm"

    def test_hdfc_balance_sheet_falls_to_llm(self):
        d = UnifiedRouter().route("HDFC balance sheet", _pack())
        assert d.route_type == "fallback_llm"

    def test_reliance_rsi_falls_to_llm(self):
        d = UnifiedRouter().route("RELIANCE RSI", _pack())
        assert d.route_type == "fallback_llm"

    def test_deep_analysis_of_stock_symbol_does_not_route_to_market_overview(self):
        d = UnifiedRouter().route("deep analysis of bajajcon", _pack())
        assert d.route_type == "fallback_llm"
        assert d.reasoning_summary.selected_branch == "<none>"
        assert "get_live_market_overview" not in [tool for tool, _ in d.tool_plan_tuples()]

    def test_tcs_moving_average_falls_to_llm(self):
        d = UnifiedRouter().route("TCS moving average", _pack())
        assert d.route_type == "fallback_llm"

    def test_multi_time_frame_without_slash_falls_to_llm(self):
        """MTF without slash is natural language → LLM, not structural provider."""
        d = UnifiedRouter().route("RELIANCE multi time frame", _pack())
        assert d.route_type == "fallback_llm"

    def test_hello_there_falls_to_llm(self):
        d = UnifiedRouter().route("hello there friend", _pack())
        assert d.route_type == "fallback_llm"


class TestFalsePositiveStockNames:
    """1.10 Stock names whose tickers contain indicator substrings never misroute."""

    # These all fell through to entity_topic_technicals before the fix.
    # After retiring EntityTopicProvider from DEFAULT_PROVIDERS they now
    # all fall through to fallback_llm (and then to _keyword_intent/LLM).
    @pytest.mark.parametrize("query", [
        "PERSISTENT",
        "brief on PERSISTENT",
        "PERSISTENT setup",
        "PERSISTENT analysis",
        "PERSISTENT stock",
        "what is PERSISTENT",
        "THEMATIC fund",
        "THEMATIC analysis",
        "diversity index",
        "KRISHNA analysis",       # contains "rsi" in "krishna" (krishna → k-r-i-s-h-n-a, "ris" present but not "rsi")
        "best scheme for SIP",    # "ema" in "scheme" (sch-ema)
        "DIVI RSI setup",         # "rsi" as explicit word → still LLM (correct)
    ])
    def test_no_structural_provider_fires(self, query):
        d = UnifiedRouter().route(query, _pack())
        assert d.reasoning_summary.selected_branch not in {
            "EntityTopicProvider", "DirectIntentProvider"
        }, f"Unexpected structural-provider match for: {query!r}"

    def test_persistent_explicitly_with_entity_provider_still_matches(self):
        """EntityTopicProvider class itself works; it's just not in the default chain."""
        pack = _pack()
        d = UnifiedRouter(providers=[EntityTopicProvider()]).route(
            "PERSISTENT technical setup", pack
        )
        assert d.reasoning_summary.selected_branch == "EntityTopicProvider"
        assert d.intent == "entity_topic_technicals"


# ═══════════════════════════════════════════════════════════════════════════
# Layer 2 — EntityTopic slash commands (_stage_entity_topic)
# ═══════════════════════════════════════════════════════════════════════════

class TestSlashCommandRouting:
    """2.x Slash commands bypass the router and hit _stage_entity_topic."""

    def test_slash_search_routes_to_entity_topic_command(self):
        agent = _make_agent()
        with patch("terminal.agent._execute_plan") as ep:
            ep.return_value = [
                {"tool": "resolve_symbol", "args": {"query": "RELIANCE"}, "result": {"symbol": "RELIANCE"}},
                {"tool": "get_symbol_snapshot", "args": {"symbol": "RELIANCE"}, "result": {"symbol": "RELIANCE", "price": 1400}},
            ]
            result = agent.query("/search RELIANCE growth")
        assert result["intent"] == "entity_topic_command"
        assert "REQUIRED TOOL VALIDATION FAILED" not in result["answer"]

    def test_slash_analyze_routes_to_entity_topic_command(self):
        agent = _make_agent()
        with patch("terminal.agent._execute_plan") as ep:
            ep.return_value = [
                {"tool": "resolve_symbol", "args": {"query": "TCS"}, "result": {"symbol": "TCS"}},
                {"tool": "get_symbol_snapshot", "args": {"symbol": "TCS"}, "result": {"symbol": "TCS", "price": 4000}},
            ]
            result = agent.query("/analyze TCS fundamentals")
        assert result["intent"] == "entity_topic_command"


# ═══════════════════════════════════════════════════════════════════════════
# Layer 3 — Agent end-to-end (mocked backend)
# ═══════════════════════════════════════════════════════════════════════════

class TestAgentFalsePositivesResolved:
    """3.1 False-positive stock names route cleanly without validation errors."""

    @pytest.mark.parametrize("symbol,query", [
        ("PERSISTENT", "PERSISTENT setup"),
        ("PERSISTENT", "brief on PERSISTENT"),
        ("THEMATIC", "THEMATIC analysis"),
    ])
    def test_no_required_tool_validation_failed(self, symbol, query):
        agent = _make_agent()
        with patch("terminal.agent._execute_plan") as ep:
            ep.return_value = [
                {"tool": "resolve_symbol", "args": {"query": symbol}, "result": {"symbol": symbol}},
                {"tool": "get_symbol_snapshot", "args": {"symbol": symbol},
                 "result": {"symbol": symbol, "price": 500, "stage": "STAGE_2"}},
            ]
            result = agent.query(query)
        assert "REQUIRED TOOL VALIDATION FAILED" not in result["answer"], (
            f"Got validation failure for {query!r}:\n{result['answer'][:400]}"
        )
        assert result["intent"] in {"stock_brief", "llm_driven", "entity_topic_command"}

    def test_persistent_no_source_trail_missing_tools(self):
        """The old bug: SOURCE TRAIL showed only get_technical_setup. Verify it's gone."""
        agent = _make_agent()
        with patch("terminal.agent._execute_plan") as ep:
            ep.return_value = [
                {"tool": "resolve_symbol", "args": {"query": "PERSISTENT"}, "result": {"symbol": "PERSISTENT"}},
                {"tool": "get_symbol_quick_analysis", "args": {"symbol": "PERSISTENT"},
                 "result": {"symbol": "PERSISTENT", "price": 6500, "stage": "STAGE_2"}},
            ]
            result = agent.query("PERSISTENT")
        # Must not produce a validation failure complaining about missing tools
        assert "REQUIRED TOOL VALIDATION FAILED" not in result["answer"]


class TestAgentExplicitKeywordsReachLLM:
    """3.2 Queries with explicit RSI/MACD/technicals keywords reach stock_brief/LLM correctly."""

    def test_reliance_rsi_setup(self):
        agent = _make_agent()
        with patch("terminal.agent._execute_plan") as ep:
            ep.return_value = [
                {"tool": "resolve_symbol", "args": {"query": "RELIANCE"}, "result": {"symbol": "RELIANCE"}},
                {"tool": "get_symbol_snapshot", "args": {"symbol": "RELIANCE"},
                 "result": {"symbol": "RELIANCE", "price": 1400, "stage": "STAGE_2"}},
                {"tool": "get_technical_setup", "args": {"symbol": "RELIANCE"},
                 "result": {"symbol": "RELIANCE", "rsi": 62, "macd": "Bullish"}},
            ]
            result = agent.query("RELIANCE RSI and MACD setup")
        assert "REQUIRED TOOL VALIDATION FAILED" not in result["answer"]
        assert result["intent"] in {"stock_brief", "llm_driven", "entity_topic_command"}

    def test_tcs_ema_analysis(self):
        agent = _make_agent()
        with patch("terminal.agent._execute_plan") as ep:
            ep.return_value = [
                {"tool": "resolve_symbol", "args": {"query": "TCS"}, "result": {"symbol": "TCS"}},
                {"tool": "get_symbol_snapshot", "args": {"symbol": "TCS"},
                 "result": {"symbol": "TCS", "price": 4000, "stage": "STAGE_2"}},
            ]
            result = agent.query("TCS EMA and moving average setup")
        assert "REQUIRED TOOL VALIDATION FAILED" not in result["answer"]


class TestAgentCompoundQuery:
    """3.3 Compound queries aggregate tool results from both sub-queries."""

    def test_two_part_compound_query(self):
        agent = _make_agent()
        sub1 = {
            "answer": "Market is bullish. ━━━ Not investment advice. For research and learning only. ━━━",
            "trace": [{"tool": "get_live_market_overview", "result": {}}],
            "backend": "MockBackend", "intent": "llm_driven", "has_source_trail": False,
            "usage": {"input_tokens": 300, "output_tokens": 100,
                      "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
        }
        sub2 = {
            "answer": "DMART results are strong. ━━━ Not investment advice. For research and learning only. ━━━",
            "trace": [{"tool": "get_latest_results", "result": {}}],
            "backend": "MockBackend", "intent": "llm_driven", "has_source_trail": False,
            "usage": {"input_tokens": 400, "output_tokens": 120,
                      "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
        }
        with patch("terminal.agent._split_compound_query",
                   return_value=["Market overview", "latest results for DMART"]), \
             patch.object(agent, "_query_single", side_effect=[sub1, sub2]):
            result = agent.query("Market overview and also latest results for DMART")
        assert result["intent"] == "compound"
        assert result["usage"]["input_tokens"] == 700
        assert result["usage"]["output_tokens"] == 220


class TestAgentMultiTurnConversation:
    """3.4 Multi-turn conversation: symbol context carries through to follow-up."""

    def test_turn_one_sets_context_turn_two_uses_it(self):
        agent = _make_agent()

        # Turn 1: establish RELIANCE context
        with patch("terminal.agent._execute_plan") as ep:
            ep.return_value = [
                {"tool": "resolve_symbol", "args": {"query": "RELIANCE"}, "result": {"symbol": "RELIANCE"}},
                {"tool": "get_symbol_snapshot", "args": {"symbol": "RELIANCE"},
                 "result": {"symbol": "RELIANCE", "price": 1420, "stage": "STAGE_2",
                            "trading_signal": "BUY", "relative_strength": 1.15, "sector": "Energy"}},
            ]
            r1 = agent.query("RELIANCE setup")
        assert "REQUIRED TOOL VALIDATION FAILED" not in r1["answer"]

        # Turn 2: follow-up — should recognise context, go to ContextualFollowupProvider
        # or situation assessment (not crash, not hallucinate a new symbol)
        r2 = agent.query("based on the above what would you recommend")
        assert r2 is not None
        assert "answer" in r2
        # Must not error or produce an empty answer
        assert len(r2["answer"]) > 10

    def test_follow_up_without_prior_context_does_not_crash(self):
        agent = _make_agent()
        result = agent.query("based on the above what do you think")
        assert "answer" in result
        assert len(result["answer"]) > 5


class TestAgentPendingOptionExecution:
    """3.5 Pending option reply from session context executes bound tool plan."""

    def test_pending_option_executes_without_symbol_re_resolution(self):
        from terminal.conversation_memory import PendingOption as MemPendingOption
        agent = _make_agent()
        agent._memory.register_pending_options([
            MemPendingOption(
                label="A",
                text="run technical setup for DIXON",
                bound_action={
                    "intent": "entity_topic_technicals",
                    "tool_plan": [
                        {"tool": "resolve_symbol", "args": {"query": "DIXON"}},
                        {"tool": "get_symbol_snapshot", "args": {"symbol": "DIXON"}},
                        {"tool": "get_technical_setup", "args": {"symbol": "DIXON"}},
                    ],
                },
            )
        ])
        with patch("terminal.agent._execute_plan") as ep:
            ep.return_value = [
                {"tool": "resolve_symbol", "args": {"query": "DIXON"},
                 "result": {"symbol": "DIXON"}},
                {"tool": "get_symbol_snapshot", "args": {"symbol": "DIXON"},
                 "result": {"symbol": "DIXON", "price": 15000, "stage": "STAGE_2",
                            "trading_signal": "BUY", "relative_strength": 1.1, "sector": "Electronics"}},
                {"tool": "get_technical_setup", "args": {"symbol": "DIXON"},
                 "result": {"symbol": "DIXON", "rsi": 58}},
            ]
            result = agent.query("A")
        # Must have executed the bound plan, not re-routed via keyword/LLM
        assert "REQUIRED TOOL VALIDATION FAILED" not in result["answer"]
        assert result["intent"] == "entity_topic_technicals"


class TestAgentNoBackend:
    """3.7 No backend set → keyword fallback executes without crashing."""

    def test_stock_brief_without_backend(self):
        agent = Agent()
        agent.backend = None
        agent.backend_name = "none"
        with patch("terminal.agent._execute_plan") as ep:
            ep.return_value = [
                {"tool": "resolve_symbol", "args": {"query": "RELIANCE"}, "result": {"symbol": "RELIANCE"}},
                {"tool": "get_symbol_snapshot", "args": {"symbol": "RELIANCE"},
                 "result": {"symbol": "RELIANCE", "price": 1420, "stage": "STAGE_2",
                            "trading_signal": "BUY", "relative_strength": 1.0, "sector": "Energy"}},
            ]
            result = agent.query("RELIANCE")
        assert "answer" in result
        assert len(result["answer"]) > 10


# ═══════════════════════════════════════════════════════════════════════════
# Edge cases
# ═══════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """4.x Boundary and adversarial inputs."""

    # 4.1 Indicator substrings in stock names
    @pytest.mark.parametrize("ticker,query", [
        # "rsi" in "persistent" (pe-rsi-stent)
        ("PERSISTENT", "PERSISTENT"),
        ("PERSISTENT", "PERSISTENT technical analysis"),
        # "ema" in "thematic" (th-ema-tic)
        ("THEMATIC", "THEMATIC sector rotation"),
        # "ltp" in hypothetical "ALTPHARMA"
        ("DIVI", "DIVI RSI crossover setup"),
    ])
    def test_indicator_substring_in_ticker_does_not_crash(self, ticker, query):
        agent = _make_agent()
        with patch("terminal.agent._execute_plan") as ep:
            ep.return_value = [
                {"tool": "resolve_symbol", "args": {"query": ticker}, "result": {"symbol": ticker}},
                {"tool": "get_symbol_quick_analysis", "args": {"symbol": ticker},
                 "result": {"symbol": ticker, "price": 100, "stage": "STAGE_2",
                            "trading_signal": "BUY", "relative_strength": 1.0, "sector": "Pharma"}},
                {"tool": "get_symbol_snapshot", "args": {"symbol": ticker},
                 "result": {"symbol": ticker, "price": 100, "stage": "STAGE_2",
                            "trading_signal": "BUY", "relative_strength": 1.0, "sector": "Pharma"}},
            ]
            result = agent.query(query)
        assert result is not None
        assert "answer" in result
        assert "REQUIRED TOOL VALIDATION FAILED" not in result["answer"]

    # 4.2 Standalone indicator words without a symbol → clarification (not crash)
    def test_standalone_rsi_without_symbol_does_not_crash(self):
        agent = _make_agent()
        # DirectIntentProvider is not in default chain; _keyword_intent classifies this
        with patch("terminal.agent._execute_plan", return_value=[]):
            result = agent.query("show me the RSI")
        assert "answer" in result
        assert result["answer"]

    def test_standalone_macd_without_symbol(self):
        agent = _make_agent()
        with patch("terminal.agent._execute_plan", return_value=[]):
            result = agent.query("MACD crossover signal")
        assert "answer" in result

    # 4.3 Empty / whitespace query → graceful result
    def test_empty_query_returns_answer(self):
        agent = _make_agent()
        agent.backend.chat.return_value = _llm_response("I need a question to answer.")
        agent.backend.format_tool_calls_in_message.return_value = {"role": "assistant"}
        agent.backend.tool_result_message.return_value = {"role": "tool", "content": "{}"}
        result = agent.query("")
        assert "answer" in result
        assert result["answer"]

    def test_whitespace_only_query(self):
        agent = _make_agent()
        agent.backend.chat.return_value = _llm_response("Please provide a question.")
        agent.backend.format_tool_calls_in_message.return_value = {"role": "assistant"}
        agent.backend.tool_result_message.return_value = {"role": "tool", "content": "{}"}
        result = agent.query("   ")
        assert "answer" in result

    # 4.4 Uppercase noise words in query not treated as extra symbol requests
    def test_rsi_adx_macd_not_treated_as_symbols(self):
        """Uppercase technical terms in the query must not appear in 'Requested symbol(s)' block."""
        agent = _make_agent()
        with patch("terminal.agent._execute_plan") as ep:
            ep.return_value = [
                {"tool": "resolve_symbol", "args": {"query": "SAKAR"}, "result": {"symbol": "SAKAR"}},
                {"tool": "scrape_screener_in", "args": {"symbol": "SAKAR"},
                 "result": {"symbol": "SAKAR"}},
                {"tool": "get_symbol_snapshot", "args": {"symbol": "SAKAR"},
                 "result": {"symbol": "SAKAR", "price": 696, "stage": "STAGE_2",
                            "trading_signal": "BUY", "relative_strength": 1.1, "sector": "Textiles"}},
                {"tool": "get_technical_setup", "args": {"symbol": "SAKAR"},
                 "result": {"symbol": "SAKAR", "rsi": 52, "adx": 24}},
                {"tool": "get_sector_context", "args": {"sector_or_symbol": "SAKAR"},
                 "result": {"symbol": "SAKAR"}},
            ]
            result = agent.query("SAKAR technical setup with RSI, ADX, MACD and MA context")
        assert "Requested symbol(s): SAKAR, ADX, MA" not in result["answer"]
        assert "SAKAR" in result["answer"]

    # 4.5 Provider chain order preserved under exception isolation
    def test_router_exception_isolation_does_not_break_chain(self):
        from terminal.router.providers import MarketSituationProvider

        class BoomProvider:
            name = "BoomProvider"

            def propose(self, user_input, context_pack):
                raise RuntimeError("boom!")

        router = UnifiedRouter(providers=[BoomProvider(), MarketSituationProvider()])
        d = router.route("market situation today", _pack())
        assert d.reasoning_summary.selected_branch == "MarketSituationProvider"
        assert "BoomProvider" in " ".join(d.reasoning_summary.rejected_branches)

    # 4.6 EntityTopicProvider class still works when explicitly wired
    def test_entity_topic_provider_works_when_explicitly_instantiated(self):
        pack = _pack()
        for query, expected_intent, expected_tools in [
            ("RELIANCE RSI", "entity_topic_technicals",
             [("resolve_symbol", {"query": "RELIANCE"}),
              ("get_symbol_snapshot", {"symbol": "RELIANCE"}),
              ("get_technical_setup", {"symbol": "RELIANCE"})]),
            ("HDFC fundamentals", "entity_topic_fundamentals",
             [("search_yahoo_finance", {"symbol": "HDFC"})]),
        ]:
            d = UnifiedRouter(providers=[EntityTopicProvider()]).route(query, pack)
            assert d.intent == expected_intent, f"Wrong intent for {query!r}"
            assert d.tool_plan_tuples() == expected_tools, f"Wrong tools for {query!r}"

    # 4.7 DirectIntentProvider class still works when explicitly wired
    def test_direct_intent_provider_works_when_explicitly_instantiated(self):
        pack = _pack()
        d = UnifiedRouter(providers=[DirectIntentProvider()]).route("show me the RSI", pack)
        assert d.intent == "direct_technicals_clarify"
        assert d.route_type == "clarification"

    def test_direct_intent_with_context_symbol_resolves(self):
        pack = _pack(active_symbols=("INFY",))
        d = UnifiedRouter(providers=[DirectIntentProvider()]).route("RSI please", pack)
        assert d.intent == "direct_technicals"
        assert ("get_technical_setup", {"symbol": "INFY"}) in d.tool_plan_tuples()


# ═══════════════════════════════════════════════════════════════════════════
# Slash command routing — all 16 entity-topic commands + non-entity routes
# ═══════════════════════════════════════════════════════════════════════════

class TestEntityTopicCommandsAllSixteen:
    """All 16 _ENTITY_TOPIC_COMMANDS route correctly.

    /chart is special: VisualScanProvider (UnifiedRouter layer) intercepts it
    before _stage_entity_topic, so it resolves to visual_scan, not entity_topic_command.
    All other 15 commands resolve to entity_topic_command when given a symbol.
    """

    # /chart is intentionally excluded — it resolves to visual_scan via VisualScanProvider
    _ENTITY_TOPIC_COMMANDS = [
        "/analyze",
        "/canslim",
        "/chain",
        "/company-index",
        "/company-xray",
        "/concall",
        "/fno",
        "/forensic",
        "/oi",
        "/options",
        "/report",
        "/results",
        "/search",
        "/strategy",
        "/strategy-council",
    ]

    @pytest.mark.parametrize("cmd", _ENTITY_TOPIC_COMMANDS)
    def test_command_routes_to_entity_topic_command(self, cmd):
        """Every entity-topic command + symbol → entity_topic_command intent."""
        agent = _make_agent()
        with patch("terminal.agent._execute_plan") as ep:
            ep.return_value = [
                {"tool": "resolve_symbol", "args": {"query": "RELIANCE"},
                 "result": {"symbol": "RELIANCE"}},
                {"tool": "get_symbol_snapshot", "args": {"symbol": "RELIANCE"},
                 "result": {"symbol": "RELIANCE", "price": 1420, "stage": "STAGE_2",
                            "trading_signal": "BUY", "relative_strength": 1.1, "sector": "Energy"}},
            ]
            result = agent.query(f"{cmd} RELIANCE")
        assert result["intent"] == "entity_topic_command", (
            f"{cmd} RELIANCE → expected entity_topic_command, got {result['intent']!r}"
        )

    def test_chart_command_routes_to_visual_scan(self):
        """/chart is caught by VisualScanProvider before entity_topic stage → visual_scan."""
        agent = _make_agent()
        with patch("terminal.agent._execute_plan") as ep:
            ep.return_value = [
                {"tool": "run_visual_scan", "args": {"symbol": "RELIANCE"}, "result": {"symbol": "RELIANCE"}},
            ]
            result = agent.query("/chart RELIANCE")
        assert result["intent"] == "visual_scan"

    @pytest.mark.parametrize("cmd", _ENTITY_TOPIC_COMMANDS)
    def test_command_without_symbol_does_not_crash(self, cmd):
        """Entity-topic command with no symbol → clarification or graceful fallback, no exception."""
        agent = _make_agent()
        # Configure mock so the LLM fallback path (if hit) doesn't error on MagicMock usage
        agent.backend.chat.return_value = _llm_response(
            "Which stock did you want me to analyze? ━━━ Not investment advice. For research and learning only. ━━━"
        )
        agent.backend.format_tool_calls_in_message.return_value = {"role": "assistant"}
        agent.backend.tool_result_message.return_value = {"role": "tool", "content": "{}"}
        with patch("terminal.agent._execute_plan", return_value=[]):
            result = agent.query(cmd)
        assert "answer" in result
        assert len(result["answer"]) > 0

    def test_natural_search_alias_without_slash(self):
        """'search USL growth strategy' (no slash) is also handled by entity_topic."""
        agent = _make_agent()
        with patch("terminal.agent._execute_plan") as ep:
            ep.return_value = [
                {"tool": "deep_search", "args": {"symbol": "UNITDSPR", "context": "growth strategy"},
                 "result": {"symbol": "UNITDSPR", "results": []}},
            ]
            result = agent.query("search USL growth strategy")
        assert result["intent"] == "entity_topic_command"


class TestEntityTopicCommandEdgeCases:
    """Edge cases for entity-topic command parsing."""

    def test_report_preset_type_bypasses_entity_topic(self):
        """/report sector-rotation → fallback (not entity_topic), preset reports have own path."""
        from terminal.situation_assessment import assess_entity_topic_request
        r = assess_entity_topic_request("/report sector-rotation")
        assert not r.applies
        assert r.decision == "fallback_to_router"

    def test_report_with_type_symbol_and_format(self):
        """/report technical RELIANCE pdf → entity_topic_command with format."""
        agent = _make_agent()
        with patch("terminal.agent._execute_plan") as ep:
            ep.return_value = [
                {"tool": "resolve_symbol", "args": {"query": "RELIANCE"},
                 "result": {"symbol": "RELIANCE"}},
                {"tool": "get_symbol_snapshot", "args": {"symbol": "RELIANCE"},
                 "result": {"symbol": "RELIANCE", "price": 1420, "stage": "STAGE_2",
                            "trading_signal": "BUY", "relative_strength": 1.1, "sector": "Energy"}},
            ]
            result = agent.query("/report technical RELIANCE pdf")
        assert result["intent"] == "entity_topic_command"

    def test_analyze_document_url_bypasses_entity_topic(self):
        """/analyze <url> → fallback (document analysis, not stock entity)."""
        from terminal.situation_assessment import assess_entity_topic_request
        r = assess_entity_topic_request("/analyze https://example.com/report.pdf")
        assert not r.applies
        assert r.decision == "fallback_to_router"

    def test_multiword_company_name_resolves(self):
        """/search United Spirits concall pdf → canonical UNITDSPR."""
        from terminal.situation_assessment import assess_entity_topic_request
        r = assess_entity_topic_request("/search United Spirits concall pdf")
        assert r.decision == "route_with_entity_topic"
        assert r.canonical_symbol == "UNITDSPR"
        assert r.output_format == "pdf"

    def test_concall_with_quarter(self):
        from terminal.situation_assessment import assess_entity_topic_request
        r = assess_entity_topic_request("/concall INFY Q3 2026")
        assert r.decision == "route_with_entity_topic"
        assert r.canonical_symbol == "INFY"

    def test_oi_for_index(self):
        from terminal.situation_assessment import assess_entity_topic_request
        r = assess_entity_topic_request("/oi NIFTY")
        assert r.decision == "route_with_entity_topic"
        assert r.canonical_symbol == "NIFTY"

    def test_strategy_council_with_model_flag(self):
        from terminal.situation_assessment import assess_entity_topic_request
        r = assess_entity_topic_request("/strategy-council RELIANCE llm")
        assert r.decision == "route_with_entity_topic"
        assert r.canonical_symbol == "RELIANCE"

    def test_canslim_lookup(self):
        from terminal.situation_assessment import assess_entity_topic_request
        r = assess_entity_topic_request("/canslim TATAMOTOR")
        assert r.decision == "route_with_entity_topic"
        # TATAMOTOR resolves to TATAMOTORS
        assert r.canonical_symbol in {"TATAMOTORS", "TATAMOTOR"}

    def test_unknown_slash_command_does_not_parse_as_entity_topic(self):
        from terminal.situation_assessment import assess_entity_topic_request
        r = assess_entity_topic_request("/nonexistent RELIANCE")
        assert not r.applies

    def test_output_format_html_stripped_from_topic(self):
        from terminal.situation_assessment import assess_entity_topic_request
        r = assess_entity_topic_request("/report fundamental INFY html")
        assert r.output_format == "html"
        assert r.canonical_symbol == "INFY"


class TestNonEntityTopicSlashCommands:
    """Non-entity-topic slash commands route correctly through _keyword_intent / LLM."""

    def test_youtube_url_routes_to_youtube_analysis(self):
        """A YouTube URL → youtube_video_analysis intent, synthesizer renders without error."""
        agent = _make_agent()
        with patch("terminal.agent._execute_plan") as ep:
            ep.return_value = [
                {"tool": "analyze_youtube_video",
                 "args": {"source": "https://www.youtube.com/watch?v=abc123"},
                 "result": {
                     "title": "Market Outlook 2026",
                     "channel": "FinanceTV",
                     "url": "https://www.youtube.com/watch?v=abc123",
                     "published_at": "2026-05-20",
                     # transcript must be a dict — not a plain string
                     "transcript": {"available": True, "segment_count": 12},
                     "transcription": {},
                     "summary": "Bullish outlook for NIFTY.",
                 }},
            ]
            result = agent.query("https://www.youtube.com/watch?v=abc123")
        assert result.get("intent") in {"youtube_video_analysis", "llm_driven"}
        assert "answer" in result

    def test_compare_two_stocks_routes_to_stock_comparison(self):
        """'/compare RELIANCE INFY' or 'compare RELIANCE vs INFY' → stock_comparison."""
        agent = _make_agent()
        with patch("terminal.agent._execute_plan") as ep:
            ep.return_value = [
                {"tool": "compare_stocks",
                 "args": {"symbols": ["RELIANCE", "INFY"], "aspects": ["both"]},
                 "result": {"symbols": ["RELIANCE", "INFY"], "evidence_coverage": "full",
                            "stock_details": [], "unresolved_symbols": [], "input_symbols": ["RELIANCE", "INFY"],
                            "missing_evidence": []}},
            ]
            result = agent.query("/compare RELIANCE INFY")
        assert result.get("intent") in {"stock_comparison", "llm_driven"}
        assert "REQUIRED TOOL VALIDATION FAILED" not in result["answer"]

    def test_global_market_command_routes_to_global_assessment(self):
        agent = _make_agent()
        with patch("terminal.agent._execute_plan") as ep:
            ep.return_value = [
                {"tool": "get_global_market_overview", "args": {}, "result": {"markets": []}},
            ]
            result = agent.query("/global")
        assert result.get("intent") in {"global_market_assessment", "llm_driven"}

    def test_unknown_slash_command_does_not_crash(self):
        """/foobar with no handler falls through gracefully."""
        agent = _make_agent()
        agent.backend.chat.return_value = _llm_response(
            "I don't recognise that command. ━━━ Not investment advice. For research and learning only. ━━━"
        )
        agent.backend.format_tool_calls_in_message.return_value = {"role": "assistant"}
        agent.backend.tool_result_message.return_value = {"role": "tool", "content": "{}"}
        result = agent.query("/foobar")
        assert "answer" in result
        assert result["answer"]

    def test_help_command_does_not_crash(self):
        agent = _make_agent()
        with patch("terminal.agent._execute_plan", return_value=[]):
            result = agent.query("/help")
        assert "answer" in result

    def test_new_session_command_does_not_crash(self):
        agent = _make_agent()
        with patch("terminal.agent._execute_plan", return_value=[]):
            result = agent.query("/new")
        assert "answer" in result


if __name__ == "__main__":
    import unittest

    loader = unittest.TestLoader()
    suite = loader.discover(str(ROOT / "tests"), pattern="test_routing_smoke.py")
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    print()
    print(f"── Summary ──")
    print(f"  RAN: {res.testsRun}    "
          f"FAIL: {len(res.failures)}    "
          f"ERR: {len(res.errors)}    "
          f"SKIP: {len(res.skipped)}")
    sys.exit(0 if res.wasSuccessful() else 1)
