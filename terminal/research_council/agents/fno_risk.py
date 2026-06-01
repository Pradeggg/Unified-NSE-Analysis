"""Deterministic F&O and derivatives-risk specialist."""

from __future__ import annotations

import json
from typing import Any

from terminal.research_council.agents.base import Agent


class FnoRiskAgent(Agent):
    name = "fno_risk"

    def run_deterministic(self, evidence: dict, mode_profile: object | None = None) -> dict:
        derivatives = evidence.get("derivatives") or {}
        futures_rows = list(derivatives.get("futures") or derivatives.get("items") or [])
        option_chain = derivatives.get("option_chain") or {}
        if not futures_rows:
            return {
                "finding_id": "fno_risk_0",
                "agent": self.name,
                "stance": "unavailable",
                "confidence": 0.2,
                "thesis": "F&O evidence is unavailable.",
                "risks": ["fno evidence missing"],
                "required_next_steps": ["Load futures and option-chain evidence"],
                "body": {"setups": []},
            }

        setups, candidates, rejects, risks, next_steps = [], [], [], [], []
        hedge_needed = False
        for row in futures_rows:
            symbol = str(row.get("symbol") or "")
            chain = option_chain.get(symbol) if isinstance(option_chain, dict) else None
            setup = _classify_setup(row, chain)
            setups.append(setup)
            if setup["option_chain_available"] is False and symbol:
                next_steps.append(f"Add option-chain evidence for {symbol}")
            if setup["fno_view"] == "bullish_derivatives" and symbol:
                candidates.append(symbol)
            if setup["fno_view"] == "bearish_derivatives" and symbol:
                rejects.append(symbol)
            if setup["crowding"] == "crowded_long":
                _append_unique(risks, "crowded long positioning")
            if setup["iv_state"] == "elevated":
                _append_unique(risks, "elevated IV")
            hedge_needed = hedge_needed or bool(setup["hedge_needed"])

        stance = _stance(hedge_needed=hedge_needed, next_steps=next_steps, candidates=candidates, rejects=rejects)
        return {
            "finding_id": "fno_risk_1",
            "agent": self.name,
            "stance": stance,
            "confidence": 0.7 if not next_steps else 0.45,
            "thesis": _thesis(stance, len(setups), bool(next_steps)),
            "evidence": ["derivatives.futures", "derivatives.option_chain"],
            "candidates": _unique(candidates),
            "rejects": _unique(rejects),
            "risks": risks,
            "required_next_steps": _unique(next_steps),
            "body": {"setups": setups},
        }

    def format_evidence_for_llm(self, evidence: dict, mode_profile: object | None = None) -> str:
        return json.dumps({"derivatives": evidence.get("derivatives")}, default=str)


def _classify_setup(row: dict[str, Any], chain: dict[str, Any] | None) -> dict[str, Any]:
    symbol = str(row.get("symbol") or "")
    buildup = str(row.get("futures_buildup") or row.get("buildup") or "").upper()
    oi_change = _num(row.get("oi_change_pct"))
    price_change = _num(row.get("price_change_pct"))
    option_available = bool(chain)
    pcr = _num(chain.get("pcr")) if chain else None
    iv_percentile = _num(chain.get("iv_percentile")) if chain else None
    fno_view = _fno_view(buildup)
    crowding = _crowding(buildup=buildup, oi_change=oi_change, price_change=price_change, pcr=pcr)
    iv_state = "elevated" if iv_percentile is not None and iv_percentile >= 75 else "normal" if iv_percentile is not None else "unknown"
    hedge_needed = crowding == "crowded_long" or iv_state == "elevated"
    return {
        "symbol": symbol,
        "cash_equity_view": "separate_from_fno",
        "fno_view": fno_view,
        "futures_buildup": buildup or "UNKNOWN",
        "oi_change_pct": oi_change,
        "price_change_pct": price_change,
        "option_chain_available": option_available,
        "pcr": pcr,
        "iv_percentile": iv_percentile,
        "iv_state": iv_state,
        "crowding": crowding,
        "hedge_needed": hedge_needed,
    }


def _fno_view(buildup: str) -> str:
    if buildup == "LONG_BUILDUP":
        return "bullish_derivatives"
    if buildup == "SHORT_BUILDUP":
        return "bearish_derivatives"
    if buildup == "LONG_UNWINDING":
        return "weakening_derivatives"
    if buildup == "SHORT_COVERING":
        return "relief_derivatives"
    return "neutral_derivatives"


def _crowding(*, buildup: str, oi_change: float, price_change: float, pcr: float | None) -> str:
    if buildup == "LONG_BUILDUP" and oi_change >= 25 and price_change >= 5:
        return "crowded_long"
    if pcr is not None and pcr >= 1.7 and buildup == "LONG_BUILDUP":
        return "crowded_long"
    if buildup == "SHORT_BUILDUP" and oi_change >= 20:
        return "crowded_short"
    return "not_crowded"


def _stance(*, hedge_needed: bool, next_steps: list[str], candidates: list[str], rejects: list[str]) -> str:
    if hedge_needed:
        return "hedge_required"
    if next_steps:
        return "needs_confirmation"
    if rejects and not candidates:
        return "defensive"
    if candidates:
        return "supportive"
    return "neutral"


def _thesis(stance: str, setup_count: int, missing_options: bool) -> str:
    if missing_options:
        return f"{setup_count} F&O setups reviewed, but option-chain confirmation is missing."
    return f"{setup_count} F&O setups reviewed with stance {stance}."


def _num(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


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
