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
    ClarificationQuestion,
    SituationAssessment,
    TurnContext,
    classify_grounded_intent,
)

_log = logging.getLogger(__name__)

# Premium-tier reasoning model (user choice). Override via env.
# Fallback chain is used if the primary id is rejected by the API.
# PG 2026-05-27: switched default from `gpt-5.5` (not a real OpenAI model id
# — was causing every assessment call to be rejected) to gpt-4o.
DEFAULT_ASSESSMENT_MODEL = "gpt-5"
DEFAULT_ASSESSMENT_REASONING_EFFORT = "high"
ASSESSMENT_MODEL = os.getenv("ASSESSMENT_MODEL", DEFAULT_ASSESSMENT_MODEL)
ASSESSMENT_REASONING_EFFORT = os.getenv(
    "ASSESSMENT_REASONING_EFFORT",
    DEFAULT_ASSESSMENT_REASONING_EFFORT,
)
ASSESSMENT_FALLBACK_MODELS = ("gpt-5-mini", "o4-mini", "o3", "gpt-4o")
ASSESSMENT_TIMEOUT_S = float(os.getenv("ASSESSMENT_LLM_TIMEOUT", "15"))
ASSESSMENT_ENABLED = os.getenv("ASSESSMENT_LLM_ENABLED", "1") not in {"0", "false", "False"}

_SYSTEM_PROMPT = """\
You are the situation-assessment layer for an NSE market-research terminal.

Before choosing a route, first read the previous turn context and reflect on
what the user is really asking. The user may be asking for an approach,
verdict, recap, report action, source audit, or follow-up scan. Bind pronouns
and phrases like "based on the analysis", "our approach", "it", "these", and
"the report" to the previous turn whenever the context supports that binding.

Assessment style:
- Think like a senior market operator consolidating evidence before action.
- Pull together available snapshot data, technical indicators, forensic or
  fundamental details, sector context, source freshness, and catalysts.
- Explicitly notice conflicts or mismatches in the evidence. For example, if
  RSI values differ between snapshot and technical setup, treat that as a
  source/timeframe conflict: the snapshot may reflect the most recent bar while
  the technical setup may use a different timeframe or calculation window.
- Decide whether the answer should be: answer from context, run a bound tool
  plan, ask one clarification, or fall back to the normal router.
- Use POT as the public plan-of-thought summary: what evidence to bind, what to
  verify, and what response form is appropriate.
- Use TOT as the public tree-of-thought summary: bull/base/bear or
  open/summarize/compare branches, with the selected branch grounded in prior
  context.
- Do not expose private chain-of-thought. Return only concise structured JSON.

Return STRICT JSON matching this schema:
{
  "decision": "run_tool_plan" | "answer_from_context" | "ask_clarification" | "fallback_to_router",
  "confidence": "low" | "medium" | "high",
  "user_is_asking": "<one short sentence>",
  "source_assessment": "<one short sentence on prior source/freshness/conflicts>",
  "carry_symbols": [<NSE tickers from prior context to keep>],
  "plan": ["<POT/TOT-safe public step>", "..."],
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
- If the user asks for "our approach", "what should we do", "stance", or "verdict" based on the previous analysis, prefer decision=answer_from_context and carry the prior symbols.
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
        parsed = _parse_response(raw, previous_context, user_input)
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
    if _uses_responses_reasoning(model_id) and hasattr(client, "responses"):
        resp = client.responses.create(
            model=model_id,
            input=messages,
            reasoning={"effort": ASSESSMENT_REASONING_EFFORT},
            text={"format": {"type": "json_object"}},
        )
        return _response_text(resp)

    # o1-class reasoning models reject `response_format`; we ask for JSON
    # in the system prompt and parse defensively.
    kwargs: dict[str, Any] = {"model": model_id, "messages": messages}
    if not model_id.startswith("o1") and not model_id.startswith("o3"):
        kwargs["temperature"] = 0
        kwargs["response_format"] = {"type": "json_object"}
    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content or ""


def _uses_responses_reasoning(model_id: str) -> bool:
    normalized = (model_id or "").lower()
    return normalized.startswith("gpt-5")


def _response_text(resp: Any) -> str:
    output_text = getattr(resp, "output_text", None)
    if isinstance(output_text, str):
        return output_text

    # Defensive extraction for SDKs that expose Responses output as nested
    # content parts rather than the convenience `output_text` property.
    for item in getattr(resp, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            text = getattr(content, "text", None)
            if isinstance(text, str):
                return text
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                return content["text"]
        if isinstance(item, dict):
            for content in item.get("content") or []:
                if isinstance(content, dict) and isinstance(content.get("text"), str):
                    return content["text"]
    return ""


def _parse_response(
    raw: str,
    previous_context: TurnContext,
    user_input: str = "",
) -> SituationAssessment | None:
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

    if decision == "run_tool_plan" and not tool_plan:
        _log.debug("LLM assessment rejected: run_tool_plan without tools.")
        return None

    if tool_plan and not _tool_plan_has_required_args(tool_plan):
        _log.debug("LLM tool_plan rejected: missing required tool args.")
        return None

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

    # PG-HALL-GUARD: Detect data-grounded intents (RS scan, screener,
    # gainers, intraday scan). For these, prose is not an acceptable
    # output — only a real tool_plan binding is. We OR-merge the current
    # input with the previous turn's user_input so multi-turn flows
    # (clarification reply -> new intent) inherit grounding.
    grounded_tag = classify_grounded_intent(user_input) or classify_grounded_intent(
        previous_context.user_input
    )
    requires_grounding = bool(grounded_tag)

    # PG-HALL-GUARD: If grounding is required but the LLM returned no
    # tool_plan (or it's been stripped above), do NOT let this turn fall
    # through to free-text prose. Force ask_clarification (or fallback
    # with low confidence) so the renderer's hallucination gate fires.
    if requires_grounding and not tool_plan:
        confidence = "low"
        if decision in {"answer_from_context", "run_tool_plan"}:
            decision = "ask_clarification" if questions else "fallback_to_router"

    return SituationAssessment(
        applies=decision != "fallback_to_router",
        decision=decision,
        confidence=confidence,
        user_is_asking=str(data.get("user_is_asking") or ""),
        context_found=(previous_context.result_summary or ""),
        source_assessment=str(data.get("source_assessment") or ""),
        resolved_entities=list(data.get("carry_symbols") or previous_context.symbols),
        tool_plan=tool_plan,
        clarification_questions=questions,
        plan=list(data.get("plan") or [
            "LLM-tier situation assessment.",
            "Routing bound to prior turn context; no fresh symbol resolution.",
        ]),
        requires_grounding=requires_grounding,
        grounded_intent=grounded_tag,
    )


def _parse_questions(raw: list) -> tuple[ClarificationQuestion, ...]:
    """Parse LLM-emitted clarification questions into ``ClarificationQuestion``s.

    Uses the :class:`terminal.clarify.Option` / :class:`Question` builder
    dataclasses for type-safe construction (single source of truth with
    the static-builder callsites) and then converts via the builder's
    ``to_clarification_*()`` adapters. Parsing stays lenient — malformed
    entries are skipped silently instead of raising, since LLM output is
    untrusted.
    """
    from .clarify import Option, Question

    out: list[ClarificationQuestion] = []
    for q in raw:
        if not isinstance(q, dict):
            continue
        builder_opts: list[Option] = []
        for o in (q.get("options") or []):
            if not isinstance(o, dict):
                continue
            builder_opts.append(Option(
                label=str(o.get("label") or ""),
                text=str(o.get("text") or ""),
                bound_action=dict(o.get("bound_action") or {}),
                preview=str(o.get("preview") or ""),
            ))
        if not builder_opts:
            continue
        question = Question(
            prompt=str(q.get("prompt") or ""),
            options=builder_opts,
            default_label=str(q.get("default_label") or ""),
        )
        out.append(question.to_clarification_question())
    return tuple(out)


def _tool_plan_has_required_args(tool_plan: list[tuple[str, dict[str, Any]]]) -> bool:
    """Reject structurally invalid LLM-generated tool calls."""
    for tool, args in tool_plan:
        if not _tool_args_have_real_symbols(tool, args):
            return False
        if tool == "scan_symbols_intraday":
            symbols = args.get("symbols")
            if not isinstance(symbols, list) or not symbols:
                return False
        if tool in {"read_report", "summarize_report", "open_report"} and not (
            args.get("path") or args.get("file") or args.get("report_path")
        ):
            return False
    return True


_SYMBOL_ARG_TOOLS = frozenset({
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
})

def _looks_like_placeholder_symbol(value: Any) -> bool:
    text = str(value or "").strip()
    normalized = re.sub(r"[^A-Z0-9]+", "_", text.upper()).strip("_")
    return (
        not text
        or "<" in text
        or ">" in text
        or normalized in {"SYMBOL", "NSE_SYMBOL", "RESOLVED_SYMBOL", "RESOLVED_NSE_SYMBOL", "TICKER"}
    )


def _tool_args_have_real_symbols(tool: str, args: dict[str, Any]) -> bool:
    if tool == "resolve_symbol":
        query = args.get("query") or args.get("symbol") or args.get("ticker")
        return not _looks_like_placeholder_symbol(query)
    if tool in _SYMBOL_ARG_TOOLS:
        symbol = args.get("symbol") or args.get("ticker")
        if symbol is None:
            return False
        return not _looks_like_placeholder_symbol(symbol)
    symbols = args.get("symbols")
    if isinstance(symbols, list):
        return bool(symbols) and all(not _looks_like_placeholder_symbol(item) for item in symbols)
    return True


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
