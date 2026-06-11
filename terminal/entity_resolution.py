"""First-class entity resolution helpers for Agent Adda.

This module wraps the existing canonical symbol resolver with a stable,
tool-friendly contract. It also centralizes the non-symbol vocabulary that
caused prior grounding failures, such as treating ADX or MA as requested
stock symbols.
"""

from __future__ import annotations

import csv
import os
import re
import threading
import time
from pathlib import Path
from typing import Any


_BASE = Path(__file__).resolve().parent.parent
_DATA = _BASE / "data"


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
        "PAT",
        "PBT",
        "OPM",
        "NPM",
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
        "F&O",
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
        # Common English uppercase words that appear inside company names
        # (e.g. "HINDUSTAN LEVER", "BHARAT FORGE") but are themselves not
        # NSE tickers. The agent resolves the actual ticker via aliases.
        "ABOUT",
        "AUTO",
        "BANK",
        "BEARISH",
        "BHARAT",
        "BIG",
        "BOTTOM",
        "BREAK",
        "BREAKDOWN",
        "BREAKOUT",
        "BULLISH",
        "CEMENT",
        "COAL",
        "COMPANIES",
        "COMPANY",
        "CORP",
        "CORPORATION",
        "DAILY",
        "EVENING",
        "FINANCE",
        "FINANCIAL",
        "GAP",
        "GAS",
        "GOOD",
        "GROUP",
        "HIGH",
        "HINDUSTAN",
        "HOLDINGS",
        "HOTEL",
        "HOTELS",
        "INC",
        "INDIA",
        "INDIAN",
        "INDUSTRIES",
        "INTERNATIONAL",
        "LAST",
        "LEVER",
        "LIMITED",
        "LOW",
        "LTD",
        "MANUFACTURING",
        "MARKET",
        "MONTHLY",
        "MORNING",
        "MOTOR",
        "NATIONAL",
        "OLD",
        "PEAK",
        "PHARMA",
        "PHARMACEUTICALS",
        "PIVOT",
        "POWER",
        "PRICE",
        "PRODUCTS",
        "RANGE",
        "RESISTANCE",
        "SERVICES",
        "STEEL",
        "SUPPORT",
        "TECHNOLOGIES",
        "TECHNOLOGY",
        "TOP",
        "TRADING",
        "TRENDING",
        "VOLUME",
        "WEEKLY",
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
    for key in ("matched", "name", "candidates", "confidence_band", "score", "method", "error"):
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


_INDEX_COMPONENT_WORDS = (
    # Tier / cap segmentation
    "50", "100", "200", "250", "500",
    "NEXT", "TOTAL", "MARKET",
    "LARGECAP", "MIDCAP", "SMALLCAP", "MICROCAP", "LARGEMIDCAP", "MIDSMALLCAP",
    # Sectoral / thematic indices published by NSE
    "BANK", "AUTO", "FMCG", "IT", "MEDIA", "METAL", "PHARMA", "REALTY",
    "ENERGY", "INFRA", "PSU", "PVT", "PSE", "CPSE", "MNC", "FIN", "SERVICE",
    "SERVICES", "HEALTHCARE", "COMMODITIES", "OIL", "GAS",
    "CONSUMER", "DURABLES", "DEFENCE", "MANUFACTURING", "CONSUMPTION",
    "TOURISM", "RAILWAYS", "CORE", "HOUSING", "MOBILITY", "EV", "AGE",
    "AUTOMOTIVE", "TRANSPORTATION", "LOGISTICS", "TELECOM",
    "DIVIDEND", "OPPORTUNITIES", "GROWTH", "SECTORS",
    "HIGH", "LOW", "BETA", "ALPHA", "QUALITY", "VALUE", "VOLATILITY",
    "FINANCIAL", "INDIA", "NEW", "PRIVATE", "INDEX",
)


# Sort component words by descending length so longer alternations (FINANCIAL,
# HEALTHCARE) match before their shorter prefixes (FIN, HEALTH) in Python's
# left-to-right alternation. Without this, "NIFTY FINANCIAL SERVICES" would
# match "NIFTY FIN" + leave "ANCIAL SERVICES" behind.
_INDEX_PHRASE_RE = re.compile(
    # Uppercase NSE index prefix + optional component words from a closed
    # vocabulary + optional numeric tier. Closed-vocab matching protects
    # legitimate tickers that may follow ("NIFTY 50 vs RELIANCE" keeps
    # RELIANCE; "NIFTY OIL & GAS" is consumed entirely). Case-sensitive
    # uppercase only — aligned with the upstream tokenizer.
    r"\b(?:BANK\s+NIFTY|BANKNIFTY|FINNIFTY|MIDCPNIFTY|SENSEX|NIFTY)"
    r"(?:\s+(?:"
    + "|".join(sorted(_INDEX_COMPONENT_WORDS, key=len, reverse=True))
    + r"|&))*"
    r"(?:\s+\d{1,4})?"
)


def _strip_index_phrases(text: str) -> str:
    """Remove NSE/BSE multi-word index names from a query so their component
    words (SMALLCAP, MIDCAP, BANK, etc.) do not surface as fake tickers in
    symbol-validation. This is intentionally permissive — extra trailing
    words like "NIFTY SMALLCAP 100 trend" are partly consumed (trailing
    'trend' has lowercase so stays). The goal is suppressing index-component
    tokens, not full NLP parsing.
    """
    if not text:
        return text
    return _INDEX_PHRASE_RE.sub(" ", text)


def _requested_symbol_tokens(text: str) -> list[str]:
    universe = _load_symbol_universe()
    symbols: list[str] = []
    # Strip well-known multi-word index names first so component tokens
    # (SMALLCAP, MIDCAP, BANK, etc.) inside e.g. "NIFTY SMALLCAP 100" are
    # not treated as user-requested tickers.
    scrubbed = _strip_index_phrases(text or "")
    for raw in re.findall(r"\b[A-Z][A-Z0-9&-]{1,12}\b", scrubbed):
        token = raw.strip().upper().rstrip("-")
        if not re.fullmatch(r"[A-Z0-9&-]{2,12}", token):
            continue
        # Positive ground truth: anything in the real NSE symbol universe is
        # definitely a ticker — never drop it via skip-lists.
        if universe and token in universe:
            symbols.append(token)
            continue
        if token in TECHNICAL_NON_SYMBOL_TERMS:
            continue
        if token in CONTEXT_NON_SYMBOL_TERMS:
            continue
        if token in {"NSE", "BSE", "PDF", "URL", "HTML", "EOD", "DB", "PG", "API", "LLM", "AI"}:
            continue
        # Token isn't in the universe and isn't a known non-symbol word — keep
        # it so misspelled tickers (e.g. NAVABUPA) still surface as
        # "requested but never executed" mismatches downstream.
        symbols.append(token)
    return list(dict.fromkeys(symbols))


# ---------------------------------------------------------------------------
# Symbol universe loader — preferred ground truth for `_requested_symbol_tokens`
# ---------------------------------------------------------------------------

_UNIVERSE_LOCK = threading.Lock()
_UNIVERSE_CACHE: dict[str, Any] = {"symbols": None, "loaded_at": 0.0, "source": None}
_UNIVERSE_TTL_SECONDS = 60 * 60 * 6  # 6 hours; PG-resident universe rarely changes
_PG_DSN_DEFAULT = (
    os.environ.get("AGENT_ADDA_PG_DSN")
    or os.environ.get("PG_DSN")
    or "dbname=nse_market user=nse_admin host=/tmp"
)


def _load_symbol_universe() -> frozenset[str]:
    """Return the set of valid NSE symbols, cached for 6h.

    Resolution order:
      1. Test override env var ``NSE_SYMBOL_UNIVERSE`` (comma-separated).
      2. ``market.equity_eod`` in PostgreSQL (authoritative; ~2700 symbols).
      3. ``data/nse_sec_full_data.csv`` (fallback when PG unavailable).
      4. ``data/index_stock_mapping.csv`` (last-resort fallback).
    Returns an empty set on total failure so callers degrade to legacy
    skip-list behaviour.
    """
    override = os.environ.get("NSE_SYMBOL_UNIVERSE")
    if override:
        return frozenset(s.strip().upper() for s in override.split(",") if s.strip())

    with _UNIVERSE_LOCK:
        cached = _UNIVERSE_CACHE.get("symbols")
        if cached is not None and (time.time() - _UNIVERSE_CACHE["loaded_at"]) < _UNIVERSE_TTL_SECONDS:
            return cached

        symbols: set[str] = set()
        source = "none"

        # 1. PostgreSQL
        try:
            import psycopg2  # type: ignore
            dsn = os.environ.get("PG_DSN", _PG_DSN_DEFAULT)
            with psycopg2.connect(dsn, connect_timeout=2) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT DISTINCT symbol FROM market.equity_eod")
                    for (s,) in cur.fetchall():
                        if s:
                            symbols.add(str(s).strip().upper())
            if symbols:
                source = "market.equity_eod"
        except Exception:
            symbols = set()

        # 2. CSV fallback
        if not symbols:
            csv_path = _DATA / "nse_sec_full_data.csv"
            if csv_path.exists():
                try:
                    with csv_path.open() as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            s = (row.get("SYMBOL") or row.get("symbol") or "").strip().upper()
                            if s:
                                symbols.add(s)
                    if symbols:
                        source = "nse_sec_full_data.csv"
                except Exception:
                    pass

        # 3. Index-mapping fallback
        if not symbols:
            idx_path = _DATA / "index_stock_mapping.csv"
            if idx_path.exists():
                try:
                    with idx_path.open() as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            s = (row.get("STOCK_SYMBOL") or "").strip().upper()
                            if s:
                                symbols.add(s)
                    if symbols:
                        source = "index_stock_mapping.csv"
                except Exception:
                    pass

        result = frozenset(symbols)
        _UNIVERSE_CACHE["symbols"] = result
        _UNIVERSE_CACHE["loaded_at"] = time.time()
        _UNIVERSE_CACHE["source"] = source
        return result


def reset_symbol_universe_cache() -> None:
    """Test hook — clear the cached universe so the next call reloads."""
    with _UNIVERSE_LOCK:
        _UNIVERSE_CACHE["symbols"] = None
        _UNIVERSE_CACHE["loaded_at"] = 0.0
        _UNIVERSE_CACHE["source"] = None


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
