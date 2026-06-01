"""Deterministic technical specialist."""

from __future__ import annotations

import json
from typing import Any

from terminal.research_council.agents.base import Agent


class TechnicalAgent(Agent):
    name = "technical"

    def run_deterministic(self, evidence: dict, mode_profile: object | None = None) -> dict:
        rows = list((evidence.get("stocks") or {}).get("candidates") or [])
        setups = [_classify(row) for row in rows]
        actionable = [row for row in setups if row["setup_bucket"] == "ACTIONABLE"]
        insufficient = any(row["setup_bucket"] == "INSUFFICIENT_DATA" for row in setups)
        risks = []
        if insufficient:
            risks.append("insufficient technical evidence")
        if any(row["setup_bucket"] == "EXTENDED" for row in setups):
            risks.append("some setups are extended")
        stance = "selective" if actionable else "neutral"
        return {
            "finding_id": "technical_1",
            "agent": self.name,
            "stance": stance,
            "confidence": min(0.85, 0.3 + 0.1 * len(actionable)),
            "thesis": f"{len(actionable)} actionable technical setups identified.",
            "evidence": ["stocks.candidates"],
            "candidates": [row["symbol"] for row in actionable],
            "rejects": [row["symbol"] for row in setups if row["setup_bucket"] in {"DAMAGED", "CHOP"}],
            "risks": risks,
            "body": {"setups": setups},
        }

    def format_evidence_for_llm(self, evidence: dict, mode_profile: object | None = None) -> str:
        return json.dumps({"stocks": evidence.get("stocks")}, default=str)


def _classify(row: dict[str, Any]) -> dict[str, Any]:
    symbol = str(row.get("symbol") or "")
    required = ("stage", "rs", "rsi", "volume_ratio")
    if any(row.get(key) is None for key in required):
        return {"symbol": symbol, "setup_bucket": "INSUFFICIENT_DATA", "setup_name": "missing_evidence"}
    stage = str(row.get("stage") or "").upper()
    rs = _num(row.get("rs"))
    rsi = _num(row.get("rsi"))
    volume_ratio = _num(row.get("volume_ratio"))
    above_stack = bool(row.get("price_above_sma20")) and bool(row.get("price_above_sma50")) and bool(row.get("price_above_sma200"))
    near_high = _num(row.get("from_52w_high_pct")) >= -15
    bullish = above_stack and str(row.get("macd", "bullish")).lower() != "bearish" and str(row.get("supertrend", "BUY")).upper() != "SELL"
    if "STAGE_4" in stage or rs < 35 or not bool(row.get("price_above_sma200", True)):
        bucket = "DAMAGED"
    elif "STAGE_2" in stage and rs >= 70 and bullish and volume_ratio >= 1.0 and near_high:
        bucket = "EXTENDED" if rsi >= 78 else "ACTIONABLE"
    elif 45 <= rsi <= 60 and above_stack:
        bucket = "CHOP"
    else:
        bucket = "CHOP"
    close = row.get("close")
    atr = row.get("atr")
    result = {
        "symbol": symbol,
        "setup_bucket": bucket,
        "setup_name": _setup_name(bucket),
        "volume_confirms": volume_ratio >= 1.0,
        "rs_status": "leader" if rs >= 70 else "laggard" if rs < 35 else "mixed",
    }
    if close is not None and atr is not None and bucket in {"ACTIONABLE", "EXTENDED"}:
        close_n = _num(close)
        atr_n = _num(atr)
        result["entry_zone"] = {"low": close_n, "high": round(close_n + 0.5 * atr_n, 2)}
        result["stop_loss"] = round(close_n - 2 * atr_n, 2)
        result["key_invalidation"] = "close below 2 ATR stop"
    return result


def _setup_name(bucket: str) -> str:
    return {
        "ACTIONABLE": "stage2_rs_volume_confirmed",
        "EXTENDED": "extended_stage2_breakout",
        "DAMAGED": "damaged_downtrend",
        "CHOP": "no_trade_chop",
    }.get(bucket, "missing_evidence")


def _num(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0
