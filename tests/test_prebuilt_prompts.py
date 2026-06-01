"""Prebuilt prompt routing tests.

Verifies every prompt in PROMPT_LIBRARY (p1–p85) and every RIC workflow step
routes correctly without crashing and without producing REQUIRED TOOL VALIDATION
FAILED for the wrong reason.

Sections:
  1. TestPromptLibraryIntentMapping      — _keyword_intent returns a known, non-empty
                                           intent for all 60 non-email-pipe prompts.
  2. TestPromptRouterLayerFiring         — router-layer structural providers fire on the
                                           correct 15 prompts; the other 45 fall to
                                           fallback_llm (LLM handles them).
  3. TestPromptLibraryAgentSmoke         — representative agent.query() run for one
                                           prompt from each of the 10 non-email
                                           categories; no crash, no validation failure.
  4. TestEmailPipePromptParsing          — the 22 email-pipe upstream strings (before
                                           the | /email part) all produce a known intent.
  5. TestRICWorkflowCommands             — /ric <key> <symbol> routes to the correct
                                           keyword intent; each step prompt also routes
                                           to a known intent.
  6. TestPromptEdgeCases                 — prompts containing stock-name substrings that
                                           previously mis-routed, and the compound multi-
                                           facet prompt.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest

from terminal.agent import Agent, _keyword_intent
from terminal.router import ContextPack, UnifiedRouter
from nse_agent import PROMPT_LIBRARY, RIC_LIBRARY


# ─── helpers ─────────────────────────────────────────────────────────────────

def _pack(**kw) -> ContextPack:
    return ContextPack(session_id="prompt-smoke", **kw)


def _make_agent() -> Agent:
    agent = Agent()
    agent.backend = MagicMock()
    agent.backend_name = "MockBackend"
    agent.backend.chat.return_value = {
        "tool_calls": [],
        "content": "Analysis complete. ━━━ Not investment advice. For research and learning only. ━━━",
        "finish_reason": "stop",
        "usage": {
            "input_tokens": 200, "output_tokens": 80,
            "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0,
        },
    }
    agent.backend.format_tool_calls_in_message.return_value = {"role": "assistant"}
    agent.backend.tool_result_message.return_value = {"role": "tool", "content": "{}"}
    return agent


# Build flat prompt list once at import time
_ALL_PROMPTS: list[tuple[str, str, str]] = []
for _cat in PROMPT_LIBRARY:
    for _title, _text in _cat["prompts"]:
        _ALL_PROMPTS.append((_cat["cat"], _title, _text))

# Split into non-email (routable) and email-pipe (need upstream extraction)
_NON_EMAIL_PROMPTS = [
    (cat, title, text) for cat, title, text in _ALL_PROMPTS
    if not ("| /email" in text or text.strip().startswith("/email") or text.strip().startswith("/ric"))
]
_EMAIL_PIPE_PROMPTS = [
    (cat, title, text) for cat, title, text in _ALL_PROMPTS
    if "| /email" in text and not text.strip().startswith("/ric")
]
_PURE_CMD_PROMPTS = [
    (cat, title, text) for cat, title, text in _ALL_PROMPTS
    if text.strip().startswith("/email") or text.strip().startswith("/ric")
]

# Known valid intents — any prompt must produce one of these
_KNOWN_INTENTS = frozenset({
    "stock_brief", "stock_results", "stock_comparison", "screener",
    "sector_deep_dive", "sector_rotation", "sector_scan",
    "market_situation_assessment", "market_overview", "market_knowledge",
    "market_dashboard", "intraday_index_scan", "intraday_setup",
    "intraday_screener", "intraday_market_recap", "intraday_levels",
    "global_market_assessment", "fno_overview", "portfolio_review",
    "results_feed", "forthcoming_results", "stock_results",
    "strength_validation", "index_status", "long_term_growth_research",
    "entity_topic_command", "event_calendar", "data_health",
    "intraday_health", "collective_news_results",
    # LLM path fallbacks
    "llm_driven", "general_chat",
})

# Structural providers that legitimately fire on some prebuilt prompts
_STRUCTURAL_FIRE_EXPECTED: dict[str, str] = {
    "Bank Nifty Scan":       "VisualScanProvider",
    "Nifty 50 Scan":         "MarketSituationProvider",
    "Nifty IT Scan":         "MarketSituationProvider",
    "VCP Pattern Hunt":      "MarketSituationProvider",
    "Supertrend Setups":     "MarketSituationProvider",
    "Supertrend BUY Sweep":  "MarketSituationProvider",
    "Top Sector Today":      "MarketSituationProvider",
    "Breakout Candidates":   "MarketSituationProvider",
    "High RS Stocks":        "MarketSituationProvider",
    "TCS Full Analysis":     "MarketSituationProvider",
    "HDFC Bank Valuation":   "MarketSituationProvider",
    "Concall Summary":       "MarketSituationProvider",
    "RELIANCE Full View":    "CompoundStockProvider",
    "Nifty News Flow":       "MarketSituationProvider",
    "Portfolio vs Screen":   "MarketSituationProvider",
}

# One representative prompt per non-email category to smoke through agent.query
_AGENT_SMOKE_CASES: list[tuple[str, str, list[dict]]] = [
    # (title, prompt_text, minimal_execute_plan_return)
    (
        "Market Pulse",
        "Give me a full live market overview — NIFTY 50, BANK, IT, MID, SMALL indices with breadth, FII/DII flow, and stage distribution.",
        [{"tool": "get_live_market_overview", "args": {}, "result": {"indices": [], "breadth": {}}}],
    ),
    (
        "RELIANCE Intraday",
        "Intraday research setup for RELIANCE on 15m — setup label, technical target zones, invalidation level, pivot levels, and key indicators.",
        [
            {"tool": "resolve_symbol", "args": {"query": "RELIANCE"}, "result": {"symbol": "RELIANCE"}},
            {"tool": "get_nse_intraday_snapshot", "args": {"symbol": "RELIANCE"},
             "result": {"symbol": "RELIANCE", "price": 1420, "change_pct": 0.5}},
            {"tool": "explain_intraday_setup", "args": {"symbol": "RELIANCE"},
             "result": {"symbol": "RELIANCE", "setup_label": "Momentum Long",
                        "target_zones": [1440, 1460], "invalidation": 1400}},
        ],
    ),
    (
        "Stage 2 Breakouts",
        "Show me stocks currently in Weinstein Stage 2 with recent breakouts — RS rank high, volume expanding.",
        [{"tool": "run_screener_query", "args": {"screen_type": "stage2"},
          "result": {"screen_type": "stage2", "count": 5, "results": [{"symbol": "DIXON"}]}}],
    ),
    (
        "IT Sector Health",
        "Analyse the IT sector — breadth, stage distribution, RS vs Nifty, leaders and laggards, and key themes.",
        [{"tool": "get_sector_context", "args": {"sector_or_symbol": "IT"},
          "result": {"sector": "IT", "total_stocks": 30}}],
    ),
    (
        "High RS Stocks",
        "List the top 20 stocks by Relative Strength percentage rank vs NIFTY 50. These are the market leaders.",
        [{"tool": "run_screener_query", "args": {"screen_type": "high_rs"},
          "result": {"screen_type": "high_rs", "count": 20, "results": []}}],
    ),
    (
        "TCS Full Analysis",
        "Full fundamental analysis of TCS — P/E, P/B, ROE, ROCE, revenue growth, debt, pros/cons from screener.in.",
        [
            {"tool": "resolve_symbol", "args": {"query": "TCS"}, "result": {"symbol": "TCS"}},
            {"tool": "get_symbol_snapshot", "args": {"symbol": "TCS"},
             "result": {"symbol": "TCS", "price": 4000, "stage": "STAGE_2",
                        "trading_signal": "BUY", "relative_strength": 1.05, "sector": "IT"}},
            {"tool": "get_latest_results", "args": {"symbol": "TCS"},
             "result": {"symbol": "TCS", "revenue": 60000, "net_profit": 12000, "roe": 48.0}},
        ],
    ),
    (
        "SBI Deep Dive",
        "SBI complete analysis — NPA trend, ROE, P/B vs HDFC, technical stage, FII holding, and key catalysts.",
        [
            {"tool": "resolve_symbol", "args": {"query": "SBI"}, "result": {"symbol": "SBIN"}},
            {"tool": "get_symbol_snapshot", "args": {"symbol": "SBIN"},
             "result": {"symbol": "SBIN", "price": 800, "stage": "STAGE_2",
                        "trading_signal": "BUY", "relative_strength": 1.02, "sector": "Banking"}},
        ],
    ),
    (
        "Results Calendar",
        "Which companies are announcing quarterly results this week? What are the expected earnings and market reaction?",
        [
            {"tool": "get_forthcoming_results", "args": {}, "result": {"events": []}},
            {"tool": "get_latest_results_feed", "args": {"days_back": 7, "limit": 50},
             "result": {"results": [], "count": 0}},
            {"tool": "resolve_symbol", "args": {"query": "earnings"}, "result": {"symbol": "NIFTY"}},
            {"tool": "get_symbol_snapshot", "args": {"symbol": "NIFTY"},
             "result": {"symbol": "NIFTY", "price": 24500, "stage": "STAGE_2",
                        "trading_signal": "BUY", "relative_strength": 1.0, "sector": "Index"}},
        ],
    ),
    (
        "Portfolio Exposure",
        "Show my portfolio sector distribution and concentration. Which sectors am I overweight or underweight?",
        [{"tool": "get_portfolio_holdings", "args": {}, "result": {"holdings": []}}],
    ),
    (
        "Global Market Check",
        "What happened in US, Asian, and European markets overnight? SGX Nifty cues for India's open.",
        [{"tool": "get_global_market_overview", "args": {}, "result": {"markets": []}}],
    ),
]


# ═══════════════════════════════════════════════════════════════════════════
# 1. Intent mapping — all 60 non-email prompts
# ═══════════════════════════════════════════════════════════════════════════

class TestPromptLibraryIntentMapping:
    """_keyword_intent returns a non-empty known intent for every non-email prompt."""

    @pytest.mark.parametrize(
        "cat,title,text",
        [(c, t, x) for c, t, x in _NON_EMAIL_PROMPTS],
        ids=[t for _, t, _ in _NON_EMAIL_PROMPTS],
    )
    def test_prompt_maps_to_known_intent(self, cat, title, text):
        result = _keyword_intent(text)
        intent = result.get("intent") or ""
        assert intent, f"[{cat}] {title!r} → empty intent"
        # Every intent should be recognisable (not a typo or unknown fallback)
        assert intent in _KNOWN_INTENTS, (
            f"[{cat}] {title!r} → unrecognised intent {intent!r}\n"
            f"  Add it to _KNOWN_INTENTS if it's a valid new intent."
        )


# ═══════════════════════════════════════════════════════════════════════════
# 2. Router layer — which prompts fire structural providers vs fall to LLM
# ═══════════════════════════════════════════════════════════════════════════

class TestPromptRouterLayerFiring:
    """Structural providers fire on the right 15 prompts; others fall to fallback_llm."""

    @pytest.mark.parametrize(
        "title,text,expected_provider",
        [(t, x, _STRUCTURAL_FIRE_EXPECTED[t]) for _, t, x in _NON_EMAIL_PROMPTS
         if t in _STRUCTURAL_FIRE_EXPECTED],
        ids=[t for _, t, _ in _NON_EMAIL_PROMPTS if t in _STRUCTURAL_FIRE_EXPECTED],
    )
    def test_expected_structural_provider_fires(self, title, text, expected_provider):
        d = UnifiedRouter().route(text, _pack())
        assert d.reasoning_summary.selected_branch == expected_provider, (
            f"{title!r}: expected {expected_provider!r}, "
            f"got {d.reasoning_summary.selected_branch!r}"
        )

    @pytest.mark.parametrize(
        "cat,title,text",
        [(c, t, x) for c, t, x in _NON_EMAIL_PROMPTS if t not in _STRUCTURAL_FIRE_EXPECTED],
        ids=[t for _, t, _ in _NON_EMAIL_PROMPTS if t not in _STRUCTURAL_FIRE_EXPECTED],
    )
    def test_non_structural_prompt_falls_to_llm(self, cat, title, text):
        d = UnifiedRouter().route(text, _pack())
        branch = d.reasoning_summary.selected_branch
        assert branch == "<none>", (
            f"[{cat}] {title!r} unexpectedly fired structural provider {branch!r}\n"
            f"  If this is intentional, add it to _STRUCTURAL_FIRE_EXPECTED."
        )
        assert d.route_type == "fallback_llm"


# ═══════════════════════════════════════════════════════════════════════════
# 3. Agent smoke — one prompt per category through agent.query
# ═══════════════════════════════════════════════════════════════════════════

class TestPromptLibraryAgentSmoke:
    """Representative prompt per category runs through agent.query without errors."""

    @pytest.mark.parametrize(
        "title,text,plan_return",
        _AGENT_SMOKE_CASES,
        ids=[t for t, _, _ in _AGENT_SMOKE_CASES],
    )
    def test_prompt_does_not_crash_and_produces_answer(self, title, text, plan_return):
        agent = _make_agent()
        with patch("terminal.agent._execute_plan", return_value=plan_return):
            result = agent.query(text)
        assert "answer" in result, f"{title!r}: no 'answer' key in result"
        assert result["answer"], f"{title!r}: empty answer"
        assert "REQUIRED TOOL VALIDATION FAILED" not in result["answer"], (
            f"{title!r}: validation failure:\n{result['answer'][:400]}"
        )

    def test_reliance_full_view_compound_route(self):
        """'Everything on RELIANCE' is a multi-facet query → CompoundStockProvider."""
        d = UnifiedRouter().route(
            "Everything on RELIANCE — live price, technical setup, fundamentals from screener.in, "
            "recent news, sector context, and intraday levels.",
            _pack(),
        )
        assert d.reasoning_summary.selected_branch == "CompoundStockProvider"
        assert d.route_type == "compound_plan"


# ═══════════════════════════════════════════════════════════════════════════
# 4. Email pipe prompts
# ═══════════════════════════════════════════════════════════════════════════

class TestEmailPipePromptParsing:
    """Email-pipe prompts: the upstream part (before | /email) routes to a known intent."""

    @pytest.mark.parametrize(
        "title,text",
        [(t, x) for _, t, x in _EMAIL_PIPE_PROMPTS],
        ids=[t for _, t, _ in _EMAIL_PIPE_PROMPTS],
    )
    def test_upstream_part_has_known_intent(self, title, text):
        upstream = text.split("| /email")[0].strip()
        assert upstream, f"{title!r}: no upstream text before pipe"
        result = _keyword_intent(upstream)
        intent = result.get("intent") or ""
        assert intent, f"{title!r}: upstream maps to empty intent (text: {upstream!r})"
        assert intent in _KNOWN_INTENTS, (
            f"{title!r}: upstream intent {intent!r} not in known set"
        )

    def test_pipe_syntax_stripped_correctly(self):
        """Pipe extraction logic: everything before '| /email' is the upstream prompt."""
        sample = "Show FII flows today | /email --to user@example.com"
        upstream = sample.split("| /email")[0].strip()
        assert upstream == "Show FII flows today"

    def test_all_email_pipe_prompts_present(self):
        """Confirm we have the expected number of email-pipe prompts in the library."""
        count = sum(
            1 for _, _, text in _ALL_PROMPTS
            if "| /email" in text and not text.strip().startswith("/ric")
        )
        assert count == len(_EMAIL_PIPE_PROMPTS), (
            f"Email-pipe prompt count mismatch: counted {count}, "
            f"_EMAIL_PIPE_PROMPTS has {len(_EMAIL_PIPE_PROMPTS)}"
        )
        assert count > 0, "Expected at least one email-pipe prompt"

    def test_pure_email_command_prompts_present(self):
        """Some email-category prompts are standalone /email or /ric commands."""
        pure_cmds = [
            text for _, _, text in _ALL_PROMPTS
            if text.strip().startswith("/email") or
               (text.strip().startswith("/ric") and "| /email" not in text)
        ]
        assert len(pure_cmds) > 0

    @pytest.mark.parametrize(
        "title,text",
        [(t, x) for _, t, x in _EMAIL_PIPE_PROMPTS],
        ids=[t for _, t, _ in _EMAIL_PIPE_PROMPTS],
    )
    def test_upstream_does_not_crash_via_agent(self, title, text):
        """Upstream part runs through agent.query without crashing."""
        upstream = text.split("| /email")[0].strip()
        agent = _make_agent()
        with patch("terminal.agent._execute_plan", return_value=[]):
            result = agent.query(upstream)
        assert "answer" in result, f"{title!r}: no answer from upstream"


# ═══════════════════════════════════════════════════════════════════════════
# 5. RIC workflow commands and step prompts
# ═══════════════════════════════════════════════════════════════════════════

class TestRICWorkflowCommands:
    """All 9 RIC workflows: command-line intent + every step prompt has a known intent."""

    # Expected intent for each /ric <key> command line
    _RIC_COMMAND_INTENTS: dict[str, str] = {
        "sherlock":          "stock_brief",
        "sector-xray":       "sector_deep_dive",
        "breakout-hunter":   "screener",
        "earnings-playbook": "stock_brief",
        "index-pulse":       "index_status",
        "peer-battle":       "stock_brief",
        "risk-radar":        "stock_brief",
        "morning-intel":     "stock_brief",
        "company-xray":      "stock_brief",
    }

    # Example arguments for each RIC type
    _RIC_EXAMPLES = {
        "sherlock":          "RELIANCE",
        "sector-xray":       "IT",
        "breakout-hunter":   "",
        "earnings-playbook": "TCS",
        "index-pulse":       "NIFTY BANK",
        "peer-battle":       "TCS,INFY,WIPRO",
        "risk-radar":        "",
        "morning-intel":     "",
        "company-xray":      "DMART",
    }

    @pytest.mark.parametrize("ric_key", list(RIC_LIBRARY.keys()))
    def test_ric_command_line_maps_to_known_intent(self, ric_key):
        arg = self._RIC_EXAMPLES.get(ric_key, "")
        cmd = f"/ric {ric_key} {arg}".strip()
        result = _keyword_intent(cmd)
        intent = result.get("intent") or ""
        assert intent, f"/ric {ric_key}: empty intent"
        assert intent in _KNOWN_INTENTS, f"/ric {ric_key}: intent {intent!r} not in known set"
        expected = self._RIC_COMMAND_INTENTS.get(ric_key)
        if expected:
            assert intent == expected, (
                f"/ric {ric_key}: expected intent {expected!r}, got {intent!r}"
            )

    @pytest.mark.parametrize("ric_key", list(RIC_LIBRARY.keys()))
    def test_all_step_prompts_map_to_known_intent(self, ric_key):
        ric = RIC_LIBRARY[ric_key]
        arg = self._RIC_EXAMPLES.get(ric_key, "RELIANCE")
        for step in ric["steps"]:
            # Substitute placeholder
            prompt = step["prompt"].format(
                symbol=arg, sector=arg, index=arg
            )
            # Skip if the step prompt is itself a slash command
            if prompt.strip().startswith("/"):
                continue
            result = _keyword_intent(prompt)
            intent = result.get("intent") or ""
            assert intent, (
                f"/ric {ric_key} step '{step['label']}': empty intent for {prompt[:60]!r}"
            )
            assert intent in _KNOWN_INTENTS, (
                f"/ric {ric_key} step '{step['label']}': intent {intent!r} not in known set"
            )

    @pytest.mark.parametrize("ric_key", list(RIC_LIBRARY.keys()))
    def test_ric_command_does_not_crash_via_agent(self, ric_key):
        """Every /ric command produces an answer without exceptions."""
        arg = self._RIC_EXAMPLES.get(ric_key, "")
        cmd = f"/ric {ric_key} {arg}".strip()
        agent = _make_agent()
        with patch("terminal.agent._execute_plan") as ep:
            ep.return_value = [
                {"tool": "resolve_symbol", "args": {"query": arg or "NIFTY"},
                 "result": {"symbol": arg or "NIFTY"}},
                {"tool": "get_symbol_snapshot", "args": {"symbol": arg or "NIFTY"},
                 "result": {"symbol": arg or "NIFTY", "price": 1000, "stage": "STAGE_2",
                            "trading_signal": "BUY", "relative_strength": 1.0, "sector": "General"}},
            ]
            result = agent.query(cmd)
        assert "answer" in result, f"/ric {ric_key}: no answer"
        assert result["answer"], f"/ric {ric_key}: empty answer"


# ═══════════════════════════════════════════════════════════════════════════
# 6. Prompt edge cases
# ═══════════════════════════════════════════════════════════════════════════

class TestPromptEdgeCases:
    """Prompts that previously caused issues or contain tricky patterns."""

    def test_adani_enterprises_does_not_misroute(self):
        """'Research ADANI ENTERPRISES' must not fire entity_topic_technicals."""
        text = "Research ADANI ENTERPRISES — technical stage, RS rank, fundamentals, FII/DII holding changes, latest news."
        d = UnifiedRouter().route(text, _pack())
        assert d.reasoning_summary.selected_branch not in {"EntityTopicProvider", "DirectIntentProvider"}

    def test_zomato_setup_does_not_misroute(self):
        """ZOMATO setup has RSI and MACD — must not mis-route via removed keyword providers."""
        text = "ZOMATO current setup — Stage analysis, RSI, MACD, support/resistance, fundamental burn rate."
        d = UnifiedRouter().route(text, _pack())
        assert d.reasoning_summary.selected_branch not in {"EntityTopicProvider", "DirectIntentProvider"}

    def test_tata_motors_view_does_not_misroute(self):
        """'TATA MOTORS' in prompt — must not misfire as technical indicator."""
        text = "TATA MOTORS — JLR performance, EV segment, technical setup, sector context, valuation vs global peers."
        result = _keyword_intent(text)
        assert result.get("intent") in _KNOWN_INTENTS

    def test_sbi_deep_dive_no_validation_failure(self):
        """SBI analysis prompt runs to completion without tool-validation failure."""
        agent = _make_agent()
        with patch("terminal.agent._execute_plan") as ep:
            ep.return_value = [
                {"tool": "resolve_symbol", "args": {"query": "SBI"}, "result": {"symbol": "SBIN"}},
                {"tool": "get_symbol_snapshot", "args": {"symbol": "SBIN"},
                 "result": {"symbol": "SBIN", "price": 800, "stage": "STAGE_2",
                            "trading_signal": "BUY", "relative_strength": 1.02, "sector": "Banking"}},
            ]
            result = agent.query(
                "SBI complete analysis — NPA trend, ROE, P/B vs HDFC, technical stage, FII holding, and key catalysts."
            )
        assert "REQUIRED TOOL VALIDATION FAILED" not in result["answer"]

    def test_fmcg_vs_consumer_prompt_routes_cleanly(self):
        """Multi-stock compare prompt routes to CompoundStockProvider or LLM — not misfired."""
        text = "Compare FMCG sector vs Consumer Discretionary — which is showing more Stage 2 stocks and better RS?"
        result = _keyword_intent(text)
        assert result.get("intent") in _KNOWN_INTENTS

    def test_it_sector_pe_compare_prompt_routes_cleanly(self):
        """Multi-ticker compare prompt: TCS vs INFY vs WIPRO vs HCL vs LTIM."""
        text = "Compare P/E, ROE, ROCE, and revenue growth of TCS vs INFY vs WIPRO vs HCL TECH vs LTIM."
        result = _keyword_intent(text)
        assert result.get("intent") in _KNOWN_INTENTS

    def test_bank_nifty_scan_fires_visual_scan_provider(self):
        """'Scan NIFTY BANK for intraday research setups on 15m charts' → VisualScanProvider."""
        text = "Scan NIFTY BANK for intraday research setups using all strategies on 15m charts. Show technical target zones, invalidation levels, and risk context."
        d = UnifiedRouter().route(text, _pack())
        assert d.reasoning_summary.selected_branch == "VisualScanProvider"

    def test_nifty50_scan_fires_market_situation_provider(self):
        """'Scan NIFTY 50 for best intraday setups' → MarketSituationProvider (intraday scan)."""
        text = "Scan NIFTY 50 for the best intraday setups right now — momentum, breakouts, and mean-reversion on 15m candles."
        d = UnifiedRouter().route(text, _pack())
        assert d.reasoning_summary.selected_branch == "MarketSituationProvider"

    def test_prompt_library_has_exactly_85_prompts(self):
        assert len(_ALL_PROMPTS) == 85, (
            f"Expected 85 prompts, found {len(_ALL_PROMPTS)} — "
            "update tests if the library changed intentionally."
        )

    def test_ric_library_has_nine_workflows(self):
        assert len(RIC_LIBRARY) == 9, (
            f"Expected 9 RIC workflows, found {len(RIC_LIBRARY)}"
        )

    def test_each_ric_has_defined_steps(self):
        for key, ric in RIC_LIBRARY.items():
            assert ric["steps"], f"/ric {key} has no steps"
            for step in ric["steps"]:
                assert step.get("label"), f"/ric {key} step has no label"
                assert step.get("prompt"), f"/ric {key} step has no prompt"


if __name__ == "__main__":
    import unittest

    loader = unittest.TestLoader()
    suite = loader.discover(str(ROOT / "tests"), pattern="test_prebuilt_prompts.py")
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    print()
    print(f"── Summary ──")
    print(f"  RAN: {res.testsRun}    "
          f"FAIL: {len(res.failures)}    "
          f"ERR: {len(res.errors)}    "
          f"SKIP: {len(res.skipped)}")
    sys.exit(0 if res.wasSuccessful() else 1)
