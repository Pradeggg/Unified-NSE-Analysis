"""AA-UR-3 Provider chain for the unified router.

Each provider takes (user_input, ContextPack) and returns 0+
:class:`RouteCandidate` objects. The :class:`UnifiedRouter` runs them
in registration order, sorts by ``(score, -priority_index)``, and
projects the winner into a :class:`RouteDecision`.

Providers in this module are deliberately thin shims over the simplest
possible signal — they exist so the wrapper can be wired and traced in
parallel with the legacy assessment chain. Per AA-UR-3 acceptance,
*no behavior is removed*: the existing situation_assessment path is
untouched. Future tickets (AA-UR-4..7) sharpen each provider.
"""

from __future__ import annotations

import re
from typing import Protocol

from .context import ContextPack
from .schema import (
    EvidenceRequirement,
    NextOption,
    RouteCandidate,
    SourcePolicy,
    ToolCallSpec,
)


class RouteProvider(Protocol):
    """Protocol every provider implements."""

    name: str

    def propose(
        self, user_input: str, context_pack: ContextPack
    ) -> list[RouteCandidate]:  # pragma: no cover - protocol body
        ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LABEL_PATTERN = re.compile(r"^\s*([A-Za-z]|\d{1,2})\s*$")
_FOLLOWUP_PHRASES = (
    "based on the above",
    "based on above",
    "what would be your recommendation",
    "what is your recommendation",
    "what would you recommend",
    "what do you think",
    "what about the above",
    "summarize the above",
    "tell me more",
    "explain that",
    "explain the above",
    "and now",
    "go deeper",
    "expand on that",
)
_REPORT_PHRASES = (
    "the report",
    "that report",
    "the mtf report",
    "the previous report",
    "the dashboard",
    "the sector report",
    "the analysis report",
    "show me the report",
    "open the report",
    "from the report",
)
_VISUAL_PHRASES = (
    "chart",
    "charts",
    "candlestick",
    "visual scan",
    "dashboard",
    "plot",
    "draw",
    "render chart",
)
_MARKET_PHRASES = (
    "market situation",
    "todays market",
    "today's market",
    "market today",
    "sector rotation",
    "screener",
    "scan nifty",
    "scan fno",
    "scan f&o",
    "intraday scan",
    "top gainers",
    "top losers",
    "rs leaders",
    "relative strength",
    "breakout scan",
    "vcp scan",
)
_DIRECT_INTENT_KEYWORDS = (
    ("mtf", ("mtf", "multi time frame", "multi-time-frame", "multi timeframe")),
    ("fundamentals", ("fundamentals", "balance sheet", "financials", "pe ratio")),
    ("technicals", ("technicals", "rsi", "macd", "ema", "moving average")),
    ("intraday_quote", ("quote", "price now", "current price", "ltp")),
)


def _norm(text: str) -> str:
    return (text or "").strip().lower()


def _pack_symbols(pack: ContextPack) -> tuple[str, ...]:
    if pack.active_symbols:
        return pack.active_symbols
    if pack.recent_turns:
        for turn in reversed(pack.recent_turns):
            if turn.symbols:
                return turn.symbols
    return ()


def _input_symbols(user_input: str) -> tuple[str, ...]:
    # Naive uppercase-token scan; the real symbol resolver lives in
    # terminal/symbol_resolver.py and is wired by UR-4.
    tokens = re.findall(r"\b[A-Z][A-Z0-9&]{1,15}\b", user_input or "")
    seen: list[str] = []
    for tok in tokens:
        if tok in seen:
            continue
        if tok in {"NSE", "NIFTY", "BSE", "EOD", "RS", "MTF", "PE", "EMA", "MACD", "RSI"}:
            continue
        seen.append(tok)
    return tuple(seen)


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


class PendingOptionProvider:
    """Resolves NEXT OPTION replies (``A``, ``B``, ``1``…) via ContextPack.

    When fired, the resulting candidate carries the bound_action's
    pre-computed tool_plan and symbols — meaning *no symbol resolution
    is required* at execution time. This satisfies the AA-UR-3
    acceptance "pending option replies execute bound actions without
    symbol re-resolution".
    """

    name = "PendingOptionProvider"

    def propose(self, user_input: str, context_pack: ContextPack) -> list[RouteCandidate]:
        text = _norm(user_input)
        if not text or not context_pack.pending_options:
            return []

        match = _LABEL_PATTERN.match(text)
        candidates: list[RouteCandidate] = []

        if match:
            label = match.group(1)
            opt = context_pack.find_pending_option(label)
            if opt is not None:
                candidates.append(self._candidate_from_option(opt, score=1.0))
                return candidates

        # Allow exact text match too (e.g. user re-types the option text).
        for opt in context_pack.pending_options:
            if _norm(opt.text) == text:
                candidates.append(self._candidate_from_option(opt, score=0.95))
                return candidates

        return []

    @staticmethod
    def _candidate_from_option(opt, score: float) -> RouteCandidate:
        action = opt.bound_action or {}
        tools = action.get("tool_plan") or []
        tool_plan: list[ToolCallSpec] = []
        for entry in tools:
            if isinstance(entry, dict) and entry.get("tool"):
                tool_plan.append(
                    ToolCallSpec(tool=str(entry["tool"]), args=dict(entry.get("args") or {}))
                )
            elif isinstance(entry, (list, tuple)) and len(entry) == 2:
                tool_plan.append(ToolCallSpec(tool=str(entry[0]), args=dict(entry[1] or {})))
        route_type = "direct_tool_plan" if tool_plan else "contextual_answer"
        intent = str(action.get("intent") or "pending_option_followup")
        return RouteCandidate(
            provider=PendingOptionProvider.name,
            intent=intent,
            route_type=route_type,
            confidence="high",
            score=score,
            reasons=(f"Bound NEXT OPTION '{opt.label}' selected by user",),
            tool_plan=tuple(tool_plan),
        )


class ContextualFollowupProvider:
    """Routes "based on the above" / recommendation-on-context asks."""

    name = "ContextualFollowupProvider"

    def propose(self, user_input: str, context_pack: ContextPack) -> list[RouteCandidate]:
        text = _norm(user_input)
        if not text:
            return []
        symbols = _pack_symbols(context_pack)
        if not (symbols or context_pack.active_workflow or context_pack.recent_turns):
            return []
        matched_phrase = next((p for p in _FOLLOWUP_PHRASES if p in text), None)
        if not matched_phrase:
            return []
        return [
            RouteCandidate(
                provider=self.name,
                intent="contextual_followup",
                route_type="contextual_answer",
                confidence="high" if symbols else "medium",
                score=0.9,
                reasons=(
                    f"Follow-up phrase detected: '{matched_phrase}'",
                    f"Context bound to {len(symbols)} symbol(s); recent turns={len(context_pack.recent_turns)}",
                ),
                source_policy=SourcePolicy(
                    required_freshness=context_pack.freshness or "",
                    allow_stale=False,
                ),
            )
        ]


class EntityTopicProvider:
    """Routes ``<SYMBOL> <topic>`` asks (e.g. ``DIXON technicals``)."""

    name = "EntityTopicProvider"

    def propose(self, user_input: str, context_pack: ContextPack) -> list[RouteCandidate]:
        if not user_input:
            return []
        symbols = _input_symbols(user_input)
        if not symbols:
            return []
        text = _norm(user_input)
        intent_tag = ""
        for tag, kws in _DIRECT_INTENT_KEYWORDS:
            if any(kw in text for kw in kws):
                intent_tag = tag
                break
        if not intent_tag:
            return []
        primary = symbols[0]
        tool_plan = (ToolCallSpec(tool=f"{intent_tag}_for_symbol", args={"symbol": primary}),)
        return [
            RouteCandidate(
                provider=self.name,
                intent=f"entity_topic_{intent_tag}",
                route_type="direct_tool_plan",
                confidence="high",
                score=0.85,
                reasons=(
                    f"Detected symbol {primary!r} + topic '{intent_tag}'",
                ),
                tool_plan=tool_plan,
                evidence_requirements=(
                    EvidenceRequirement(name=intent_tag, required_tools=(tool_plan[0].tool,)),
                ),
            )
        ]


class ReportProvider:
    """Routes asks that reference a previously generated report."""

    name = "ReportProvider"

    def propose(self, user_input: str, context_pack: ContextPack) -> list[RouteCandidate]:
        text = _norm(user_input)
        if not text or not context_pack.active_reports:
            return []
        if not any(phrase in text for phrase in _REPORT_PHRASES):
            return []
        # If the user named a symbol, prefer that report; else the most recent.
        symbols = _input_symbols(user_input)
        report = None
        for sym in symbols:
            report = context_pack.report_for(symbol=sym)
            if report is not None:
                break
        if report is None:
            report = context_pack.active_reports[-1]
        return [
            RouteCandidate(
                provider=self.name,
                intent="report_recall",
                route_type="contextual_answer",
                confidence="high",
                score=0.8,
                reasons=(
                    f"Report phrase matched; bound to report '{report.path}'"
                    + (f" for symbol {report.symbol}" if report.symbol else ""),
                ),
            )
        ]


class VisualScanProvider:
    """Routes chart/dashboard/visual scan asks."""

    name = "VisualScanProvider"

    def propose(self, user_input: str, context_pack: ContextPack) -> list[RouteCandidate]:
        text = _norm(user_input)
        if not text:
            return []
        matched = next((p for p in _VISUAL_PHRASES if p in text), None)
        if not matched:
            return []
        symbols = _input_symbols(user_input) or _pack_symbols(context_pack)
        tool_args: dict[str, object] = {}
        if symbols:
            tool_args["symbol"] = symbols[0]
        tool_plan = (ToolCallSpec(tool="render_visual_scan", args=tool_args),)
        return [
            RouteCandidate(
                provider=self.name,
                intent="visual_scan",
                route_type="direct_tool_plan",
                confidence="high" if symbols else "medium",
                score=0.7,
                reasons=(f"Visual phrase '{matched}' matched",),
                tool_plan=tool_plan,
                evidence_requirements=(
                    EvidenceRequirement(name="chart_data", required_tools=("render_visual_scan",)),
                ),
            )
        ]


class MarketSituationProvider:
    """Routes market-wide situation / scan / screener asks."""

    name = "MarketSituationProvider"

    def propose(self, user_input: str, context_pack: ContextPack) -> list[RouteCandidate]:
        text = _norm(user_input)
        if not text:
            return []
        matched = next((p for p in _MARKET_PHRASES if p in text), None)
        if not matched:
            return []
        tool_plan = (ToolCallSpec(tool="run_market_situation", args={}),)
        return [
            RouteCandidate(
                provider=self.name,
                intent="market_situation",
                route_type="direct_tool_plan",
                confidence="medium",
                score=0.65,
                reasons=(f"Market phrase '{matched}' matched",),
                tool_plan=tool_plan,
                evidence_requirements=(
                    EvidenceRequirement(
                        name="market_snapshot",
                        required_tools=("run_market_situation",),
                    ),
                ),
                source_policy=SourcePolicy(allow_stale=False),
            )
        ]


class DirectIntentProvider:
    """Last-resort fallback: keyword → generic tool intent."""

    name = "DirectIntentProvider"

    def propose(self, user_input: str, context_pack: ContextPack) -> list[RouteCandidate]:
        text = _norm(user_input)
        if not text:
            return []
        for tag, kws in _DIRECT_INTENT_KEYWORDS:
            if any(kw in text for kw in kws):
                return [
                    RouteCandidate(
                        provider=self.name,
                        intent=f"direct_{tag}",
                        route_type="direct_tool_plan",
                        confidence="medium",
                        score=0.5,
                        reasons=(f"Direct intent keyword for {tag!r}",),
                        tool_plan=(ToolCallSpec(tool=f"{tag}_default", args={}),),
                    )
                ]
        return []


# Default registration order; first provider wins ties.
DEFAULT_PROVIDERS: tuple[type, ...] = (
    PendingOptionProvider,
    ContextualFollowupProvider,
    EntityTopicProvider,
    ReportProvider,
    VisualScanProvider,
    MarketSituationProvider,
    DirectIntentProvider,
)


__all__ = [
    "ContextualFollowupProvider",
    "DEFAULT_PROVIDERS",
    "DirectIntentProvider",
    "EntityTopicProvider",
    "MarketSituationProvider",
    "PendingOptionProvider",
    "ReportProvider",
    "RouteProvider",
    "VisualScanProvider",
]
