#!/usr/bin/env python3
"""LLM-backed short-term and long-term stock verdicts for portfolio reports."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from config import OUTPUT_DIR, STOCK_NARRATIVES_JSON
except ImportError:
    OUTPUT_DIR = Path(__file__).resolve().parent / "output"
    STOCK_NARRATIVES_JSON = OUTPUT_DIR / "stock_narratives.json"


LLM_STOCK_VIEWS_JSON = OUTPUT_DIR / "llm_stock_views.json"
VIEW_ENUM = ("MUST BUY", "HOLD", "MUST SELL")


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    except Exception:
        pass


def _short_text(value: Any, max_chars: int = 380) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "..."


def _num(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def build_evidence(narratives: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return compact per-stock evidence safe to send to the LLM."""
    evidence: list[dict[str, Any]] = []
    for row in narratives:
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        fundamental_analysis = {
            "composite_score": _num(row.get("fund_score"), 50),
            "earnings_quality": _num(row.get("fund_earnings_quality")),
            "sales_growth": _num(row.get("fund_sales_growth")),
            "financial_strength": _num(row.get("fund_financial_strength")),
            "institutional_backing": _num(row.get("fund_institutional_backing")),
            "pnl_summary": _short_text(row.get("pnl_summary"), 500),
            "quarterly_summary": _short_text(row.get("quarterly_summary"), 500),
            "balance_sheet_summary": _short_text(row.get("balance_sheet_summary"), 500),
            "ratios_summary": _short_text(row.get("ratios_summary"), 500),
        }
        evidence.append(
            {
                "symbol": symbol,
                "quantity": _num(row.get("quantity"), 0),
                "value_rs": _num(row.get("value_rs"), 0),
                "current_price": _num(row.get("current_price")),
                "technical_score": _num(row.get("technical_score"), 50),
                "fund_score": _num(row.get("fund_score"), 50),
                "fundamental_analysis": fundamental_analysis,
                "rule_recommendation": str(row.get("recommendation") or "HOLD").upper(),
                "technical_recommendation": str(row.get("tech_recommendation") or "").upper(),
                "trading_signal": str(row.get("trading_signal") or "").upper(),
                "trend_signal": str(row.get("trend_signal") or "").upper(),
                "rsi": _num(row.get("rsi")),
                "change_1d_pct": _num(row.get("change_1d_pct")),
                "change_1w_pct": _num(row.get("change_1w_pct")),
                "change_1m_pct": _num(row.get("change_1m_pct")),
                "relative_strength": _num(row.get("relative_strength")),
                "narrative_excerpt": _short_text(row.get("narrative")),
            }
        )
    return evidence


def _schema(allowed_symbols: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "views": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "symbol": {"type": "string", "enum": allowed_symbols},
                        "short_term_view": {"type": "string", "enum": list(VIEW_ENUM)},
                        "long_term_view": {"type": "string", "enum": list(VIEW_ENUM)},
                        "final_verdict": {"type": "string", "enum": list(VIEW_ENUM)},
                        "confidence": {"type": "number"},
                        "key_reasons": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "risks_to_view": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": [
                        "symbol",
                        "short_term_view",
                        "long_term_view",
                        "final_verdict",
                        "confidence",
                        "key_reasons",
                        "risks_to_view",
                    ],
                },
            }
        },
        "required": ["views"],
    }


def _prompt(evidence: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "task": "Classify each portfolio holding into short-term and long-term views.",
        "allowed_verdicts": list(VIEW_ENUM),
        "policy": [
            "Use MUST SELL only when risk or deterioration is decisive from the evidence.",
            "For long-term view, weigh fundamental_analysis heavily: earnings quality, sales growth, financial strength, institutional backing, P&L commentary, balance sheet, ratios, and valuation context.",
            "Use MUST BUY only when both technical setup and long-term fundamental quality/risk-reward are constructive.",
            "Do not mark a weak-fundamental stock as long-term MUST BUY only because short-term momentum is strong.",
            "Use HOLD when evidence is mixed, insufficient, or action should wait for confirmation.",
            "Final verdict should reconcile the short-term and long-term view conservatively.",
            "This is research context, not personalized financial advice.",
        ],
        "evidence": evidence,
    }


def _coerce_view(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in VIEW_ENUM:
        return text
    if "SELL" in text or "REDUCE" in text or "EXIT" in text:
        return "MUST SELL"
    if "BUY" in text or "ADD" in text or "ACCUMULATE" in text:
        return "MUST BUY"
    return "HOLD"


def normalize_view(raw: dict[str, Any], *, allowed_symbols: set[str]) -> dict[str, Any] | None:
    symbol = str(raw.get("symbol") or "").strip().upper()
    if symbol not in allowed_symbols:
        return None
    confidence = _num(raw.get("confidence"), 0.0) or 0.0
    confidence = max(0.0, min(1.0, confidence))
    reasons = [str(v).strip() for v in (raw.get("key_reasons") or []) if str(v).strip()]
    risks = [str(v).strip() for v in (raw.get("risks_to_view") or []) if str(v).strip()]
    return {
        "symbol": symbol,
        "short_term_view": _coerce_view(raw.get("short_term_view")),
        "long_term_view": _coerce_view(raw.get("long_term_view")),
        "final_verdict": _coerce_view(raw.get("final_verdict")),
        "confidence": round(confidence, 3),
        "key_reasons": reasons[:4],
        "risks_to_view": risks[:4],
        "source": "llm",
    }


def _fallback_view(symbol: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "short_term_view": "HOLD",
        "long_term_view": "HOLD",
        "final_verdict": "HOLD",
        "confidence": 0.0,
        "key_reasons": ["LLM omitted this stock; fallback HOLD used."],
        "risks_to_view": ["Review manually before taking action."],
        "source": "fallback",
    }


def complete_views(evidence: list[dict[str, Any]], views: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return one view per evidence row, preserving evidence order."""
    by_symbol = {str(view.get("symbol") or "").upper(): view for view in views}
    complete = []
    for item in evidence:
        symbol = str(item.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        view = by_symbol.get(symbol)
        if view:
            view = {**view, "source": view.get("source") or "llm"}
        complete.append(view or _fallback_view(symbol))
    return complete


def _call_openai(
    *,
    evidence: list[dict[str, Any]],
    client: Any,
    model: str,
) -> list[dict[str, Any]]:
    allowed_symbols = [item["symbol"] for item in evidence]
    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "system",
                "content": (
                    "You are a disciplined Indian equity portfolio analyst. "
                    "Return only schema-valid JSON. Prefer HOLD when evidence is incomplete."
                ),
            },
            {"role": "user", "content": json.dumps(_prompt(evidence), ensure_ascii=True)},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "portfolio_llm_stock_views",
                "strict": True,
                "schema": _schema(allowed_symbols),
            }
        },
    )
    parsed = json.loads(response.output_text)
    views = parsed.get("views") if isinstance(parsed, dict) else []
    if not isinstance(views, list):
        return []
    allowed = set(allowed_symbols)
    out = []
    for raw in views:
        if isinstance(raw, dict):
            normalized = normalize_view(raw, allowed_symbols=allowed)
            if normalized:
                out.append(normalized)
    return out


def _chunks(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def run_llm_stock_views(
    *,
    narratives_json: Path = STOCK_NARRATIVES_JSON,
    output_json: Path = LLM_STOCK_VIEWS_JSON,
    client: Any = None,
    model: str = "gpt-4o",
    max_stocks: int | None = None,
    chunk_size: int = 25,
) -> dict[str, Any]:
    """Generate LLM stock views from stock_narratives.json."""
    narratives_path = Path(narratives_json)
    output_path = Path(output_json)
    if not narratives_path.exists():
        return {"success": False, "n_views": 0, "note": f"Missing {narratives_path}"}

    narratives = json.loads(narratives_path.read_text(encoding="utf-8") or "[]")
    if not isinstance(narratives, list):
        return {"success": False, "n_views": 0, "note": "stock_narratives.json is not a list"}
    evidence = build_evidence(narratives)
    if max_stocks is not None:
        evidence = evidence[:max_stocks]
    if not evidence:
        payload = _artifact(model=model, views=[], status="empty", note="No stock evidence found.")
        _write(output_path, payload)
        return {"success": True, "n_views": 0, "path": str(output_path), "note": "No stock evidence found."}

    if client is None:
        _load_dotenv()
        if not os.getenv("OPENAI_API_KEY"):
            payload = _artifact(
                model=model,
                views=[],
                status="skipped",
                note="OPENAI_API_KEY not set; LLM stock views skipped.",
            )
            _write(output_path, payload)
            return {"success": False, "n_views": 0, "path": str(output_path), "note": payload["note"]}
        from openai import OpenAI

        client = OpenAI()

    views: list[dict[str, Any]] = []
    for chunk in _chunks(evidence, max(1, chunk_size)):
        views.extend(_call_openai(evidence=chunk, client=client, model=model))
    views = complete_views(evidence, views)
    payload = _artifact(model=model, views=views, status="ok", note="")
    _write(output_path, payload)
    return {"success": True, "n_views": len(views), "path": str(output_path), "note": ""}


def _artifact(*, model: str, views: list[dict[str, Any]], status: str, note: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "status": status,
        "note": note,
        "views": views,
    }


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def load_view_lookup(path: Path = LLM_STOCK_VIEWS_JSON) -> dict[str, dict[str, Any]]:
    """Load ``symbol -> view`` mapping; missing/invalid artifacts return empty."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}
    views = payload.get("views") if isinstance(payload, dict) else []
    if not isinstance(views, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in views:
        if isinstance(row, dict):
            symbol = str(row.get("symbol") or "").strip().upper()
            if symbol:
                out[symbol] = row
    return out


if __name__ == "__main__":
    result = run_llm_stock_views()
    print(json.dumps(result, indent=2))
