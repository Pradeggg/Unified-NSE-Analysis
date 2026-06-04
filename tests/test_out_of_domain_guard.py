"""tests/test_out_of_domain_guard.py — Out-of-domain query guard tests.

Verifies that clearly non-financial queries are caught deterministically
BEFORE any LLM call, and that NSE-adjacent / ambiguous queries are allowed
through (conservative guard — never block a valid financial query).
"""
from __future__ import annotations
import pytest
from terminal.router.providers import is_out_of_domain


# ── Queries that MUST be blocked ─────────────────────────────────────────────

@pytest.mark.parametrize("query", [
    "what is the temperature in France",
    "temperature in France",
    "weather in Paris today",
    "What is the weather in London",
    "weather in New York",
    "cricket score today",
    "IPL match result",
    "ipl score",
    "football score",
    "recipe for biryani",
    "restaurant near me",
    "movie review for latest film",
    "symptoms of fever",
    "medicine dosage for paracetamol",
    # "flight to dubai" — ambiguous (airline stocks exist), intentionally not blocked
])
def test_blocks_out_of_domain(query):
    result = is_out_of_domain(query)
    assert result is not None, (
        f"Expected OOD block for '{query}' but got None (allowed through)"
    )
    assert "Agent Adda" in result
    assert "NSE" in result or "market" in result.lower()


# ── Queries that MUST be allowed (conservative — never block finance) ─────────

@pytest.mark.parametrize("query", [
    # Core finance queries
    "what is the temperature of RELIANCE stock today",  # metaphorical "temperature"
    "how hot is the market",       # slang for momentum
    "weather in Adani Ports stock", # company with travel/geo name
    "sector rotation",
    "which sectors are doing well",
    "RELIANCE technical setup",
    "top gainers today",
    "how is the market",
    "FII today",
    "nifty today",
    "GRANULES EPS growth",
    "India pharma sector",
    "how is IT sector",
    "cricket bat manufacturer stocks",   # cricket = industry, not sport score
    "monsoon impact on agri stocks",     # monsoon = agricultural context
    "inflation and pharma",
    "/my-portfolio",                     # slash commands always pass through
    "/scan NIFTY",
    "market overview",
    "stage 2 stocks",
    "advance decline ratio",
    # Ambiguous but lean financial
    "Mumbai stocks today",
    "Indian market sentiment",
    "how hot is the metals sector",
    "rain on Tata Steel",               # very unlikely but must not block
    "temperature check on my portfolio",
])
def test_allows_financial_queries(query):
    result = is_out_of_domain(query)
    assert result is None, (
        f"'{query}' was incorrectly blocked by OOD guard:\n  {result}"
    )


# ── Response format ───────────────────────────────────────────────────────────

def test_ood_response_contains_redirect():
    result = is_out_of_domain("what is the weather in Paris")
    assert result is not None
    assert "weather" in result.lower() or "paris" in result.lower() or "topic" in result.lower()
    assert "portfolio" in result.lower() or "stock" in result.lower() or "sector" in result.lower()


def test_ood_response_is_string():
    result = is_out_of_domain("cricket score today")
    assert isinstance(result, str)
    assert len(result) > 20


def test_empty_query_passes_through():
    """Empty input must not crash and must pass through."""
    assert is_out_of_domain("") is None
    assert is_out_of_domain("   ") is None
    assert is_out_of_domain(None) is None   # type: ignore[arg-type]


def test_slash_commands_not_blocked():
    """Slash commands bypass the guard (guard only operates on NL)."""
    # The is_out_of_domain function itself doesn't know about slashes —
    # the chat loop guards with `not text.startswith('/')` before calling.
    # But even if called directly with slash content, it must not false-positive.
    assert is_out_of_domain("/scan NIFTY") is None
    assert is_out_of_domain("/my-portfolio sell") is None
