"""
agent_adda/web_api/trace_extract.py — Extract T2S sidebar data from the Agent trace.

The CLI Agent.query() returns a trace list where each item is one of:
  {"tool": "get_symbol_snapshot",  "result": {...}, ...}
  {"tool": "get_technical_setup",  "result": {...}, ...}
  {"tool": "get_market_breadth",   "result": {...}, ...}
  {"tool": "get_index_snapshot",   "result": {...}, ...}
  {"tool": "run_screener_query",   "result": {...}, ...}
  {"step": "unified_router",       "decision": {...}}
  ...

This module pulls that structured data back out into the shapes that
TalkChatResponse expects: comparison[], market_context[], screener_results[],
evidence[], symbols[].
"""
from __future__ import annotations

from datetime import date
from typing import Any

from .schemas import TalkEvidenceItem

# ── helpers ────────────────────────────────────────────────────────────────────

def _str(v: Any) -> str:
    return str(v) if v is not None else ""


def _coerce_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "").replace("%", "").strip())
    except Exception:
        return None


def _fmt(value: Any, suffix: str = "") -> str:
    num = _coerce_float(value)
    if num is None:
        return "n/a"
    return f"{num:,.1f}{suffix}"


def _score_label(value: Any) -> str:
    num = _coerce_float(value)
    if num is None:
        return "n/a"
    if num >= 75:
        return "strong"
    if num >= 60:
        return "constructive"
    if num >= 45:
        return "mixed"
    return "weak"


_PRICE_FIELDS = ("price", "live_price", "db_price", "current_price", "latest_close")


def _first_price(snapshot: dict, technicals: dict) -> Any:
    for f in _PRICE_FIELDS:
        if snapshot.get(f) not in (None, ""):
            return snapshot[f]
        if technicals.get(f) not in (None, ""):
            return technicals[f]
    return None


# ── trace scanning ─────────────────────────────────────────────────────────────

def _tool_results(trace: list[dict]) -> list[dict]:
    """Return only tool-result items (have a 'tool' key)."""
    return [t for t in trace if isinstance(t, dict) and "tool" in t]


def _results_by_tool(trace: list[dict]) -> dict[str, list[dict]]:
    """Group trace items by tool name → list of result dicts."""
    out: dict[str, list[dict]] = {}
    for item in _tool_results(trace):
        tool = str(item.get("tool") or "")
        result = item.get("result") or item.get("data") or {}
        if not isinstance(result, dict):
            # Some tools return lists; wrap them
            result = {"results": result}
        out.setdefault(tool, []).append(result)
    return out


# ── comparison rows ────────────────────────────────────────────────────────────

def _comparison_row(snapshot: dict, technicals: dict) -> dict[str, Any]:
    """Build a T2S comparison row from snapshot + technicals dicts."""
    sym = _str(snapshot.get("symbol") or snapshot.get("ticker") or "")
    fund_score = (
        snapshot.get("enhanced_fund_score")
        or snapshot.get("fundamental_score")
        or snapshot.get("investment_score")
    )
    tech_score = snapshot.get("technical_score") or technicals.get("technical_score")
    stage = _str(snapshot.get("stage") or technicals.get("stage") or "")
    trend = _str(snapshot.get("trend_signal") or "")
    if "STAGE_2" in stage.upper() and _coerce_float(tech_score) is not None and (_coerce_float(tech_score) or 0) >= 60:
        tech_assess = "constructive uptrend setup"
    elif "BEARISH" in trend.upper() or (_coerce_float(tech_score) or 100) < 45:
        tech_assess = "weak or cautious technical setup"
    else:
        tech_assess = f"{_score_label(tech_score)} technical setup"
    fund_label = _score_label(fund_score)
    fund_assess = f"{fund_label} fundamental profile" if fund_label != "n/a" else "fundamental score unavailable"
    as_of = _str(
        snapshot.get("snapshot_date")
        or snapshot.get("price_date")
        or date.today().isoformat()
    )
    return {
        "symbol": sym,
        "company": snapshot.get("company_name") or snapshot.get("name") or sym,
        "price": _first_price(snapshot, technicals),
        "stage": stage or None,
        "sector": snapshot.get("sector"),
        "rsi": snapshot.get("rsi") or technicals.get("rsi"),
        "technical_score": tech_score,
        "technical_assessment": tech_assess,
        "investment_score": snapshot.get("investment_score"),
        "fundamental_score": snapshot.get("fundamental_score"),
        "enhanced_fund_score": snapshot.get("enhanced_fund_score"),
        "fundamental_assessment": fund_assess,
        "can_slim_score": snapshot.get("can_slim_score"),
        "minervini_score": snapshot.get("minervini_score"),
        "earnings_quality": snapshot.get("earnings_quality"),
        "sales_growth": snapshot.get("sales_growth"),
        "financial_strength": snapshot.get("financial_strength"),
        "institutional_backing": snapshot.get("institutional_backing"),
        "trend_signal": snapshot.get("trend_signal"),
        "trading_signal": snapshot.get("trading_signal"),
        "supertrend": snapshot.get("supertrend_state") or technicals.get("supertrend_signal"),
        "change_1d_pct": snapshot.get("change_1d_pct"),
        "change_1w_pct": snapshot.get("change_1w_pct"),
        "change_1m_pct": snapshot.get("change_1m_pct"),
        "support": technicals.get("support"),
        "resistance": technicals.get("resistance"),
        "as_of": as_of,
    }


def extract_comparison(trace: list[dict]) -> list[dict[str, Any]]:
    """Extract per-symbol comparison rows from the trace."""
    by_tool = _results_by_tool(trace)
    snapshots = by_tool.get("get_symbol_snapshot", [])
    technicals_list = by_tool.get("get_technical_setup", [])

    # Pair by index; technicals list may be shorter or absent
    rows: list[dict] = []
    for i, snap in enumerate(snapshots):
        if snap.get("error"):
            continue
        tech = technicals_list[i] if i < len(technicals_list) else {}
        row = _comparison_row(snap, tech)
        if row["symbol"]:
            rows.append(row)

    # Also check generic "get_stock_brief" / "get_symbol_data" style results
    for tool in ("get_stock_brief", "get_symbol_data", "get_equity_eod"):
        for result in by_tool.get(tool, []):
            sym = _str(result.get("symbol") or result.get("ticker") or "")
            if not sym or any(r["symbol"] == sym for r in rows):
                continue
            rows.append(_comparison_row(result, {}))

    return rows


# ── market context rows ────────────────────────────────────────────────────────

def extract_market_context(trace: list[dict]) -> list[dict[str, Any]]:
    """Extract market/index breadth rows from the trace."""
    by_tool = _results_by_tool(trace)
    rows: list[dict] = []

    # Index snapshots + breadth
    for snap in by_tool.get("get_index_snapshot", []):
        if snap.get("error"):
            continue
        index = _str(snap.get("index") or snap.get("index_name") or "")
        as_of = _str(snap.get("as_of") or date.today().isoformat())
        rows.append({
            "index": index,
            "index_name": index,
            "close": snap.get("close"),
            "chg_pct": snap.get("chg_pct"),
            "52w_high": snap.get("52w_high"),
            "52w_low": snap.get("52w_low"),
            "trend_10d": snap.get("trend_10d"),
            "as_of": as_of,
        })

    # Breadth data — enrich matching index row or add standalone
    for breadth in by_tool.get("get_market_breadth", []):
        if breadth.get("error"):
            continue
        index = _str(breadth.get("index_name") or breadth.get("index") or "")
        as_of = _str(breadth.get("snapshot_date") or date.today().isoformat())
        existing = next((r for r in rows if r.get("index_name") == index or r.get("index") == index), None)
        fields = {
            "total_stocks": breadth.get("total_stocks"),
            "advances": breadth.get("advances"),
            "declines": breadth.get("declines"),
            "ad_ratio": breadth.get("ad_ratio"),
            "avg_rs_pct": breadth.get("avg_rs_pct"),
            "stage_distribution": breadth.get("stage_distribution"),
            "as_of": as_of,
        }
        if existing:
            existing.update({k: v for k, v in fields.items() if v is not None})
        else:
            rows.append({"index": index, "index_name": index, **fields})

    # Sector breadth CSV results
    for sector_data in by_tool.get("get_sector_breadth", []):
        if isinstance(sector_data.get("sectors"), list):
            for r in sector_data["sectors"]:
                rows.append({
                    "sector": r.get("sector"),
                    "index_name": r.get("index_name"),
                    "pct_above_50dma": r.get("pct_above_50dma"),
                    "change_5d": r.get("change_5d"),
                    "breadth_signal": r.get("breadth_signal"),
                    "as_of": r.get("as_of_date") or date.today().isoformat(),
                })

    return rows


# ── screener rows ──────────────────────────────────────────────────────────────

_SCREENER_TOOLS = {
    "run_screener_query",
    "run_quality_breakout_screener",
    "get_long_term_growth_candidates",
    "validate_strength_watchlist",
    "get_stage2_candidates",
    "get_momentum_leaders",
}


def extract_screener_results(trace: list[dict]) -> list[dict[str, Any]]:
    """Extract screener result rows from the trace."""
    by_tool = _results_by_tool(trace)
    rows: list[dict] = []
    for tool in _SCREENER_TOOLS:
        for result in by_tool.get(tool, []):
            raw_rows = result.get("results") or result.get("candidates") or []
            screen_key = result.get("screen_type") or tool
            for r in raw_rows:
                if not isinstance(r, dict):
                    continue
                sym = _str(r.get("symbol") or "").strip().upper()
                if not sym:
                    continue
                rows.append({
                    "symbol": sym,
                    "company": r.get("company_name") or r.get("company") or sym,
                    "sector": r.get("sector"),
                    "price": r.get("price") or r.get("latest_close"),
                    "stage": r.get("stage"),
                    "rsi": r.get("rsi"),
                    "rs_pct": r.get("rs_pct"),
                    "relative_strength": r.get("relative_strength") or r.get("rs"),
                    "technical_score": r.get("technical_score"),
                    "investment_score": r.get("investment_score"),
                    "composite_score": r.get("composite_score") or r.get("strength_score"),
                    "trading_signal": r.get("trading_signal"),
                    "setup_tags": r.get("setup_tags") or r.get("reason_tags") or [],
                    "risk_flags": r.get("risk_flags") or [],
                    "screen_type": screen_key,
                })
    return rows


# ── evidence items ─────────────────────────────────────────────────────────────

def extract_evidence(trace: list[dict]) -> list[TalkEvidenceItem]:
    """Convert trace tool results into TalkEvidenceItem evidence items."""
    items: list[TalkEvidenceItem] = []
    for item in _tool_results(trace):
        tool = _str(item.get("tool") or "")
        result = item.get("result") or item.get("data") or {}
        if not isinstance(result, dict):
            result = {"raw": result}
        as_of = _str(
            result.get("snapshot_date")
            or result.get("as_of")
            or result.get("price_date")
            or date.today().isoformat()
        )
        symbol = _str(
            result.get("symbol")
            or result.get("index")
            or result.get("index_name")
            or item.get("symbol")
            or ""
        )
        label = f"{symbol} {tool.replace('_', ' ')}" if symbol else tool.replace("_", " ")
        has_error = bool(result.get("error"))
        items.append(TalkEvidenceItem(
            label=label,
            value={k: v for k, v in result.items() if k != "error"} if not has_error else result,
            source=tool,
            as_of=as_of,
            freshness="unknown",
        ))
    return items


# ── symbol list ───────────────────────────────────────────────────────────────

def extract_symbols(trace: list[dict], comparison: list[dict]) -> list[str]:
    """Derive the resolved symbol list from comparison rows (primary) or trace context.

    Only include symbols that have real tool-result backing.  Router-decision
    context symbols are skipped — they include every token the router tried to
    resolve (meta-words like SCREEN, EOD, CNL, etc.).
    """
    seen: list[str] = []

    # Primary: symbols that have actual comparison/snapshot data
    for row in comparison:
        sym = _str(row.get("symbol") or "").strip().upper()
        if sym and sym not in seen:
            seen.append(sym)

    # Secondary: any symbol that appeared as the subject of a real tool call
    # (get_symbol_snapshot, get_technical_setup, get_cached_financials, etc.)
    # — but NOT from router context which includes un-resolved tokens.
    _SYMBOL_TOOLS = {
        "get_symbol_snapshot", "get_technical_setup", "get_cached_financials",
        "get_fno_data", "get_intraday_levels",
    }
    for item in trace:
        if not isinstance(item, dict):
            continue
        tool = item.get("tool") or ""
        if tool not in _SYMBOL_TOOLS:
            continue
        res = item.get("result") or {}
        if not isinstance(res, dict):
            continue
        sym = _str(res.get("symbol") or item.get("symbol") or "").strip().upper()
        if sym and sym not in seen:
            seen.append(sym)

    return seen


# ── intent extraction ─────────────────────────────────────────────────────────

def extract_intent(result: dict[str, Any]) -> str:
    """Return a human-readable intent string from the Agent result dict."""
    intent = _str(result.get("intent") or "")
    if intent and intent not in ("", "none"):
        return intent

    # Try to derive from the unified_router step in the trace
    for item in result.get("trace") or []:
        if isinstance(item, dict) and item.get("step") == "unified_router":
            decision = item.get("decision") or {}
            if decision.get("intent"):
                return _str(decision["intent"])
    return "general_research"


# ── usage / cost ──────────────────────────────────────────────────────────────

def extract_usage(result: dict[str, Any]) -> tuple[int, int, float]:
    """Return (input_tokens, output_tokens, cost_usd) from Agent result."""
    usage = result.get("usage") or {}
    in_tok = int(usage.get("input_tokens") or 0)
    out_tok = int(usage.get("output_tokens") or 0)
    # Rough cost estimate (gpt-4o-mini rates as default)
    cost = round((in_tok / 1_000_000 * 0.15) + (out_tok / 1_000_000 * 0.60), 6)
    return in_tok, out_tok, cost
