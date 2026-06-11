"""Composite EOD screeners built from existing Agent Adda screeners."""
from __future__ import annotations

import os
from decimal import Decimal
from typing import Any, Callable


SOURCE_SCREENS = ("new_highs", "momentum_52w", "tight_range", "breakouts")
SETUP_LABELS = {
    "new_highs": "new_high",
    "momentum_52w": "momentum_52w",
    "tight_range": "vcp_like",
    "breakouts": "breakout",
}


def _num(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except Exception:
        return default


def _default_screener_runner(screen_type: str, top_n: int) -> dict:
    from terminal.tools import run_screener_query

    return run_screener_query(screen_type, top_n=top_n)


def _default_snapshot_loader(symbols: list[str]) -> dict[str, dict]:
    if not symbols:
        return {}
    try:
        import psycopg2
        import psycopg2.extras
    except Exception:
        return {}

    dsn = os.environ.get("AGENT_ADDA_PG_DSN") or "dbname=nse_market user=nse_admin host=/tmp"
    sql = """
        WITH latest AS (SELECT MAX(snapshot_date) AS d FROM scores.stage_snapshots)
        SELECT symbol, company_name, sector, price, stage, trading_signal,
               relative_strength, rsi, technical_score, investment_score,
               enhanced_fund_score, earnings_quality, sales_growth,
               financial_strength, institutional_backing
        FROM scores.stage_snapshots s
        JOIN latest l ON s.snapshot_date=l.d
        WHERE symbol = ANY(%s)
    """
    try:
        with psycopg2.connect(dsn) as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(sql, (symbols,))
            return {str(row["symbol"]).upper(): dict(row) for row in cur.fetchall()}
    except Exception:
        return {}


def _quality_pass(row: dict, mode: str) -> bool:
    if mode == "broad":
        return True
    fund = _num(row.get("enhanced_fund_score"), -1)
    invest = _num(row.get("investment_score"), -1)
    if mode == "strict":
        return fund >= 70 or invest >= 65
    return fund >= 60 or invest >= 60


def _score(row: dict) -> float:
    score = 0.0
    score += len(row.get("setup_tags") or []) * 8
    if row.get("stage") == "STAGE_2":
        score += 15
    if str(row.get("trading_signal") or "").upper() == "STRONG_BUY":
        score += 12
    elif str(row.get("trading_signal") or "").upper() == "BUY":
        score += 10
    rsi = _num(row.get("rsi"), 0)
    if 50 <= rsi <= 75:
        score += 10
    elif rsi > 82:
        score -= 8
    score += min(max(_num(row.get("rs"), _num(row.get("relative_strength"), 0)), 0), 100) * 0.12
    score += min(max(_num(row.get("technical_score"), 0), 0), 100) * 0.12
    score += min(max(_num(row.get("enhanced_fund_score"), 0), 0), 100) * 0.20
    score += min(max(_num(row.get("investment_score"), 0), 0), 100) * 0.16
    score += min(max(_num(row.get("financial_strength"), 0), 0), 100) * 0.08
    return round(score, 2)


def _reason_tags(row: dict) -> list[str]:
    tags: list[str] = []
    setup_map = {
        "breakout": "Breakout",
        "new_high": "New high",
        "momentum_52w": "52W momentum",
        "vcp_like": "VCP-like tight range",
    }
    for tag in row.get("setup_tags") or []:
        if tag in setup_map:
            tags.append(setup_map[tag])
    if row.get("stage") == "STAGE_2":
        tags.append("Stage 2")
    signal = str(row.get("trading_signal") or "").upper()
    if signal in {"BUY", "STRONG_BUY"}:
        tags.append(signal.replace("_", " "))
    if _num(row.get("enhanced_fund_score"), 0) >= 70:
        tags.append("High fundamental score")
    elif _num(row.get("enhanced_fund_score"), 0) >= 60:
        tags.append("Good fundamental score")
    return list(dict.fromkeys(tags))


def _risk_flags(row: dict) -> list[str]:
    flags: list[str] = []
    if _num(row.get("enhanced_fund_score"), 0) < 50 and _num(row.get("investment_score"), 0) < 55:
        flags.append("weak_fundamentals")
    if _num(row.get("rsi"), 0) > 82:
        flags.append("extended_rsi")
    if row.get("stage") != "STAGE_2":
        flags.append("not_stage2")
    return flags


def run_quality_breakout_screener(
    top_n: int = 15,
    mode: str = "balanced",
    *,
    screener_runner: Callable[[str, int], dict] | None = None,
    snapshot_loader: Callable[[list[str]], dict[str, dict]] | None = None,
) -> dict:
    """Find new-high/VCP/breakout candidates with a fundamental quality overlay."""
    mode_key = (mode or "balanced").lower()
    if mode_key not in {"strict", "balanced", "broad"}:
        mode_key = "balanced"

    runner = screener_runner or _default_screener_runner
    load_snapshot = snapshot_loader or _default_snapshot_loader

    source_counts: dict[str, int] = {}
    candidates: dict[str, dict] = {}
    snapshot_date = None
    source_trail: list[str] = []

    for screen in SOURCE_SCREENS:
        payload = runner(screen, max(top_n * 3, top_n))
        rows = payload.get("results") or []
        source_counts[screen] = len(rows)
        snapshot_date = snapshot_date or payload.get("snapshot_date")
        source_trail.append(f"run_screener_query:{screen}")
        for row in rows:
            symbol = str(row.get("symbol") or "").upper().strip()
            if not symbol:
                continue
            existing = candidates.setdefault(symbol, {"symbol": symbol, "setup_tags": []})
            existing.update({k: v for k, v in row.items() if v is not None})
            tag = SETUP_LABELS[screen]
            if tag not in existing["setup_tags"]:
                existing["setup_tags"].append(tag)

    enrich = load_snapshot(sorted(candidates))
    enriched_rows: list[dict] = []
    for symbol, row in candidates.items():
        merged = dict(row)
        merged.update({k: v for k, v in (enrich.get(symbol) or {}).items() if v is not None})
        merged["symbol"] = symbol
        merged["price"] = _num(merged.get("price"), _num(merged.get("close"), 0))
        merged["rs"] = _num(merged.get("relative_strength"), _num(merged.get("rs_pct"), 0))
        merged["rsi"] = _num(merged.get("rsi"), 0)
        merged["investment_score"] = _num(merged.get("investment_score"), 0)
        merged["enhanced_fund_score"] = _num(merged.get("enhanced_fund_score"), 0)
        merged["technical_score"] = _num(merged.get("technical_score"), 0)
        merged["financial_strength"] = _num(merged.get("financial_strength"), 0)
        merged["setup_tags"] = sorted(merged.get("setup_tags") or [])
        merged["reason_tags"] = _reason_tags(merged)
        merged["risk_flags"] = _risk_flags(merged)
        merged["tradingview_symbol"] = f"NSE:{symbol}"
        merged["composite_score"] = _score(merged)
        if _quality_pass(merged, mode_key):
            enriched_rows.append(merged)

    enriched_rows.sort(key=lambda r: (-_num(r.get("composite_score")), r.get("symbol", "")))
    limited = enriched_rows[:top_n]
    return {
        "screen_type": "quality_breakouts",
        "mode": mode_key,
        "description": "Composite new-high, VCP-like, breakout screener with fundamental quality overlay",
        "snapshot_date": snapshot_date,
        "source_counts": source_counts,
        "merged_count": len(candidates),
        "passed_count": len(enriched_rows),
        "count": len(limited),
        "results": limited,
        "tradingview_symbols": [row["tradingview_symbol"] for row in limited],
        "source_trail": source_trail + ["scores.stage_snapshots"],
    }

