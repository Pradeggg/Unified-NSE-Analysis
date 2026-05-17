"""First-class entity resolution helpers for Agent Adda.

This module wraps the existing canonical symbol resolver with a stable,
tool-friendly contract. It also centralizes the non-symbol vocabulary that
caused prior grounding failures, such as treating ADX or MA as requested
stock symbols.
"""

from __future__ import annotations

import re
from typing import Any


TECHNICAL_NON_SYMBOL_TERMS: frozenset[str] = frozenset(
    {
        "RS",
        "RSI",
        "ADX",
        "ATR",
        "MA",
        "SMA",
        "EMA",
        "DMA",
        "MACD",
        "VWAP",
        "VCP",
        "ORB",
        "BB",
        "OBV",
        "PE",
        "PB",
        "EPS",
        "ROE",
        "ROCE",
        "EBITDA",
        "CAGR",
        "IV",
        "OI",
        "PCR",
        "FII",
        "DII",
        "FNO",
        "FY",
        "QOQ",
        "YOY",
    }
)


CONTEXT_NON_SYMBOL_TERMS: frozenset[str] = frozenset(
    {
        "ANALYSIS",
        "ASSESSMENT",
        "BRIEF",
        "CONTEXT",
        "DETAILED",
        "FUNDAMENTAL",
        "FUNDAMENTALS",
        "REPORT",
        "RESEARCH",
        "RESULT",
        "RESULTS",
        "SETUP",
        "STOCK",
        "STOCKS",
        "STRATEGY",
        "TECHNICAL",
        "TECHNICALS",
        "TRADE",
        "TRADING",
        "WITH",
        "AND",
        "FOR",
        "THE",
        "SHOW",
        "TELL",
        "GIVE",
        "WHAT",
        "HOW",
        # English connectives / instruction-template words that appear in
        # /analyze, /canslim and other slash-command rewrites. None of these
        # are valid NSE tickers and must never trigger symbol-grounding
        # mismatches.
        "ALL",
        "ANY",
        "AVOID",
        "BUY",
        "CALL",
        "CALLS",
        "DATA",
        "DO",
        "DROP",
        "EACH",
        "EXECUTE",
        "FROM",
        "HOLD",
        "INTO",
        "IN",
        "NEW",
        "NOT",
        "ORDER",
        "PASS",
        "PERFORM",
        "READ",
        "SELL",
        "SKIP",
        "THEN",
        "THESE",
        "USE",
        "USING",
        "VERDICT",
    }
)


INDEX_ALIASES: dict[str, str] = {
    "NIFTY": "NIFTY",
    "NIFTY50": "NIFTY",
    "NIFTY 50": "NIFTY",
    "BANKNIFTY": "BANKNIFTY",
    "BANK NIFTY": "BANKNIFTY",
    "NIFTY BANK": "BANKNIFTY",
    "FINNIFTY": "FINNIFTY",
    "NIFTY FINANCIAL": "FINNIFTY",
    "MIDCPNIFTY": "MIDCPNIFTY",
    "MIDCAP NIFTY": "MIDCPNIFTY",
    "NIFTY MIDCAP SELECT": "MIDCPNIFTY",
}


def _tokenize_upper(text: str) -> list[str]:
    return [t.upper() for t in re.findall(r"\b[A-Za-z][A-Za-z0-9&-]{1,12}\b", text or "")]


def _normalise_phrase(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().upper())


def detect_non_symbol_terms(text: str) -> dict:
    """Detect market/technical vocabulary that should not be resolved as tickers."""
    terms = sorted(dict.fromkeys(t for t in _tokenize_upper(text) if t in TECHNICAL_NON_SYMBOL_TERMS))
    return {
        "text": text,
        "terms": terms,
        "count": len(terms),
        "classification": "technical_or_market_terms",
    }


def _resolve_symbol_via_tools(query: str) -> dict:
    from terminal.tools import resolve_symbol

    result = resolve_symbol(query)
    return result if isinstance(result, dict) else {"symbol": None, "confidence": "none", "query": query}


def resolve_stock_entity(query: str) -> dict:
    """Resolve a stock/company alias to a canonical NSE equity symbol."""
    raw = str(query or "").strip()
    if not raw:
        return {
            "query": query,
            "entity_type": "stock",
            "status": "unresolved",
            "canonical_symbol": None,
            "confidence": "none",
            "error": "Empty entity query",
        }

    upper = _normalise_phrase(raw)
    if upper in TECHNICAL_NON_SYMBOL_TERMS:
        return {
            "query": query,
            "entity_type": "non_symbol_term",
            "status": "not_a_symbol",
            "canonical_symbol": None,
            "confidence": "none",
            "term": upper,
            "error": f"'{raw}' is a technical/market term, not a stock symbol.",
        }
    if upper in INDEX_ALIASES:
        return {
            "query": query,
            "entity_type": "index",
            "status": "resolved",
            "canonical_symbol": INDEX_ALIASES[upper],
            "confidence": "exact",
            "matched": upper,
        }

    resolved = _resolve_symbol_via_tools(raw)
    symbol = resolved.get("symbol")
    status = "resolved" if symbol else "unresolved"
    out: dict[str, Any] = {
        "query": query,
        "entity_type": "stock",
        "status": status,
        "canonical_symbol": str(symbol).upper() if symbol else None,
        "confidence": resolved.get("confidence") or "none",
    }
    for key in ("matched", "name", "candidates", "error"):
        if key in resolved:
            out[key] = resolved[key]
    if not symbol and "error" not in out:
        out["error"] = f"No NSE stock symbol found for '{raw}'"
    return out


def resolve_company_alias(alias: str) -> dict:
    """Resolve a company alias/name and preserve the original alias in output."""
    result = resolve_stock_entity(alias)
    result["alias"] = alias
    return result


def resolve_index_or_stock(query: str) -> dict:
    """Resolve an index/derivative underlying first, otherwise resolve as stock."""
    upper = _normalise_phrase(query)
    if upper in INDEX_ALIASES:
        return {
            "query": query,
            "entity_type": "index",
            "status": "resolved",
            "canonical_symbol": INDEX_ALIASES[upper],
            "confidence": "exact",
            "matched": upper,
        }
    return resolve_stock_entity(query)


def _requested_symbol_tokens(text: str) -> list[str]:
    symbols: list[str] = []
    for raw in re.findall(r"\b[A-Z][A-Z0-9&-]{1,12}\b", text or ""):
        token = raw.strip().upper()
        if token in TECHNICAL_NON_SYMBOL_TERMS:
            continue
        if token in CONTEXT_NON_SYMBOL_TERMS:
            continue
        if token in {"NSE", "BSE", "PDF", "URL", "HTML", "EOD", "DB", "PG", "API", "LLM", "AI"}:
            continue
        if re.fullmatch(r"[A-Z0-9&-]{2,12}", token):
            symbols.append(token)
    return list(dict.fromkeys(symbols))


def validate_requested_symbols(query: str, executed_symbols: list[str] | None = None) -> dict:
    """Compare explicit ticker-looking user tokens against executed evidence symbols."""
    requested = _requested_symbol_tokens(query)
    ignored = detect_non_symbol_terms(query)["terms"]
    executed = [str(s).strip().upper() for s in (executed_symbols or []) if str(s).strip()]
    missing = [sym for sym in requested if sym not in executed]
    unrequested = [sym for sym in executed if sym not in requested]
    return {
        "query": query,
        "requested_symbols": requested,
        "executed_symbols": executed,
        "ignored_terms": ignored,
        "missing_symbols": missing,
        "unrequested_symbols": unrequested,
        "status": "ok" if not missing and not unrequested else "mismatch",
    }
