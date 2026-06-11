"""LLM-backed semantic intent routing for open-ended market queries.

The LLM is used only as an intent classifier. It never supplies executable
tool calls directly; this module maps approved intent labels to fixed,
deterministic tool plans.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

SEMANTIC_INTENT_ENABLED = os.getenv("AGENT_ADDA_SEMANTIC_INTENT", "1").lower() not in {
    "0",
    "false",
    "no",
}

MIN_CONFIDENCE = float(os.getenv("AGENT_ADDA_SEMANTIC_INTENT_MIN_CONF", "0.72"))

ALLOWED_INTENTS = frozenset({
    "market_swing_candidates",
    "quality_breakouts",
    "market_overview",
    "market_knowledge",
    "no_route",
})

_SYSTEM_PROMPT = """\
You are Agent Adda's semantic intent classifier for Indian market research.

Classify the user's natural-language request into exactly one allowed intent.
You are not allowed to call tools or invent symbols. Return JSON only.

Allowed intents:
- market_swing_candidates: market-wide swing trade ideas, 2-3 week opportunities,
  swing candidates, trade opportunities, market setup plus names to watch.
- quality_breakouts: new highs, VCP/tight-range, breakouts with good fundamentals,
  quality breakout candidates.
- market_overview: broad market status, breadth, index/sector overview.
- market_knowledge: educational concept explanations, e.g. ROCE, ROE, RSI, PE.
- no_route: stock-specific analysis, exact slash commands, unclear requests, or
  anything not covered above.

Return strict JSON:
{
  "intent": "market_swing_candidates" | "quality_breakouts" | "market_overview" | "market_knowledge" | "no_route",
  "confidence": 0.0,
  "reason": "short public reason",
  "horizon": "intraday" | "swing" | "long_term" | "",
  "universe": "NIFTY 500" | "NIFTY 50" | ""
}

Rules:
- Prefer no_route for named-stock questions like "analyze RELIANCE" or "TATASTEEL results".
- Prefer no_route for slash commands because deterministic command routing owns them.
- Prefer market_swing_candidates for loose phrases like "swing trades opportunities",
  "2-3 week trading ideas", or "what can I buy for swing".
- Do not output tool names.
"""


@dataclass(frozen=True)
class SemanticIntentDecision:
    intent: str
    confidence: float
    reason: str = ""
    horizon: str = ""
    universe: str = ""
    plan: tuple[tuple[str, dict[str, Any]], ...] = ()

    def to_trace(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "confidence": self.confidence,
            "reason": self.reason,
            "horizon": self.horizon,
            "universe": self.universe,
            "plan": [(tool, args) for tool, args in self.plan],
        }


def _normalize_index_universe(universe: str) -> str:
    raw = re.sub(r"\s+", " ", (universe or "").strip().upper())
    if not raw:
        return ""
    match = re.match(r"^NIFTY(\d{2,4})$", raw)
    if match:
        return f"NIFTY {match.group(1)}"
    return raw if raw.startswith("NIFTY ") else ""


def semantic_intent_plan(
    intent: str,
    user_input: str,
    data_mode: str = "historical",
    universe: str = "",
) -> tuple[tuple[str, dict[str, Any]], ...]:
    """Return a fixed grounded tool plan for an approved semantic intent."""
    index_universe = _normalize_index_universe(universe)
    breadth_args = {"index": index_universe} if index_universe else {}
    if intent == "market_swing_candidates":
        return (
            ("get_index_snapshot", {"index_name": "NIFTY 50"}),
            ("get_index_snapshot", {"index_name": "NIFTY MIDCAP 100"}),
            ("get_market_breadth", breadth_args),
            ("run_quality_breakout_screener", {"top_n": 15, "mode": "balanced"}),
        )
    if intent == "quality_breakouts":
        return (("run_quality_breakout_screener", {"top_n": 15, "mode": "balanced"}),)
    if intent == "market_overview":
        return (
            ("get_live_market_overview", {}),
            ("get_market_breadth", breadth_args),
        )
    if intent == "market_knowledge":
        return (("search_market_knowledge", {"query": user_input.strip()}),)
    return ()


def should_run_semantic_intent(user_input: str) -> bool:
    """Cheap gate so exact commands and obvious symbols keep deterministic paths."""
    if not SEMANTIC_INTENT_ENABLED:
        return False
    text = (user_input or "").strip()
    if not text or text.startswith("/"):
        return False
    if len(text.split()) <= 1:
        return False
    # Avoid named-stock/symbol-looking requests; stock routes have stronger
    # symbol grounding logic than the semantic classifier.
    if re.search(r"\b[A-Z][A-Z0-9&.-]{1,11}\b", text):
        return False
    trigger = re.search(
        r"\b("
        r"swing|opportunit(?:y|ies)|ideas?|candidates?|setups?|"
        r"breakouts?|vcp|new highs?|market overview|market status|"
        r"breadth|explain|define|what is|how does"
        r")\b",
        text,
        flags=re.IGNORECASE,
    )
    return bool(trigger)


def classify_semantic_intent(
    user_input: str,
    backend: Any,
    *,
    data_mode: str = "historical",
) -> SemanticIntentDecision | None:
    """Classify an open-ended query using the configured LLM backend."""
    if backend is None or not should_run_semantic_intent(user_input):
        return None
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps({"user_input": user_input, "mode": data_mode})},
    ]
    try:
        response = backend.chat(messages, tools=[])
        content = str(response.get("content") or "")
        data = _parse_json_object(content)
        return validate_semantic_intent(data, user_input, data_mode=data_mode)
    except Exception as exc:
        log.debug("semantic intent classification failed", exc_info=True)
        return None


def validate_semantic_intent(
    data: dict[str, Any],
    user_input: str,
    *,
    data_mode: str = "historical",
) -> SemanticIntentDecision | None:
    """Validate raw LLM JSON and attach the deterministic tool plan."""
    if not isinstance(data, dict):
        return None
    intent = str(data.get("intent") or "").strip()
    if intent not in ALLOWED_INTENTS or intent == "no_route":
        return None
    try:
        confidence = float(data.get("confidence", 0.0))
    except Exception:
        confidence = 0.0
    if confidence < MIN_CONFIDENCE:
        return None
    universe = str(data.get("universe") or "")
    plan = semantic_intent_plan(intent, user_input, data_mode=data_mode, universe=universe)
    if not plan:
        return None
    return SemanticIntentDecision(
        intent=intent,
        confidence=confidence,
        reason=str(data.get("reason") or ""),
        horizon=str(data.get("horizon") or ""),
        universe=universe,
        plan=plan,
    )


def _parse_json_object(content: str) -> dict[str, Any]:
    cleaned = (content or "").strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1)
    try:
        data = json.loads(cleaned)
    except Exception:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            return {}
        data = json.loads(match.group(0))
    return data if isinstance(data, dict) else {}
