from unittest.mock import patch

import pytest

from terminal.entity_resolution import (
    detect_non_symbol_terms,
    resolve_company_alias,
    resolve_index_or_stock,
    resolve_stock_entity,
    validate_requested_symbols,
)
from terminal.tools import call_tool


def test_usl_alias_resolves_to_united_spirits_not_unrelated_fuzzy_match():
    result = resolve_stock_entity("USL")

    assert result["status"] == "resolved"
    assert result["canonical_symbol"] == "UNITDSPR"
    assert result["entity_type"] == "stock"


def test_company_name_alias_resolves_to_canonical_symbol():
    result = resolve_company_alias("United Spirits")

    assert result["canonical_symbol"] == "UNITDSPR"
    assert result["alias"] == "United Spirits"


def test_technical_terms_are_detected_not_treated_as_symbols():
    result = detect_non_symbol_terms("SAKAR RSI ADX MA MACD setup")

    assert result["terms"] == ["ADX", "MA", "MACD", "RSI"]
    assert result["count"] == 4


def test_index_names_resolve_as_index_underlyings_not_equity_symbols():
    assert resolve_index_or_stock("NIFTY")["entity_type"] == "index"
    assert resolve_index_or_stock("NIFTY 50")["canonical_symbol"] == "NIFTY"
    assert resolve_index_or_stock("BANKNIFTY")["canonical_symbol"] == "BANKNIFTY"
    assert resolve_index_or_stock("BANK NIFTY")["entity_type"] == "index"


def test_exact_uppercase_symbol_wins_over_fuzzy_name_match():
    with patch(
        "terminal.tools._all_symbols_map",
        return_value={"ABC": "ABC", "ABC INDUSTRIES LIMITED": "XYZ", "ABCD": "ABCD"},
    ), patch("terminal.tools._get_live_session") as live_session:
        result = resolve_stock_entity("ABC")

    assert result["status"] == "resolved"
    assert result["canonical_symbol"] == "ABC"
    assert result["confidence"] == "exact"
    live_session.assert_not_called()


def test_unresolved_exact_ticker_returns_explicit_unresolved_status():
    with patch(
        "terminal.tools._all_symbols_map",
        return_value={"NIVABUPA": "NIVABUPA", "NAVA": "NAVA"},
    ), patch("terminal.tools._get_live_session") as live_session:
        result = resolve_stock_entity("NAVABUPA")

    assert result["status"] == "unresolved"
    assert result["canonical_symbol"] is None
    assert "No exact NSE symbol found" in result["error"]


def test_validate_requested_symbols_ignores_indicator_terms():
    result = validate_requested_symbols(
        "technical setup for SAKAR with ADX and MA",
        executed_symbols=["SAKAR"],
    )

    assert result["requested_symbols"] == ["SAKAR"]
    assert result["ignored_terms"] == ["ADX", "MA"]
    assert result["missing_symbols"] == []
    assert result["status"] == "ok"


def test_validate_requested_symbols_drops_company_name_words():
    """English words that show up inside multi-word company names — LEVER
    in HINDUSTAN LEVER, BHARAT, INDIA, LIMITED, etc. — must not be treated
    as requested tickers. The agent resolves the actual symbol via aliases.
    """
    result = validate_requested_symbols(
        "p18 for HINDUSTAN LEVER",
        executed_symbols=["HINDUNILVR"],
    )

    assert "LEVER" not in result["requested_symbols"]
    assert "HINDUSTAN" not in result["requested_symbols"]
    assert result["missing_symbols"] == []


def test_validate_requested_symbols_still_flags_misspelled_tickers():
    """If the user types a token that isn't a known ticker and isn't a
    common English word (e.g. NAVABUPA), it must still surface as a
    requested-but-not-executed mismatch so silent fuzzy substitutions
    by the resolver are caught.
    """
    result = validate_requested_symbols(
        "NAVABUPA technical setup",
        executed_symbols=["TALBROAUTO"],
    )

    assert "NAVABUPA" in result["requested_symbols"]
    assert "NAVABUPA" in result["missing_symbols"]
    assert result["status"] == "mismatch"


def test_entity_resolution_tools_are_registered():
    result = call_tool("detect_non_symbol_terms", {"text": "RSI ADX for SAKAR"})

    assert result["terms"] == ["ADX", "RSI"]


# ---------------------------------------------------------------------------
# Index-name phrase suppression
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query", [
    "lets analyze NIFTY SMALLCAP 100",
    "how is NIFTY SMALLCAP 100 doing today",
    "NIFTY SMALLCAP 100 trend",
    "show me NIFTY SMALLCAP 100 performance",
    "NIFTY MIDCAP 100",
    "NIFTY MIDCAP 150 trend",
    "NIFTY BANK",
    "NIFTY IT performance",
    "NIFTY PHARMA",
    "NIFTY FMCG",
    "NIFTY OIL & GAS",
    "NIFTY FINANCIAL SERVICES",
    "NIFTY NEXT 50",
    "NIFTY 500",
    "BANK NIFTY",
])
def test_index_name_does_not_surface_as_requested_symbol(query):
    """Regression: 'lets analyze NIFTY SMALLCAP 100' must not surface
    SMALLCAP (or any other index component word) as a 'requested' ticker
    in the symbol-validation gate. The whole index phrase is stripped
    before tokenization.
    """
    result = validate_requested_symbols(query, executed_symbols=[])
    forbidden = {
        "SMALLCAP", "MIDCAP", "LARGEMIDCAP", "MICROCAP", "MIDSMALLCAP",
        "BANK", "IT", "PHARMA", "FMCG", "OIL", "GAS", "FINANCIAL",
        "SERVICES", "NEXT",
    }
    leaked = forbidden & set(result["requested_symbols"])
    assert not leaked, (
        f"query={query!r} leaked index-component tokens "
        f"{sorted(leaked)} into requested_symbols={result['requested_symbols']}"
    )


def test_index_phrase_strip_preserves_following_tickers():
    """If the user genuinely mentions a ticker after an index phrase
    (e.g. 'NIFTY 50 vs RELIANCE'), the ticker must survive stripping."""
    result = validate_requested_symbols("NIFTY 50 vs RELIANCE", executed_symbols=[])
    assert "RELIANCE" in result["requested_symbols"]


def test_index_phrase_strip_preserves_following_ticker_after_and():
    """'NIFTY AND RELIANCE' — closed-vocabulary stripping must NOT
    consume the conjunction-gap up to RELIANCE."""
    result = validate_requested_symbols("NIFTY AND RELIANCE", executed_symbols=[])
    assert "RELIANCE" in result["requested_symbols"]
