"""LLM-first contextual situation assessment for Agent Adda.

The LLM is allowed to assess conversation context and select from a bounded
tool vocabulary. It is not allowed to execute tools directly, invent new tools,
or bypass the deterministic situation assessor fallback.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from .situation_assessment import (
    ClarificationOption,
    ClarificationQuestion,
    SituationAssessment,
    TurnContext,
    classify_grounded_intent,
    needs_situation_assessment,
)

log = logging.getLogger(__name__)


def llm_situation_assessment_enabled() -> bool:
    return os.getenv("AGENT_ADDA_LLM_SITUATION_ASSESSMENT", "1").lower() not in {
        "0",
        "false",
        "no",
    }


MIN_CONFIDENCE = float(os.getenv("AGENT_ADDA_LLM_SITUATION_MIN_CONF", "0.70"))

ALLOWED_DECISIONS = frozenset({
    "answer_from_context",
    "ask_clarification",
    "run_tool_plan",
    "fallback_to_deterministic",
})

ALLOWED_TOOLS = frozenset({
    "resolve_symbol",
    "get_symbol_snapshot",
    "get_symbol_quick_analysis",
    "get_technical_setup",
    "get_sector_context",
    "get_cached_financials",
    "scrape_screener_in",
    "get_latest_results",
    "search_nse_announcements",
    "search_bse_filings",
    "search_latest_catalysts",
    "read_report",
    "summarize_report",
    "open_report",
    "compare_stocks",
    "explain_intraday_setup",
    "get_intraday_levels",
    "run_screener_query",
    "get_market_breadth",
    "get_index_snapshot",
    "get_live_market_overview",
    "get_long_term_growth_candidates",
})

_SYSTEM_PROMPT = """\
You are Agent Adda's first-class situation assessor for Indian equity research.

Your job is to understand whether the current user message depends on the
active conversation context, then decide the safest next action.

Return strict JSON only. Do not call tools. Do not invent facts, symbols, or
tool names. Use only the provided conversation_context and allowed_tools.

Allowed decisions:
- answer_from_context: only when the prior context already contains enough
  evidence to answer without fresh tools.
- ask_clarification: when the user reference is ambiguous or context is absent.
- run_tool_plan: when fresh grounded evidence is needed.
- fallback_to_deterministic: when deterministic routing should handle it.

Required JSON shape:
{
  "applies": true,
  "decision": "answer_from_context" | "ask_clarification" | "run_tool_plan" | "fallback_to_deterministic",
  "confidence": 0.0,
  "user_is_asking": "one sentence",
  "context_found": "one sentence",
  "source_assessment": "one sentence",
  "clarification_question": "",
  "clarification_options": [{"label": "A", "text": "short option"}],
  "resolved_entities": ["NSE_SYMBOL"],
  "evidence_plan": ["short evidence step"],
  "tool_plan": [{"tool": "allowed_tool_name", "args": {"symbol": "NSE_SYMBOL"}}],
  "plan": ["short execution step"],
  "synthesis_intent": "stock_brief"
}

Stock-market rules:
- Resolve pronouns like it/this/these from conversation_context, not from the
  current text alone.
- For sales, EPS, profit, quarterly results, shareholding, valuation, or
  business questions, prefer PostgreSQL cached fundamentals first, then
  screener.in evidence, then exchange filings when useful.
- For technical, stage, RS, RSI, trend, support/resistance, or setup questions,
  use technical/snapshot tools.
- For index breadth or top-pick universe requests, use scoped index/breadth or
  long-term candidate tools rather than treating the index name as a stock.
- When market_status says closed, avoid implying live intraday freshness unless
  an intraday tool is explicitly planned.
"""


def should_run_llm_situation_assessment(
    user_input: str,
    previous_context: TurnContext | None,
) -> bool:
    if not llm_situation_assessment_enabled():
        return False
    text = (user_input or "").strip()
    if not text:
        return False
    if needs_situation_assessment(text):
        return True
    if previous_context is None:
        return False
    return bool(
        re.search(
            r"\b("
            r"it|its|this|that|these|those|same|above|previous|earlier|"
            r"context|report|growth|eps|sales|results|fundamental|technical"
            r")\b",
            text,
            flags=re.IGNORECASE,
        )
    )


def classify_llm_situation_assessment(
    user_input: str,
    previous_context: TurnContext | None,
    backend: Any,
    *,
    data_mode: str = "historical",
    market_status: dict[str, Any] | None = None,
) -> SituationAssessment | None:
    if backend is None:
        return None
    payload = _prompt_payload(
        user_input=user_input,
        previous_context=previous_context,
        data_mode=data_mode,
        market_status=market_status,
    )
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, indent=2, sort_keys=True)},
    ]
    try:
        response = backend.chat(messages, tools=[])
        data = _parse_json_object(str(response.get("content") or ""))
        return validate_llm_situation_assessment(data, user_input, previous_context)
    except Exception:
        log.debug("LLM situation assessment failed", exc_info=True)
        return None


def validate_llm_situation_assessment(
    data: dict[str, Any],
    user_input: str,
    previous_context: TurnContext | None,
) -> SituationAssessment | None:
    if not isinstance(data, dict):
        return None
    if data.get("applies") is False:
        return None
    decision = str(data.get("decision") or "").strip()
    if decision not in ALLOWED_DECISIONS or decision == "fallback_to_deterministic":
        return None
    confidence_value = _float_confidence(data.get("confidence"))
    if confidence_value < MIN_CONFIDENCE:
        return None
    if decision == "answer_from_context" and previous_context is None:
        return None

    tool_plan = _validate_tool_plan(data.get("tool_plan"))
    if decision == "run_tool_plan" and not tool_plan:
        return None
    if decision != "run_tool_plan":
        tool_plan = []

    clarification_questions = _clarification_questions(data)
    if decision == "ask_clarification" and not (
        str(data.get("clarification_question") or "").strip() or clarification_questions
    ):
        return None

    grounded_intent = classify_grounded_intent(user_input)
    return SituationAssessment(
        applies=True,
        decision=decision,
        confidence=_confidence_label(confidence_value),
        user_is_asking=str(data.get("user_is_asking") or "").strip(),
        context_found=str(data.get("context_found") or "").strip(),
        source_assessment=str(data.get("source_assessment") or "").strip(),
        clarification_question=str(data.get("clarification_question") or "").strip(),
        clarification_questions=tuple(clarification_questions),
        resolved_entities=_string_list(data.get("resolved_entities")),
        evidence_plan=_string_list(data.get("evidence_plan")),
        tool_plan=tool_plan,
        plan=_string_list(data.get("plan")),
        requires_grounding=bool(grounded_intent),
        grounded_intent=grounded_intent,
        synthesis_intent=str(data.get("synthesis_intent") or "").strip(),
    )


def _prompt_payload(
    *,
    user_input: str,
    previous_context: TurnContext | None,
    data_mode: str,
    market_status: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "user_input": user_input,
        "mode": data_mode,
        "market_status": _compact_market_status(market_status),
        "allowed_tools": sorted(ALLOWED_TOOLS),
        "conversation_context": _compact_context(previous_context),
    }


def _compact_market_status(status: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(status, dict):
        return {}
    keys = (
        "is_open",
        "status",
        "state",
        "clock",
        "now",
        "next_open",
        "next_close",
        "timezone",
    )
    return {key: status[key] for key in keys if key in status and status[key] is not None}


def _compact_context(ctx: TurnContext | None) -> dict[str, Any]:
    if ctx is None:
        return {
            "available": False,
            "summary": "No active structured turn context is available.",
        }
    return {
        "available": True,
        "last_user_input": ctx.user_input,
        "intent": ctx.intent,
        "mode": ctx.mode,
        "tools": list(ctx.tools)[:20],
        "source_label": ctx.source_label,
        "freshness": ctx.freshness or "",
        "result_type": ctx.result_type or "",
        "result_summary": ctx.result_summary[:1200],
        "symbols": list(ctx.symbols)[:30],
        "result_items": list(ctx.result_items)[:40],
        "result_groups": {key: values[:30] for key, values in (ctx.result_groups or {}).items()},
        "tool_args": list(ctx.tool_args)[:10],
    }


def _validate_tool_plan(raw: Any) -> list[tuple[str, dict[str, Any]]]:
    if not isinstance(raw, list):
        return []
    plan: list[tuple[str, dict[str, Any]]] = []
    for item in raw:
        if isinstance(item, dict):
            tool = str(item.get("tool") or "").strip()
            args = item.get("args") if isinstance(item.get("args"), dict) else {}
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            tool = str(item[0] or "").strip()
            args = item[1] if isinstance(item[1], dict) else {}
        else:
            return []
        if tool not in ALLOWED_TOOLS:
            return []
        plan.append((tool, dict(args)))
    return plan


def _clarification_questions(data: dict[str, Any]) -> list[ClarificationQuestion]:
    prompt = str(data.get("clarification_question") or "").strip()
    raw_options = data.get("clarification_options")
    if not isinstance(raw_options, list) or not prompt:
        return []
    options: list[ClarificationOption] = []
    for idx, item in enumerate(raw_options[:5]):
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or chr(ord("A") + idx)).strip()[:3]
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        options.append(ClarificationOption(label=label, text=text))
    if not options:
        return []
    return [ClarificationQuestion(prompt=prompt, options=tuple(options))]


def _string_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        value = str(item or "").strip()
        if value:
            out.append(value)
    return out


def _float_confidence(raw: Any) -> float:
    try:
        value = float(raw)
    except Exception:
        label = str(raw or "").lower().strip()
        if label == "high":
            value = 0.9
        elif label == "medium":
            value = 0.75
        else:
            value = 0.0
    return max(0.0, min(1.0, value))


def _confidence_label(value: float) -> str:
    if value >= 0.85:
        return "high"
    if value >= 0.70:
        return "medium"
    return "low"


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
