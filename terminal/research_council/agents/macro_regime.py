"""Deterministic macro and market-regime specialist."""

from __future__ import annotations

import json
from typing import Any

from terminal.research_council.agents.base import Agent


class MacroRegimeAgent(Agent):
    name = "macro_regime"

    def run_deterministic(self, evidence: dict, mode_profile: object | None = None) -> dict:
        market = evidence.get("market") or {}
        breadth = _num(market.get("breadth_pct_above_50dma") or market.get("breadth"))
        flow_5d = _num(market.get("fii_dii_flow_5d_cr"))
        flow_1d = _num(market.get("fii_dii_flow_1d_cr"))
        raw_regime = str(market.get("regime") or "").lower()
        flow_context = _flow_context(flow_5d)
        risk_regime = _risk_regime(raw_regime=raw_regime, breadth=breadth, flow_5d=flow_5d)
        tailwinds, headwinds = _sector_winds(evidence)
        risks = []
        if breadth < 40:
            risks.append("breadth deterioration")
        if flow_5d < 0:
            risks.append("five-day institutional flow pressure")

        return {
            "finding_id": "macro_regime_1",
            "agent": self.name,
            "stance": risk_regime,
            "confidence": _confidence(breadth=breadth, flow_5d=flow_5d),
            "thesis": f"Macro regime is {risk_regime} with {flow_context} flow context.",
            "evidence": ["market.regime", "market.breadth_pct_above_50dma", "market.fii_dii_flow_5d_cr"],
            "risks": risks,
            "body": {
                "risk_regime": risk_regime,
                "breadth_pct_above_50dma": breadth,
                "flow_5d_cr": flow_5d,
                "flow_1d_cr": flow_1d,
                "flow_context": flow_context,
                "tailwinds": tailwinds,
                "headwinds": headwinds,
            },
        }

    def format_evidence_for_llm(self, evidence: dict, mode_profile: object | None = None) -> str:
        return json.dumps({"market": evidence.get("market"), "sectors": evidence.get("sectors")}, default=str)


def _risk_regime(*, raw_regime: str, breadth: float, flow_5d: float) -> str:
    if breadth < 25 or (breadth < 40 and flow_5d < 0):
        return "risk_off"
    if breadth < 45 or flow_5d < 0:
        return "risk_mixed"
    if "risk_on" in raw_regime or breadth >= 60:
        return "risk_on"
    return "risk_mixed"


def _flow_context(flow_5d: float) -> str:
    if flow_5d > 0:
        return "five_day_positive"
    if flow_5d < 0:
        return "five_day_negative"
    return "five_day_neutral"


def _sector_winds(evidence: dict) -> tuple[list[str], list[str]]:
    tailwinds, headwinds = [], []
    for row in ((evidence.get("sectors") or {}).get("items") or []):
        sector = str(row.get("sector") or "")
        rs_1m = _num(row.get("rs_1m"))
        breadth = _num(row.get("breadth_pct_above_50dma"))
        if sector and rs_1m >= 8 and breadth >= 60:
            tailwinds.append(sector)
        elif sector and rs_1m < 0 and breadth < 40:
            headwinds.append(sector)
    return tailwinds, headwinds


def _confidence(*, breadth: float, flow_5d: float) -> float:
    score = 0.45
    if breadth:
        score += 0.15
    if flow_5d:
        score += 0.1
    return min(0.8, score)


def _num(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0
