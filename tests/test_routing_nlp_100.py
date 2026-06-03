"""tests/test_routing_nlp_100.py — 100-query NLP routing coverage test.

Verifies that the UnifiedRouter correctly dispatches natural-language
queries to the right provider/intent across four difficulty levels:

  Simple   (25) — single-intent, unambiguous
  Medium   (25) — multi-word, slightly harder, context-dependent
  Complex  (25) — research-level, compound screeners, multi-condition
  Ambiguous(25) — bare words, jargon, edge cases

Expected routes (per provider):
  market_situation → MarketSituationProvider
  top_movers       → TopMoversProvider
  visual_scan      → VisualScanProvider
  fallback         → fallback_llm (LLM handles — e.g. specific stocks,
                     multi-stock comparisons that need full reasoning)

Design rules:
  - Multi-stock COMPARISON queries ("compare X and Y", "X vs Y") correctly
    fall to fallback_llm — CompoundStockProvider handles multi-facet single
    stock, not peer comparisons.
  - Stock chart queries ("TATAMOTORS chart") correctly go to VisualScanProvider.
  - Bare unambiguous market words ("market", "sectors", "breadth", "fii")
    route to MarketSituationProvider when query length ≤ 3 tokens.
"""
from __future__ import annotations
import pytest
from terminal.router import UnifiedRouter, ContextPack

@pytest.fixture(scope="module")
def router():
    return UnifiedRouter()

@pytest.fixture(scope="module")
def pack():
    return ContextPack(session_id="nlp-100-qa")


def _route(router, pack, query):
    result = router.route(query, pack)
    return (
        f"{result.intent or ''} "
        f"{result.reasoning_summary.selected_branch or ''} "
        f"{result.route_type or ''}"
    ).lower()


def _check(router, pack, query, expected):
    combined = _route(router, pack, query)
    # Match either "market situation" (space) or "market_situation" (underscore form)
    exp_space = expected.lower().replace("_", " ")
    exp_under = expected.lower()
    assert exp_space in combined or exp_under in combined, (
        f"'{query}'\n  expected '{expected}' in route string\n  got: '{combined}'"
    )


# ── SIMPLE ────────────────────────────────────────────────────────────────────

class TestSimple:
    @pytest.mark.parametrize("query", [
        "how is the market today",
        "what is nifty doing",
        "how is nifty today",
        "market overview",
        "market breadth",
        "which sectors are doing well",
        "sector rotation",
        "which sectors are outperforming",
        "what sectors are leading",
        "sector performance today",
        "show me stage 2 stocks",
        "screener",
        "scan nifty 50",
        "breakout scan",
        "VCP scan",
    ])
    def test_market_situation(self, router, pack, query):
        _check(router, pack, query, "market_situation")

    @pytest.mark.parametrize("query", [
        "top gainers today",
        "top losers nifty 500",
        "biggest movers today",
        "what are the top movers",
        "which stocks are up the most",
    ])
    def test_top_movers(self, router, pack, query):
        _check(router, pack, query, "top_movers")

    @pytest.mark.parametrize("query", [
        "RELIANCE share price",
        "HDFC Bank today",
        "Infosys technical",
        "TCS fundamentals",
    ])
    def test_fallback(self, router, pack, query):
        _check(router, pack, query, "fallback")

    def test_chart_goes_to_visual_scan(self, router, pack):
        _check(router, pack, "TATAMOTORS chart", "visual_scan")


# ── MEDIUM ────────────────────────────────────────────────────────────────────

class TestMedium:
    @pytest.mark.parametrize("query", [
        "what sectors are doing well today in the market",
        "give me an overview of how the market is performing",
        "which sectors should I be looking at right now",
        "where is the money flowing in the market today",
        "what is the current market sentiment",
        "stocks hitting 52 week high today",
        "show me momentum leaders",
        "how are IT stocks performing compared to pharma",
        "intraday scan on nifty bank",
        "relative strength leaders today",
        "what does the stage distribution look like",
        "how many stocks are in stage 2 today",
        "show advance decline ratio",
        "nifty bank sector outlook",
        "is pharma sector strong",
        "show me the FII DII activity today",
        "macro proxies and market signals",
    ])
    def test_market_situation(self, router, pack, query):
        _check(router, pack, query, "market_situation")

    @pytest.mark.parametrize("query", [
        "top 5 gainers in nifty 500",
        "show me the biggest losers in midcap today",
        "which stocks gained the most this week",
    ])
    def test_top_movers(self, router, pack, query):
        _check(router, pack, query, "top_movers")

    @pytest.mark.parametrize("query", [
        "compare HDFC Bank and ICICI Bank",
        "RELIANCE vs ONGC performance",
        "WIPRO RSI and trend",
        "give me the MACD for Bajaj Finance",
        "what is the support level for NIFTY",
    ])
    def test_fallback(self, router, pack, query):
        _check(router, pack, query, "fallback")


# ── COMPLEX ───────────────────────────────────────────────────────────────────

class TestComplex:
    @pytest.mark.parametrize("query", [
        "which stage 2 stocks in IT sector have RSI below 60 and strong relative strength",
        "give me the top sector rotation leaders and their VCP setups",
        "which sectors are outperforming nifty 500 on a 1 month basis",
        "show me the breadth of the market along with sector strength ranking",
        "which sectors have strong fundamentals and bullish stage 2 momentum",
        "show me stage 2 stocks with CANSLIM score above 18 and supertrend bullish",
        "what are the top 10 momentum stocks across metals and capital goods",
        "identify stocks that entered stage 2 in the last 7 days",
        "how is global market impacting Indian IT sector today",
        "which FII-backed stocks are in stage 2 with bullish supertrend",
        "show me the sector rotation pattern over the last month",
        "top pharma stocks by relative strength with earnings growth above 20%",
        "what is the current market regime and which sectors benefit",
        "give me a deep analysis of Nifty IT — technicals breadth and top picks",
        "which auto stocks are outperforming on strong volume today",
        "are midcap stocks showing better breadth than largecaps today",
        "what sectors are benefiting from the weak rupee today",
        "screen for energy stocks at 52-week high with strong institutional buying",
        "which small cap stocks have strong CANSLIM score and are in stage 2",
        "what is the global risk impact on Indian markets today",
    ])
    def test_market_situation(self, router, pack, query):
        _check(router, pack, query, "market_situation")

    @pytest.mark.parametrize("query", [
        "compare HDFC Bank ICICI Bank Kotak Bank on technicals",
        "RELIANCE vs ONGC vs BP — oil sector comparison",
        "TATASTEEL technical setup with volume analysis and peer comparison",
        "give me HDFC Bank Q4 earnings analysis with forward guidance",
        "compare the MTF setup of RELIANCE INFY and TCS",
    ])
    def test_fallback(self, router, pack, query):
        _check(router, pack, query, "fallback")


# ── AMBIGUOUS ─────────────────────────────────────────────────────────────────

class TestAmbiguous:
    @pytest.mark.parametrize("query", [
        "IT", "metals", "banks", "up", "show me",
        "which", "what", "good stocks", "buy now", "what should I buy",
        "pharma", "nifty", "rotation",
        "green stocks", "flying stocks",
        "news", "results", "open interest", "PCR today",
    ])
    def test_fallback(self, router, pack, query):
        _check(router, pack, query, "fallback")

    @pytest.mark.parametrize("query", [
        "market", "sectors", "breadth", "advance decline", "FII today",
    ])
    def test_market_situation(self, router, pack, query):
        _check(router, pack, query, "market_situation")

    def test_hot_today_is_top_movers(self, router, pack):
        _check(router, pack, "what's hot today", "top_movers")
