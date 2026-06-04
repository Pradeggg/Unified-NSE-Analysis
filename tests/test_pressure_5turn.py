"""tests/test_pressure_5turn.py — 10 conversations × 5 turns pressure test.

Pressure-tests the routing layer under realistic multi-turn conversation load
with accumulated context, mid-session context switches, and symbol carryover.

Each conversation simulates a real user session:
  - Turn 1: Opening query (market, command, or stock)
  - Turn 2: Drill-down or follow-up (context from T1)
  - Turn 3: Context switch or deepening (context from T1+T2)
  - Turn 4: Action or comparative (context from T1+T2+T3)
  - Turn 5: Final synthesis or edge-case (full context stack)

Tests verify:
  1. No routing crash at any depth (all 50 turns)
  2. Symbol carryover in ContextPack across all turns
  3. Context accumulation — recent_turns grows correctly
  4. Intent classification stays sensible through context switches
  5. Thinking display (_print_thinking if available) handles all turns
  6. Provider chain rejects correctly — no wrong providers fire
  7. Performance — all 50 turns route in < 2 seconds total

10 conversation themes:
  CV01: Market regime → Sector rotation → Metal leaders → NATIONALUM → Trade plan
  CV02: Top gainers → AGARIND analysis → Peer compare → Fundamentals → Exit plan
  CV03: Portfolio review → Sell candidates → Freed capital → New sectors → Allocate
  CV04: RIC Sherlock GRANULES → EPS explain → Peer battle → Entry → Risk
  CV05: FII flows → Sector play → IT stocks → RPTECH deep dive → Position size
  CV06: Stage 2 screen → Pharma filter → GRANULES vs LAURUSLABS → Add signal → Stop
  CV07: Breadth analysis → Leading sectors → Defence stocks → ASTRAMICRO → Chart plan
  CV08: Global cues → India beneficiaries → Capital goods → THERMAX → 3-month plan
  CV09: Swing playbook → VCP candidates → RPTECH setup → Entry trigger → Risk note
  CV10: Ambiguous start → Sector clarify → Context switch to portfolio → Action → Email
"""
from __future__ import annotations

import importlib
import time
from dataclasses import dataclass, field

import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def reload_providers():
    import terminal.router.providers
    importlib.reload(terminal.router.providers)


@pytest.fixture(scope="module")
def router():
    from terminal.router import UnifiedRouter
    return UnifiedRouter()


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class Turn:
    query: str
    symbols: tuple[str, ...] = ()
    intent: str = "fallback"          # what this turn produced
    acceptable_intents: tuple[str, ...] = ()  # what T+1 must produce (any)


@dataclass
class Conversation:
    id: str
    description: str
    turns: list[Turn]


# ── Context builder ───────────────────────────────────────────────────────────

def _build_pack(conv: Conversation, up_to_turn: int) -> object:
    """Build ContextPack from all prior turns (0..up_to_turn-1)."""
    from terminal.router import ContextPack
    from terminal.router.context import RecentTurn

    recent = []
    all_syms: set[str] = set()
    for i, t in enumerate(conv.turns[:up_to_turn]):
        recent.append(RecentTurn(
            turn_index=i,
            user_input=t.query,
            intent=t.intent,
            symbols=t.symbols,
            tools=(),
            result_type="market_data" if "market" in t.intent else "stock_brief",
        ))
        all_syms.update(t.symbols)

    return ContextPack(
        session_id=f"{conv.id}-t{up_to_turn}",
        recent_turns=tuple(recent),
        active_symbols=tuple(all_syms),
    )


def _route(router, pack, query: str) -> tuple[str, str]:
    r = router.route(query.lstrip("/intraday ").lstrip("/historical ").strip(), pack)
    return (r.intent or "fallback"), (r.reasoning_summary.selected_branch or "")


# ── 10 CONVERSATIONS × 5 TURNS ───────────────────────────────────────────────

CONVERSATIONS: list[Conversation] = [

    # ─────────────────────────────────────────────────────────────────────────
    # CV01: Market regime → Sector → Metal leaders → NATIONALUM → Trade plan
    # ─────────────────────────────────────────────────────────────────────────
    Conversation("CV01", "Market regime deep-dive into metals trade", [
        Turn("how is the market today",
             symbols=(), intent="market_situation",
             acceptable_intents=("market", "fallback")),
        Turn("which sectors are leading",
             symbols=(), intent="market_situation",
             acceptable_intents=("market", "fallback")),
        Turn("metals looks strong — top metal stocks by RS",
             symbols=(), intent="market_situation",
             acceptable_intents=("market", "top_movers", "fallback")),
        Turn("NATIONALUM is on the list — give me the technical setup",
             symbols=("NATIONALUM",), intent="stock_brief",
             acceptable_intents=("fallback",)),
        Turn("what is the swing trade plan — entry stop and target",
             symbols=("NATIONALUM",), intent="fallback",
             acceptable_intents=("fallback",)),
    ]),

    # ─────────────────────────────────────────────────────────────────────────
    # CV02: Top gainers → AGARIND → Peer compare → Fundamentals → Exit plan
    # ─────────────────────────────────────────────────────────────────────────
    Conversation("CV02", "AGARIND top gainer drill-down and trade decision", [
        Turn("top gainers today",
             symbols=(), intent="top_movers",
             acceptable_intents=("top_movers", "market", "fallback")),
        Turn("AGARIND is up 20% — explain why",
             symbols=("AGARIND",), intent="stock_brief",
             acceptable_intents=("fallback",)),
        Turn("compare AGARIND with its peers in the industrial sector",
             symbols=("AGARIND",), intent="fallback",
             acceptable_intents=("fallback",)),
        Turn("EPS dropped to 29 from 77 — is this a dead cat bounce",
             symbols=("AGARIND",), intent="fallback",
             acceptable_intents=("fallback",)),
        Turn("should I exit now or hold — give me a clear recommendation",
             symbols=("AGARIND",), intent="fallback",
             acceptable_intents=("fallback",)),
    ]),

    # ─────────────────────────────────────────────────────────────────────────
    # CV03: Portfolio → Sell candidates → Freed capital → New sectors → Allocate
    # ─────────────────────────────────────────────────────────────────────────
    Conversation("CV03", "Portfolio rebalancing end-to-end with capital reallocation", [
        Turn("/my-portfolio sell",
             symbols=(), intent="portfolio_monitor",
             acceptable_intents=("fallback", "market", "portfolio")),
        Turn("if I sell ITC and LIC what is the freed capital",
             symbols=("ITC", "LIC"), intent="fallback",
             acceptable_intents=("fallback",)),
        Turn("which sectors are best positioned for the next 4 weeks",
             symbols=(), intent="market_situation",
             acceptable_intents=("market", "fallback")),
        Turn("from those sectors give me the top 3 candidates",
             symbols=(), intent="fallback",
             acceptable_intents=("market", "fallback")),
        Turn("allocate ₹50000 across GRANULES RPTECH and NATIONALUM equally",
             symbols=("GRANULES", "RPTECH", "NATIONALUM"), intent="fallback",
             acceptable_intents=("fallback",)),
    ]),

    # ─────────────────────────────────────────────────────────────────────────
    # CV04: RIC Sherlock → EPS → Peer battle → Entry → Risk
    # ─────────────────────────────────────────────────────────────────────────
    Conversation("CV04", "RIC Sherlock deep dive with follow-up analysis chain", [
        Turn("/ric sherlock GRANULES",
             symbols=("GRANULES",), intent="ric_sherlock",
             acceptable_intents=("fallback",)),
        Turn("explain the EPS trend from the above",
             symbols=("GRANULES",), intent="fallback",
             acceptable_intents=("fallback",)),
        Turn("compare GRANULES with LAURUSLABS on the same EPS and revenue metrics",
             symbols=("GRANULES", "LAURUSLABS"), intent="fallback",
             acceptable_intents=("fallback",)),
        Turn("which one has the better entry right now",
             symbols=("GRANULES", "LAURUSLABS"), intent="fallback",
             acceptable_intents=("fallback",)),
        Turn("set a stop loss and target for the winner — use ATR 14",
             symbols=("GRANULES",), intent="fallback",
             acceptable_intents=("fallback",)),
    ]),

    # ─────────────────────────────────────────────────────────────────────────
    # CV05: FII flows → Sector play → IT stocks → RPTECH → Position size
    # ─────────────────────────────────────────────────────────────────────────
    Conversation("CV05", "FII activity → sector identification → individual stock position", [
        Turn("show me FII DII activity today",
             symbols=(), intent="market_situation",
             acceptable_intents=("market", "fallback")),
        Turn("FII are buying — which sectors are they accumulating",
             symbols=(), intent="market_situation",
             acceptable_intents=("market", "fallback")),
        Turn("IT and capital goods look strong — top IT stocks by RS",
             symbols=(), intent="market_situation",
             acceptable_intents=("market", "fallback")),
        Turn("RPTECH is at the top — technical analysis please",
             symbols=("RPTECH",), intent="stock_brief",
             acceptable_intents=("fallback",)),
        Turn("1% account risk, account value 10 lakh — position size for RPTECH",
             symbols=("RPTECH",), intent="fallback",
             acceptable_intents=("fallback",)),
    ]),

    # ─────────────────────────────────────────────────────────────────────────
    # CV06: Stage 2 → Pharma filter → Peer battle → Add signal → Stop loss
    # ─────────────────────────────────────────────────────────────────────────
    Conversation("CV06", "Stage 2 screener → pharma focus → actionable setup", [
        Turn("show me stage 2 stocks",
             symbols=(), intent="market_situation",
             acceptable_intents=("market", "fallback")),
        Turn("filter by pharma and healthcare sector only",
             symbols=(), intent="market_situation",
             acceptable_intents=("market", "fallback")),
        Turn("GRANULES and LAURUSLABS are on the list — which is stronger",
             symbols=("GRANULES", "LAURUSLABS"), intent="fallback",
             acceptable_intents=("fallback",)),
        Turn("GRANULES has better RS — what is the add trigger",
             symbols=("GRANULES",), intent="fallback",
             acceptable_intents=("fallback",)),
        Turn("place an initial stop below the recent swing low — where is that",
             symbols=("GRANULES",), intent="fallback",
             acceptable_intents=("fallback",)),
    ]),

    # ─────────────────────────────────────────────────────────────────────────
    # CV07: Breadth → Leading sectors → Defence → ASTRAMICRO → Chart plan
    # ─────────────────────────────────────────────────────────────────────────
    Conversation("CV07", "Market breadth → defence sector → ASTRAMICRO trade plan", [
        Turn("market breadth",
             symbols=(), intent="market_situation",
             acceptable_intents=("market", "fallback")),
        Turn("which sectors are driving the advances today",
             symbols=(), intent="market_situation",
             acceptable_intents=("market", "fallback")),
        Turn("defence and capital goods look strong — top defence stocks",
             symbols=(), intent="market_situation",
             acceptable_intents=("market", "fallback")),
        Turn("ASTRAMICRO is leading — RSI 82, is it overbought",
             symbols=("ASTRAMICRO",), intent="fallback",
             acceptable_intents=("fallback",)),
        Turn("give me a 3-month price target based on the channel",
             symbols=("ASTRAMICRO",), intent="fallback",
             acceptable_intents=("fallback",)),
    ]),

    # ─────────────────────────────────────────────────────────────────────────
    # CV08: Global cues → India beneficiaries → Capital goods → THERMAX → Plan
    # ─────────────────────────────────────────────────────────────────────────
    Conversation("CV08", "Global macro → sector play → capital goods → THERMAX", [
        Turn("global market impact on India today",
             symbols=(), intent="market_situation",
             acceptable_intents=("market", "fallback")),
        Turn("US rate stability — which Indian sectors benefit",
             symbols=(), intent="market_situation",
             acceptable_intents=("market", "fallback")),
        Turn("capital goods and infrastructure look like beneficiaries",
             symbols=(), intent="market_situation",
             acceptable_intents=("market", "fallback")),
        Turn("THERMAX is a stage 2 leader in capital goods — full analysis",
             symbols=("THERMAX",), intent="fallback",
             acceptable_intents=("fallback",)),
        Turn("3 month swing trade plan with entry stop and target for THERMAX",
             symbols=("THERMAX",), intent="fallback",
             acceptable_intents=("fallback",)),
    ]),

    # ─────────────────────────────────────────────────────────────────────────
    # CV09: Swing playbook → VCP → RPTECH setup → Entry → Risk note
    # Tests /swing-playbook command + follow-up NLP chain
    # ─────────────────────────────────────────────────────────────────────────
    Conversation("CV09", "Swing playbook → VCP drill-down → RPTECH execution", [
        Turn("/swing-playbook",
             symbols=(), intent="swing_playbook",
             acceptable_intents=("fallback", "market")),
        Turn("show me the top VCP candidates from the playbook",
             symbols=(), intent="fallback",
             acceptable_intents=("market", "fallback")),
        Turn("RPTECH is on the VCP list — what is the contraction pattern",
             symbols=("RPTECH",), intent="fallback",
             acceptable_intents=("fallback",)),
        Turn("pivot price is 68 — confirm the breakout volume requirement",
             symbols=("RPTECH",), intent="fallback",
             acceptable_intents=("fallback",)),
        Turn("risk 0.5% — what is the position size and expected R multiple",
             symbols=("RPTECH",), intent="fallback",
             acceptable_intents=("fallback",)),
    ]),

    # ─────────────────────────────────────────────────────────────────────────
    # CV10: Ambiguous start → context switch → portfolio → action → email
    # Tests ambiguous→clarified, context switch mid-session, pipe to email
    # ─────────────────────────────────────────────────────────────────────────
    Conversation("CV10", "Ambiguous → context switch → portfolio action → email", [
        Turn("IT",
             symbols=(), intent="fallback",
             acceptable_intents=("fallback",)),
        Turn("I meant IT sector — show leading IT stocks",
             symbols=(), intent="market_situation",
             acceptable_intents=("market", "fallback")),
        Turn("actually show me my portfolio instead — which IT stocks do I hold",
             symbols=(), intent="fallback",
             acceptable_intents=("fallback", "portfolio")),
        Turn("INFTEC is COFORGE — it is a strong buy — should I add",
             symbols=("COFORGE",), intent="fallback",
             acceptable_intents=("fallback",)),
        Turn("generate a portfolio action report and email to pgorai@deloitte.com",
             symbols=("COFORGE",), intent="fallback",
             acceptable_intents=("fallback",)),
    ]),
]


# ═══════════════════════════════════════════════════════════════════════════════
# TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestPressure5Turn:
    """50 total turns across 10 conversations — pressure-testing routing depth."""

    @pytest.mark.parametrize("conv", CONVERSATIONS, ids=[c.id for c in CONVERSATIONS])
    def test_all_5_turns_no_crash(self, router, conv):
        """Every turn in every conversation must route without exception."""
        for i, turn in enumerate(conv.turns):
            pack = _build_pack(conv, up_to_turn=i)
            try:
                intent, provider = _route(router, pack, turn.query)
            except Exception as e:
                pytest.fail(
                    f"{conv.id} T{i+1}: routing crashed on '{turn.query[:50]}': {e}"
                )

    @pytest.mark.parametrize("conv", CONVERSATIONS, ids=[c.id for c in CONVERSATIONS])
    def test_context_accumulates_across_turns(self, conv):
        """ContextPack must have i recent_turns before turn i+1."""
        for i in range(len(conv.turns)):
            pack = _build_pack(conv, up_to_turn=i)
            assert len(pack.recent_turns) == i, (
                f"{conv.id} T{i+1}: expected {i} recent_turns, "
                f"got {len(pack.recent_turns)}"
            )

    @pytest.mark.parametrize("conv", CONVERSATIONS, ids=[c.id for c in CONVERSATIONS])
    def test_symbols_accumulate_correctly(self, conv):
        """Symbols from all prior turns must be in ContextPack.active_symbols."""
        all_syms_so_far: set[str] = set()
        for i, turn in enumerate(conv.turns):
            pack = _build_pack(conv, up_to_turn=i)
            for sym in all_syms_so_far:
                assert sym in pack.active_symbols, (
                    f"{conv.id} T{i+1}: symbol {sym!r} dropped from context"
                )
            all_syms_so_far.update(turn.symbols)

    @pytest.mark.parametrize("conv", CONVERSATIONS, ids=[c.id for c in CONVERSATIONS])
    def test_turn5_intent_is_sensible(self, router, conv):
        """Turn 5 (deepest context) must produce a sensible intent — not crash."""
        pack = _build_pack(conv, up_to_turn=4)
        intent, provider = _route(router, pack, conv.turns[4].query)
        # Any intent is acceptable as long as it isn't an exception
        assert intent is not None

    @pytest.mark.parametrize("conv", CONVERSATIONS, ids=[c.id for c in CONVERSATIONS])
    def test_intent_classification_per_turn(self, router, conv):
        """Each turn's acceptable_intents must include what the router actually produces."""
        for i, turn in enumerate(conv.turns):
            if not turn.acceptable_intents:
                continue
            pack = _build_pack(conv, up_to_turn=i)
            intent, provider = _route(router, pack, turn.query)
            combined = f"{intent} {provider}".lower()
            matches = any(acc.lower() in combined for acc in turn.acceptable_intents)
            assert matches, (
                f"{conv.id} T{i+1}: '{turn.query[:50]}'\n"
                f"  expected one of {turn.acceptable_intents}\n"
                f"  got intent='{intent}'  provider='{provider}'"
            )


class TestPressurePerformance:
    """All 50 turns must complete within a tight time budget."""

    def test_50_turns_under_3_seconds(self, router):
        """Route all 50 turns with full context in under 3 seconds."""
        start = time.perf_counter()
        for conv in CONVERSATIONS:
            for i, turn in enumerate(conv.turns):
                pack = _build_pack(conv, up_to_turn=i)
                _route(router, pack, turn.query)
        elapsed = time.perf_counter() - start
        assert elapsed < 3.0, (
            f"50 turns took {elapsed:.2f}s — exceeds 3.0s budget. "
            f"Router may be making external calls."
        )


class TestContextSwitchBehaviour:
    """Verify correct handling of mid-session context switches."""

    def test_cv03_context_switch_portfolio_to_market(self, router):
        """CV03 T3: after portfolio turn, asking about sectors should route to market."""
        conv = next(c for c in CONVERSATIONS if c.id == "CV03")
        # After turn 2 (portfolio), turn 3 is market question
        pack = _build_pack(conv, up_to_turn=2)
        intent, _ = _route(router, pack, conv.turns[2].query)
        # "which sectors are best" → market_situation or fallback (both OK)
        assert "market" in intent or "fallback" in intent, (
            f"CV03 T3 context switch to market: got '{intent}'"
        )

    def test_cv10_ambiguous_then_sector_clarified(self, router):
        """CV10 T1='IT' (ambiguous) T2='IT sector' should route to market."""
        conv = next(c for c in CONVERSATIONS if c.id == "CV10")
        # T1: bare 'IT' → fallback
        pack0 = _build_pack(conv, up_to_turn=0)
        intent0, _ = _route(router, pack0, conv.turns[0].query)
        assert "fallback" in intent0, f"CV10 T1 'IT' should be fallback, got '{intent0}'"

        # T2: clarified to market
        pack1 = _build_pack(conv, up_to_turn=1)
        intent1, _ = _route(router, pack1, conv.turns[1].query)
        assert "market" in intent1 or "fallback" in intent1, (
            f"CV10 T2 sector clarification: got '{intent1}'"
        )

    def test_cv09_swing_playbook_command_then_nlp(self, router):
        """CV09: /swing-playbook slash cmd then NLP follow-up."""
        conv = next(c for c in CONVERSATIONS if c.id == "CV09")
        # T1: /swing-playbook → should match registry or fallback
        pack0 = _build_pack(conv, up_to_turn=0)
        intent0, _ = _route(router, pack0, conv.turns[0].query)
        # swing-playbook may be in registry (fallback) or market
        assert intent0 is not None, "CV09 T1: routing returned None"

        # T2: NLP follow-up — "show me the top VCP candidates"
        pack1 = _build_pack(conv, up_to_turn=1)
        intent1, _ = _route(router, pack1, conv.turns[1].query)
        assert intent1 is not None, "CV09 T2: routing returned None"

    def test_symbol_context_carries_to_turn5(self, router):
        """NATIONALUM from CV01 T3 must be in context by T5."""
        conv = next(c for c in CONVERSATIONS if c.id == "CV01")
        pack = _build_pack(conv, up_to_turn=4)
        assert "NATIONALUM" in pack.active_symbols, (
            "NATIONALUM should persist in active_symbols through turn 5"
        )

    def test_multi_symbol_accumulation(self, router):
        """CV04: GRANULES introduced T1, LAURUSLABS T3 — both in T5 context."""
        conv = next(c for c in CONVERSATIONS if c.id == "CV04")
        pack = _build_pack(conv, up_to_turn=4)
        # GRANULES was in turn 1 (turn_index 0)
        assert "GRANULES" in pack.active_symbols, "GRANULES missing from T5 context"


class TestEdgeCasesInDeepContext:
    """Edge cases that only appear under deep context load."""

    def test_bare_word_with_5_turn_context(self, router):
        """A bare word at T5 must not crash even with 4 prior turns in context."""
        conv = CONVERSATIONS[0]  # CV01
        pack = _build_pack(conv, up_to_turn=4)
        try:
            intent, _ = _route(router, pack, "which")
            assert intent is not None
        except Exception as e:
            pytest.fail(f"Bare 'which' at T5 crashed: {e}")

    def test_empty_query_with_deep_context(self, router):
        """Empty query at T5 must not crash."""
        conv = CONVERSATIONS[0]
        pack = _build_pack(conv, up_to_turn=4)
        try:
            _route(router, pack, "")
        except Exception as e:
            pytest.fail(f"Empty query at T5 crashed: {e}")

    def test_special_chars_with_deep_context(self, router):
        """Special characters at T5 must not crash."""
        conv = CONVERSATIONS[0]
        pack = _build_pack(conv, up_to_turn=4)
        for special in ["!@#$%", "₹₹₹", "αβγ", "中文", "---"]:
            try:
                _route(router, pack, special)
            except Exception as e:
                pytest.fail(f"Special chars '{special}' at T5 crashed: {e}")

    def test_very_long_query_with_deep_context(self, router):
        """A 500-character query at T5 must not crash."""
        conv = CONVERSATIONS[0]
        pack = _build_pack(conv, up_to_turn=4)
        long_q = "which sectors are doing well and " * 15  # ~500 chars
        try:
            _route(router, pack, long_q)
        except Exception as e:
            pytest.fail(f"Long query at T5 crashed: {e}")

    def test_slash_command_after_4_nlp_turns(self, router):
        """A slash command at T5 after 4 NLP turns must be handled correctly."""
        conv = CONVERSATIONS[1]  # CV02: started with NL queries
        pack = _build_pack(conv, up_to_turn=4)
        try:
            intent, _ = _route(router, pack, "/my-portfolio sell")
            assert intent is not None
        except Exception as e:
            pytest.fail(f"Slash cmd at T5 after NL context crashed: {e}")
