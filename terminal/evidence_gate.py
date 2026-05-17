"""Evidence gating helpers for Agent Adda responses."""

from __future__ import annotations

from typing import Any


TOOL_CATEGORIES: dict[str, tuple[str, ...]] = {
    "technical": ("get_technical_setup", "explain_intraday_setup", "get_intraday_analysis"),
    "fundamental": ("scrape_screener_in", "get_symbol_snapshot"),
    "results": ("get_latest_results",),
    "filing": ("discover_financial_filings", "ingest_financial_filing", "parse_financial_filing", "search_bse_filings", "search_nse_announcements"),
    "catalyst": ("search_latest_catalysts", "search_nse_announcements", "search_bse_filings"),
    "broker": ("search_broker_research",),
    "forensic": ("run_forensic_analysis", "screen_forensic_watchlist"),
    "sector": ("get_sector_context", "get_market_breadth"),
    "fno": ("get_options_chain", "get_futures_analysis", "get_strategy_recommendations", "get_fno_overview"),
    "strategy": ("run_strategy_council", "build_strategy_council_evidence_pack"),
    "report_context": ("open_report", "read_report", "summarize_report", "get_last_report", "list_generated_reports"),
}

REQUIRED_CATEGORY_TOOLS: dict[str, tuple[str, ...]] = {
    "fno": ("get_options_chain", "get_futures_analysis", "get_strategy_recommendations"),
}


CLAIM_KEYWORDS: dict[str, tuple[str, ...]] = {
    "broker": ("broker", "analyst target", "target price", "brokerage", "rating"),
    "results": ("latest results", "quarterly results", "revenue", "pat", "eps", "profit after tax"),
    "forensic": ("beneish", "piotroski", "altman", "manipulation", "forensic"),
    "sector": ("sector is leading", "sector leading", "sector breadth", "sector strength"),
    "fno": ("option strategy", "options strategy", "max pain", "futures basis", "cost of carry", "pcr"),
    "strategy": ("strategy council", "locked strategy", "recommendation:"),
}


def _tool_error(result: dict[str, Any]) -> str:
    if not isinstance(result, dict):
        return ""
    return str(result.get("error") or "")


def build_evidence_matrix(tool_results: list[dict]) -> dict:
    """Group executed tool evidence by semantic category."""
    executed = {str(item.get("tool") or ""): item for item in tool_results or []}
    matrix: dict[str, dict[str, Any]] = {}
    for category, tools in TOOL_CATEGORIES.items():
        present = [tool for tool in tools if tool in executed]
        required = REQUIRED_CATEGORY_TOOLS.get(category)
        missing_required = [tool for tool in (required or ()) if tool not in present]
        errors = {
            tool: _tool_error(executed[tool].get("result") if isinstance(executed[tool], dict) else {})
            for tool in present
            if _tool_error(executed[tool].get("result") if isinstance(executed[tool], dict) else {})
        }
        matrix[category] = {
            "status": "available" if present and not errors and not missing_required else ("error" if errors else "missing"),
            "tools": present,
            "missing_required_tools": missing_required,
            "errors": errors,
        }
    return matrix


def validate_required_tools_executed(required_tools: list[str] | tuple[str, ...], tool_results: list[dict]) -> dict:
    executed = {str(item.get("tool") or "") for item in tool_results or []}
    missing = [tool for tool in required_tools or [] if tool not in executed]
    return {
        "status": "ok" if not missing else "missing_required_tools",
        "required_tools": list(required_tools or []),
        "executed_tools": sorted(executed),
        "missing_tools": missing,
    }


def validate_answer_against_evidence(answer: str, tool_results: list[dict]) -> dict:
    """Detect obvious unsupported claim categories in a rendered answer."""
    text = (answer or "").lower()
    matrix = build_evidence_matrix(tool_results)
    missing: list[str] = []
    for category, keywords in CLAIM_KEYWORDS.items():
        if any(keyword in text for keyword in keywords) and matrix.get(category, {}).get("status") != "available":
            missing.append(category)
    return {
        "status": "ok" if not missing else "missing_evidence",
        "missing_categories": missing,
        "evidence_matrix": matrix,
    }


def render_missing_evidence_block(
    intent: str,
    missing_categories: list[str] | tuple[str, ...] | None = None,
    missing_tools: list[str] | tuple[str, ...] | None = None,
) -> str:
    lines = [
        "▶ MISSING EVIDENCE",
        f"  Intent: {intent}",
    ]
    if missing_categories:
        lines.append(f"  Missing categories: {', '.join(missing_categories)}")
    if missing_tools:
        lines.append(f"  Missing required tool(s): {', '.join(missing_tools)}")
    lines.append("  No unsupported market conclusion was rendered from missing evidence.")
    lines.append("")
    lines.append("━━━ Not investment advice. For research and learning only. ━━━")
    return "\n".join(lines)
