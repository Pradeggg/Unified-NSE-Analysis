"""First-class situation assessment for contextual terminal turns."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TurnContext:
    user_input: str
    intent: str
    mode: str
    tools: list[str]
    source_label: str
    freshness: str | None = None
    result_type: str | None = None
    result_summary: str = ""
    symbols: list[str] = field(default_factory=list)
    result_items: list[str] = field(default_factory=list)
    tool_args: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class SituationAssessment:
    applies: bool
    decision: str
    confidence: str = "low"
    user_is_asking: str = ""
    context_found: str = ""
    source_assessment: str = ""
    clarification_question: str = ""
    resolved_entities: list[str] = field(default_factory=list)
    evidence_plan: list[str] = field(default_factory=list)
    tool_plan: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    plan: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EntityTopicAssessment:
    applies: bool
    decision: str
    confidence: str = "low"
    command: str = ""
    entity_query: str = ""
    canonical_symbol: str = ""
    topic: str = ""
    output_format: str = ""
    rewritten_input: str = ""
    user_is_asking: str = ""
    plan: list[str] = field(default_factory=list)


_CONTEXTUAL_PATTERNS = (
    "were these",
    "are these",
    "what about these",
    "what about this",
    "scan these",
    "check these",
    "from postgresql",
    "from postgres",
    "or fallback",
    "what source",
    "which source",
    "last 30",
    "last-30",
    "last thirty",
    "what expiry",
    "which expiry",
    "based on the report",
    "based on report",
    "the report",
    "previous conversation",
    "same for",
)

_ENTITY_TOPIC_COMMANDS = {
    "/analyze",
    "/canslim",
    "/chain",
    "/chart",
    "/company-index",
    "/company-xray",
    "/concall",
    "/fno",
    "/forensic",
    "/oi",
    "/options",
    "/report",
    "/results",
    "/search",
    "/strategy",
    "/strategy-council",
}
_OUTPUT_FORMATS = {"html", "pdf", "md"}
_REPORT_TYPES = {
    "technical",
    "fundamental",
    "forensic",
    "research",
    "intraday",
    "canslim",
    "ric",
    "sector",
}
_REPORT_PRESET_TYPES = {"sector-rotation", "stage2"}
_DOCUMENT_EXTENSIONS = (".pdf", ".docx", ".doc", ".txt", ".csv", ".md", ".xlsx")


def needs_situation_assessment(user_input: str) -> bool:
    q = _normalize(user_input)
    # Bypass: agent-generated tool-execution prompts (e.g. /analyze expansion) are
    # not contextual follow-ups even when they reference "the report" in instructions.
    if "analyze_document tool with source=" in q or "use the analyze_document tool" in q:
        return False
    return q.startswith("search ") or any(pattern in q for pattern in _CONTEXTUAL_PATTERNS) or any(
        q.startswith(command + " ") for command in _ENTITY_TOPIC_COMMANDS
    )


def assess_entity_topic_request(user_input: str) -> EntityTopicAssessment:
    """Resolve direct command shape into entity + topic before routing.

    Example:
      /search USL growth strategy -> entity UNITDSPR, topic growth strategy
      /search United Spirits concall pdf -> entity UNITDSPR, topic concall, format pdf
    """
    text = (user_input or "").strip()
    parts = text.split()
    if not parts:
        return EntityTopicAssessment(applies=False, decision="fallback_to_router")

    command = parts[0].lower()
    if command == "search":
        command = "/search"
    if command not in _ENTITY_TOPIC_COMMANDS:
        return EntityTopicAssessment(applies=False, decision="fallback_to_router")
    args = parts[1:]
    output_format = ""
    if args and args[-1].lower() in _OUTPUT_FORMATS:
        output_format = args[-1].lower()
        args = args[:-1]
    if command == "/report" and args and args[0].lower() in _REPORT_PRESET_TYPES:
        return EntityTopicAssessment(applies=False, decision="fallback_to_router")
    if command == "/analyze" and args and _looks_like_document_source(" ".join(args)):
        return EntityTopicAssessment(applies=False, decision="fallback_to_router")
    if not args:
        return EntityTopicAssessment(
            applies=True,
            decision="ask_clarification",
            confidence="high",
            command=command,
            output_format=output_format,
            rewritten_input=_rewrite_command(command, "", "", output_format),
            user_is_asking="Run a direct research command, but no stock/index entity was supplied.",
            plan=["Ask for the missing symbol before running search tools."],
        )

    from .tools import resolve_symbol

    prefix: list[str] = []
    entity_args = list(args)
    if command == "/report" and entity_args and entity_args[0].lower() in _REPORT_TYPES:
        prefix = [entity_args[0].lower()]
        entity_args = entity_args[1:]
    if command == "/results" and len(entity_args) > 1:
        result_context_markers = {
            "latest",
            "quarter",
            "quarterly",
            "q1",
            "q2",
            "q3",
            "q4",
            "fy",
            "annual",
            "yearly",
            "earnings",
            "results",
            "result",
        }
        for i, token in enumerate(entity_args[1:], start=1):
            if token.lower() in result_context_markers:
                prefix = entity_args[i:]
                entity_args = entity_args[:i]
                break

    if not entity_args:
        return EntityTopicAssessment(
            applies=True,
            decision="ask_clarification",
            confidence="high",
            command=command,
            topic=" ".join(prefix),
            output_format=output_format,
            rewritten_input=_rewrite_command(command, "", " ".join(prefix), output_format),
            user_is_asking="Run a direct research command, but no stock/index entity was supplied.",
            plan=["Ask for the missing symbol before running search tools."],
        )

    max_entity_tokens = min(len(entity_args), 4)
    for size in range(max_entity_tokens, 0, -1):
        candidate = " ".join(entity_args[:size])
        resolved = resolve_symbol(candidate)
        symbol = str(resolved.get("symbol") or "").strip().upper()
        if symbol:
            suffix = " ".join(entity_args[size:]).strip()
            topic = " ".join([*prefix, suffix]).strip()
            rewritten = _rewrite_command(command, symbol, topic, output_format)
            return EntityTopicAssessment(
                applies=True,
                decision="route_with_entity_topic",
                confidence="high" if resolved.get("confidence") in {"exact", "fuzzy"} else "medium",
                command=command,
                entity_query=candidate,
                canonical_symbol=symbol,
                topic=topic,
                output_format=output_format,
                rewritten_input=rewritten,
                user_is_asking=(
                    f"Run {command} for {symbol}"
                    + (f" about {topic}." if topic else ".")
                ),
                plan=[
                    f"Resolve entity '{candidate}' to canonical symbol {symbol}.",
                    f"Treat remaining text as topic/context: {topic or 'full overview'}.",
                    "Route the command using the canonical symbol so context words cannot become tickers.",
                ],
            )

    if len(entity_args) == 1 and re.fullmatch(r"[A-Z0-9&-]{2,12}", entity_args[0].upper()):
        symbol = entity_args[0].upper()
        topic = " ".join(prefix).strip()
        return EntityTopicAssessment(
            applies=True,
            decision="route_with_entity_topic",
            confidence="medium",
            command=command,
            entity_query=entity_args[0],
            canonical_symbol=symbol,
            topic=topic,
            output_format=output_format,
            rewritten_input=_rewrite_command(command, symbol, topic, output_format),
            user_is_asking=(
                f"Run {command} for {symbol}"
                + (f" about {topic}." if topic else ".")
            ),
            plan=[
                f"Treat exact ticker-like input '{symbol}' as the requested symbol.",
                f"Treat remaining text as topic/context: {topic or 'full overview'}.",
                "Route the command using the supplied symbol so context words cannot become tickers.",
            ],
        )

    return EntityTopicAssessment(
        applies=True,
        decision="ask_clarification",
        confidence="medium",
        command=command,
        entity_query=entity_args[0],
        topic=" ".join([*prefix, *entity_args[1:]]).strip(),
        output_format=output_format,
        rewritten_input=_rewrite_command(command, "", " ".join([*prefix, *entity_args[1:]]).strip(), output_format),
        user_is_asking="Run a direct research command, but the stock/index entity could not be resolved.",
        plan=["Ask for a valid NSE symbol or company name before running search tools."],
    )


def _rewrite_command(command: str, symbol: str, topic: str = "", output_format: str = "") -> str:
    topic = (topic or "").strip()
    fmt = (output_format or "").strip()
    parts: list[str] = [command]
    if command == "/report":
        report_type = topic.split()[0] if topic.split() and topic.split()[0] in _REPORT_TYPES else ""
        if report_type:
            parts.append(report_type)
        if symbol:
            parts.append(symbol)
        if fmt:
            parts.append(fmt)
        return " ".join(parts)
    if symbol:
        parts.append(symbol)
    if topic:
        parts.append(topic)
    if fmt:
        parts.append(fmt)
    return " ".join(parts)


def _looks_like_document_source(value: str) -> bool:
    text = (value or "").strip().lower()
    return (
        text.startswith(("http://", "https://"))
        or text.endswith(_DOCUMENT_EXTENSIONS)
        or "/" in text
        or "\\" in text
        or text.startswith("~")
    )


def build_turn_context(
    *,
    user_input: str,
    intent: str,
    mode: str,
    source_label: str,
    tool_results: list[dict[str, Any]],
    answer: str,
) -> TurnContext:
    tools = [str(item.get("tool", "")) for item in tool_results if item.get("tool")]
    tool_args = [dict(item.get("args") or {}) for item in tool_results]
    symbols = _extract_symbols(tool_results)
    result_items = _extract_result_items(tool_results)
    freshness = _extract_freshness(tool_results, answer)
    result_type = _infer_result_type(intent, tool_results)
    result_summary = _summarize_result(result_type, tool_results, symbols, result_items)

    return TurnContext(
        user_input=user_input,
        intent=intent,
        mode=mode,
        tools=tools,
        source_label=source_label,
        freshness=freshness,
        result_type=result_type,
        result_summary=result_summary,
        symbols=symbols,
        result_items=result_items,
        tool_args=tool_args,
    )


def assess_followup(user_input: str, previous_context: TurnContext | None) -> SituationAssessment:
    if not previous_context:
        return SituationAssessment(
            applies=True,
            decision="ask_clarification",
            confidence="medium",
            user_is_asking="A contextual follow-up, but no prior result context is available.",
            context_found="No previous turn context was found.",
            clarification_question="Which result should I use as the context for this follow-up?",
            plan=["Ask for the missing reference before running tools."],
        )

    q = _normalize(user_input)

    if _asks_scan_15m(q) and previous_context.result_items:
        symbols = previous_context.result_items[:20]
        return SituationAssessment(
            applies=True,
            decision="run_tool_plan",
            confidence="high",
            user_is_asking="Scan the prior result list for 15-minute intraday setups.",
            context_found=_context_found(previous_context),
            source_assessment=_source_assessment(previous_context),
            tool_plan=[("scan_symbols_intraday", {"symbols": symbols, "interval": "15m"})],
            plan=[
                "Reuse the prior result list as the symbol universe.",
                "Run an intraday 15m setup scan for those symbols.",
                "Report source freshness and avoid treating the EOD screener as live evidence.",
            ],
        )

    if "what about these" in q or "what about this" in q:
        return _clarify(
            previous_context,
            "A contextual follow-up, but the requested analysis type is unclear.",
            "Do you mean technical setup, fundamentals, news/catalysts, intraday levels, or F&O context for these?",
        )

    if _asks_report_reference(q):
        report_path = _report_path_from_context(previous_context)
        if report_path and ("open" in q or "show" in q):
            return SituationAssessment(
                applies=True,
                decision="run_tool_plan",
                confidence="high",
                user_is_asking="Open the prior report referenced by the previous conversation.",
                context_found=_report_context_found(previous_context, report_path),
                source_assessment=_source_assessment(previous_context),
                resolved_entities=previous_context.symbols,
                evidence_plan=["open_report"],
                tool_plan=[("open_report", {"path": report_path})],
                plan=[
                    "Resolve 'the report' to the prior report path from conversation context.",
                    "Open that exact report rather than searching unrelated report types.",
                ],
            )
        if report_path and "result" in q:
            return SituationAssessment(
                applies=True,
                decision="run_tool_plan",
                confidence="high",
                user_is_asking="Assess the prior report context and summarize what the report concluded.",
                context_found=_report_context_found(previous_context, report_path),
                source_assessment=_source_assessment(previous_context),
                resolved_entities=previous_context.symbols,
                evidence_plan=["read_report", "summarize_report"],
                tool_plan=[
                    ("read_report", {"path": report_path, "max_chars": 12000}),
                    ("summarize_report", {"path": report_path}),
                ],
                plan=[
                    "Resolve 'the report' to the prior report path from conversation context.",
                    "Read and summarize the report before making any statement about its result.",
                    "If price-performance evaluation is needed, ask for the evaluation window.",
                ],
            )
        return SituationAssessment(
            applies=True,
            decision="ask_clarification",
            confidence="medium",
            user_is_asking="The user is asking a report-based follow-up.",
            context_found=_context_found(previous_context),
            source_assessment=_source_assessment(previous_context),
            clarification_question=(
                "Do you want me to open the report, summarize its recommendation, "
                "or compare the report result against later price action?"
            ),
            plan=[
                "Use prior conversation/report context.",
                "Ask for the desired report evaluation before running new tools.",
            ],
        )

    if ("scan these" in q or "check these" in q) and "live" in q and previous_context.result_items:
        return _clarify(
            previous_context,
            "A live scan request, but the live analysis scope is ambiguous.",
            "Do you want live quotes, last-30-minute momentum, 15m intraday setups, or news/catalysts for these?",
        )

    if _asks_last_window(q) and previous_context.result_type == "stage2_screener":
        return SituationAssessment(
            applies=True,
            decision="answer_from_context",
            confidence="high",
            user_is_asking="Whether the prior Stage 2 screener results were pulled from the last 30 minutes.",
            context_found=_context_found(previous_context),
            source_assessment=(
                f"The prior Stage 2 list was not generated from last-30-minute intraday data. "
                f"It used {previous_context.source_label}"
                f"{_freshness_suffix(previous_context)}."
            ),
            plan=[
                "Answer directly from the previous turn context.",
                "Do not route to a generic market recap.",
                "Offer the correct next action if the user wants a live 30-minute scan.",
            ],
        )

    if _asks_source(q):
        return SituationAssessment(
            applies=True,
            decision="answer_from_context",
            confidence="high",
            user_is_asking="The user is asking what data source or expiry supported the prior answer.",
            context_found=_context_found(previous_context),
            source_assessment=_source_assessment(previous_context),
            plan=[
                "Answer from the previous turn source trail and freshness.",
                "Do not infer unsupported live, historical, or derivative evidence.",
            ],
        )

    return SituationAssessment(applies=False, decision="fallback_to_router")


def assess_user_situation(
    user_input: str,
    previous_context: TurnContext | None = None,
    data_mode: str = "historical",
) -> dict:
    """Return the v2 situation-assessment contract used before routing."""
    entity = assess_entity_topic_request(user_input)
    if entity.applies:
        return {
            "applies": True,
            "user_is_asking": entity.user_is_asking,
            "context_found": "Direct entity/topic command." if entity.canonical_symbol else "No resolved entity.",
            "resolved_entities": [entity.canonical_symbol] if entity.canonical_symbol else [],
            "evidence_plan": [tool for tool, _ in _entity_topic_plan_preview(entity)],
            "decision": entity.decision,
            "clarification_question": "" if entity.decision != "ask_clarification" else "Which NSE symbol or company should I use?",
            "confidence": entity.confidence,
            "data_mode": data_mode,
        }

    if needs_situation_assessment(user_input):
        assessment = assess_followup(user_input, previous_context)
        return {
            "applies": assessment.applies,
            "user_is_asking": assessment.user_is_asking,
            "context_found": assessment.context_found,
            "resolved_entities": assessment.resolved_entities,
            "evidence_plan": assessment.evidence_plan,
            "decision": assessment.decision,
            "clarification_question": assessment.clarification_question,
            "confidence": assessment.confidence,
            "data_mode": data_mode,
        }

    return {
        "applies": False,
        "user_is_asking": "Non-contextual query; use normal routing.",
        "context_found": "",
        "resolved_entities": [],
        "evidence_plan": [],
        "decision": "fallback_to_router",
        "clarification_question": "",
        "confidence": "low",
        "data_mode": data_mode,
    }


def resolve_conversation_reference(
    user_input: str,
    previous_context: TurnContext | None = None,
) -> dict:
    """Resolve references like 'the report' or 'these' against prior context."""
    q = _normalize(user_input)
    if not previous_context:
        return {"status": "unresolved", "reference_type": "unknown", "reason": "No previous context."}
    if _asks_report_reference(q):
        path = _report_path_from_context(previous_context)
        if path:
            return {
                "status": "resolved",
                "reference_type": "report",
                "path": path,
                "symbols": previous_context.symbols,
                "context_found": _report_context_found(previous_context, path),
            }
    if any(term in q for term in ("these", "this", "same")) and previous_context.result_items:
        return {
            "status": "resolved",
            "reference_type": "result_items",
            "items": previous_context.result_items,
            "symbols": previous_context.symbols,
            "context_found": _context_found(previous_context),
        }
    return {"status": "unresolved", "reference_type": "unknown", "reason": "No matching contextual reference."}


def resolve_entity_context(user_input: str) -> dict:
    """Resolve an entity/topic prompt without running evidence tools."""
    assessment = assess_entity_topic_request(user_input)
    if not assessment.applies or not assessment.canonical_symbol:
        return {
            "status": "unresolved",
            "query": user_input,
            "topic": assessment.topic if assessment.applies else "",
            "reason": "No resolvable entity/topic command found.",
        }
    return {
        "status": "resolved",
        "query": user_input,
        "command": assessment.command,
        "entity_query": assessment.entity_query,
        "canonical_symbol": assessment.canonical_symbol,
        "topic": assessment.topic,
        "rewritten_input": assessment.rewritten_input,
    }


def validate_intent_evidence_plan(
    intent: str,
    evidence_plan: list[str] | tuple[str, ...] | None = None,
    required_tools: list[str] | tuple[str, ...] | None = None,
) -> dict:
    """Validate that an assessment/tool plan covers the required evidence tools."""
    planned = list(dict.fromkeys(evidence_plan or []))
    required = list(dict.fromkeys(required_tools or []))
    missing = [tool for tool in required if tool not in planned]
    return {
        "intent": intent,
        "evidence_plan": planned,
        "required_tools": required,
        "missing_tools": missing,
        "status": "ok" if not missing else "missing_required_tools",
    }


def request_clarification(question: str, reason: str = "") -> dict:
    """Return a structured clarification decision."""
    return {
        "applies": True,
        "decision": "ask_clarification",
        "confidence": "high",
        "reason": reason,
        "clarification_question": question,
        "evidence_plan": [],
    }


def render_assessment_block(assessment: SituationAssessment) -> str:
    lines = ["▶ SITUATION ASSESSMENT"]
    lines.append(f"  User is asking:   {assessment.user_is_asking or 'Unclear contextual follow-up.'}")
    lines.append(f"  Context found:    {assessment.context_found or 'None.'}")
    lines.append(f"  Source assessment:{' ' if assessment.source_assessment else ' '} {assessment.source_assessment or 'Not enough evidence yet.'}")
    lines.append(f"  Decision:         {assessment.decision} ({assessment.confidence})")
    if assessment.plan:
        lines.append("  Plan:")
        lines.extend(f"    {idx}. {step}" for idx, step in enumerate(assessment.plan, start=1))
    return "\n".join(lines)


def render_context_answer(
    user_input: str,
    assessment: SituationAssessment,
    previous_context: TurnContext,
) -> str:
    block = render_assessment_block(assessment)

    if assessment.decision == "ask_clarification":
        return (
            f"{block}\n\n"
            f"▶ CLARIFICATION NEEDED\n"
            f"  {assessment.clarification_question}\n\n"
            f"━━━ Not investment advice. For research and learning only. ━━━"
        )

    if assessment.decision == "answer_from_context" and _asks_last_window(_normalize(user_input)):
        return (
            f"{block}\n\n"
            f"▶ ANSWER\n"
            f"  No. The prior Stage 2 list came from {previous_context.source_label}"
            f"{_freshness_suffix(previous_context)}, not from the last 30 minutes.\n"
            f"  To evaluate the same names over the last 30 minutes, run a live intraday scan for the listed symbols.\n\n"
            f"━━━ Not investment advice. For research and learning only. ━━━"
        )

    return (
        f"{block}\n\n"
        f"▶ ANSWER\n"
        f"  {assessment.source_assessment}\n\n"
        f"━━━ Not investment advice. For research and learning only. ━━━"
    )


def _normalize(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _asks_last_window(q: str) -> bool:
    return "last 30" in q or "last-30" in q or "last thirty" in q


def _asks_source(q: str) -> bool:
    return any(
        token in q
        for token in (
            "from postgresql",
            "from postgres",
            "or fallback",
            "what source",
            "which source",
            "what expiry",
            "which expiry",
        )
    )


def _asks_report_reference(q: str) -> bool:
    return (
        "based on the report" in q
        or "based on report" in q
        or "the report" in q
        or "last report" in q
        or "previous report" in q
    )


def _asks_scan_15m(q: str) -> bool:
    return ("scan these" in q or "check these" in q) and ("15m" in q or "15 m" in q or "15-minute" in q)


def _context_found(context: TurnContext) -> str:
    pieces = []
    if context.result_summary:
        pieces.append(context.result_summary)
    if context.result_items:
        pieces.append(f"{len(context.result_items)} prior symbols available.")
    if context.tools:
        pieces.append(f"Tools: {', '.join(context.tools)}.")
    return " ".join(pieces) or "Previous turn context is available."


def _source_assessment(context: TurnContext) -> str:
    source = context.source_label.replace("PG ", "PostgreSQL ")
    pieces = [f"Source: {source}."]
    if context.freshness:
        pieces.append(f"Freshness: {context.freshness}.")
    if context.result_summary:
        pieces.append(context.result_summary)
    return " ".join(pieces)


def _report_path_from_context(context: TurnContext) -> str:
    for item in context.result_items:
        text = str(item)
        if re.search(r"\.(?:html|md|pdf|json|csv)$", text, re.IGNORECASE) or "/" in text or "\\" in text:
            return text
    for args in context.tool_args:
        for key in ("path", "file", "report_path"):
            value = args.get(key)
            if value:
                return str(value)
    return ""


def _report_context_found(context: TurnContext, report_path: str) -> str:
    pieces = [f"Prior report context resolved to {report_path}."]
    if context.symbols:
        pieces.append(f"Symbols: {', '.join(context.symbols)}.")
    if context.result_summary:
        pieces.append(context.result_summary)
    return " ".join(pieces)


def _freshness_suffix(context: TurnContext) -> str:
    return f" with freshness {context.freshness}" if context.freshness else ""


def _clarify(context: TurnContext, asking: str, question: str) -> SituationAssessment:
    return SituationAssessment(
        applies=True,
        decision="ask_clarification",
        confidence="medium",
        user_is_asking=asking,
        context_found=_context_found(context),
        source_assessment=_source_assessment(context),
        clarification_question=question,
        plan=["Ask one targeted clarification before choosing tools."],
    )


def _entity_topic_plan_preview(assessment: EntityTopicAssessment) -> list[tuple[str, dict[str, Any]]]:
    if not assessment.canonical_symbol:
        return []
    command = assessment.command
    if command == "/search":
        return [("deep_search", {"symbol": assessment.canonical_symbol, "context": assessment.topic or "full overview"})]
    if command == "/results":
        return [
            ("resolve_symbol", {"query": assessment.canonical_symbol}),
            ("get_latest_results", {"symbol": assessment.canonical_symbol}),
        ]
    if command in {"/fno", "/chain", "/oi", "/options"}:
        if command == "/fno":
            return [("get_fno_overview", {"symbol": assessment.canonical_symbol, "expiry_index": 0})]
        tools = [("get_options_chain", {"symbol": assessment.canonical_symbol})]
        return tools
    return [("resolve_symbol", {"query": assessment.canonical_symbol})]


def _infer_result_type(intent: str, tool_results: list[dict[str, Any]]) -> str:
    tool_names = {str(item.get("tool", "")) for item in tool_results}
    if "run_screener_query" in tool_names:
        for item in tool_results:
            result = item.get("result") or {}
            screen_type = str(result.get("screen_type") or (item.get("args") or {}).get("screen_type") or "").lower()
            if screen_type == "stage2":
                return "stage2_screener"
        return "screener"
    if {"get_options_chain", "get_futures_analysis", "get_fno_overview"} & tool_names:
        return "fno_overview"
    if "explain_intraday_setup" in tool_names:
        return "intraday_setup"
    if tool_names & {"find_latest_report", "list_generated_reports", "get_last_report", "open_report", "read_report", "summarize_report"}:
        return "report"
    return intent or "unknown"


def _extract_symbols(tool_results: list[dict[str, Any]]) -> list[str]:
    symbols: list[str] = []
    for item in tool_results:
        for source in (item.get("args") or {}, item.get("result") or {}):
            symbol = source.get("symbol")
            if isinstance(symbol, str) and symbol:
                symbols.append(symbol.upper())
        result = item.get("result") or {}
        rows = result.get("results") if isinstance(result, dict) else None
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict) and row.get("symbol"):
                    symbols.append(str(row["symbol"]).upper())
        report = result.get("report") if isinstance(result, dict) else None
        if isinstance(report, dict) and report.get("symbol"):
            symbols.append(str(report["symbol"]).upper())
    return _dedupe(symbols)


def _extract_result_items(tool_results: list[dict[str, Any]]) -> list[str]:
    for item in tool_results:
        result = item.get("result") or {}
        for key in ("path", "absolute_path"):
            if isinstance(result, dict) and result.get(key):
                return [str(result[key])]
        report = result.get("report") if isinstance(result, dict) else None
        if isinstance(report, dict):
            for key in ("path", "absolute_path"):
                if report.get(key):
                    return [str(report[key])]
        rows = result.get("results") if isinstance(result, dict) else None
        if isinstance(rows, list):
            return _dedupe(
                str(row["symbol"]).upper()
                for row in rows
                if isinstance(row, dict) and row.get("symbol")
            )
    return []


def _extract_freshness(tool_results: list[dict[str, Any]], answer: str) -> str | None:
    for key in ("as_of", "timestamp", "freshness", "snapshot_time", "bar_time"):
        value = _first_result_value(tool_results, key)
        if value:
            return str(value)

    match = re.search(r"snapshot\s+(\d{4}-\d{2}-\d{2})", answer or "")
    if match:
        return match.group(1)

    value = _first_result_value(tool_results, "expiry")
    return str(value) if value else None


def _first_result_value(tool_results: list[dict[str, Any]], key: str) -> Any:
    for item in tool_results:
        result = item.get("result") or {}
        if isinstance(result, dict) and result.get(key):
            return result[key]
    return None


def _summarize_result(
    result_type: str,
    tool_results: list[dict[str, Any]],
    symbols: list[str],
    result_items: list[str],
) -> str:
    if result_type == "stage2_screener":
        count = len(result_items) or _first_result_value(tool_results, "count") or 0
        return f"Stage 2 screener returned {count} results."

    if result_type == "fno_overview":
        expiry = _first_result_value(tool_results, "expiry")
        symbol = symbols[0] if symbols else "symbol"
        if expiry:
            return f"F&O overview for {symbol}, expiry {expiry}."
        return f"F&O overview for {symbol}."

    if symbols:
        return f"{result_type.replace('_', ' ')} for {', '.join(symbols[:5])}."
    return result_type.replace("_", " ").strip()


def _dedupe(values: Any) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value).strip().upper()
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return output
