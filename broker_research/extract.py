"""Structured fact extraction for broker research reports."""

from __future__ import annotations

import re
from typing import Any

from .storage import insert_broker_research_facts


RATING_RE = re.compile(r"\b(?:maintain|reiterate|upgrade(?:d)?\s+to|rating[:\s]+)?(BUY|SELL|HOLD|ADD|REDUCE|NEUTRAL|ACCUMULATE)\b", re.I)
TARGET_RE = re.compile(r"\b(?:target price|price target|target|tp)\s*(?:of|to|:)?\s*(?:rs\.?|inr|₹)?\s*([0-9][0-9,]*(?:\.[0-9]+)?)", re.I)
VALUATION_RE = re.compile(r"\b([0-9]+(?:\.[0-9]+)?x)\s*(FY[0-9]{2}E?)?\s*(P/E|PE|EV/EBITDA|EV/SALES|P/B|PB)\b", re.I)


def _fact(
    *,
    broker_report_id: int,
    symbol: str,
    fact_type: str,
    fact_name: str,
    fact_value: str,
    page_number: int,
    unit: str = "",
    period: str = "",
    confidence: float = 0.75,
    extractor: str = "deterministic",
) -> dict[str, Any]:
    return {
        "broker_report_id": broker_report_id,
        "symbol": symbol.strip().upper(),
        "fact_type": fact_type,
        "fact_name": fact_name,
        "fact_value": fact_value,
        "unit": unit,
        "period": period,
        "page_number": page_number,
        "confidence": confidence,
        "extractor": extractor,
    }


def _snippet_after(text: str, marker: str) -> str:
    match = re.search(rf"\b{re.escape(marker)}\b(.{{0,220}})", text, re.I | re.S)
    if not match:
        return ""
    return " ".join(match.group(0).split()).strip(" .")


def extract_deterministic_facts(
    *,
    broker_report_id: int,
    symbol: str,
    page_number: int,
    text: str,
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    body = text or ""
    rating = RATING_RE.search(body)
    if rating:
        facts.append(
            _fact(
                broker_report_id=broker_report_id,
                symbol=symbol,
                fact_type="rating",
                fact_name="broker_rating",
                fact_value=rating.group(1).upper(),
                page_number=page_number,
                confidence=0.8,
            )
        )
    target = TARGET_RE.search(body)
    if target:
        facts.append(
            _fact(
                broker_report_id=broker_report_id,
                symbol=symbol,
                fact_type="target_price",
                fact_name="broker_target_price",
                fact_value=target.group(1).replace(",", ""),
                unit="INR",
                page_number=page_number,
                confidence=0.85,
            )
        )
    valuation = VALUATION_RE.search(body)
    if valuation:
        method = valuation.group(3).upper().replace("PE", "P/E").replace("PB", "P/B")
        facts.append(
            _fact(
                broker_report_id=broker_report_id,
                symbol=symbol,
                fact_type="valuation_method",
                fact_name=valuation.group(1).lower(),
                fact_value=method,
                period=(valuation.group(2) or "").upper(),
                page_number=page_number,
                confidence=0.75,
            )
        )
    catalyst = _snippet_after(body, "catalysts")
    if catalyst:
        facts.append(
            _fact(
                broker_report_id=broker_report_id,
                symbol=symbol,
                fact_type="catalyst",
                fact_name="catalyst_snippet",
                fact_value=catalyst,
                page_number=page_number,
                confidence=0.65,
            )
        )
    risk = _snippet_after(body, "risks")
    if risk:
        facts.append(
            _fact(
                broker_report_id=broker_report_id,
                symbol=symbol,
                fact_type="risk",
                fact_name="risk_snippet",
                fact_value=risk,
                page_number=page_number,
                confidence=0.65,
            )
        )
    return facts


def extract_facts_from_pages(*, broker_report_id: int, symbol: str, pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for page in pages:
        facts.extend(
            extract_deterministic_facts(
                broker_report_id=broker_report_id,
                symbol=symbol,
                page_number=int(page.get("page_number") or 0),
                text=str(page.get("text") or ""),
            )
        )
    return facts


def build_page_bounded_fact_prompt(*, symbol: str, pages: list[dict[str, Any]], max_chars_per_page: int = 1800) -> str:
    chunks = []
    for page in pages:
        page_number = int(page.get("page_number") or 0)
        text = " ".join(str(page.get("text") or "").split())[:max_chars_per_page]
        chunks.append(f"Page {page_number}: {text}")
    return "\n".join(
        [
            "Extract broker research facts for Indian equity research.",
            f"Symbol: {symbol.strip().upper()}",
            "Return JSON only with a top-level facts array.",
            "Each fact must include fact_type, fact_name, fact_value, page_number, and confidence.",
            "Only cite page_number values present in the context below.",
            "",
            *chunks,
        ]
    )


def validate_llm_fact_payload(
    payload: dict[str, Any],
    *,
    broker_report_id: int,
    symbol: str,
    allowed_page_numbers: set[int],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    for raw in payload.get("facts") or []:
        fact_name = str(raw.get("fact_name") or "")
        page_number = int(raw.get("page_number") or 0)
        if page_number not in allowed_page_numbers:
            rejected.append({"fact_name": fact_name, "reason": "page_number_not_in_context"})
            continue
        fact_type = str(raw.get("fact_type") or "").strip()
        fact_value = str(raw.get("fact_value") or "").strip()
        if not fact_type or not fact_name or not fact_value:
            rejected.append({"fact_name": fact_name, "reason": "missing_required_field"})
            continue
        accepted.append(
            _fact(
                broker_report_id=broker_report_id,
                symbol=symbol,
                fact_type=fact_type,
                fact_name=fact_name,
                fact_value=fact_value,
                page_number=page_number,
                confidence=float(raw.get("confidence") or 0.0),
                extractor="llm",
            )
        )
    return accepted, rejected


def extract_and_store_facts_from_pages(
    conn: Any,
    *,
    broker_report_id: int,
    symbol: str,
    pages: list[dict[str, Any]],
) -> dict[str, Any]:
    facts = extract_facts_from_pages(broker_report_id=broker_report_id, symbol=symbol, pages=pages)
    return {"facts_stored": insert_broker_research_facts(conn, facts)}
