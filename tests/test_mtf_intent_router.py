"""Tests for the freeform → /mtf rewrite hook (nse_agent._detect_mtf_intent)."""

import importlib
import os
import sys


def _load():
    # Loading nse_agent triggers a lot of subsystem init at import time; provide
    # the same env shims tests/conftest.py already sets, but be defensive.
    os.environ.setdefault("ASSESSMENT_LLM_ENABLED", "0")
    os.environ.setdefault("AGENT_ADDA_MEMORY_PG", "0")
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return importlib.import_module("nse_agent")


def test_symbol_specific_mtf_prompt_routes_to_single_symbol():
    mod = _load()
    assert mod._detect_mtf_intent("Run MTF on HDFCBANK") == "/mtf HDFCBANK"
    assert mod._detect_mtf_intent("multi timeframe analyse TCS") == "/mtf TCS"
    assert mod._detect_mtf_intent("Show me multi-timeframe view of RELIANCE") == "/mtf RELIANCE"


def test_universe_mtf_prompt_routes_to_scan_bullish_default():
    mod = _load()
    out = mod._detect_mtf_intent("Which stocks are aligned across all timeframes today")
    assert out is not None
    assert out.startswith("/mtf scan")
    assert "bullish" in out


def test_universe_mtf_prompt_picks_bearish_when_requested():
    mod = _load()
    out = mod._detect_mtf_intent("Show bearish multi time frame setups in NIFTY 50")
    assert out is not None
    assert out.startswith("/mtf scan")
    assert "bearish" in out
    assert "NIFTY 50" in out


def test_non_mtf_prompt_returns_none():
    mod = _load()
    assert mod._detect_mtf_intent("Just show me a market overview") is None
    assert mod._detect_mtf_intent("How is the market today?") is None
    assert mod._detect_mtf_intent("RELIANCE technical setup") is None
    assert mod._detect_mtf_intent("") is None


def test_existing_slash_command_not_intercepted():
    mod = _load()
    # If the user already typed /mtf or /something, leave the prompt alone so
    # the existing slash dispatch chain handles it verbatim.
    assert mod._detect_mtf_intent("/mtf RELIANCE") is None
    assert mod._detect_mtf_intent("/scan stage2") is None


def test_typo_in_index_still_routes_to_scan():
    mod = _load()
    out = mod._detect_mtf_intent("multi-timeframe confluence in nifty")
    assert out is not None
    assert out.startswith("/mtf scan")
