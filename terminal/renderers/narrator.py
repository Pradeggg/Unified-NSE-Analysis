"""LLM narrative layer.

Takes the deterministic structured output produced by a renderer and adds a
short interpretation paragraph ("so what does this mean?") via a 1-shot LLM
call.  The prose is appended AFTER the tables/data so the structured output
is always present even when the LLM call fails or is skipped.

Intents that benefit from narration are listed in NARRATION_INTENTS.  All
others skip the LLM call to keep latency near-zero.
"""
from __future__ import annotations

import logging
import os
import re
import textwrap

logger = logging.getLogger(__name__)

# Intents where a 2–3 sentence interpretation adds genuine value on top of
# the deterministic data tables.
NARRATION_INTENTS: frozenset[str] = frozenset({
    "stock_brief",
    "stock_results",
    "collective_news_results",
    "screener",
    "sector_deep_dive",
    "sector_scan",
    "sector_rotation",
    "market_dashboard",
    "market_overview",
    "market_situation_assessment",
    "market_situation",
    "market_swing_candidates",
    "quality_breakouts",
    "symbol_quick_analysis",
    "stock_comparison",
    "portfolio_review",
    "portfolio_forensic_review",
    "market_knowledge",
    "entity_topic_command",
    "startup_morning_briefing",
    "intraday_setup",
    "intraday_market_recap",
    "fno_overview",
    "results_feed",
    "forthcoming_results",
    "skill_store",
})

# Maximum tokens for the narrative response — keep it short and punchy.
_MAX_NARRATIVE_TOKENS = 160
_MAX_FINAL_ANSWER_TOKENS = 700

_SYSTEM_PROMPT = """\
You are a concise market analyst assistant. You receive structured investment \
research data that has already been formatted into tables and bullet lists. \
Your job: write 2–3 sentences of plain-English interpretation — the \
"so what?" — that a trader or investor would find actionable. \
Do NOT repeat the numbers already in the tables. Do NOT add new facts. \
Do NOT mention RS percentiles or percentile distribution unless those exact \
fields are present in the structured data. \
Do NOT mention that this is not investment advice (that footer is added \
separately). Keep it under 50 words.\
"""

_FINAL_ANSWER_SYSTEM_PROMPT = """\
You are Agent Adda's final answer synthesizer. You receive the expanded user \
query, executed tool evidence, and a deterministic structured render. Write the \
user-facing answer first.

Rules:
- Answer the user's exact expanded query directly.
- Use only facts, numbers, and source status present in the evidence or \
structured render.
- You may compute simple arithmetic from displayed tables when the user asks \
for growth, comparison, trend, or ratios.
- Start with a terminal title line using box-rule text, for example \
"━━━ SYMBOL — Growth Story ━━━" or "━━━ SYMBOL — Direct Answer ━━━".
- For stock/company analysis, use this section order when evidence exists:
  1. "▶ CURRENT OVERVIEW"
  2. "▶ FINANCIAL PERFORMANCE"
  3. "▶ TECHNICAL AND SECTOR CONTEXT"
  4. "▶ KEY CONSIDERATIONS"
  5. "▶ BOTTOM LINE"
- Always include all five section headers for stock/company analysis when \
matching evidence exists. If a section is not central to the user query, keep \
it to one short bullet such as "Not central to this question."
- Avoid markdown heading syntax such as ### or #### in the answer body.
- Use one bullet level. If a subsection is needed, write it as "Label: value" \
instead of nested bullets.
- Prefer compact aligned bullets and short sentences over long paragraphs.
- Be specific: include the key numbers needed to support the conclusion.
- Do not invent company facts, prices, filings, or metrics.
- Do not include SOURCE TRAIL or investment-advice disclaimers; those are \
appended by the deterministic renderer.
- If evidence is missing or conflicting, say that explicitly and avoid a firm \
conclusion.
"""

# Intents that represent market/sector-level (not stock-level) queries.
_MARKET_INTENTS: frozenset[str] = frozenset({
    "market_situation_assessment",
    "market_situation",
    "market_overview",
    "market_dashboard",
    "sector_deep_dive",
    "sector_scan",
    "sector_rotation",
    "global_market_assessment",
    "startup_morning_briefing",
    "intraday_market_recap",
    "market_swing_candidates",
    "quality_breakouts",
})

_MARKET_FINAL_ANSWER_SYSTEM_PROMPT = """\
You are Agent Adda's final answer synthesizer for market and sector queries. \
You receive the user's query, tool evidence, and a deterministic structured render.

Rules:
- Answer the user's exact query directly and concisely.
- Use only facts and numbers present in the evidence or structured render.
- Start with a short terminal title line: "━━━ Market Snapshot — <topic> ━━━".
- Use these sections (include only those relevant to the query):
  1. "▶ LEADING SECTORS / INDICES"  — sectors and indices showing strength with % change
  2. "▶ WEAK SECTORS / INDICES"     — sectors and indices under pressure with % change
  3. "▶ BREADTH READING"            — advance/decline, stage distribution, RS context
  4. "▶ KEY MOVERS"                 — notable stocks driving the move (gainers / losers)
  5. "▶ MARKET VERDICT"             — 1–2 sentence actionable takeaway for the trader
- Do NOT use stock-analysis section headers (FINANCIAL PERFORMANCE, etc.).
- Do NOT include SOURCE TRAIL or investment-advice disclaimers.
- Do NOT repeat every number in the table — pick the 3–5 most relevant facts.
- Be specific: name the sectors/indices with their % change.
- Keep total answer under 300 words.
"""


def _final_synthesis_enabled() -> bool:
    value = os.environ.get("AGENT_ADDA_LLM_FINAL_SYNTHESIS", "1").strip().lower()
    return value not in {"0", "false", "no", "off", "disabled"}


def _compact_tool_evidence(tool_results: list[dict]) -> str:
    lines: list[str] = []
    for tr in (tool_results or [])[:12]:
        if not isinstance(tr, dict):
            continue
        tool = tr.get("tool") or "unknown_tool"
        result = tr.get("result") if isinstance(tr.get("result"), dict) else {}
        if result.get("error"):
            lines.append(f"{tool}: ERROR: {result.get('error')}")
            continue
        preview = {}
        for key, value in result.items():
            if key in {
                "symbol",
                "name",
                "company",
                "sector",
                "industry",
                "price",
                "pct_change",
                "stage",
                "signal",
                "technical_score",
                "rsi",
                "status",
                "period",
            }:
                preview[key] = value
        lines.append(f"{tool}: ok" + (f" {preview}" if preview else ""))
    return "\n".join(lines)


def _strip_forbidden_final_sections(content: str) -> str:
    text = (content or "").strip()
    if not text:
        return ""
    for sentinel in ("▶ SOURCE TRAIL", "━━━ Not investment advice"):
        idx = text.find(sentinel)
        if idx != -1:
            text = text[:idx].strip()
    return text


_FINAL_SECTION_LABELS = {
    # Stock analysis sections
    "current overview": "CURRENT OVERVIEW",
    "financial performance": "FINANCIAL PERFORMANCE",
    "technical and sector context": "TECHNICAL AND SECTOR CONTEXT",
    "key considerations": "KEY CONSIDERATIONS",
    "bottom line": "BOTTOM LINE",
    # Market / sector analysis sections
    "leading sectors / indices": "LEADING SECTORS / INDICES",
    "leading sectors": "LEADING SECTORS / INDICES",
    "weak sectors / indices": "WEAK SECTORS / INDICES",
    "weak sectors": "WEAK SECTORS / INDICES",
    "breadth reading": "BREADTH READING",
    "key movers": "KEY MOVERS",
    "market verdict": "MARKET VERDICT",
    "sector strength": "SECTOR STRENGTH",
    "index movers": "INDEX MOVERS",
    "verdict": "MARKET VERDICT",
}

_FINAL_ANSWER_WRAP_WIDTH = 72


def _normalize_final_answer_format(content: str) -> str:
    """Coerce common markdown answer headings into Agent Adda terminal style."""
    text = (content or "").strip()
    if not text:
        return ""

    lines: list[str] = []
    continuation_indent: str | None = None
    section_body_indent: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            lines.append("")
            continuation_indent = None
            continue

        title = re.match(r"^###\s+(.+?)\s*$", stripped)
        if title:
            heading = title.group(1).strip().strip("#").strip()
            lines.append(f"━━━ {heading} ━━━")
            continuation_indent = None
            section_body_indent = None
            continue

        section = re.match(r"^####\s+(.+?)\s*$", stripped)
        if section:
            label = section.group(1).strip().strip(":").lower()
            normalized = _FINAL_SECTION_LABELS.get(label, label.upper())
            lines.append(f"▶ {normalized}")
            continuation_indent = None
            section_body_indent = "  "
            continue

        if (
            (continuation_indent or section_body_indent)
            and line == stripped
            and not stripped.startswith(("▶", "━━━", "-", "•"))
        ):
            line = f"{continuation_indent or section_body_indent}{stripped}"

        lines.append(line)
        bullet = re.match(r"^(\s*)[-•]\s+", line)
        if bullet:
            continuation_indent = f"{bullet.group(1)}  "
        elif stripped.startswith(("▶", "━━━")):
            continuation_indent = None
            section_body_indent = "  " if stripped.startswith("▶") else None
        elif section_body_indent and line.startswith((" ", "\t")):
            continuation_indent = re.match(r"^(\s*)", line).group(1)

    normalized_text = "\n".join(lines).strip()
    normalized_text = re.sub(r"\n{3,}", "\n\n", normalized_text)
    wrapped_lines: list[str] = []
    for line in normalized_text.splitlines():
        if not line or line.lstrip().startswith(("▶", "━━━")):
            wrapped_lines.append(line)
            continue
        indent = re.match(r"^(\s*)", line).group(1)
        if len(line) <= _FINAL_ANSWER_WRAP_WIDTH:
            wrapped_lines.append(line)
            continue
        wrapped_lines.extend(
            textwrap.wrap(
                line,
                width=_FINAL_ANSWER_WRAP_WIDTH,
                subsequent_indent=indent,
                break_long_words=False,
                break_on_hyphens=False,
            )
        )
    return "\n".join(wrapped_lines)




def _build_market_evidence_summary(tool_results: list[dict]) -> str:
    """Compact market-focused evidence string for the LLM prompt."""
    lines: list[str] = []
    for tr in (tool_results or [])[:12]:
        if not isinstance(tr, dict):
            continue
        tool = tr.get("tool") or "unknown_tool"
        result = tr.get("result") if isinstance(tr.get("result"), dict) else {}
        if result.get("error"):
            lines.append(f"{tool}: ERROR")
            continue
        # Pull the most market-relevant fields
        keep_keys = {
            "indices", "sector_performance", "leading_sectors", "weak_sectors",
            "breadth", "adv_dec", "stage_distribution", "rs_percentiles",
            "gainers", "losers", "top_gainers", "top_losers",
            "as_of", "nifty50", "nifty_bank",
        }
        preview = {k: v for k, v in result.items() if k in keep_keys}
        if not preview:
            # Fallback: first 5 non-nested keys
            preview = {k: v for k, v in result.items() if not isinstance(v, (list, dict))}
        lines.append(f"{tool}: {preview}")
    return "\n".join(lines[:10])


def build_market_final_answer(
    intent: str,
    query: str,
    tool_results: list[dict],
    structured_output: str,
    backend,
) -> str:
    """LLM-written market/sector answer using the market-specific system prompt.

    Returns '' on skip or error so callers can fall back gracefully.
    """
    if not _final_synthesis_enabled():
        return ""
    if backend is None:
        return ""

    evidence = _build_market_evidence_summary(tool_results)
    # Use the first 6000 chars of the structured render (sector/breadth tables are compact)
    render_snippet = (structured_output or "")[:6000]

    user_content = (
        f"User query:\n{query}\n\n"
        f"Intent: {intent}\n\n"
        f"Tool evidence:\n{evidence}\n\n"
        f"Structured render (first 6000 chars):\n{render_snippet}"
    )
    messages = [
        {"role": "system", "content": _MARKET_FINAL_ANSWER_SYSTEM_PROMPT},
        {"role": "user",   "content": user_content},
    ]
    try:
        resp = backend.chat(messages, tools=[], max_tokens=_MAX_FINAL_ANSWER_TOKENS)
        content = _strip_forbidden_final_sections((resp or {}).get("content") or "")
        return _normalize_final_answer_format(content)
    except Exception as exc:
        logger.debug("Market final answer LLM synthesis failed: %s", exc)
        return ""


def build_final_answer(
    intent: str,
    query: str,
    tool_results: list[dict],
    structured_output: str,
    backend,
    assessment_plan: dict | None = None,
) -> str:
    """Return an LLM-written first-class answer, or '' on skip/error.

    Routes market/sector intents to build_market_final_answer so they use
    the market-specific system prompt instead of the stock-analysis template.
    The deterministic renderer remains the evidence body.
    """
    if not _final_synthesis_enabled():
        return ""
    if intent not in NARRATION_INTENTS:
        return ""
    if backend is None:
        return ""

    # Route market/sector queries to the dedicated market synthesizer
    if intent in _MARKET_INTENTS:
        return build_market_final_answer(intent, query, tool_results, structured_output, backend)

    assessment = ""
    if assessment_plan:
        try:
            tasks = assessment_plan.get("tasks") or []
            assessment = "\n".join(
                f"- {task.get('question')} via {task.get('tool') or task.get('derived_from') or 'unknown'}"
                for task in tasks[:8]
                if isinstance(task, dict)
            )
        except Exception:
            assessment = ""

    user_content = (
        f"Expanded user query:\n{query}\n\n"
        f"Intent:\n{intent}\n\n"
        f"Situation / assessment context:\n{assessment or 'None'}\n\n"
        f"Executed tool evidence summary:\n{_compact_tool_evidence(tool_results)}\n\n"
        f"Deterministic structured render:\n{(structured_output or '')[:12000]}"
    )
    messages = [
        {"role": "system", "content": _FINAL_ANSWER_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    try:
        resp = backend.chat(messages, tools=[], max_tokens=_MAX_FINAL_ANSWER_TOKENS)
        content = _strip_forbidden_final_sections((resp or {}).get("content") or "")
        return _normalize_final_answer_format(content)
    except Exception as exc:
        logger.debug("Final answer LLM synthesis failed: %s", exc)
        return ""


def build_narrative(
    intent: str,
    query: str,
    tool_results: list[dict],
    structured_output: str,
    backend,
    *,
    force: bool = False,
) -> str:
    """Return a short LLM-generated narrative paragraph, or '' on skip/error.

    Args:
        intent:            Routing intent for the current query.
        query:             The original user query text.
        tool_results:      Raw tool result dicts.
        structured_output: The deterministic renderer output (tables + bullets).
        backend:           Agent backend instance (must have .chat() method).
        force:             If True, generate narration even for non-listed intents.
    """
    if not force and intent not in NARRATION_INTENTS:
        return ""

    if backend is None:
        return ""

    # Condense tool data to a compact JSON-like summary (avoid huge prompts)
    data_lines: list[str] = []
    for tr in (tool_results or [])[:12]:
        r = tr.get("result") or {}
        if not isinstance(r, dict) or r.get("error"):
            continue
        # Only include a handful of top-level keys to keep the prompt small
        preview = {k: v for k, v in r.items()
                   if not isinstance(v, (list, dict)) or k in (
                       "symbol", "stage", "sector", "rs_percentiles", "rs_distribution",
                       "stage_distribution", "adv_dec",
                   )}
        data_lines.append(f"{tr['tool']}: {preview}")

    user_content = (
        f"Query: {query}\n\n"
        f"Intent: {intent}\n\n"
        f"Key data summary:\n" + "\n".join(data_lines[:8]) + "\n\n"
        f"Already-rendered output (first 600 chars):\n{structured_output[:600]}"
    )

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": user_content},
    ]

    try:
        resp = backend.chat(messages, tools=[], max_tokens=_MAX_NARRATIVE_TOKENS)
        content = (resp or {}).get("content") or ""
        if _contains_unsupported_rs_percentile_claim(content, tool_results, structured_output):
            return ""
        return content.strip()
    except Exception as exc:
        logger.debug("Narrator LLM call failed: %s", exc)
        return ""


def _contains_unsupported_rs_percentile_claim(
    content: str,
    tool_results: list[dict],
    structured_output: str,
) -> bool:
    text = (content or "").lower()
    if "percentile" not in text:
        return False
    evidence_text = (structured_output or "").lower()
    if "rs distribution" in evidence_text or "rs percentiles" in evidence_text:
        return False
    for tr in tool_results or []:
        result = tr.get("result") if isinstance(tr, dict) else None
        if not isinstance(result, dict):
            continue
        if result.get("rs_percentiles") or result.get("rs_distribution"):
            return False
    return True


def attach_narrative(
    structured_output: str,
    narrative: str,
    *,
    section_header: str = "▶ INTERPRETATION",
) -> str:
    """Splice the narrative paragraph into the structured output.

    Inserts the narrative BEFORE the SOURCE TRAIL block so the footer
    stays at the end.  If no narrative, returns the output unchanged.
    """
    if not narrative:
        return structured_output

    block = f"\n{section_header}\n  {narrative}\n"

    # Insert before SOURCE TRAIL if present, otherwise before FOOTER
    for sentinel in ("▶ SOURCE TRAIL", "━━━ Not investment advice"):
        idx = structured_output.find(sentinel)
        if idx != -1:
            return structured_output[:idx] + block + structured_output[idx:]

    return structured_output + block
