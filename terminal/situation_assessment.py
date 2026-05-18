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
    # Optional grouped symbol breakdown produced by multi-bucket tools
    # (e.g. intraday scans with separate long/short signal lists, screener
    # results split by direction). Keyed by bucket name; values are
    # uppercase NSE symbols in display order. Empty for tools that do not
    # produce a directional breakdown.
    result_groups: dict[str, list[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class ClarificationOption:
    """One selectable answer in a structured clarification question.

    `bound_action` is an opaque payload the agent executes verbatim when
    the user picks this option — typically `{"decision": "run_tool_plan",
    "tool_plan": [...], "resolved_entities": [...]}`. The agent must NOT
    re-resolve symbols or topics from the reply text; this binding is the
    authoritative routing.
    """
    label: str
    text: str
    bound_action: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ClarificationQuestion:
    prompt: str
    options: tuple[ClarificationOption, ...] = ()
    default_label: str = ""


@dataclass(frozen=True)
class SituationAssessment:
    applies: bool
    decision: str
    confidence: str = "low"
    user_is_asking: str = ""
    context_found: str = ""
    source_assessment: str = ""
    clarification_question: str = ""  # legacy single-line; kept for back-compat
    clarification_questions: tuple[ClarificationQuestion, ...] = ()
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
    "based on the above",
    "based on above",
    "above financial analysis",
    "above analysis",
    "previous analysis",
    "your recommendation",
    "what would be your recommendation",
    "what is your recommendation",
    "the report",
    "previous conversation",
    "same for",
    # Implicit prior-report references — only meaningful when the previous
    # turn produced a report, but cheap enough to always include in the
    # trigger so the deterministic chain gets a chance to bind context.
    "summarize",
    "summarise",
    "summary",
    "recap",
    "tldr",
    "tl;dr",
    "its recommendation",
    "the recommendation",
    "its conclusion",
    "the conclusion",
    "what does it say",
    "what does the report say",
    # Multi-symbol setup review — bind to prior intraday-scan buckets.
    "review",
    "long setups",
    "short setups",
    "longs",
    "shorts",
    "the longs",
    "the shorts",
    "deep dive",
    "deep-dive",
    "details on",
)
_AFFIRMATIVE_FOLLOWUPS = {
    "yes",
    "yes please",
    "please",
    "do it",
    "go ahead",
    "sure",
    "ok",
    "okay",
}

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
    # Bypass: the startup/session briefing prompt is a first-class direct
    # request. It contains words such as "previous trading day" and "today",
    # which are contextual in ordinary follow-ups but not here.
    if (
        "morning briefing" in q
        or "startup briefing" in q
        or "market intelligence briefing" in q
        or ("starting a new trading session" in q and "global overnight context" in q)
    ):
        return False
    return q in _AFFIRMATIVE_FOLLOWUPS or q.startswith("search ") or any(pattern in q for pattern in _CONTEXTUAL_PATTERNS) or any(
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
    result_groups = _extract_result_groups(tool_results)
    # If grouped buckets carry symbols (e.g. intraday scan long/short setups)
    # but the flat symbols/result_items lists are empty, promote them so
    # downstream follow-up rules that key off symbols still match.
    if result_groups:
        merged: list[str] = []
        for bucket_symbols in result_groups.values():
            merged.extend(bucket_symbols)
        if merged:
            if not symbols:
                symbols = _dedupe(merged)
            if not result_items:
                result_items = _dedupe(merged)
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
        result_groups=result_groups,
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

    if q in _AFFIRMATIVE_FOLLOWUPS:
        report_path = _report_path_from_context(previous_context)
        if report_path:
            return SituationAssessment(
                applies=True,
                decision="run_tool_plan",
                confidence="medium",
                user_is_asking="Confirming the prior clarification; default to summarizing the report result.",
                context_found=_report_context_found(previous_context, report_path),
                source_assessment=_source_assessment(previous_context),
                resolved_entities=previous_context.symbols,
                evidence_plan=["read_report", "summarize_report"],
                tool_plan=[
                    ("read_report", {"path": report_path, "max_chars": 12000}),
                    ("summarize_report", {"path": report_path}),
                ],
                plan=[
                    "Resolve the affirmative reply against the prior report clarification.",
                    "Read and summarize the latest remembered report.",
                    "Avoid making new market conclusions beyond the report evidence.",
                ],
            )
        return SituationAssessment(
            applies=True,
            decision="answer_from_context",
            confidence="medium",
            user_is_asking="Confirming the prior clarification; answer from available prior context.",
            context_found=_context_found(previous_context),
            source_assessment=_source_assessment(previous_context),
            resolved_entities=previous_context.symbols,
            evidence_plan=previous_context.tools,
            plan=[
                "Treat the affirmative reply as a continuation of the previous contextual turn.",
                "Use prior context only; do not resolve 'yes' or 'please' as entities.",
            ],
        )

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

    if _asks_contextual_recommendation(q):
        return SituationAssessment(
            applies=True,
            decision="answer_from_context",
            confidence="high",
            user_is_asking="A recommendation based on the prior financial/market analysis.",
            context_found=_context_found(previous_context),
            source_assessment=_source_assessment(previous_context),
            resolved_entities=previous_context.symbols,
            evidence_plan=previous_context.tools,
            plan=[
                "Use the previous turn context as the evidence base.",
                "Do not resolve words from the follow-up as a new ticker.",
                "Give an evidence-gated research stance, not investment advice.",
            ],
        )

    report_path_for_implicit = _report_path_from_context(previous_context)
    is_report_ref = _asks_report_reference(q) or (
        bool(report_path_for_implicit) and _refers_to_prior_report_implicitly(q)
    )
    if is_report_ref:
        report_path = report_path_for_implicit
        wants_open = "open" in q or "show it" in q or q.strip() == "open it" or "show me the report" in q or "show the report" in q
        wants_summarize = any(
            tok in q
            for tok in (
                "summarize",
                "summarise",
                "summary",
                "recap",
                "tl;dr",
                "tldr",
                "recommendation",
                "conclusion",
                "what does it say",
                "what does the report say",
            )
        )
        if report_path and wants_open and not wants_summarize:
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
        if report_path and (wants_summarize or "result" in q):
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
                    "Resolve the implicit report reference to the prior report path from conversation context.",
                    "Read and summarize the report before making any statement about its result.",
                    "Do not re-resolve any words from the reply as new tickers.",
                ],
            )
        # Genuinely ambiguous — ask with structured options. Each option
        # carries a bound_action so the reply binds straight to the tool
        # plan without re-running symbol resolution.
        options: list[ClarificationOption] = []
        if report_path:
            options = [
                ClarificationOption(
                    label="A",
                    text="Open the report",
                    bound_action={
                        "decision": "run_tool_plan",
                        "tool_plan": [("open_report", {"path": report_path})],
                        "evidence_plan": ["open_report"],
                        "resolved_entities": list(previous_context.symbols),
                        "user_is_asking": "Open the prior report referenced by the previous conversation.",
                        "context_found": _report_context_found(previous_context, report_path),
                    },
                ),
                ClarificationOption(
                    label="B",
                    text="Summarize its recommendation",
                    bound_action={
                        "decision": "run_tool_plan",
                        "tool_plan": [
                            ("read_report", {"path": report_path, "max_chars": 12000}),
                            ("summarize_report", {"path": report_path}),
                        ],
                        "evidence_plan": ["read_report", "summarize_report"],
                        "resolved_entities": list(previous_context.symbols),
                        "user_is_asking": "Summarize the prior report's recommendation.",
                        "context_found": _report_context_found(previous_context, report_path),
                    },
                ),
                ClarificationOption(
                    label="C",
                    text="Compare report result against later price action",
                    bound_action={
                        "decision": "ask_clarification",
                        "clarification_questions": (
                            ClarificationQuestion(
                                prompt="What evaluation window should I use?",
                                options=(
                                    ClarificationOption(label="A", text="1 week"),
                                    ClarificationOption(label="B", text="1 month"),
                                    ClarificationOption(label="C", text="3 months"),
                                ),
                            ),
                        ),
                    },
                ),
            ]
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
            clarification_questions=(
                ClarificationQuestion(
                    prompt="What would you like me to do with the prior report?",
                    options=tuple(options),
                    default_label="B" if options else "",
                ),
            ) if options else (),
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

    if (
        ("are these" in q or "were these" in q)
        and ("stage 2" in q or "stage2" in q or "still" in q)
        and previous_context.result_items
    ):
        # User asks whether the prior result list is still valid — this is
        # ambiguous (vs. snapshot freshness vs. fresh stage scan vs. live).
        return _clarify(
            previous_context,
            "A revalidation request, but the time-frame is ambiguous.",
            "Do you want a fresh Stage 2 re-scan on the same symbols, an intraday momentum check, or just the source/freshness of the prior list?",
        )

    # "review (all the | these) (long|short)? setups" — bind to the prior
    # intraday-scan long/short buckets and emit a deterministic compare_stocks
    # plan over the requested direction. Without this rule the LLM router has
    # no anchor and tends to hallucinate an unrelated single ticker
    # (observed: 'Review all the long setups' → LATENTVIEW Market Brief).
    review_setups = _asks_review_setups(q)
    if review_setups and previous_context.result_groups:
        direction = review_setups  # "long" | "short" | "both"
        groups = previous_context.result_groups or {}
        if direction == "long":
            symbols = list(groups.get("long") or [])
        elif direction == "short":
            symbols = list(groups.get("short") or [])
        else:
            symbols = list(groups.get("long") or []) + list(groups.get("short") or [])
        symbols = _dedupe(symbols)[:10]
        if symbols:
            label = (
                "long setups" if direction == "long"
                else "short setups" if direction == "short"
                else "setups"
            )
            return SituationAssessment(
                applies=True,
                decision="run_tool_plan",
                confidence="high",
                user_is_asking=f"Deep-dive review of the prior intraday scan's {label}.",
                context_found=_context_found(previous_context),
                source_assessment=_source_assessment(previous_context),
                resolved_entities=symbols,
                evidence_plan=["compare_stocks"],
                tool_plan=[("compare_stocks", {"symbols": symbols, "aspects": ["both"]})],
                plan=[
                    f"Bind the reply to the prior scan's {label} ({len(symbols)} symbols).",
                    "Run compare_stocks on those symbols across technical + fundamental aspects.",
                    "Do not resolve a new symbol from the reply text; the binding is authoritative.",
                ],
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

    # Deterministic chain exhausted. If there's genuine prior context
    # (symbols, a report path, or a result list) to bind to, escalate
    # to the premium LLM tier. It returns applies=False on any error so
    # the caller falls through to the normal LLM router safely.
    has_prior_context = bool(
        previous_context.symbols
        or previous_context.result_items
        or previous_context.result_summary
    )
    if has_prior_context:
        try:
            from .assessment_llm import llm_assess_followup
            llm_assessment = llm_assess_followup(user_input, previous_context)
        except Exception:
            llm_assessment = SituationAssessment(applies=False, decision="fallback_to_router")
        if llm_assessment.applies:
            return llm_assessment

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


def match_clarification_reply(
    user_input: str,
    pending: SituationAssessment | None,
) -> ClarificationOption | None:
    """Match a user's reply against the pending clarification's options.

    Accepts:
      - Single-letter (case-insensitive): "A", "b", "C."
      - Exact option text (case-insensitive substring): "summarize its recommendation"
      - Numeric index: "1", "2"

    Returns the matched ClarificationOption (with its bound_action) or
    None if no clean match. Returning None lets the caller fall through
    to normal routing, e.g. when the user ignores the clarification and
    types a completely new query.
    """
    if not pending or pending.decision != "ask_clarification" or not pending.clarification_questions:
        return None
    text = (user_input or "").strip()
    if not text:
        return None

    # Flatten options across all questions; in practice we ask one at a
    # time but the data model permits multi-question rounds.
    all_options: list[ClarificationOption] = []
    for q in pending.clarification_questions:
        all_options.extend(q.options)
    if not all_options:
        return None

    text_norm = text.lower().strip().rstrip(".!?,")

    # 1. Single letter match (most common reply).
    if len(text_norm) == 1 and text_norm.isalpha():
        for opt in all_options:
            if opt.label.lower() == text_norm:
                return opt

    # 2. Letter followed by punctuation/word: "A.", "A — open report"
    first_token = re.split(r"[\s\W]+", text_norm, maxsplit=1)[0]
    if first_token and len(first_token) == 1 and first_token.isalpha():
        for opt in all_options:
            if opt.label.lower() == first_token:
                return opt

    # 3. Numeric index "1" / "2" → A / B / C.
    if text_norm.isdigit():
        idx = int(text_norm) - 1
        if 0 <= idx < len(all_options):
            return all_options[idx]

    # 4. Substring match against option text (longest-first to avoid
    #    "summarize" partially matching multiple options).
    by_text_len = sorted(all_options, key=lambda o: -len(o.text))
    for opt in by_text_len:
        opt_norm = opt.text.lower().strip()
        if opt_norm and opt_norm in text_norm:
            return opt
    # Loose token overlap: at least 2 distinctive option words present.
    for opt in by_text_len:
        opt_tokens = {t for t in re.findall(r"[a-z]{4,}", opt.text.lower())}
        if not opt_tokens:
            continue
        reply_tokens = set(re.findall(r"[a-z]{4,}", text_norm))
        if len(opt_tokens & reply_tokens) >= max(2, len(opt_tokens) // 2):
            return opt
    return None


def assessment_from_bound_action(
    bound_action: dict,
    previous_context: TurnContext | None = None,
) -> SituationAssessment:
    """Convert a ClarificationOption.bound_action payload into a SituationAssessment.

    The payload is the authoritative routing for the user's clarification
    reply; we wrap it so the agent's existing execution paths
    (run_tool_plan / answer_from_context / ask_clarification) can dispatch
    it without changes.
    """
    decision = str(bound_action.get("decision") or "answer_from_context")
    raw_plan = bound_action.get("tool_plan") or []
    tool_plan: list[tuple[str, dict[str, Any]]] = []
    for item in raw_plan:
        if isinstance(item, tuple) and len(item) == 2:
            tool_plan.append((str(item[0]), dict(item[1] or {})))
        elif isinstance(item, list) and len(item) == 2:
            tool_plan.append((str(item[0]), dict(item[1] or {})))
        elif isinstance(item, dict) and "tool" in item:
            tool_plan.append((str(item["tool"]), dict(item.get("args") or {})))

    raw_questions = bound_action.get("clarification_questions") or ()
    questions: tuple[ClarificationQuestion, ...]
    if raw_questions and all(isinstance(q, ClarificationQuestion) for q in raw_questions):
        questions = tuple(raw_questions)
    else:
        questions = ()

    return SituationAssessment(
        applies=True,
        decision=decision,
        confidence=str(bound_action.get("confidence") or "high"),
        user_is_asking=str(bound_action.get("user_is_asking") or "Clarification reply executed."),
        context_found=str(bound_action.get("context_found") or (previous_context.result_summary if previous_context else "")),
        source_assessment=str(bound_action.get("source_assessment") or ""),
        clarification_question=str(bound_action.get("clarification_question") or ""),
        clarification_questions=questions,
        resolved_entities=list(bound_action.get("resolved_entities") or (previous_context.symbols if previous_context else [])),
        evidence_plan=list(bound_action.get("evidence_plan") or []),
        tool_plan=tool_plan,
        plan=list(bound_action.get("plan") or [
            "Executed the user's clarification choice via the bound action.",
            "Did not re-resolve any symbols/topics from the reply text.",
        ]),
    )


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


def _render_structured_clarifications(
    questions: tuple[ClarificationQuestion, ...],
    legacy_question: str = "",
) -> str:
    """Render numbered questions with [A]/[B]/[C] options.

    Falls back to the legacy single-line clarification if no structured
    questions are present.
    """
    if not questions:
        if legacy_question:
            return f"▶ CLARIFICATION NEEDED\n  {legacy_question}"
        return "▶ CLARIFICATION NEEDED\n  (no question provided)"

    lines: list[str] = ["▶ CLARIFICATION NEEDED"]
    for q_idx, q in enumerate(questions, start=1):
        lines.append(f"  Q{q_idx}. {q.prompt}")
        for opt in q.options:
            marker = "*" if opt.label == q.default_label else " "
            lines.append(f"      [{opt.label}]{marker} {opt.text}")
        if len(questions) > 1:
            lines.append("")
    lines.append("  Reply with the option letter (e.g. \"A\") or the option text.")
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
            f"{_render_structured_clarifications(assessment.clarification_questions, assessment.clarification_question)}\n\n"
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

    if assessment.decision == "answer_from_context" and _asks_contextual_recommendation(_normalize(user_input)):
        return (
            f"{block}\n\n"
            f"{_render_contextual_recommendation(previous_context)}\n\n"
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


def _refers_to_prior_report_implicitly(q: str) -> bool:
    """Match phrasings that imply the prior report without saying 'the report'.

    Used when previous_context has a report_path. Examples:
      'summarize its recommendation'
      'what does it say'
      'recap the recommendation'
      'open it'
    """
    return any(
        phrase in q
        for phrase in (
            "summarize",
            "summarise",
            "summary",
            "recap",
            "recapitulate",
            "tl;dr",
            "tldr",
            "what does it say",
            "what does the report say",
            "what did it conclude",
            "its recommendation",
            "the recommendation",
            "its conclusion",
            "the conclusion",
            "open it",
            "show it",
        )
    )


def _asks_contextual_recommendation(q: str) -> bool:
    contextual = any(
        phrase in q
        for phrase in (
            "based on the above",
            "based on above",
            "above financial analysis",
            "above analysis",
            "previous analysis",
            "based on this analysis",
            "based on the analysis",
            "based on financial analysis",
        )
    )
    asks_recommendation = any(
        phrase in q
        for phrase in (
            "recommendation",
            "recommend",
            "what would you do",
            "what should i do",
            "buy",
            "sell",
            "hold",
            "avoid",
        )
    )
    return contextual and asks_recommendation


def _asks_scan_15m(q: str) -> bool:
    return ("scan these" in q or "check these" in q) and ("15m" in q or "15 m" in q or "15-minute" in q)


def _asks_review_setups(q: str) -> str | None:
    """If the user asks to review the prior scan's setups, return the
    direction bucket they want — ``"long"``, ``"short"``, or ``"both"``.
    Returns ``None`` if no review intent is detected.

    Matches phrasings like:
        review all the long setups / review the longs / review longs
        deep dive on the short setups / details on these setups
        review setups / review all setups (→ both)
    """
    has_review_verb = (
        "review" in q
        or "deep dive" in q
        or "deep-dive" in q
        or "details on" in q
    )
    if not has_review_verb:
        return None
    # Direction detection. Look for whole-word matches so we don't catch
    # "longs" inside arbitrary words. We tolerate "long setups", "the longs",
    # "longsetups" (no space) — all observed in practice.
    long_hit = bool(re.search(r"\blongs?(?:etups)?\b|long\s*setups?\b", q))
    short_hit = bool(re.search(r"\bshorts?(?:etups)?\b|short\s*setups?\b", q))
    if long_hit and not short_hit:
        return "long"
    if short_hit and not long_hit:
        return "short"
    if long_hit and short_hit:
        return "both"
    # Bare 'review setups' / 'review these' / 'review all setups' → both buckets.
    if (
        "setup" in q
        or "these" in q
        or "all" in q
    ):
        return "both"
    return None


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


def _render_contextual_recommendation(context: TurnContext) -> str:
    summary = context.result_summary or "Previous analysis is available."
    lower = summary.lower()
    symbol_text = ", ".join(context.symbols[:3]) if context.symbols else "the prior subject"
    caution_terms = ("sell", "weak", "not in stage 2", "unknown", "bearish", "missing evidence", "low interest coverage")
    positive_terms = ("buy", "stage 2", "strong", "bullish", "high rs")

    lines = ["▶ CONTEXTUAL RECOMMENDATION"]
    if any(term in lower for term in caution_terms):
        stance = "Research stance: cautious / avoid fresh entry until evidence improves."
        rationale = (
            "The prior analysis had negative or incomplete evidence, so the safer research conclusion is to wait for confirmation "
            "rather than infer a buy case."
        )
    elif any(term in lower for term in positive_terms):
        stance = "Research stance: constructive, but only with confirmation and risk controls."
        rationale = (
            "The prior analysis had supportive signals, but this still needs price confirmation, source freshness, and position-risk checks."
        )
    else:
        stance = "Research stance: neutral / watchlist until stronger evidence is available."
        rationale = (
            "The prior context is not enough to justify a decisive buy/sell conclusion without fresh technical, fundamental, and catalyst checks."
        )

    lines.append(f"  Subject: {symbol_text}")
    lines.append(f"  {stance}")
    lines.append(f"  Why: {rationale}")
    lines.append("")
    lines.append("▶ EVIDENCE USED")
    lines.append(f"  {summary}")
    lines.append(f"  Source: {context.source_label}{_freshness_suffix(context)}.")
    if context.tools:
        lines.append(f"  Tools: {', '.join(context.tools)}.")
    lines.append("")
    lines.append("▶ WHAT WOULD CHANGE THE VIEW")
    lines.append("  • Positive: Stage 2/price strength, improving RS, supportive fundamentals, and fresh catalysts.")
    lines.append("  • Negative: weak trend, SELL/UNKNOWN stage, deteriorating margins/coverage, or missing key evidence.")
    return "\n".join(lines)


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


def _extract_result_groups(tool_results: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Pull bucketed symbol lists from tools that produce a directional split.

    Currently recognises the intraday-scan family (``scan_intraday_market``,
    ``scan_symbols_intraday``, ``run_intraday_screener``) which return
    ``buy_signals`` / ``sell_signals`` lists of setup dicts. Each dict has
    a ``symbol`` key plus entry/target/invalidation fields. We project
    those down to uppercase NSE symbols in display order and expose them
    under stable keys (``long`` / ``short``) so follow-up rules like
    "review the long setups" can bind to them deterministically.
    """
    long_symbols: list[str] = []
    short_symbols: list[str] = []
    for item in tool_results:
        result = item.get("result") or {}
        if not isinstance(result, dict):
            continue
        # Intraday scan family: buy_signals / sell_signals are lists of
        # {symbol, strategy, entry, target, invalidation, rr, ...} dicts.
        for key, bucket in (("buy_signals", long_symbols), ("sell_signals", short_symbols)):
            rows = result.get(key)
            if isinstance(rows, list):
                for row in rows:
                    if isinstance(row, dict) and row.get("symbol"):
                        bucket.append(str(row["symbol"]).upper())
    groups: dict[str, list[str]] = {}
    if long_symbols:
        groups["long"] = _dedupe(long_symbols)
    if short_symbols:
        groups["short"] = _dedupe(short_symbols)
    return groups


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

    if symbols and {"stock_brief", "stock_results", "market_situation_assessment"} & {result_type}:
        symbol = symbols[0]
        snapshot = _first_result_dict(tool_results, "get_symbol_snapshot")
        technical = _first_result_dict(tool_results, "get_technical_setup")
        screener = _first_result_dict(tool_results, "scrape_screener_in")
        parts = [f"{result_type.replace('_', ' ')} for {symbol}"]
        price = snapshot.get("price") or snapshot.get("last_price") or snapshot.get("last")
        signal = snapshot.get("signal") or snapshot.get("trading_signal") or technical.get("signal")
        stage = snapshot.get("stage") or technical.get("stage")
        rs = snapshot.get("rs") or snapshot.get("relative_strength")
        if price is not None:
            parts.append(f"price {price}")
        if signal:
            parts.append(f"signal {signal}")
        if stage:
            parts.append(f"stage {stage}")
        if rs is not None:
            parts.append(f"RS {rs}")
        if technical.get("macd"):
            parts.append(f"MACD {technical.get('macd')}")
        if technical.get("supertrend"):
            parts.append(f"supertrend {technical.get('supertrend')}")
        cons = screener.get("cons") if isinstance(screener.get("cons"), list) else []
        if cons:
            parts.append(f"risk: {str(cons[0])[:80]}")
        return "; ".join(parts) + "."

    if symbols:
        return f"{result_type.replace('_', ' ')} for {', '.join(symbols[:5])}."
    return result_type.replace("_", " ").strip()


def _first_result_dict(tool_results: list[dict[str, Any]], tool_name: str) -> dict[str, Any]:
    for item in tool_results:
        if item.get("tool") == tool_name and isinstance(item.get("result"), dict):
            return item.get("result") or {}
    return {}


def _dedupe(values: Any) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value).strip().upper()
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return output
