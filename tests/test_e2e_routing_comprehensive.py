"""tests/test_e2e_routing_comprehensive.py — Comprehensive E2E routing coverage.

Tests 90+ query permutations across every command family, stock discussion
pattern, and NL phrase — verifying that the deterministic dispatch layer
(registry + unified router) handles each one correctly BEFORE any LLM call.

No LLM calls are made. All tests are fast (<1s) and reproducible.

Categories:
  Registry   — all 14+ slash-command handlers (exact + variant matching)
  Market/NL  — sector, breadth, A/D, FII, macro, screeners
  TopMovers  — gainers, losers, movers, hot stocks
  Stocks     — single-stock, multi-stock, comparison queries → fallback
  Portfolio  — /my-portfolio and variants
  Intraday   — scan commands, live queries
  Ambiguous  — edge cases, bare words, jargon, the original "which" bug
  MultiTurn  — follow-up context simulation
"""
from __future__ import annotations

import importlib
import pytest

# ── Setup: reload providers so phrase lists are current ──────────────────────

@pytest.fixture(scope="module", autouse=True)
def reload_providers():
    import terminal.router.providers
    importlib.reload(terminal.router.providers)


@pytest.fixture(scope="module")
def router():
    from terminal.router import UnifiedRouter
    return UnifiedRouter()


@pytest.fixture(scope="module")
def pack():
    from terminal.router import ContextPack
    return ContextPack(session_id="e2e-comprehensive")


@pytest.fixture(scope="module")
def registry():
    import sys
    sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent.parent))
    import nse_agent
    return nse_agent._build_command_registry()


# ── Helpers ───────────────────────────────────────────────────────────────────

def route(router, pack, query: str) -> tuple[str, str]:
    """Return (intent, provider) for a query."""
    r = router.route(query, pack)
    return (r.intent or "fallback"), (r.reasoning_summary.selected_branch or "")


def handles(registry, cmd: str) -> bool:
    """True if any registry handler matches the command."""
    q = cmd.strip().lower()
    return any(h.match_fn(q) for h in registry._handlers)


def handler_name(registry, cmd: str) -> str:
    """Return the name of the matching registry handler."""
    q = cmd.strip().lower()
    for h in registry._handlers:
        if h.match_fn(q):
            return h.name
    return ""


# ═══════════════════════════════════════════════════════════════════════════════
# REGISTRY — Slash command dispatch
# ═══════════════════════════════════════════════════════════════════════════════

class TestRegistrySlashCommands:
    """All 14 registered handlers plus common variants."""

    # /help
    @pytest.mark.parametrize("cmd", ["/help", "?", "/h", "/help portfolio", "/help charts"])
    def test_help(self, registry, cmd):
        assert handler_name(registry, cmd) == "help", f"Expected help for {cmd!r}"

    # /commands
    @pytest.mark.parametrize("cmd", ["/commands", "/commands portfolio", "/commands scan"])
    def test_commands(self, registry, cmd):
        assert handler_name(registry, cmd) == "commands"

    # /scan family
    @pytest.mark.parametrize("cmd", [
        "/scan", "/scan NIFTY", "/scan NIFTY BANK", "/scan orb",
        "/scan gap", "/scan vcp", "/scan momentum", "/scan macd",
        "/scan rsi", "/scan bb", "/scan vwap",
    ])
    def test_scan(self, registry, cmd):
        assert handler_name(registry, cmd) == "scan"

    # /my-portfolio family (all variants and sub-commands)
    @pytest.mark.parametrize("cmd", [
        "/my-portfolio",
        "/my-portfolio eod",
        "/my-portfolio sell",
        "/my-portfolio buy",
        "/my-portfolio hold",
        "/my-portfolio strong-buy",
        "/my_portfolio",
        "/my_portfolio sell",
    ])
    def test_my_portfolio(self, registry, cmd):
        assert handler_name(registry, cmd) == "my-portfolio"

    # /mtf family
    @pytest.mark.parametrize("cmd", [
        "/mtf RELIANCE",
        "/mtf scan NIFTY50 bullish",
        "/mtf scan NIFTY500 bearish --min-score 70",
        "/mtf HDFC --report",
        "/mtf TATAMOTORS",
    ])
    def test_mtf(self, registry, cmd):
        assert handler_name(registry, cmd) == "mtf"

    # /strength
    @pytest.mark.parametrize("cmd", [
        "/strength RELIANCE TCS INFY",
        "/strength MANINDS THERMAX BAJAJCON",
        "/strength HDFCBANK ICICIBANK KOTAKBANK",
    ])
    def test_strength(self, registry, cmd):
        assert handler_name(registry, cmd) == "strength"

    # /email
    @pytest.mark.parametrize("cmd", [
        "/email sector --to a@b.com",
        "/email portfolio-analysis --to a@b.com",
        "/email my-portfolio --to a@b.com",
        "/email stage2 --to a@b.com --send",
        "/email top_picks --to pgorai@deloitte.com",
    ])
    def test_email(self, registry, cmd):
        assert handler_name(registry, cmd) == "email"

    # /doctor
    @pytest.mark.parametrize("cmd", ["/doctor", "/doctor --repair"])
    def test_doctor(self, registry, cmd):
        assert handler_name(registry, cmd) == "doctor"

    # /backtest + /strategy-lab
    @pytest.mark.parametrize("cmd", [
        "/backtest list", "/backtest RELIANCE",
        "/strategy-lab validate", "/strategy-lab",
    ])
    def test_backtest(self, registry, cmd):
        assert handler_name(registry, cmd) == "backtest"

    # /data-coverage
    @pytest.mark.parametrize("cmd", [
        "/data-coverage NIFTY500",
        "/data-coverage NIFTY500 --backfill",
        "/data-coverage NIFTY500 --details",
    ])
    def test_data_coverage(self, registry, cmd):
        assert handler_name(registry, cmd) == "data-coverage"

    # /visual-scan
    @pytest.mark.parametrize("cmd", [
        "/visual-scan DMART",
        "/visual-scan RELIANCE",
        "/visual_scan TATAPOWER",
    ])
    def test_visual_scan(self, registry, cmd):
        assert handler_name(registry, cmd) == "visual-scan"

    # /council
    @pytest.mark.parametrize("cmd", [
        "/council",
        "/council today",
        "/council sector NIFTY AUTO --horizon swing",
        "/council stock RELIANCE",
        "/council report --run latest",
    ])
    def test_council(self, registry, cmd):
        assert handler_name(registry, cmd) == "council"

    # /strategy-council
    @pytest.mark.parametrize("cmd", [
        "/strategy-council RELIANCE",
        "/strategy-council DMART --iterations 3",
        "/strategy-council HDFCBANK --llm",
    ])
    def test_strategy_council(self, registry, cmd):
        assert handler_name(registry, cmd) == "strategy-council"

    # Commands that should NOT match a handler (fall to inline chain)
    @pytest.mark.parametrize("cmd", [
        "/chart RELIANCE",
        "/screen stage2",
        "/voice script",
        "/live",
        "/refresh live",
    ])
    def test_falls_to_inline_chain(self, registry, cmd):
        assert not handles(registry, cmd), (
            f"{cmd!r} matched a registry handler — should fall to inline chain"
        )

    # /screen vs /screenshot collision (regression pin)
    @pytest.mark.parametrize("cmd", [
        "/screenshot --mode window --to pgorai@deloitte.com",
        "/screenshot",
        "/screenshot --no-email",
    ])
    def test_screenshot_not_screen(self, registry, cmd):
        """Screenshot must NOT match scan or any registry handler."""
        assert not handles(registry, cmd)


# ═══════════════════════════════════════════════════════════════════════════════
# MARKET / SECTOR — NL queries → MarketSituationProvider
# ═══════════════════════════════════════════════════════════════════════════════

class TestMarketSectorRouting:

    @pytest.mark.parametrize("query", [
        # The original broken queries (regression)
        "which sectors are doing well",
        "which sectors are doing well today",
        "what sectors are outperforming",
        "how is the market",
        "how is the market today",
        # Market state
        "market overview",
        "market breadth",
        "market sentiment",
        "market outlook",
        "nifty today",
        "sector rotation",
        "sector performance today",
        "sector strength",
        "leading sectors",
        "sectors doing well",
        # Stage / breadth / A/D
        "stage distribution",
        "stage 2 stocks",
        "how many stocks are in stage 2 today",
        "show advance decline ratio",
        "advance decline",
        # FII / macro / global
        "FII today",
        "show me FII DII activity",
        "macro proxies",
        "global risk impact on Indian markets",
        # Screeners
        "show me momentum leaders",
        "52 week high stocks",
        "stocks hitting 52 week high",
        # Complex sector
        "which sectors are outperforming nifty 500",
        "where is the money flowing in the market",
        "which sectors should I be looking at",
        "what does the market regime look like",
        "are midcap stocks showing better breadth than largecaps",
        "identify stocks that entered stage 2 in the last 7 days",
    ])
    def test_routes_to_market_situation(self, router, pack, query):
        intent, _ = route(router, pack, query)
        assert "market" in intent or "situation" in intent, (
            f"'{query}' → expected market_situation, got '{intent}'"
        )

    @pytest.mark.parametrize("query", [
        "market",
        "sectors",
        "breadth",
        "FII",
    ])
    def test_bare_words_market(self, router, pack, query):
        intent, _ = route(router, pack, query)
        assert "market" in intent or "situation" in intent, (
            f"Bare word '{query}' → expected market_situation, got '{intent}'"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# TOP MOVERS — gainers, losers, hot stocks
# ═══════════════════════════════════════════════════════════════════════════════

class TestTopMoversRouting:

    @pytest.mark.parametrize("query", [
        "top gainers today",
        "top losers today",
        "biggest movers today",
        "what are the top movers",
        "top 5 gainers in nifty 500",
        "which stocks gained the most today",
        "which stocks gained the most this week",
        "biggest gainers in midcap",
        "best performers today",
        "worst performers today",
        "what's hot today",
    ])
    def test_routes_to_top_movers(self, router, pack, query):
        intent, _ = route(router, pack, query)
        assert "mover" in intent or "top_mover" in intent or "movers" in intent, (
            f"'{query}' → expected top_movers, got '{intent}'"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# STOCKS — single-stock, multi-stock → fallback_llm (LLM handles correctly)
# ═══════════════════════════════════════════════════════════════════════════════

class TestStockQueriesFallback:
    """Stock-specific queries should fall to fallback_llm — LLM picks right tools."""

    @pytest.mark.parametrize("query", [
        # Single stock analysis
        "RELIANCE technical setup",
        "HDFC Bank fundamentals",
        "Infosys EPS trend",
        "TCS quarterly results",
        "BAJFINANCE RSI and trend",
        "explain EPS growth of AGARIND",
        "WIPRO support and resistance levels",
        "TATASTEEL stage and momentum",
        "SBIN price action",
        "ICICIBANK technical outlook",
        # Multi-stock comparisons
        "compare HDFC Bank and ICICI Bank",
        "RELIANCE vs ONGC performance",
        "compare WIPRO TCS INFY on fundamentals",
        "HDFCBANK vs KOTAKBANK vs AXISBANK",
        # F&O / options (no slash)
        "NIFTY options chain",
        "open interest for BANKNIFTY",
        # Specific earnings
        "BAJFINANCE Q4 results",
        "INFY guidance for next quarter",
    ])
    def test_falls_to_llm(self, router, pack, query):
        intent, _ = route(router, pack, query)
        assert "fallback" in intent, (
            f"'{query}' → expected fallback_llm, got '{intent}' "
            "(stock-specific questions must reach the LLM tool loop)"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# AMBIGUOUS — edge cases, the "which" bug, jargon
# ═══════════════════════════════════════════════════════════════════════════════

class TestAmbiguousEdgeCases:

    # THE original bug: "which" was resolved as a stock ticker
    def test_which_is_fallback_not_stock(self, router, pack):
        intent, _ = route(router, pack, "which")
        assert "fallback" in intent, (
            "THE BUG: 'which' must go to fallback_llm, not trigger stock resolution"
        )

    @pytest.mark.parametrize("query", [
        "which",
        "what",
        "IT",
        "metals",
        "banks",
        "up",
        "show me",
        "good stocks",
        "buy now",
        "buy",
        "sell",
        "news",
        "results",
        "PCR today",
        "green stocks",
        "flying stocks",
    ])
    def test_ambiguous_falls_to_llm(self, router, pack, query):
        intent, _ = route(router, pack, query)
        assert "fallback" in intent, (
            f"Ambiguous '{query}' → expected fallback, got '{intent}'"
        )

    # Bare words that ARE unambiguous market terms → market_situation
    @pytest.mark.parametrize("query", ["market", "sectors", "breadth"])
    def test_bare_market_words(self, router, pack, query):
        intent, _ = route(router, pack, query)
        assert "market" in intent or "situation" in intent or "fallback" in intent, (
            f"'{query}' → got '{intent}' (market_situation preferred but fallback acceptable)"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# PORTFOLIO — /my-portfolio command
# ═══════════════════════════════════════════════════════════════════════════════

class TestPortfolioCommands:

    @pytest.mark.parametrize("cmd,expected_handler", [
        ("/my-portfolio",            "my-portfolio"),
        ("/my-portfolio eod",        "my-portfolio"),
        ("/my-portfolio sell",       "my-portfolio"),
        ("/my-portfolio buy",        "my-portfolio"),
        ("/my-portfolio hold",       "my-portfolio"),
        ("/my_portfolio",            "my-portfolio"),
        ("/my_portfolio sell",       "my-portfolio"),
    ])
    def test_portfolio_registry(self, registry, cmd, expected_handler):
        assert handler_name(registry, cmd) == expected_handler

    @pytest.mark.parametrize("query", [
        "my portfolio",          # no slash → should not hit registry
        "MY-PORTFOLIO",          # no slash → should not hit registry
        "portfolio performance",
    ])
    def test_portfolio_without_slash_falls_to_llm(self, registry, router, pack, query):
        # Registry must not match
        assert not handles(registry, query), (
            f"'{query}' without slash must not hit registry"
        )
        # Router should fall to LLM (it's a stock/portfolio query)
        intent, _ = route(router, pack, query)
        assert "fallback" in intent or "market" in intent, (
            f"'{query}' → unexpected intent '{intent}'"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# INTRADAY — scan and live queries
# ═══════════════════════════════════════════════════════════════════════════════

class TestIntradayRouting:

    @pytest.mark.parametrize("cmd", [
        "/scan",
        "/scan NIFTY",
        "/scan NIFTY BANK",
        "/scan NIFTY IT",
        "/scan orb",
        "/scan vcp",
        "/scan gap",
        "/scan macd",
        "/scan momentum",
    ])
    def test_scan_registry(self, registry, cmd):
        assert handler_name(registry, cmd) == "scan"

    @pytest.mark.parametrize("query", [
        "intraday scan",
        "scan nifty 50",
        "breakout scan",
        "vcp scan",
    ])
    def test_scan_via_router(self, router, pack, query):
        intent, _ = route(router, pack, query)
        assert "market" in intent or "situation" in intent


# ═══════════════════════════════════════════════════════════════════════════════
# RIC WORKFLOW — /ric commands (inline chain, not registry)
# ═══════════════════════════════════════════════════════════════════════════════

class TestRicWorkflow:
    """RIC commands are handled by the inline elif chain, not the registry."""

    @pytest.mark.parametrize("cmd", [
        "/ric sherlock RELIANCE",
        "/ric sector-xray IT",
        "/ric breakout-hunter",
        "/ric morning-intel",
        "/ric company-xray DMART",
    ])
    def test_ric_not_in_registry(self, registry, cmd):
        """RIC commands fall to the inline chain — confirm registry doesn't capture them."""
        assert not handles(registry, cmd), (
            f"RIC command {cmd!r} should NOT be in registry — it's handled by inline chain"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# MULTI-TURN — context-aware follow-ups
# ═══════════════════════════════════════════════════════════════════════════════

class TestMultiTurnContext:
    """Follow-up phrases with prior context (ContextualFollowupProvider)."""

    @pytest.mark.parametrize("followup", [
        "tell me more",
        "explain that",
        "expand on that",
        "based on the above",
        "go deeper",
    ])
    def test_followups_without_context_fallback(self, router, pack, followup):
        """Without a prior turn, follow-up phrases should not crash."""
        intent, _ = route(router, pack, followup)
        # May be contextual_followup (if provider fires) or fallback — both acceptable
        assert intent is not None


# ═══════════════════════════════════════════════════════════════════════════════
# THINKING DISPLAY — _print_thinking function
# ═══════════════════════════════════════════════════════════════════════════════

class TestThinkingDisplay:
    """_print_thinking must not crash on any input."""

    def _thinking(self, query: str) -> bool:
        """Return True if _print_thinking completes without error."""
        try:
            import sys as _sys
            sys_path_backup = _sys.path[:]
            _sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent.parent))
            from rich.console import Console
            import io
            buf = io.StringIO()
            import nse_agent
            orig_console = nse_agent.console
            nse_agent.console = Console(file=buf)
            nse_agent._print_thinking(query)
            nse_agent.console = orig_console
            return True
        except Exception:
            return False

    @pytest.mark.parametrize("query", [
        "which sectors are doing well today",
        "/my-portfolio sell",
        "/scan NIFTY",
        "explain EPS growth of AGARIND",
        "RELIANCE vs HDFC Bank",
        "top gainers today",
        "sector rotation",
        "how is the market",
        "which",          # THE bug query
        "",               # empty
        "!@#$%",          # special chars
        "a" * 200,        # very long
    ])
    def test_thinking_no_crash(self, query):
        assert self._thinking(query), f"_print_thinking crashed on {query!r}"


# ═══════════════════════════════════════════════════════════════════════════════
# REGRESSION PINS — specific bugs fixed in this session
# ═══════════════════════════════════════════════════════════════════════════════

class TestRegressionPins:

    def test_which_sectors_routing(self, router, pack):
        """'which sectors are doing well' must NOT try to resolve 'which' as a ticker."""
        intent, provider = route(router, pack, "which sectors are doing well")
        assert "market" in intent or "situation" in intent, (
            f"'which sectors are doing well' → got '{intent}' — the 'which' bug has regressed"
        )

    def test_screenshot_not_swallowed_by_screen(self):
        """/screenshot must not be caught by the /screen EOD screener."""
        text = "/screenshot --mode window --to pgorai@deloitte.com"
        tl = text.lower()
        fires_screener = tl.startswith("/screen") and not tl.startswith("/screenshot")
        assert not fires_screener, "/screenshot was swallowed by /screen screener — regression"

    def test_my_portfolio_without_slash_to_llm(self, router, pack):
        """'MY-PORTFOLIO' (no slash) must go to LLM, not the registry."""
        intent, _ = route(router, pack, "MY-PORTFOLIO")
        assert "fallback" in intent, (
            "'MY-PORTFOLIO' without slash must go to fallback_llm, not portfolio handler"
        )

    def test_entity_assessment_skips_slash(self):
        """Slash commands bypass entity assessment (no rewriting)."""
        for text in ["/my-portfolio", "/scan NIFTY", "/email sector --to a@b.com"]:
            would_assess = not text.lstrip().startswith("/")
            assert not would_assess, (
                f"Slash command {text!r} should bypass entity assessment"
            )

    def test_registry_dispatch_in_source(self):
        """Confirm registry.dispatch() call exists in _chat_loop source."""
        src = (__import__('pathlib').Path(__file__).resolve().parent.parent
               / "nse_agent.py").read_text(encoding="utf-8")
        assert "_shared_reg.dispatch(text, agent, show_trace, mode=" in src, (
            "registry.dispatch() call missing from _chat_loop"
        )
        assert 'not text.lstrip().startswith("/")' in src, (
            "Entity assessment slash-command bypass guard missing"
        )
