"""Deterministic fundamental specialist."""

from __future__ import annotations

import json
from typing import Any

from terminal.research_council.agents.base import Agent


class FundamentalAgent(Agent):
    name = "fundamental"

    def run_deterministic(self, evidence: dict, mode_profile: object | None = None) -> dict:
        rows = list((evidence.get("fundamentals") or {}).get("items") or [])
        quality = [_classify(row) for row in rows]
        supportive = [row["symbol"] for row in quality if row["quality"] == "quality_supportive"]
        weak = [row["symbol"] for row in quality if row["quality"] == "quality_weak"]
        stance = "supportive" if supportive else "neutral"
        risks = ["fundamental evidence missing"] if any(row["quality"] == "quality_unknown" for row in quality) else []
        return {
            "finding_id": "fundamental_1",
            "agent": self.name,
            "stance": stance,
            "confidence": min(0.8, 0.3 + 0.08 * len(supportive)),
            "thesis": f"{len(supportive)} candidates have supportive quality evidence.",
            "evidence": ["fundamentals.items"],
            "candidates": supportive,
            "rejects": weak,
            "risks": risks,
            "body": {"quality": quality},
        }

    def format_evidence_for_llm(self, evidence: dict, mode_profile: object | None = None) -> str:
        return json.dumps({"fundamentals": evidence.get("fundamentals")}, default=str)


def _classify(row: dict[str, Any]) -> dict[str, Any]:
    symbol = str(row.get("symbol") or "")
    fields = ("sales_growth", "profit_growth", "roe", "roce", "debt_to_equity", "promoter_pledge")
    if any(row.get(field) is None for field in fields):
        return {"symbol": symbol, "quality": "quality_unknown", "reasons": ["missing fundamentals"]}
    sales = _num(row.get("sales_growth"))
    profit = _num(row.get("profit_growth"))
    roe = _num(row.get("roe"))
    roce = _num(row.get("roce"))
    debt = _num(row.get("debt_to_equity"))
    pledge = _num(row.get("promoter_pledge"))
    opm = _num(row.get("opm"))
    reasons = []
    if sales >= 15 and profit >= 15:
        reasons.append("growth supportive")
    if roe >= 15 and roce >= 15:
        reasons.append("returns supportive")
    if debt <= 0.5:
        reasons.append("balance sheet conservative")
    if pledge > 25:
        reasons.append("promoter pledge high")
    if debt > 2:
        reasons.append("debt elevated")
    if profit < 0 or roe < 8 or roce < 8:
        reasons.append("profitability weak")
    if profit >= 15 and roe >= 15 and roce >= 15 and debt <= 0.75 and pledge <= 5 and opm >= 10:
        quality = "quality_supportive"
    elif pledge > 25 or debt > 2 or profit < 0 or roe < 8 or roce < 8:
        quality = "quality_weak"
    else:
        quality = "quality_mixed"
    return {"symbol": symbol, "quality": quality, "reasons": reasons}


def _num(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0
