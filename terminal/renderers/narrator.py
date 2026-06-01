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
    "startup_morning_briefing",
    "intraday_setup",
    "intraday_market_recap",
    "fno_overview",
    "results_feed",
    "forthcoming_results",
})

# Maximum tokens for the narrative response — keep it short and punchy.
_MAX_NARRATIVE_TOKENS = 160

_SYSTEM_PROMPT = """\
You are a concise market analyst assistant. You receive structured investment \
research data that has already been formatted into tables and bullet lists. \
Your job: write 2–3 sentences of plain-English interpretation — the \
"so what?" — that a trader or investor would find actionable. \
Do NOT repeat the numbers already in the tables. Do NOT add new facts. \
Do NOT mention that this is not investment advice (that footer is added \
separately). Keep it under 50 words.\
"""


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
                   if not isinstance(v, (list, dict)) or k in ("symbol", "stage", "sector")}
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
        return content.strip()
    except Exception as exc:
        logger.debug("Narrator LLM call failed: %s", exc)
        return ""


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
