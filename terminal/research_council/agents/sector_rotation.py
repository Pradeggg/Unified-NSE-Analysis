"""Deterministic sector-rotation specialist."""

from __future__ import annotations

import json
from typing import Any

from terminal.research_council.agents.base import Agent


class SectorRotationAgent(Agent):
    name = "sector_rotation"

    def run_deterministic(self, evidence: dict, mode_profile: object | None = None) -> dict:
        items = list((evidence.get("sectors") or {}).get("items") or [])
        if not items:
            return {
                "finding_id": "sector_rotation_0",
                "agent": self.name,
                "stance": "neutral",
                "confidence": 0.2,
                "thesis": "Sector evidence is unavailable.",
                "risks": ["sector evidence missing"],
                "body": {"leader_sectors": [], "improver_sectors": [], "laggard_sectors": [], "rotation_signals": []},
            }

        tailwinds = (evidence.get("sectors") or {}).get("macro_tailwinds") or {}
        targeted_mode = bool(evidence.get("sector_opportunity"))
        leaders, improvers, laggards, targeted, signals, candidates = [], [], [], [], [], []
        for row in items:
            sector = str(row.get("sector") or "")
            rs_1m = _num(row.get("rs_1m"))
            rs_3m = _num(row.get("rs_3m"))
            breadth_raw = row.get("breadth_pct_above_50dma")
            breadth = _num(breadth_raw)
            stage2 = int(row.get("stage2_count") or 0)
            buy_signals = int(row.get("buy_signals") or 0)
            top_stocks = list(row.get("top_stocks") or [])
            record = {
                "sector": sector,
                "rs_1m": rs_1m,
                "rs_3m": rs_3m,
                "breadth_pct_above_50dma": breadth,
                "stage2_count": stage2,
                "buy_signals": buy_signals,
                "macro_tailwind": tailwinds.get(sector),
                "top_stocks": top_stocks,
            }
            if rs_1m >= 8 and rs_3m >= 10 and breadth >= 60:
                leaders.append(record)
                candidates.extend(top_stocks[:5])
            elif rs_1m > 0 and rs_3m > 0 and breadth >= 45:
                improvers.append(record)
                candidates.extend(top_stocks[:3])
            elif rs_1m <= -5 and rs_3m <= -5 and breadth < 40:
                laggards.append(record)
            elif targeted_mode and top_stocks and breadth_raw is None and (stage2 > 0 or buy_signals > 0):
                targeted.append(record)
                candidates.extend(top_stocks[:5])
            if rs_1m > 5 and breadth < 45:
                signals.append({"sector": sector, "signal": "BREADTH_BREAKDOWN"})
            elif rs_1m >= 8 and rs_3m >= 10 and breadth < 55:
                signals.append({"sector": sector, "signal": "MOMENTUM_PEAK"})

        stance = (
            "constructive"
            if leaders
            else "mixed"
            if improvers
            else "targeted_shortlist"
            if targeted
            else "defensive"
            if laggards
            else "neutral"
        )
        unique_candidates = _unique(candidates)
        thesis = f"{len(leaders)} leader sectors and {len(improvers)} improver sectors identified."
        if targeted and not leaders and not improvers:
            thesis = f"{len(unique_candidates)} ranked stocks available for targeted sector review."
        risks = ["sector breadth divergence"] if signals else []
        if targeted:
            risks.append("sector breadth evidence missing")
        return {
            "finding_id": "sector_rotation_1",
            "agent": self.name,
            "stance": stance,
            "confidence": min(0.85, 0.35 + 0.1 * len(leaders) + 0.05 * len(improvers) + 0.05 * len(targeted)),
            "thesis": thesis,
            "evidence": ["sectors.items", "sectors.macro_tailwinds"],
            "candidates": unique_candidates,
            "rejects": [s for row in laggards for s in row["top_stocks"]],
            "risks": risks,
            "body": {
                "leader_sectors": leaders,
                "improver_sectors": improvers,
                "targeted_sectors": targeted,
                "laggard_sectors": laggards,
                "rotation_signals": signals,
                "candidate_clusters": [{"theme": row["sector"], "symbols": row["top_stocks"]} for row in leaders],
            },
        }

    def format_evidence_for_llm(self, evidence: dict, mode_profile: object | None = None) -> str:
        return json.dumps({"sectors": evidence.get("sectors")}, default=str)


def _num(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _unique(values: list[str]) -> list[str]:
    seen = set()
    out = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out
