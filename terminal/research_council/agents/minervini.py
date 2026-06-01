"""Deterministic Minervini-style setup specialist."""

from __future__ import annotations

import json
from typing import Any

from terminal.research_council.agents.base import Agent


class MinerviniAgent(Agent):
    name = "minervini"

    def run_deterministic(self, evidence: dict, mode_profile: object | None = None) -> dict:
        setups, candidates, rejects, next_steps = [], [], [], []
        for row in ((evidence.get("stocks") or {}).get("candidates") or []):
            symbol = str(row.get("symbol") or "")
            reasons = _reject_reasons(row)
            if _tightness_missing(row):
                next_steps.append(f"Add VCP/tightness evidence for {symbol}")
            verdict = "MINERVINI_PASS" if not reasons else "REJECT"
            setups.append(
                {
                    "symbol": symbol,
                    "verdict": verdict,
                    "rs": _num(row.get("rs")),
                    "from_52w_high_pct": _num(row.get("from_52w_high_pct")),
                    "tightness_pct": row.get("tightness_pct"),
                    "reject_reasons": reasons,
                }
            )
            if verdict == "MINERVINI_PASS":
                candidates.append(symbol)
            elif symbol:
                rejects.append(symbol)

        stance = "selective_long" if candidates else "watchlist" if next_steps else "no_setup"
        return {
            "finding_id": "minervini_1",
            "agent": self.name,
            "stance": stance,
            "confidence": 0.75 if candidates else 0.45 if next_steps else 0.55,
            "thesis": f"{len(candidates)} candidates passed strict Minervini-style filters.",
            "evidence": ["stocks.candidates"],
            "candidates": candidates,
            "rejects": rejects,
            "risks": ["strict filter may reject early turnarounds"] if rejects else [],
            "required_next_steps": next_steps,
            "body": {"setups": setups},
        }

    def format_evidence_for_llm(self, evidence: dict, mode_profile: object | None = None) -> str:
        return json.dumps({"stocks": evidence.get("stocks")}, default=str)


def _reject_reasons(row: dict[str, Any]) -> list[str]:
    reasons = []
    if str(row.get("stage") or "").upper() != "STAGE_2":
        reasons.append("not_stage2")
    if _num(row.get("rs")) < 80:
        reasons.append("rs_below_80")
    if not (row.get("price_above_sma20") and row.get("price_above_sma50") and row.get("price_above_sma200")):
        reasons.append("ma_alignment_failed")
    if _num(row.get("from_52w_high_pct")) < -25:
        reasons.append("too_far_from_52w_high")
    if _num(row.get("volume_ratio")) < 1.2:
        reasons.append("volume_confirmation_missing")
    if _tightness_missing(row):
        reasons.append("tightness_unavailable")
    elif _num(row.get("from_52w_high_pct")) > 2 or _num(row.get("tightness_pct")) > 12 or _num(row.get("volume_ratio")) > 3:
        reasons.append("extended_or_loose")
    return reasons


def _tightness_missing(row: dict[str, Any]) -> bool:
    return row.get("tightness_pct") is None


def _num(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0
