"""Broker consensus comparison over extracted research facts."""

from __future__ import annotations

import re
from collections import Counter
from statistics import mean
from typing import Any


def _clean_text(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9%./ x-]+", " ", str(value).lower()).split()).strip(" .")


def _float_value(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", ""))
    except Exception:
        return None


def recurring_fact_values(facts: list[dict[str, Any]], *, fact_type: str, min_count: int = 2) -> list[dict[str, Any]]:
    counts = Counter(
        _clean_text(str(fact.get("fact_value") or ""))
        for fact in facts
        if fact.get("fact_type") == fact_type and str(fact.get("fact_value") or "").strip()
    )
    return [
        {"value": value, "count": count}
        for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        if count >= min_count
    ]


def build_broker_consensus(*, symbol: str, facts: list[dict[str, Any]]) -> dict[str, Any]:
    brokers = sorted({str(fact.get("broker_code") or "") for fact in facts if fact.get("broker_code")})
    rating_seen: set[tuple[str, str]] = set()
    rating_values: list[str] = []
    for fact in facts:
        if fact.get("fact_type") != "rating":
            continue
        value = str(fact.get("fact_value") or "").strip().upper()
        if not value:
            continue
        key = (str(fact.get("broker_report_id") or fact.get("broker_code") or ""), value)
        if key in rating_seen:
            continue
        rating_seen.add(key)
        rating_values.append(value)
    ratings = Counter(
        rating_values
    )
    target_seen: set[tuple[str, float]] = set()
    target_values = []
    for fact in facts:
        if fact.get("fact_type") != "target_price":
            continue
        value = _float_value(fact.get("fact_value"))
        if value is None:
            continue
        key = (str(fact.get("broker_report_id") or fact.get("broker_code") or ""), value)
        if key in target_seen:
            continue
        target_seen.add(key)
        target_values.append(value)
    target_summary = {
        "count": len(target_values),
        "min": min(target_values) if target_values else None,
        "max": max(target_values) if target_values else None,
        "average": round(mean(target_values), 2) if target_values else None,
        "spread": (max(target_values) - min(target_values)) if len(target_values) >= 2 else 0.0,
    }
    disagreements: list[str] = []
    if len(ratings) > 1:
        disagreements.append("rating_disagreement")
    if target_summary["spread"] and target_summary["spread"] > 0:
        disagreements.append("target_price_spread")
    return {
        "symbol": symbol.strip().upper(),
        "broker_count": len(brokers),
        "brokers": brokers,
        "ratings": dict(sorted(ratings.items())),
        "target_price": target_summary,
        "recurring_risks": recurring_fact_values(facts, fact_type="risk"),
        "recurring_catalysts": recurring_fact_values(facts, fact_type="catalyst"),
        "disagreements": disagreements,
    }
