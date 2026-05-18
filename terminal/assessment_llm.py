"""Premium-LLM tier for situation assessment.

This module is invoked **only** when the deterministic chain in
``situation_assessment.assess_followup`` returns ``fallback_to_router``
or a low/medium-confidence ``ask_clarification`` AND there is genuine
prior turn context to bind. It must never run for every turn — the cost
and latency of a premium reasoning model would be prohibitive.

Design contract:
  - Same return type as ``assess_followup`` (``SituationAssessment``).
  - Structured JSON output enforced via ``response_format``.
  - On any error (no API key, timeout, schema mismatch, network) we
    return ``applies=False`` so the caller falls through to the existing
    LLM router. The deterministic+main-router pipeline is the safety net.
  - No side effects, no global state.
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
)

_log = logging.getLogger(__name__)

# Premium-tier reasoning model (user choice). Override via env.
# Fallback chain is used if the primary id is rejected by the API.
ASSESSMENT_MODEL = os.getenv("ASSESSMENT_MODEL", "o1")
ASSESSMENT_FALLBACK_MODELS = ("o1-mini", "gpt-4o")
ASSESSMENT_TIMEOUT_S = float(os.getenv("ASSESSMENT_LLM_TIMEOUT", "15"))
ASSESSMENT_ENABLED = os.getenv("ASSESSMENT_LLM_ENABLED", "1") not in {"0", "false", "False"}

_SYSTEM_PROMPT = """\
You classify a user's follow-up message against the previous turn's context for an NSE market-research terminal.

Return STRICT JSON matching this schema:
{
  "decision": "run_tool_plan" | "answer_from_context" | "ask_clarification" | "fallback_to_router",
  "confidence": "low" | "medium" | "high",
  "user_is_asking": "<one short sentence>",
  "carry_symbols": [<NSE tickers from prior context to keep>],
  "tool_plan": [
    {"tool": "read_report" | "summarize_report" | "open_report" | "scan_symbols_intraday" | ..., "args": {...}}
  ],
  "clarification_questions": [
    {
      "prompt": "<question>",
      "default_label": "A" | "B" | "C" | "",
      "options": [
        {"label": "A", "text": "<choice>", "bound_action": {"decision": "...", "tool_plan": [...]}},
        ...
      ]
    }
  ]
}

Rules:
- NEVER invent a ticker that wasn't in the previous turn's symbols.
- If the user refers to "the report", "it", "summary", "recommendation" and the previous turn has a report path, set decision=run_tool_plan with read_report+summarize_report on that exact path.
- If the user wants the report opened ("open it", "show me"), use open_report.
- If the user is genuinely ambiguous, set decision=ask_clarification and emit 2-4 numbered options with bound_action payloads (each bound_action MUST itself be a valid {decision, tool_plan} object so the agent can execute it directly).
- If the user is asking something unrelated to prior context, set decision=fallback_to_router with empty tool_plan.
- tool_plan args MUST use the actual paths/symbols from the previous turn context — do not paraphrase.
"""


def llm_assess_followup(
    user_input: str,
    previous_context: TurnContext | None,
    pending_clarification: SituationAssessment | None = None,
) -> SituationAssessment:
    """Premium-LLM situation assessment for ambiguous follow-ups.

    Returns ``applies=False`` if the LLM tier is disabled, the API is
    unreachable, or the response cannot be parsed. Callers MUST treat
    that as a clean fall-through to the existing LLM router.
    """
    if not ASSESSMENT_ENABLED:
        return _disabled("LLM assessment tier disabled via env.")
    if not previous_context:
        return _disabled("No previous turn context — LLM tier skipped.")
    if not os.getenv("OPENAI_API_KEY"):
        return _disabled("OPENAI_API_KEY not set — LLM tier skipped.")

    try:
        client = _get_client()
    except Exception as exc:
        _log.debug("LLM assessment client init failed: %s", exc)
        return _disabled(f"LLM client init failed: {exc}")

    payload = _build_payload(user_input, previous_context, pending_clarification)
    last_err: str = ""
    for model_id in (ASSESSMENT_MODEL, *ASSESSMENT_FALLBACK_MODELS):
        try:
            raw = _call_llm(client, model_id, payload)
        except Exception as exc:
            last_err = f"{model_id}: {exc}"
            _log.debug("LLM assessment call failed: %s", last_err)
            continue
        parsed = _parse_response(raw, previous_context)
        if parsed is not None:
            return parsed
        last_err = f"{model_id}: schema parse failed"
        _log.debug("LLM assessment parse failed for %s", model_id)
    return _disabled(f"LLM tier exhausted ({last_err})")


# ─────────────────────────────────────────────────────────────────────────────
# Internals
# ─────────────────────────────────────────────────────────────────────────────


def _disabled(reason: str) -> SituationAssessment:
    return SituationAssessment(
        applies=False,
        decision="fallback_to_router",
        confidence="low",
        user_is_asking=reason,
    )


def _get_client():
    from openai import OpenAI
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=ASSESSMENT_TIMEOUT_S)


def _build_payload(
    user_input: str,
    previous_context: TurnContext,
    pending_clarification: SituationAssessment | None,
) -> dict[str, Any]:
    prior_report_path = ""
    for item in previous_context.result_items:
        text = str(item)
        if re.search(r"\.(?:html|md|pdf|json|csv)$", text, re.IGNORECASE):
            prior_report_path = text
            break

    pending_view: dict[str, Any] = {}
    if pending_clarification and pending_clarification.clarification_questions:
        pending_view = {
            "questions": [
                {
                    "prompt": q.prompt,
                    "options": [
                        {"label": opt.label, "text": opt.text} for opt in q.options
                    ],
                }
                for q in pending_clarification.clarification_questions
            ],
        }

    return {
        "user_input": user_input,
        "previous_turn": {
            "intent": previous_context.intent,
            "mode": previous_context.mode,
            "source_label": previous_context.source_label,
            "symbols": previous_context.symbols,
            "tools": previous_context.tools,
            "result_summary": previous_context.result_summary,
            "report_path": prior_report_path,
            "result_items": previous_context.result_items[:10],
        },
        "pending_clarification": pending_view,
    }


def _call_llm(client, model_id: str, payload: dict) -> str:
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, default=str)},
    ]
    # o1-class reasoning models reject `response_format`; we ask for JSON
    # in the system prompt and parse defensively.
    kwargs: dict[str, Any] = {"model": model_id, "messages": messages}
    if not model_id.startswith("o1") and not model_id.startswith("o3"):
        kwargs["temperature"] = 0
        kwargs["response_format"] = {"type": "json_object"}
    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content or ""


def _parse_response(raw: str, previous_context: TurnContext) -> SituationAssessment | None:
    if not raw:
        return None
    # o1 sometimes wraps JSON in fenced code blocks.
    cleaned = raw.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1)
    try:
        data = json.loads(cleaned)
    except Exception:
        # Last resort: extract the first {...} block.
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except Exception:
            return None

    if not isinstance(data, dict):
        return None

    decision = str(data.get("decision") or "fallback_to_router")
    if decision not in {"run_tool_plan", "answer_from_context", "ask_clarification", "fallback_to_router"}:
        return None

    confidence = str(data.get("confidence") or "medium")
    if confidence not in {"low", "medium", "high"}:
        confidence = "medium"

    tool_plan: list[tuple[str, dict[str, Any]]] = []
    for item in (data.get("tool_plan") or []):
        if isinstance(item, dict) and "tool" in item:
            tool_plan.append((str(item["tool"]), dict(item.get("args") or {})))

    questions = _parse_questions(data.get("clarification_questions") or [])

    # Safety: if the LLM returns a tool_plan referencing a symbol or path
    # absent from the prior context, drop the plan and downgrade to
    # ask_clarification or fallback. Prevents hallucinated tickers
    # (the original SWELECTES → TI failure mode).
    if tool_plan and not _tool_plan_grounded(tool_plan, previous_context):
        _log.debug("LLM tool_plan rejected: not grounded in previous context.")
        if questions:
            decision = "ask_clarification"
            tool_plan = []
        else:
            return None

    return SituationAssessment(
        applies=decision != "fallback_to_router",
        decision=decision,
        confidence=confidence,
        user_is_asking=str(data.get("user_is_asking") or ""),
        context_found=(previous_context.result_summary or ""),
        resolved_entities=list(data.get("carry_symbols") or previous_context.symbols),
        tool_plan=tool_plan,
        clarification_questions=questions,
        plan=[
            "LLM-tier situation assessment.",
            "Routing bound to prior turn context; no fresh symbol resolution.",
        ],
    )


def _parse_questions(raw: list) -> tuple[ClarificationQuestion, ...]:
    out: list[ClarificationQuestion] = []
    for q in raw:
        if not isinstance(q, dict):
            continue
        opts: list[ClarificationOption] = []
        for o in (q.get("options") or []):
            if not isinstance(o, dict):
                continue
            opts.append(ClarificationOption(
                label=str(o.get("label") or ""),
                text=str(o.get("text") or ""),
                bound_action=dict(o.get("bound_action") or {}),
            ))
        if not opts:
            continue
        out.append(ClarificationQuestion(
            prompt=str(q.get("prompt") or ""),
            options=tuple(opts),
            default_label=str(q.get("default_label") or ""),
        ))
    return tuple(out)


def _tool_plan_grounded(
    tool_plan: list[tuple[str, dict[str, Any]]],
    previous_context: TurnContext,
) -> bool:
    """Every symbol/path in the tool plan must trace to prior context."""
    prior_symbols = {str(s).upper() for s in previous_context.symbols}
    prior_paths = {str(it) for it in previous_context.result_items}
    # Also accept any path from tool_args (deeper history).
    for args in previous_context.tool_args:
        for key in ("path", "file", "report_path"):
            value = args.get(key)
            if value:
                prior_paths.add(str(value))

    for tool, args in tool_plan:
        sym = args.get("symbol") or args.get("ticker")
        if sym and str(sym).upper() not in prior_symbols:
            return False
        path = args.get("path") or args.get("file") or args.get("report_path")
        if path and str(path) not in prior_paths:
            return False
        symbols = args.get("symbols")
        if isinstance(symbols, list):
            for s in symbols:
                if str(s).upper() not in prior_symbols:
                    return False
    return True
