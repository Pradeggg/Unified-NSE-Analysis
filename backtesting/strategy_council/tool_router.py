"""Read-only tool surface exposed to the Strategy Council LLM.

The strategist and critics use OpenAI tool calling to fetch additional
evidence (snapshots, breadth, news, results, filings, sector context,
technicals, screeners) during deliberation. All handlers proxy into
``terminal.tools`` / ``terminal.results_tools`` modules so the council reuses
the same code paths as the interactive CLI.

This module is intentionally side-effect free: no writes to disk or
Postgres, no order execution. Failures are caught and returned as
``{"error": ...}`` so the LLM loop never explodes on a single tool failure.
"""

from __future__ import annotations

import json
from typing import Any, Callable


def _safe_call(fn: Callable[..., Any], **kwargs) -> dict[str, Any]:
    try:
        result = fn(**kwargs)
        if isinstance(result, dict):
            return result
        return {"result": result}
    except Exception as exc:  # pragma: no cover - defensive
        return {"error": f"{type(exc).__name__}: {exc}"}


def _tool_get_symbol_snapshot(symbol: str) -> dict[str, Any]:
    from terminal.tools import get_symbol_snapshot

    return _safe_call(get_symbol_snapshot, symbol=symbol)


def _tool_get_market_breadth() -> dict[str, Any]:
    from terminal.tools import get_market_breadth

    return _safe_call(get_market_breadth)


def _tool_search_latest_catalysts(symbol: str, max_results: int = 5) -> dict[str, Any]:
    from terminal.tools import search_latest_catalysts

    return _safe_call(search_latest_catalysts, symbol=symbol, max_results=max_results)


def _tool_get_latest_results(symbol: str) -> dict[str, Any]:
    from terminal.results_tools import get_latest_results

    return _safe_call(get_latest_results, symbol=symbol)


def _tool_get_filing_extract(symbol: str) -> dict[str, Any]:
    from backtesting.strategy_council.evidence_filings import summarise_filing

    summary = summarise_filing(symbol)
    if not summary:
        return {"error": f"No parsed filing available for {symbol}"}
    return summary


def _tool_run_screener_query(screen_type: str = "stage2", top_n: int = 10) -> dict[str, Any]:
    from terminal.tools import run_screener_query

    return _safe_call(run_screener_query, screen_type=screen_type, top_n=top_n)


def _tool_get_sector_context(sector_or_symbol: str) -> dict[str, Any]:
    from terminal.tools import get_sector_context

    return _safe_call(get_sector_context, sector_or_symbol=sector_or_symbol)


def _tool_get_technical_setup(symbol: str, days: int = 400) -> dict[str, Any]:
    from terminal.tools import get_technical_setup

    return _safe_call(get_technical_setup, symbol=symbol, days=days)


def _tool_get_index_snapshot(index_name: str = "NIFTY 50") -> dict[str, Any]:
    from terminal.tools import get_index_snapshot

    return _safe_call(get_index_snapshot, index_name=index_name)


COUNCIL_TOOL_HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
    "get_symbol_snapshot": _tool_get_symbol_snapshot,
    "get_market_breadth": _tool_get_market_breadth,
    "search_latest_catalysts": _tool_search_latest_catalysts,
    "get_latest_results": _tool_get_latest_results,
    "get_filing_extract": _tool_get_filing_extract,
    "run_screener_query": _tool_run_screener_query,
    "get_sector_context": _tool_get_sector_context,
    "get_technical_setup": _tool_get_technical_setup,
    "get_index_snapshot": _tool_get_index_snapshot,
}


COUNCIL_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_symbol_snapshot",
            "description": (
                "Fetch the latest fundamental / valuation snapshot for an NSE symbol "
                "(stage, RSI, P/E, ROE, sector, market cap, etc.)."
            ),
            "parameters": {
                "type": "object",
                "properties": {"symbol": {"type": "string"}},
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_market_breadth",
            "description": "Return current NSE market breadth: advances, declines, A/D ratio, new highs/lows.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_latest_catalysts",
            "description": "Web search for the most recent catalysts/news for a symbol; returns top results.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "max_results": {"type": "integer", "minimum": 1, "maximum": 10},
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_latest_results",
            "description": (
                "Return the latest quarterly results summary for a symbol from the local "
                "results store (revenue, PAT, YoY%, etc.)."
            ),
            "parameters": {
                "type": "object",
                "properties": {"symbol": {"type": "string"}},
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_filing_extract",
            "description": (
                "Return the parsed latest filing summary (pages excerpts, key tables, "
                "headline revenue/PAT/EBITDA/net-debt rows) for a symbol, if present on disk."
            ),
            "parameters": {
                "type": "object",
                "properties": {"symbol": {"type": "string"}},
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_screener_query",
            "description": (
                "Run a pre-built screener (e.g. stage2, 52w_high, vcp, momentum) and return the top N hits."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "screen_type": {"type": "string"},
                    "top_n": {"type": "integer", "minimum": 1, "maximum": 50},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sector_context",
            "description": "Return the sector rotation / relative-strength context for a symbol or sector name.",
            "parameters": {
                "type": "object",
                "properties": {"sector_or_symbol": {"type": "string"}},
                "required": ["sector_or_symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_technical_setup",
            "description": "Return a detailed technical setup for a symbol (trend, levels, RSI, MACD, stage).",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "days": {"type": "integer", "minimum": 60, "maximum": 1500},
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_index_snapshot",
            "description": "Return the latest snapshot for an index (NIFTY 50, NIFTY BANK, etc.).",
            "parameters": {
                "type": "object",
                "properties": {"index_name": {"type": "string"}},
            },
        },
    },
]


def execute_tool(name: str, arguments_json: str) -> str:
    """Dispatch a single LLM tool call by name; always returns a JSON string."""
    handler = COUNCIL_TOOL_HANDLERS.get(name)
    if handler is None:
        return json.dumps({"error": f"unknown tool: {name}"})
    try:
        kwargs = json.loads(arguments_json or "{}")
    except Exception as exc:
        return json.dumps({"error": f"invalid arguments JSON: {exc}"})
    try:
        result = handler(**kwargs) if kwargs else handler()
    except TypeError as exc:
        return json.dumps({"error": f"bad arguments for {name}: {exc}"})
    except Exception as exc:  # pragma: no cover - defensive
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"})
    try:
        return json.dumps(result, default=str)[:24000]
    except Exception as exc:
        return json.dumps({"error": f"could not serialise tool result: {exc}"})


__all__ = [
    "COUNCIL_TOOL_HANDLERS",
    "COUNCIL_TOOL_SCHEMAS",
    "execute_tool",
]
