"""Deterministic catalyst and event-risk specialist."""

from __future__ import annotations

import json
from typing import Any

from terminal.research_council.agents.base import Agent


class CatalystAgent(Agent):
    name = "catalyst"

    def run_deterministic(self, evidence: dict, mode_profile: object | None = None) -> dict:
        rows = list((evidence.get("events") or {}).get("items") or [])
        if not rows:
            return {
                "finding_id": "catalyst_0",
                "agent": self.name,
                "stance": "absent",
                "confidence": 0.25,
                "thesis": "No catalyst evidence available.",
                "body": {"catalysts": []},
            }

        catalysts, candidates, risks, next_steps = [], [], [], []
        classifications = []
        for row in rows:
            catalyst = _classify(row)
            catalysts.append(catalyst)
            classifications.append(catalyst["classification"])
            symbol = catalyst["symbol"]
            if catalyst["classification"] == "verified" and catalyst["high_impact_within_5d"] and symbol:
                candidates.append(symbol)
                _append_unique(risks, "high-impact event within 5 trading days")
            if catalyst["classification"] == "unstructured" and symbol:
                next_steps.append(f"Add source trail for {symbol} catalyst evidence")

        stance = _stance(classifications=classifications, risks=risks, next_steps=next_steps)
        return {
            "finding_id": "catalyst_1",
            "agent": self.name,
            "stance": stance,
            "confidence": 0.7 if stance in {"wait_for_confirmation", "verified"} else 0.4,
            "thesis": _thesis(stance, catalysts),
            "evidence": ["events.items"],
            "candidates": _unique(candidates),
            "risks": risks,
            "required_next_steps": _unique(next_steps),
            "body": {"catalysts": catalysts},
        }

    def format_evidence_for_llm(self, evidence: dict, mode_profile: object | None = None) -> str:
        return json.dumps({"events": evidence.get("events")}, default=str)


def _classify(row: dict[str, Any]) -> dict[str, Any]:
    days = _num(row.get("trading_days_ahead"))
    source = str(row.get("source") or "").strip()
    classification = "verified"
    if not source:
        classification = "unstructured"
    elif days < -5:
        classification = "stale"
    elif str(row.get("status") or "").lower() in {"stale", "expired"}:
        classification = "stale"
    elif str(row.get("status") or "").lower() == "absent":
        classification = "absent"
    high_impact = str(row.get("impact") or "").lower() == "high"
    return {
        "symbol": str(row.get("symbol") or ""),
        "event_type": str(row.get("event_type") or "UNKNOWN"),
        "trading_days_ahead": days,
        "impact": str(row.get("impact") or "unknown"),
        "source": source or None,
        "classification": classification,
        "high_impact_within_5d": classification == "verified" and high_impact and 0 <= days <= 5,
    }


def _stance(*, classifications: list[str], risks: list[str], next_steps: list[str]) -> str:
    if risks:
        return "wait_for_confirmation"
    if next_steps or "unstructured" in classifications:
        return "unstructured"
    if "verified" in classifications:
        return "verified"
    if "stale" in classifications:
        return "stale"
    return "absent"


def _thesis(stance: str, catalysts: list[dict[str, Any]]) -> str:
    if stance == "wait_for_confirmation":
        return "High-impact near-term catalyst requires confirmation before fresh risk."
    return f"{len(catalysts)} catalyst records classified as {stance}."


def _num(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 999_999


def _append_unique(values: list[str], item: str) -> None:
    if item not in values:
        values.append(item)


def _unique(values: list[str]) -> list[str]:
    seen, out = set(), []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out
