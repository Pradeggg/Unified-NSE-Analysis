"""terminal.renderers — deterministic response renderer package.

Public API
----------
render(intent, tool_results, assessment_plan=None) -> str
    Route an intent to its dedicated renderer and return structured text.

build_narrative(intent, query, tool_results, structured_output, backend) -> str
    Optional LLM-generated interpretation paragraph (see narrator.py).

attach_narrative(structured_output, narrative) -> str
    Splice the narrative into the structured output before SOURCE TRAIL.
"""
from __future__ import annotations

# Re-export the narrative helpers so callers only need one import
from .narrator import build_final_answer, build_narrative, attach_narrative, NARRATION_INTENTS

_YOUTUBE_INTENTS = frozenset({
    "youtube_video_analysis",
    "youtube_channel_latest",
    "youtube_channel_list",
    "youtube_channels",
})


def render(
    intent: str,
    tool_results: list[dict],
    assessment_plan: dict | None = None,
) -> str:
    """Route *intent* to its dedicated renderer and return a formatted string."""

    # ── simple / static intents ────────────────────────────────────────────
    from . import misc
    if intent == "visual_scan":
        return misc.render_visual_scan(tool_results)
    if intent == "greeting":
        return misc.render_greeting()
    if intent == "placeholder_symbol_request":
        return misc.render_placeholder_symbol_request(tool_results)
    if intent == "document_link_help":
        return misc.render_document_link_help(tool_results)

    # ── report lookup ──────────────────────────────────────────────────────
    from . import report
    if intent == "report_lookup":
        return report.render(tool_results)

    # ── YouTube ────────────────────────────────────────────────────────────
    from . import youtube
    if intent in _YOUTUBE_INTENTS:
        return youtube.render(tool_results)

    # ── results (filed / forthcoming) ──────────────────────────────────────
    from . import results_feed as _rf
    if intent == "results_feed":
        return _rf.render_results_feed(tool_results)
    if intent == "forthcoming_results":
        return _rf.render_forthcoming(tool_results)

    # ── stock results ──────────────────────────────────────────────────────
    from . import stock_results as _sr
    if intent == "collective_news_results":
        return _sr.render_collective_news(tool_results)
    if intent == "stock_results":
        return _sr.render_stock_results(tool_results)

    # ── entity topic command ───────────────────────────────────────────────
    from . import entity
    if intent == "entity_topic_command":
        return entity.render(tool_results)

    # ── market ─────────────────────────────────────────────────────────────
    from . import market
    if intent == "market_dashboard":
        return market.render_dashboard(tool_results)
    if intent == "market_situation_assessment":
        # Old code: assessment header (plan / low-confidence note) printed,
        # then fell through to the big live-market fallback.  Replicate that.
        from . import stock_brief as _sb
        header = market.render_situation_assessment(tool_results, assessment_plan)
        body   = _sb.render(intent, tool_results, assessment_plan)
        return (header + "\n" + body).strip() if header else body
    if intent == "market_swing_candidates":
        from . import market_swing
        return market_swing.render(tool_results)
    if intent == "startup_morning_briefing":
        return market.render_morning_briefing(tool_results)

    # ── F&O ────────────────────────────────────────────────────────────────
    from . import fno
    if intent == "fno_overview":
        return fno.render(tool_results)

    # ── composite screeners ───────────────────────────────────────────────
    if intent == "quality_breakouts":
        from . import quality_breakouts
        return quality_breakouts.render(tool_results)

    # ── bare-symbol quick analysis ────────────────────────────────────────
    if intent == "symbol_quick_analysis":
        from . import symbol_quick_analysis
        return symbol_quick_analysis.render(tool_results)

    # ── fallback: stock_brief + screener + intraday + forensic ────────────
    from . import stock_brief
    return stock_brief.render(intent, tool_results, assessment_plan)
