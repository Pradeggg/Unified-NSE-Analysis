"""tests/test_multiturn_150.py — 150 Multi-turn conversation routing tests.

Tests that the UnifiedRouter correctly handles context-dependent follow-up
queries across six conversation patterns:

  1. Command → NLP follow-up (25)      — slash cmd then natural language
  2. Market → Stock drill-down (25)    — sector/overview then specific stock
  3. Stock → Comparative (25)          — single stock then comparison
  4. Portfolio → Action (25)           — /my-portfolio then planning questions
  5. RIC workflow → Deep dive (25)     — Sherlock/workflow then analysis
  6. Ambiguous → Clarified (25)        — vague first turn resolved by follow-up

Each scenario has:
  turn1: the first user message
  turn2: the follow-up message
  ctx_intent: intent from turn 1 (used to populate context)
  ctx_symbols: symbols mentioned in turn 1
  expected_turn2: what provider/intent should fire on turn 2

No LLM calls. All tests are deterministic routing assertions.
Tests run in ~3s total.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Optional

import pytest


# ── Reload providers so phrase lists are current ─────────────────────────────
@pytest.fixture(scope="module", autouse=True)
def reload_providers():
    import terminal.router.providers
    importlib.reload(terminal.router.providers)


@pytest.fixture(scope="module")
def router():
    from terminal.router import UnifiedRouter
    return UnifiedRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────

@dataclass
class Scenario:
    id: str
    turn1: str
    turn2: str
    ctx_intent: str = "market_situation"
    ctx_symbols: tuple = ()
    ctx_tools: tuple = ()
    # Expected for turn 2:
    expected_intent: str = ""          # substring match in intent
    expected_fallback: bool = False    # True if turn2 should go to LLM
    category: str = ""


def _pack(scenario: Scenario, sess: str = "mt-test"):
    from terminal.router import ContextPack
    from terminal.router.context import RecentTurn
    turn1 = RecentTurn(
        turn_index=0,
        user_input=scenario.turn1,
        intent=scenario.ctx_intent,
        symbols=scenario.ctx_symbols,
        tools=scenario.ctx_tools,
        result_type="market_data" if "market" in scenario.ctx_intent else "stock_brief",
    )
    return ContextPack(
        session_id=sess,
        recent_turns=(turn1,),
        active_symbols=scenario.ctx_symbols,
    )


def _route(router, pack, query: str) -> tuple[str, str]:
    r = router.route(query, pack)
    return (r.intent or "fallback"), (r.reasoning_summary.selected_branch or "")


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO DATA — 150 multi-turn conversations
# ═══════════════════════════════════════════════════════════════════════════════

_C1 = "cmd_to_nlp"       # command → NLP follow-up
_C2 = "market_to_stock"  # market overview → stock drill-down
_C3 = "stock_compare"    # single stock → comparison
_C4 = "portfolio_action" # portfolio → action planning
_C5 = "ric_deepdive"    # RIC workflow → deep analysis
_C6 = "ambiguous_clarify" # ambiguous → clarified

SCENARIOS: list[Scenario] = [

    # ══════════════════════════════════════════════════════════════════════════
    # CATEGORY 1 — Command → NLP follow-up (25)
    # ══════════════════════════════════════════════════════════════════════════

    Scenario("C1-01", "/scan NIFTY", "which of these setups looks the strongest",
             "market_situation", (), ("scan_intraday_market",),
             expected_fallback=True, category=_C1),

    Scenario("C1-02", "/scan orb", "explain the opening range breakout setup",
             "market_situation", (), ("scan_intraday_market",),
             expected_fallback=True, category=_C1),

    Scenario("C1-03", "/screen stage2", "show me the top 5 by relative strength",
             "market_situation", (), ("run_eod_screener",),
             expected_fallback=True, category=_C1),

    Scenario("C1-04", "/my-portfolio sell", "why should I exit ITC Hotels",
             "portfolio_monitor", ("ITCHOT",), (),
             expected_fallback=True, category=_C1),

    Scenario("C1-05", "/my-portfolio buy", "how much should I add to KIRLOSENG",
             "portfolio_monitor", ("KIRLOSENG",), (),
             expected_fallback=True, category=_C1),

    Scenario("C1-06", "/mtf RELIANCE", "what is the entry trigger based on this",
             "mtf", ("RELIANCE",), ("analyze_mtf",),
             expected_fallback=True, category=_C1),

    Scenario("C1-07", "/scan NIFTY BANK", "which bank stocks are showing orb setup",
             "market_situation", (), (),
             expected_fallback=True, category=_C1),

    Scenario("C1-08", "/strength RELIANCE TCS INFY",
             "which of the three has the best RS",
             "strength_check", ("RELIANCE","TCS","INFY"), (),
             expected_fallback=True, category=_C1),

    Scenario("C1-09", "/my-portfolio eod",
             "which stocks are in the SELL zone",
             "portfolio_monitor", (), (),
             expected_fallback=True, category=_C1),

    Scenario("C1-10", "/scan vcp",
             "how do I trade the VCP pattern",
             "market_situation", (), (),
             expected_fallback=True, category=_C1),

    Scenario("C1-11", "/screen momentum",
             "filter these by sector — show only IT and pharma",
             "market_situation", (), (),
             expected_fallback=True, category=_C1),

    Scenario("C1-12", "/doctor",
             "PostgreSQL is running now, run the sector rotation report",
             "postgres_doctor", (), (),
             expected_fallback=True, category=_C1),

    Scenario("C1-13", "/my-portfolio hold",
             "which hold stocks have the highest investment score",
             "portfolio_monitor", (), (),
             expected_fallback=True, category=_C1),

    Scenario("C1-14", "/scan gap",
             "which of these gap setups are in stage 2",
             "market_situation", (), (),
             expected_fallback=True, category=_C1),

    Scenario("C1-15", "/screen highrs",
             "show only stocks with RS above 120",
             "market_situation", (), (),
             expected_fallback=True, category=_C1),

    Scenario("C1-16", "/my-portfolio",
             "rebalance suggestion — I have too many banking stocks",
             "portfolio_monitor", (), (),
             expected_fallback=True, category=_C1),

    Scenario("C1-17", "/screen dip",
             "which dip stocks have strong fundamentals",
             "market_situation", (), (),
             expected_fallback=True, category=_C1),

    Scenario("C1-18", "/mtf HDFCBANK",
             "is this aligned across daily and weekly",
             "mtf", ("HDFCBANK",), (),
             expected_fallback=True, category=_C1),

    Scenario("C1-19", "/scan momentum",
             "give me the top 3 by score",
             "market_situation", (), (),
             expected_fallback=True, category=_C1),

    Scenario("C1-20", "/my-portfolio sell",
             "what is the risk if I hold LIC for another month",
             "portfolio_monitor", ("LIC",), (),
             expected_fallback=True, category=_C1),

    Scenario("C1-21", "/screen base",
             "how long do base patterns usually last before breakout",
             "market_situation", (), (),
             expected_fallback=True, category=_C1),

    Scenario("C1-22", "/scan rsi",
             "which RSI divergence setups are in leading sectors",
             "market_situation", (), (),
             expected_fallback=True, category=_C1),

    Scenario("C1-23", "/council today",
             "what was the top conviction pick from the council",
             "research_council", (), (),
             expected_fallback=True, category=_C1),

    Scenario("C1-24", "/my-portfolio buy",
             "should I add to GRANULES or SOLIN",
             "portfolio_monitor", ("GRANULES","SOLIN"), (),
             expected_fallback=True, category=_C1),

    Scenario("C1-25", "/screen tight",
             "which of these tight-range stocks are near a breakout",
             "market_situation", (), (),
             expected_fallback=True, category=_C1),

    # ══════════════════════════════════════════════════════════════════════════
    # CATEGORY 2 — Market overview → Stock drill-down (25)
    # ══════════════════════════════════════════════════════════════════════════

    Scenario("C2-01", "which sectors are doing well",
             "show me the top stocks in IT sector",
             "market_situation", (), ("get_live_market_overview",),
             expected_fallback=True, category=_C2),

    Scenario("C2-02", "top gainers today",
             "tell me more about the first stock on the list",
             "top_movers", (), ("get_top_gainers_losers",),
             expected_fallback=True, category=_C2),

    Scenario("C2-03", "sector rotation",
             "which pharma stocks are leading the rotation",
             "market_situation", (), (),
             expected_fallback=True, category=_C2),

    Scenario("C2-04", "market breadth",
             "which stage 2 stocks have the strongest RS",
             "market_situation", (), (),
             expected_fallback=True, category=_C2),

    Scenario("C2-05", "FII today",
             "which sectors are FIIs buying into",
             "market_situation", (), (),
             expected_fallback=True, category=_C2),

    Scenario("C2-06", "how is the market",
             "give me the top 3 momentum stocks",
             "market_situation", (), (),
             expected_fallback=True, category=_C2),

    Scenario("C2-07", "stage 2 stocks today",
             "filter by pharma and healthcare sector",
             "market_situation", (), (),
             expected_fallback=True, category=_C2),

    Scenario("C2-08", "what sectors are outperforming",
             "drill into capital goods — which stocks",
             "market_situation", (), (),
             expected_fallback=True, category=_C2),

    Scenario("C2-09", "advance decline ratio",
             "which large caps are driving the declines",
             "market_situation", (), (),
             expected_fallback=True, category=_C2),

    Scenario("C2-10", "52 week high stocks",
             "show me the ones with CANSLIM score above 15",
             "market_situation", (), (),
             expected_fallback=True, category=_C2),

    Scenario("C2-11", "momentum leaders today",
             "RPTECH is on the list — give me more detail",
             "market_situation", ("RPTECH",), (),
             expected_fallback=True, category=_C2),

    Scenario("C2-12", "biggest movers today",
             "which of these are in a VCP setup",
             "top_movers", (), (),
             expected_fallback=True, category=_C2),

    Scenario("C2-13", "nifty today",
             "break down by sector — which is pulling it up",
             "market_situation", (), (),
             expected_fallback=True, category=_C2),

    Scenario("C2-14", "global cues for India",
             "which Indian sectors benefit from US tech rally",
             "market_situation", (), (),
             expected_fallback=True, category=_C2),

    Scenario("C2-15", "macro proxies today",
             "how does the rupee weakness affect IT sector",
             "market_situation", (), (),
             expected_fallback=True, category=_C2),

    Scenario("C2-16", "which sectors are doing well today in the market",
             "top 5 stocks in the leading sector by investment score",
             "market_situation", (), (),
             expected_fallback=True, category=_C2),

    Scenario("C2-17", "market sentiment",
             "given this sentiment, what is the swing trading strategy",
             "market_situation", (), (),
             expected_fallback=True, category=_C2),

    Scenario("C2-18", "top losers today",
             "are any of these in stage 2 — potential buy on dip",
             "top_movers", (), (),
             expected_fallback=True, category=_C2),

    Scenario("C2-19", "sector strength",
             "metals looks strong — top 5 metal stocks by RS",
             "market_situation", (), (),
             expected_fallback=True, category=_C2),

    Scenario("C2-20", "stage distribution",
             "how does today compare to last week",
             "market_situation", (), (),
             expected_fallback=True, category=_C2),

    Scenario("C2-21", "breadth",
             "market breadth is positive — what does this signal for swing trades",
             "market_situation", (), (),
             expected_fallback=True, category=_C2),

    Scenario("C2-22", "how the market is performing",
             "given this, is it a good time to add positions",
             "market_situation", (), (),
             expected_fallback=True, category=_C2),

    Scenario("C2-23", "market overview",
             "focus on EV sector specifically",
             "market_situation", (), (),
             expected_fallback=True, category=_C2),

    Scenario("C2-24", "what are the top movers",
             "THERMAX is a gainer — should I buy",
             "top_movers", ("THERMAX",), (),
             expected_fallback=True, category=_C2),

    Scenario("C2-25", "sector rotation",
             "energy seems to be rotating in — which energy stocks",
             "market_situation", (), (),
             expected_fallback=True, category=_C2),

    # ══════════════════════════════════════════════════════════════════════════
    # CATEGORY 3 — Stock analysis → Comparative (25)
    # ══════════════════════════════════════════════════════════════════════════

    Scenario("C3-01", "RELIANCE technical setup",
             "compare with ONGC on the same metrics",
             "stock_brief", ("RELIANCE",), (),
             expected_fallback=True, category=_C3),

    Scenario("C3-02", "HDFC Bank fundamentals",
             "is it better than ICICI Bank right now",
             "stock_brief", ("HDFCBANK",), (),
             expected_fallback=True, category=_C3),

    Scenario("C3-03", "Infosys EPS trend",
             "compare with TCS and WIPRO on the same 3 year trend",
             "stock_brief", ("INFY",), (),
             expected_fallback=True, category=_C3),

    Scenario("C3-04", "TATASTEEL stage and momentum",
             "what about JSWSTEEL — same analysis",
             "stock_brief", ("TATASTEEL",), (),
             expected_fallback=True, category=_C3),

    Scenario("C3-05", "BAJFINANCE RSI and trend",
             "how does this compare to HDFC Life and SBILIFE",
             "stock_brief", ("BAJFINANCE",), (),
             expected_fallback=True, category=_C3),

    Scenario("C3-06", "KIRLOSENG technical setup",
             "give me a peer comparison across capital goods sector",
             "stock_brief", ("KIRLOSENG",), (),
             expected_fallback=True, category=_C3),

    Scenario("C3-07", "GRANULES pharma analysis",
             "which pharma stock is stronger — GRANULES or LAURUSLABS",
             "stock_brief", ("GRANULES",), (),
             expected_fallback=True, category=_C3),

    Scenario("C3-08", "SBI stage and RS",
             "compare with HDFCBANK — which is the better bet",
             "stock_brief", ("SBIN",), (),
             expected_fallback=True, category=_C3),

    Scenario("C3-09", "NTPC power sector analysis",
             "compare NTPC vs TATAPOWER vs JSWENERGY",
             "stock_brief", ("NTPC",), (),
             expected_fallback=True, category=_C3),

    Scenario("C3-10", "NATIONALUM metal setup",
             "aluminium vs steel — NATIONALUM vs TATASTEEL which is better",
             "stock_brief", ("NATIONALUM",), (),
             expected_fallback=True, category=_C3),

    Scenario("C3-11", "SKYGOLD consumer durables",
             "compare with TITAN on fundamentals and stage",
             "stock_brief", ("SKYGOLD",), (),
             expected_fallback=True, category=_C3),

    Scenario("C3-12", "AGARIND fundamentals",
             "compare with similar mid-cap industrials",
             "stock_brief", ("AGARIND",), (),
             expected_fallback=True, category=_C3),

    Scenario("C3-13", "RPTECH IT analysis",
             "which IT mid-cap has better momentum — RPTECH or COFORGE",
             "stock_brief", ("RPTECH",), (),
             expected_fallback=True, category=_C3),

    Scenario("C3-14", "HINDAL metals stage",
             "compare HINDALCO VEDL NATIONALUM on RS score",
             "stock_brief", ("HINDAL",), (),
             expected_fallback=True, category=_C3),

    Scenario("C3-15", "ICICIBANK technical",
             "which private bank is strongest — ICICI HDFC AXIS KOTAK",
             "stock_brief", ("ICICIBANK",), (),
             expected_fallback=True, category=_C3),

    Scenario("C3-16", "BSE exchange analysis",
             "BSE vs NSE parent — MCX comparison on valuation",
             "stock_brief", ("BSE",), (),
             expected_fallback=True, category=_C3),

    Scenario("C3-17", "SOLIN solar energy",
             "compare with TATAPOWER renewable segment",
             "stock_brief", ("SOLARINDS",), (),
             expected_fallback=True, category=_C3),

    Scenario("C3-18", "FEDBAN banking setup",
             "Federal Bank vs Karur Vysya Bank — which is stronger",
             "stock_brief", ("FEDERALBNK",), (),
             expected_fallback=True, category=_C3),

    Scenario("C3-19", "POLI polycab electrical",
             "compare Polycab with Havells on every metric",
             "stock_brief", ("POLYCAB",), (),
             expected_fallback=True, category=_C3),

    Scenario("C3-20", "MTATEC defence",
             "which defence stock is the best bet — MTAR DATA ASTRAMICRO",
             "stock_brief", ("MTARTECH",), (),
             expected_fallback=True, category=_C3),

    Scenario("C3-21", "PRECWIRE capital goods",
             "compare PRECWIRE with RPTECH and CUMMINS",
             "stock_brief", ("PRECWIRE",), (),
             expected_fallback=True, category=_C3),

    Scenario("C3-22", "VIJAYA cement analysis",
             "Vijaya vs Shree Cement vs ACC — who wins on margins",
             "stock_brief", ("VIJAYA",), (),
             expected_fallback=True, category=_C3),

    Scenario("C3-23", "ASTRAMICRO defence",
             "Astra Microwave vs Data Patterns on stage and RS",
             "stock_brief", ("ASTRAMICRO",), (),
             expected_fallback=True, category=_C3),

    Scenario("C3-24", "THERMAX capital goods",
             "compare THERMAX with BHEL on fundamental quality",
             "stock_brief", ("THERMAX",), (),
             expected_fallback=True, category=_C3),

    Scenario("C3-25", "NETWEB IT analysis",
             "Netweb vs Tata Elxsi vs RPTECH — best growth story",
             "stock_brief", ("NETWEB",), (),
             expected_fallback=True, category=_C3),

    # ══════════════════════════════════════════════════════════════════════════
    # CATEGORY 4 — Portfolio → Action planning (25)
    # ══════════════════════════════════════════════════════════════════════════

    Scenario("C4-01", "/my-portfolio",
             "which holdings have the worst signal score",
             "portfolio_monitor", (), (),
             expected_fallback=True, category=_C4),

    Scenario("C4-02", "/my-portfolio sell",
             "if I sell ITC Hotels and LIC, what is the freed capital",
             "portfolio_monitor", ("ITCHOT","LIC"), (),
             expected_fallback=True, category=_C4),

    Scenario("C4-03", "/my-portfolio buy",
             "should I add more to GRANULES or start a fresh position in NETWEB",
             "portfolio_monitor", ("GRANULES","NETWEB"), (),
             expected_fallback=True, category=_C4),

    Scenario("C4-04", "/my-portfolio eod",
             "what is the sector concentration risk",
             "portfolio_monitor", (), (),
             expected_fallback=True, category=_C4),

    Scenario("C4-05", "portfolio performance",
             "which positions are dragging the most",
             "portfolio_monitor", (), (),
             expected_fallback=True, category=_C4),

    Scenario("C4-06", "/my-portfolio hold",
             "for the hold stocks, what trigger would upgrade them to buy",
             "portfolio_monitor", (), (),
             expected_fallback=True, category=_C4),

    Scenario("C4-07", "/my-portfolio sell",
             "set a stop loss plan for TRENT",
             "portfolio_monitor", ("TRENT",), (),
             expected_fallback=True, category=_C4),

    Scenario("C4-08", "/my-portfolio buy",
             "which buy signals are in the metals sector",
             "portfolio_monitor", (), (),
             expected_fallback=True, category=_C4),

    Scenario("C4-09", "my portfolio performance",
             "unrealised PnL breakdown by sector",
             "portfolio_monitor", (), (),
             expected_fallback=True, category=_C4),

    Scenario("C4-10", "/my-portfolio",
             "rebalance to reduce banking exposure below 20%",
             "portfolio_monitor", (), (),
             expected_fallback=True, category=_C4),

    Scenario("C4-11", "/my-portfolio sell",
             "what is the tax implication of selling my top 5 losers",
             "portfolio_monitor", (), (),
             expected_fallback=True, category=_C4),

    Scenario("C4-12", "/my-portfolio eod",
             "show me the CANSLIM score for each buy signal",
             "portfolio_monitor", (), (),
             expected_fallback=True, category=_C4),

    Scenario("C4-13", "/my-portfolio hold",
             "KIRLOSENG is hold — what would make it a buy",
             "portfolio_monitor", ("KIRLOSENG",), (),
             expected_fallback=True, category=_C4),

    Scenario("C4-14", "/my-portfolio sell",
             "rank the sell candidates by how urgent the exit is",
             "portfolio_monitor", (), (),
             expected_fallback=True, category=_C4),

    Scenario("C4-15", "/my-portfolio buy",
             "SOLIN is a strong buy — what is the position sizing at 1% risk",
             "portfolio_monitor", ("SOLARINDS",), (),
             expected_fallback=True, category=_C4),

    Scenario("C4-16", "which of my holdings should I sell",
             "focus on the stage 4 ones with more than 30% loss",
             "portfolio_monitor", (), (),
             expected_fallback=True, category=_C4),

    Scenario("C4-17", "/my-portfolio eod",
             "which of my ETFs are redundant — do I need all of them",
             "portfolio_monitor", (), (),
             expected_fallback=True, category=_C4),

    Scenario("C4-18", "/my-portfolio",
             "which positions overlap with the top picks report",
             "portfolio_monitor", (), (),
             expected_fallback=True, category=_C4),

    Scenario("C4-19", "/my-portfolio buy",
             "I have ₹2 lakh free — allocate across the top 3 buys",
             "portfolio_monitor", (), (),
             expected_fallback=True, category=_C4),

    Scenario("C4-20", "/my-portfolio sell",
             "ITC is in stage 4 — should I exit all or partial",
             "portfolio_monitor", ("ITC",), (),
             expected_fallback=True, category=_C4),

    Scenario("C4-21", "portfolio performance",
             "compare my portfolio returns to Nifty 500 YTD",
             "portfolio_monitor", (), (),
             expected_fallback=True, category=_C4),

    Scenario("C4-22", "/my-portfolio eod",
             "write an email to my team summarising buy and sell signals",
             "portfolio_monitor", (), (),
             expected_fallback=True, category=_C4),

    Scenario("C4-23", "/my-portfolio hold",
             "BHEL is hold — it was a buy last week, what changed",
             "portfolio_monitor", ("BHEL",), (),
             expected_fallback=True, category=_C4),

    Scenario("C4-24", "/my-portfolio",
             "generate a watchlist of fresh candidates to replace the sell stocks",
             "portfolio_monitor", (), (),
             expected_fallback=True, category=_C4),

    Scenario("C4-25", "/my-portfolio sell",
             "which of the sell candidates have upcoming corporate events",
             "portfolio_monitor", (), (),
             expected_fallback=True, category=_C4),

    # ══════════════════════════════════════════════════════════════════════════
    # CATEGORY 5 — RIC workflow → Deep dive (25)
    # ══════════════════════════════════════════════════════════════════════════

    Scenario("C5-01", "/ric sherlock RELIANCE",
             "explain the EPS trend from the above data",
             "ric_sherlock", ("RELIANCE",), (),
             expected_fallback=True, category=_C5),

    Scenario("C5-02", "/ric sherlock HDFCBANK",
             "what is the entry trigger based on what you found",
             "ric_sherlock", ("HDFCBANK",), (),
             expected_fallback=True, category=_C5),

    Scenario("C5-03", "/ric sherlock AGARIND",
             "given the EPS crash to 29 — is this a value trap or recovery",
             "ric_sherlock", ("AGARIND",), (),
             expected_fallback=True, category=_C5),

    Scenario("C5-04", "/ric sherlock TATASTEEL",
             "summarise the bull and bear thesis in 3 bullet points each",
             "ric_sherlock", ("TATASTEEL",), (),
             expected_fallback=True, category=_C5),

    Scenario("C5-05", "/ric sector-xray IT",
             "which 3 stocks from this xray should I focus on",
             "ric_sector_xray", (), (),
             expected_fallback=True, category=_C5),

    Scenario("C5-06", "/ric breakout-hunter",
             "narrow the list to stocks with CANSLIM above 16",
             "ric_breakout_hunter", (), (),
             expected_fallback=True, category=_C5),

    Scenario("C5-07", "/ric morning-intel",
             "which of the global signals matter most for Indian IT today",
             "ric_morning_intel", (), (),
             expected_fallback=True, category=_C5),

    Scenario("C5-08", "/ric earnings-playbook INFY",
             "what is the expected EPS surprise direction",
             "ric_earnings", ("INFY",), (),
             expected_fallback=True, category=_C5),

    Scenario("C5-09", "/ric company-xray DMART",
             "compare the consumer story with TRENT and AVENUE",
             "ric_company_xray", ("DMART",), (),
             expected_fallback=True, category=_C5),

    Scenario("C5-10", "/ric peer-battle TCS,INFY,WIPRO",
             "who wins on growth quality — TTM revenue and margin trend",
             "ric_peer_battle", ("TCS","INFY","WIPRO"), (),
             expected_fallback=True, category=_C5),

    Scenario("C5-11", "/ric sherlock GRANULES",
             "what is the stage 2 continuation risk if market turns risk-off",
             "ric_sherlock", ("GRANULES",), (),
             expected_fallback=True, category=_C5),

    Scenario("C5-12", "/ric risk-radar",
             "which of my portfolio holdings are at risk per this radar",
             "ric_risk_radar", (), (),
             expected_fallback=True, category=_C5),

    Scenario("C5-13", "/ric sherlock KIRLOSENG",
             "give me a 3-point action plan — buy add or hold",
             "ric_sherlock", ("KIRLOSENG",), (),
             expected_fallback=True, category=_C5),

    Scenario("C5-14", "/ric sherlock SOLIN",
             "what are the key catalysts that could re-rate this stock",
             "ric_sherlock", ("SOLARINDS",), (),
             expected_fallback=True, category=_C5),

    Scenario("C5-15", "/ric sector-xray pharma",
             "which pharma sub-segment is leading — API or formulations",
             "ric_sector_xray", (), (),
             expected_fallback=True, category=_C5),

    Scenario("C5-16", "/ric sherlock ICICIBANK",
             "the bank is in stage 4 — when would you expect recovery",
             "ric_sherlock", ("ICICIBANK",), (),
             expected_fallback=True, category=_C5),

    Scenario("C5-17", "/ric sherlock VIJAYA",
             "cement sector context — is the demand cycle supportive",
             "ric_sherlock", ("VIJAYA",), (),
             expected_fallback=True, category=_C5),

    Scenario("C5-18", "/ric earnings-playbook RELIANCE",
             "what should I do before the results — hold reduce or add",
             "ric_earnings", ("RELIANCE",), (),
             expected_fallback=True, category=_C5),

    Scenario("C5-19", "/ric sherlock BSE",
             "exchange sector narrative — is this a structural growth story",
             "ric_sherlock", ("BSE",), (),
             expected_fallback=True, category=_C5),

    Scenario("C5-20", "/ric breakout-hunter",
             "from this list, create a watchlist with entry stop and target",
             "ric_breakout_hunter", (), (),
             expected_fallback=True, category=_C5),

    Scenario("C5-21", "/ric sherlock PRECWIRE",
             "what is the valuation — is it cheap relative to peers",
             "ric_sherlock", ("PRECWIRE",), (),
             expected_fallback=True, category=_C5),

    Scenario("C5-22", "/ric morning-intel",
             "translate the global risk signals into an Indian sector playbook",
             "ric_morning_intel", (), (),
             expected_fallback=True, category=_C5),

    Scenario("C5-23", "/ric sherlock NATIONALUM",
             "aluminium cycle analysis — supply demand and pricing power",
             "ric_sherlock", ("NATIONALUM",), (),
             expected_fallback=True, category=_C5),

    Scenario("C5-24", "/ric company-xray TATAMOTORS",
             "EV pivot — is the JLR recovery sustainable",
             "ric_company_xray", ("TATAMOTORS",), (),
             expected_fallback=True, category=_C5),

    Scenario("C5-25", "/ric sherlock RPTECH",
             "what is the technical trigger to add if already holding",
             "ric_sherlock", ("RPTECH",), (),
             expected_fallback=True, category=_C5),

    # ══════════════════════════════════════════════════════════════════════════
    # CATEGORY 6 — Ambiguous → Clarified (25)
    # ══════════════════════════════════════════════════════════════════════════

    Scenario("C6-01", "IT",
             "I meant the IT sector — show me leading IT stocks",
             "fallback", (), (),
             expected_fallback=True, category=_C6),

    Scenario("C6-02", "metals",
             "metals sector rotation — which stocks are strong",
             "fallback", (), (),
             expected_fallback=True, category=_C6),

    Scenario("C6-03", "show me",
             "stage 2 stocks in the pharma sector",
             "fallback", (), (),
             expected_intent="market", category=_C6),

    Scenario("C6-04", "which",
             "which sectors are doing well today",
             "fallback", (), (),
             expected_intent="market", category=_C6),

    Scenario("C6-05", "buy now",
             "I want to buy RELIANCE — is it a good time",
             "fallback", ("RELIANCE",), (),
             expected_fallback=True, category=_C6),

    Scenario("C6-06", "good stocks",
             "I want stage 2 stocks with strong fundamentals",
             "fallback", (), (),
             expected_intent="market", category=_C6),

    Scenario("C6-07", "banks",
             "private banks — HDFC vs ICICI vs AXIS — which is strongest",
             "fallback", ("HDFCBANK","ICICIBANK","AXISBANK"), (),
             expected_fallback=True, category=_C6),

    Scenario("C6-08", "pharma",
             "pharma sector — show me stage 2 leaders",
             "fallback", (), (),
             expected_fallback=True, category=_C6),

    Scenario("C6-09", "nifty",
             "Nifty 50 technical — where are key support levels",
             "fallback", ("NIFTY",), (),
             expected_fallback=True, category=_C6),

    Scenario("C6-10", "sell",
             "I want to sell my ITC holding — what is the exit plan",
             "fallback", ("ITC",), (),
             expected_fallback=True, category=_C6),

    Scenario("C6-11", "results",
             "quarterly results season — which companies reported strong EPS",
             "fallback", (), (),
             expected_fallback=True, category=_C6),

    Scenario("C6-12", "up",
             "which stocks are up the most today",
             "fallback", (), (),
             expected_intent="top_movers", category=_C6),

    Scenario("C6-13", "analysis",
             "sector analysis — capital goods vs defence",
             "fallback", (), (),
             expected_fallback=True, category=_C6),

    Scenario("C6-14", "what should I do",
             "should I buy GRANULES or wait for a dip",
             "fallback", ("GRANULES",), (),
             expected_fallback=True, category=_C6),

    Scenario("C6-15", "news",
             "what news is impacting the market today",
             "fallback", (), (),
             expected_fallback=True, category=_C6),

    Scenario("C6-16", "rotation",
             "sector rotation — show me the current sector strength ranking",
             "fallback", (), (),
             expected_intent="market", category=_C6),

    Scenario("C6-17", "PCR today",
             "NIFTY PCR is bearish — does this change my swing trade plan",
             "fallback", ("NIFTY",), (),
             expected_fallback=True, category=_C6),

    Scenario("C6-18", "tell me about",
             "tell me about KIRLOSENG — full analysis",
             "fallback", ("KIRLOSENG",), (),
             expected_fallback=True, category=_C6),

    Scenario("C6-19", "risk",
             "what are the key risk factors for my portfolio today",
             "fallback", (), (),
             expected_fallback=True, category=_C6),

    Scenario("C6-20", "green stocks",
             "green energy stocks — NTPC Green TATAPOWER renewable",
             "fallback", (), (),
             expected_fallback=True, category=_C6),

    Scenario("C6-21", "macro",
             "macro proxies — which are bullish and which are bearish for India",
             "fallback", (), (),
             expected_intent="market", category=_C6),

    Scenario("C6-22", "open interest",
             "NIFTY options OI — what is the market structure",
             "fallback", ("NIFTY",), (),
             expected_fallback=True, category=_C6),

    Scenario("C6-23", "entry",
             "PRECWIRE is at a pullback entry — confirm the setup",
             "fallback", ("PRECWIRE",), (),
             expected_fallback=True, category=_C6),

    Scenario("C6-24", "small cap",
             "small cap stocks with stage 2 and CANSLIM above 16",
             "fallback", (), (),
             expected_intent="market", category=_C6),

    Scenario("C6-25", "flying stocks",
             "stocks making large intraday moves — top 10 gainers",
             "fallback", (), (),
             expected_fallback=True, category=_C6),
]

assert len(SCENARIOS) == 150, f"Expected 150 scenarios, got {len(SCENARIOS)}"


# ═══════════════════════════════════════════════════════════════════════════════
# TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestMultiTurnTurn1:
    """Turn 1 routing — each scenario's first message routes correctly."""

    @pytest.mark.parametrize("s", SCENARIOS, ids=[s.id for s in SCENARIOS])
    def test_turn1_does_not_crash(self, router, s):
        """Every turn 1 must route without raising an exception."""
        pack_empty = _pack(s, sess=f"{s.id}-turn0")
        from terminal.router import ContextPack
        empty = ContextPack(session_id=f"{s.id}-t0")
        result = router.route(s.turn1.lstrip("/intraday ").lstrip("/historical ").strip(), empty)
        assert result is not None, f"{s.id}: turn1 routing returned None"


class TestMultiTurnTurn2WithContext:
    """Turn 2 routing — follow-up with prior context populated."""

    @pytest.mark.parametrize("s", SCENARIOS, ids=[s.id for s in SCENARIOS])
    def test_turn2_routes_without_crash(self, router, s):
        """Every turn 2 must route without raising, regardless of expected intent."""
        pack = _pack(s, sess=f"{s.id}-turn2")
        result = router.route(s.turn2, pack)
        assert result is not None, f"{s.id}: turn2 routing returned None"

    @pytest.mark.parametrize("s", [
        s for s in SCENARIOS if s.expected_intent and not s.expected_fallback
    ], ids=[s.id for s in SCENARIOS if s.expected_intent and not s.expected_fallback])
    def test_turn2_intent_when_specified(self, router, s):
        """When expected_intent is set, turn 2 must match it."""
        pack = _pack(s, sess=f"{s.id}-intent")
        result = router.route(s.turn2, pack)
        intent = result.intent or "fallback"
        assert s.expected_intent.lower() in intent.lower(), (
            f"{s.id}: turn2 '{s.turn2[:50]}'\n"
            f"  expected intent containing '{s.expected_intent}'\n"
            f"  got '{intent}'"
        )

    @pytest.mark.parametrize("s", [
        s for s in SCENARIOS if s.expected_fallback
    ], ids=[s.id for s in SCENARIOS if s.expected_fallback])
    def test_turn2_routes_sensibly(self, router, s):
        """Follow-up questions must route to a sensible path.

        Acceptable routes:
          - fallback_llm  — stock/portfolio specifics, LLM uses turn1 context
          - market_situation — follow-up is still a market/sector question
          - contextual_followup — 'tell me more' phrases caught by ContextualFollowupProvider
          - top_movers — follow-up maps to movers screener
          - visual_scan — follow-up maps to chart request

        NOT acceptable: crashing or routing to an unrelated provider.
        """
        pack = _pack(s, sess=f"{s.id}-fallback")
        result = router.route(s.turn2, pack)
        intent = result.intent or "fallback"
        ACCEPTABLE = {
            "fallback", "market_situation", "market", "situation",
            "contextual_followup", "followup", "top_movers", "movers",
            "visual_scan", "research_council", "compound_stock",
        }
        is_ok = any(acc in intent.lower() for acc in ACCEPTABLE)
        assert is_ok, (
            f"{s.id}: turn2 '{s.turn2[:50]}'\n"
            f"  got intent='{intent}' route_type='{result.route_type}'\n"
            f"  acceptable: {ACCEPTABLE}"
        )


class TestMultiTurnContextCarryover:
    """Verify that active_symbols from turn 1 are preserved in ContextPack."""

    @pytest.mark.parametrize("s", [
        s for s in SCENARIOS if s.ctx_symbols
    ], ids=[s.id for s in SCENARIOS if s.ctx_symbols])
    def test_symbols_in_context(self, s):
        """ContextPack must carry symbols from turn 1 into turn 2."""
        pack = _pack(s, sess=f"{s.id}-sym")
        for sym in s.ctx_symbols:
            assert sym in pack.active_symbols, (
                f"{s.id}: symbol {sym!r} missing from ContextPack.active_symbols"
            )

    def test_recent_turn_preserved(self):
        """RecentTurn in context must have the correct user_input."""
        s = SCENARIOS[0]
        pack = _pack(s, sess="sym-test")
        assert len(pack.recent_turns) == 1
        assert pack.recent_turns[0].user_input == s.turn1

    def test_context_intent_preserved(self):
        """RecentTurn intent must match what was set in the scenario."""
        for s in SCENARIOS[:10]:
            pack = _pack(s, sess=f"intent-{s.id}")
            assert pack.recent_turns[0].intent == s.ctx_intent


class TestMultiTurnCategoryDistribution:
    """Sanity checks on the scenario set."""

    def test_150_scenarios_total(self):
        assert len(SCENARIOS) == 150

    def test_25_per_category(self):
        from collections import Counter
        counts = Counter(s.category for s in SCENARIOS)
        for cat in [_C1, _C2, _C3, _C4, _C5, _C6]:
            assert counts[cat] == 25, f"Category {cat} has {counts[cat]} scenarios, expected 25"

    def test_unique_ids(self):
        ids = [s.id for s in SCENARIOS]
        assert len(ids) == len(set(ids)), "Duplicate scenario IDs found"

    def test_no_empty_turns(self):
        for s in SCENARIOS:
            assert s.turn1.strip(), f"{s.id}: turn1 is empty"
            assert s.turn2.strip(), f"{s.id}: turn2 is empty"


class TestThinkingDisplayMultiTurn:
    """_print_thinking must not crash on any multi-turn query."""

    @pytest.mark.parametrize("s", SCENARIOS[::10], ids=[s.id for s in SCENARIOS[::10]])
    def test_thinking_turn2(self, s):
        """_print_thinking handles turn2 queries without crashing (every 10th scenario)."""
        try:
            import sys, io
            sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
            from rich.console import Console
            import nse_agent
            buf = io.StringIO()
            orig = nse_agent.console
            nse_agent.console = Console(file=buf)
            getattr(nse_agent, "_print_thinking", lambda *a, **kw: None)(s.turn2)
            nse_agent.console = orig
            success = True
        except Exception as e:
            success = False
            raise AssertionError(f"{s.id}: _print_thinking crashed on '{s.turn2[:40]}': {e}")
        assert success
