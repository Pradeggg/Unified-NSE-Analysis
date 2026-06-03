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
from .compound_stock import CompoundStockProvider as _CompoundStockProvider
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
    # ── Market state ─────────────────────────────────────────────────────────
    "market situation",
    "todays market",
    "today's market",
    "market today",
    "how is the market",
    "how is market",
    "market doing",
    "market now",
    "market outlook",
    "market overview",
    "market pulse",
    "market breadth",
    "market open",
    "market status",
    "nifty today",
    "nifty now",
    "whats moving",
    "what's moving",
    "what is moving",
    # ── Sector queries ────────────────────────────────────────────────────────
    "sector rotation",
    "sector strength",
    "sector performance",
    "sectors are",
    "sector today",
    "which sector",
    "what sector",
    "leading sector",
    "best sector",
    "top sector",
    "doing well",        # "which sectors are doing well"
    "outperforming",     # "what sectors are outperforming"
    "underperforming",
    "sector leader",
    "sector overview",
    # ── Screeners / scans ─────────────────────────────────────────────────────
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
    # ── Broad "which stocks" questions ─────────────────────────────────────────
    "stocks up today",
    "stocks down today",
    "which stocks are up",
    "which stocks are down",
    "stocks doing well",
    "what stocks are",
    "stocks today",
)
_TOP_MOVERS_PHRASES = (
    "top gainers",
    "top losers",
    "top movers",
    "biggest gainers",
    "biggest losers",
    "biggest movers",
)
_TOP_MOVERS_INTRADAY_HINTS = (
    "intraday",
    "live",
    "right now",
    "now",
    "real time",
    "real-time",
    "realtime",
)
_TOP_MOVERS_EOD_HINTS = (
    "eod",
    "end of day",
    "end-of-day",
    "yesterday",
    "close",
    "closing",
    "historical",
    "today's close",
    "todays close",
)
_DIRECT_INTENT_KEYWORDS = (
    ("mtf", ("mtf", "multi time frame", "multi-time-frame", "multi timeframe")),
    ("fundamentals", ("fundamentals", "balance sheet", "financials", "pe ratio")),
    ("technicals", ("technicals", "technical", "rsi", "macd", "ema", "moving average")),
    ("intraday_quote", ("quote", "price now", "current price", "ltp")),
)

# AA-UR-5: map provider intent tags to real entries in
# ``terminal.tools.TOOL_REGISTRY`` so route validation accepts them.
_INTENT_TOOL_MAP: dict[str, str] = {
    "mtf": "analyze_mtf",
    "fundamentals": "search_yahoo_finance",
    "technicals": "get_technical_setup",
    "intraday_quote": "get_live_quote",
}


def _topic_tool_plan(intent_tag: str, symbol: str) -> tuple[ToolCallSpec, ...]:
    """Build the minimal evidence plan for a single-symbol topic route."""
    sym = symbol.strip().upper()
    if intent_tag == "technicals":
        return (
            ToolCallSpec(tool="resolve_symbol", args={"query": sym}),
            ToolCallSpec(tool="get_symbol_snapshot", args={"symbol": sym}),
            ToolCallSpec(tool="get_technical_setup", args={"symbol": sym}),
        )
    tool_name = _INTENT_TOOL_MAP.get(intent_tag, "get_live_quote")
    return (ToolCallSpec(tool=tool_name, args={"symbol": sym}),)


def _norm(text: str) -> str:
    return (text or "").strip().lower()


def _kw_matches(kw: str, text: str, words: frozenset[str]) -> bool:
    """True if keyword matches text without false-positive substring hits.

    Single-word keywords (e.g. 'rsi', 'ema') require a whole-word match so
    that stock names like PERSISTENT or THEMATIC are not mis-classified.
    Multi-word / hyphenated keywords (e.g. 'moving average') keep the faster
    substring check because splitting on whitespace would miss them.
    """
    if " " in kw or "-" in kw:
        return kw in text
    return kw in words


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


class CouncilCommandProvider:
    """Routes first-class `/council` commands to Research Council wrappers."""

    name = "CouncilCommandProvider"

    def propose(self, user_input: str, context_pack: ContextPack) -> list[RouteCandidate]:
        raw = (user_input or "").strip()
        if not raw.lower().startswith("/council"):
            return []
        try:
            from terminal.research_council.commands import parse_council_command

            parsed = parse_council_command(raw)
        except Exception as exc:
            return [
                RouteCandidate(
                    provider=self.name,
                    intent="research_council_parse_error",
                    route_type="clarification",
                    confidence="high",
                    score=0.99,
                    reasons=(f"/council command did not parse: {exc}",),
                )
            ]
        tool_plan = self._tool_plan_for(parsed)
        return [
            RouteCandidate(
                provider=self.name,
                intent="research_council",
                route_type="direct_tool_plan",
                confidence="high",
                score=0.99,
                reasons=("First-class /council command matched",),
                tool_plan=tool_plan,
                evidence_requirements=(
                    EvidenceRequirement(
                        name="research_council_run",
                        required_tools=tuple(spec.tool for spec in tool_plan),
                    ),
                ),
                source_policy=SourcePolicy(required_freshness="mode_profile", allow_stale=False),
            )
        ]

    @staticmethod
    def _tool_plan_for(parsed) -> tuple[ToolCallSpec, ...]:
        if parsed.action == "steward":
            return (ToolCallSpec(tool="run_data_steward_check", args={"mode": parsed.mode}),)
        report_path = _council_report_path(parsed)
        if parsed.action == "review" and report_path:
            return (
                ToolCallSpec(
                    tool="run_research_council",
                    args={
                        "objective": parsed.objective,
                        "mode": parsed.mode,
                        "symbols": parsed.symbols,
                        "horizon": parsed.horizon,
                        "risk_budget": parsed.risk_budget,
                        "report_path": report_path,
                    },
                ),
            )
        if parsed.action == "report":
            return (
                ToolCallSpec(
                    tool="render_research_council_report",
                    args={
                        "run_id": str(parsed.options.get("run") or parsed.options.get("run_id") or "latest"),
                        "output_format": str(parsed.options.get("format") or "html"),
                    },
                ),
            )
        if parsed.action in {"review", "resume", "debug", "export"}:
            return (
                ToolCallSpec(
                    tool="resume_council_run",
                    args={
                        "run_id": str(parsed.options.get("run") or parsed.options.get("run_id") or "latest"),
                        "include_debug": parsed.action == "debug",
                        "output_format": str(parsed.options.get("format") or "json"),
                    },
                ),
            )
        return (
            ToolCallSpec(
                tool="run_research_council",
                args={
                    "objective": parsed.objective,
                    "mode": parsed.mode,
                    "symbols": parsed.symbols,
                    "horizon": parsed.horizon,
                    "risk_budget": parsed.risk_budget,
                    **_council_run_options(parsed),
                },
            ),
        )


def _council_report_path(parsed) -> str | None:
    value = parsed.options.get("report_path") or parsed.options.get("file") or parsed.options.get("path") or parsed.options.get("report")
    return str(value) if value else None


def _council_run_options(parsed) -> dict:
    excluded = {"horizon", "risk", "risk_budget", "file", "path", "report", "report_path"}
    return {key: value for key, value in parsed.options.items() if key not in excluded}


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
    """Routes "based on the above" / recommendation-on-context asks.

    When an :class:`ActiveWorkflow` is present in the context pack, the
    follow-up is bound to the **full** workflow (every step's evidence),
    not just the most recent turn — per AA-UR-7 acceptance. The route
    surfaces the workflow span, freshness divergence across steps, and
    any conflicting stances so synthesis can audit provenance.
    """

    name = "ContextualFollowupProvider"

    def propose(self, user_input: str, context_pack: ContextPack) -> list[RouteCandidate]:
        text = _norm(user_input)
        if not text:
            return []
        symbols = _pack_symbols(context_pack)
        workflow = context_pack.active_workflow
        if not (symbols or workflow or context_pack.recent_turns):
            return []
        matched_phrase = next((p for p in _FOLLOWUP_PHRASES if p in text), None)
        if not matched_phrase:
            return []

        reasons: list[str] = [f"Follow-up phrase detected: '{matched_phrase}'"]
        evidence_reqs: list[EvidenceRequirement] = []
        intent = "contextual_followup"

        if workflow is not None and workflow.steps:
            intent = "contextual_followup_workflow"
            step_kinds = [step.kind for step in workflow.steps if step.kind]
            wf_symbols = list(workflow.symbols)
            reasons.append(
                f"Active workflow '{workflow.workflow_id}' ({workflow.kind}) covers "
                f"{len(workflow.steps)} step(s): {', '.join(step_kinds) or 'unlabeled'}"
            )
            if wf_symbols:
                reasons.append(
                    f"Workflow symbols: {', '.join(wf_symbols)}"
                )
            # Build one evidence requirement per step kind so validation /
            # synthesis can audit per-facet coverage of the full workflow.
            seen_kinds: set[str] = set()
            for kind in step_kinds:
                lowered = kind.lower()
                if lowered in seen_kinds:
                    continue
                seen_kinds.add(lowered)
                evidence_reqs.append(
                    EvidenceRequirement(
                        name=lowered.replace(" ", "_"),
                        optional=True,
                    )
                )
            # Surface freshness divergence across steps so downstream can
            # warn the user.
            freshness_values = [
                step.freshness.strip() for step in workflow.steps if step.freshness.strip()
            ]
            unique_freshness = list(dict.fromkeys(freshness_values))
            if len(unique_freshness) > 1:
                reasons.append(
                    "Freshness divergence across workflow steps: "
                    + " | ".join(unique_freshness)
                )
            # Surface conflicting stances if structured evidence carries them.
            stances: list[str] = []
            for step in workflow.steps:
                for fact in step.evidence:
                    if not isinstance(fact, dict):
                        continue
                    stance = str(fact.get("stance") or "").strip().lower()
                    if stance and stance not in stances:
                        stances.append(stance)
            if len(stances) > 1:
                reasons.append(
                    "Conflicting stances in workflow evidence: " + ", ".join(stances)
                )
        else:
            reasons.append(
                f"Context bound to {len(symbols)} symbol(s); recent turns={len(context_pack.recent_turns)}"
            )

        return [
            RouteCandidate(
                provider=self.name,
                intent=intent,
                route_type="contextual_answer",
                confidence="high" if symbols or workflow else "medium",
                score=0.92 if workflow else 0.9,
                reasons=tuple(reasons),
                evidence_requirements=tuple(evidence_reqs),
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
        words = frozenset(re.findall(r"[a-z0-9]+", text))
        intent_tag = ""
        for tag, kws in _DIRECT_INTENT_KEYWORDS:
            if any(_kw_matches(kw, text, words) for kw in kws):
                intent_tag = tag
                break
        if not intent_tag:
            return []
        primary = symbols[0]
        tool_plan = _topic_tool_plan(intent_tag, primary)
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
                    EvidenceRequirement(
                        name=intent_tag,
                        required_tools=tuple(spec.tool for spec in tool_plan),
                    ),
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
        tool_plan = (ToolCallSpec(tool="run_visual_scan", args=tool_args),)
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
                    EvidenceRequirement(name="chart_data", required_tools=("run_visual_scan",)),
                ),
            )
        ]


class TopMoversProvider:
    """Routes 'top gainers / losers / movers' asks to the right tool.

    Two distinct backends:

    * `get_top_gainers_losers` — NSE live API; use when the user wants
      the *current* market (phrases like "intraday", "live", "right now",
      or no qualifier during market hours).
    * `get_eod_top_movers` — `scores.stage_snapshots` end-of-day source;
      use when the user explicitly asks for "EOD", "end of day",
      "yesterday", or "close".

    Previously these phrases were swept into `MarketSituationProvider`
    and silently routed to `scan_intraday_market` (which returns trade
    setups, not movers). That is now fixed.
    """

    name = "TopMoversProvider"

    def propose(self, user_input: str, context_pack: ContextPack) -> list[RouteCandidate]:
        text = _norm(user_input)
        if not text:
            return []
        matched = next((p for p in _TOP_MOVERS_PHRASES if p in text), None)
        if not matched:
            return []

        # Defer to broader market-situation / breadth handlers when the
        # ask is compound. A pure "top gainers" query is short; once the
        # user also asks about breadth, status, or sector context they
        # want the full market overview synthesis, not just movers.
        _COMPOUND_MARKET_HINTS = (
            "breadth", "market status", "market situation", "advance",
            "declines", "ad ratio", "sector rotation", "and how is",
            "and indices", "and index", "and sectors",
        )
        if any(h in text for h in _COMPOUND_MARKET_HINTS):
            return []

        direction = "both"
        if "loser" in text and "gainer" not in text:
            direction = "losers"
        elif "gainer" in text and "loser" not in text:
            direction = "gainers"

        wants_eod = any(h in text for h in _TOP_MOVERS_EOD_HINTS)
        wants_intraday = any(h in text for h in _TOP_MOVERS_INTRADAY_HINTS)

        if wants_eod and not wants_intraday:
            tool_name = "get_eod_top_movers"
            reason = "EOD hint matched"
        else:
            tool_name = "get_top_gainers_losers"
            reason = "intraday default" if not wants_intraday else "intraday hint matched"

        tool_plan = (
            ToolCallSpec(tool=tool_name, args={"direction": direction}),
        )
        return [
            RouteCandidate(
                provider=self.name,
                intent="top_movers",
                route_type="direct_tool_plan",
                confidence="high",
                score=0.85,
                reasons=(f"'{matched}' matched; {reason}; direction={direction}",),
                tool_plan=tool_plan,
                evidence_requirements=(
                    EvidenceRequirement(
                        name="top_movers",
                        required_tools=(tool_name,),
                    ),
                ),
                source_policy=SourcePolicy(allow_stale=False),
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
        if matched in {"scan nifty", "scan fno", "scan f&o", "intraday scan", "breakout scan", "vcp scan"}:
            tool_plan = (ToolCallSpec(tool="scan_intraday_market", args={}),)
            required_tools = ("scan_intraday_market",)
        else:
            tool_plan = (
                ToolCallSpec(tool="get_live_market_overview", args={}),
                ToolCallSpec(tool="get_market_breadth", args={}),
                ToolCallSpec(
                    tool="get_top_gainers_losers",
                    args={"index": "NIFTY 500", "top_n": 5, "direction": "both"},
                ),
            )
            intent = "market_situation"
            required_tools = (
                "get_live_market_overview",
                "get_market_breadth",
                "get_top_gainers_losers",
            )
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
                        required_tools=required_tools,
                    ),
                ),
                source_policy=SourcePolicy(allow_stale=False),
            )
        ]


class DirectIntentProvider:
    """Last-resort fallback: keyword → generic tool intent.

    If a symbol can be derived from the input or the ContextPack, we
    bind the topic tool; otherwise we emit a ``clarification`` so the
    user is asked which symbol they mean rather than the agent
    executing a tool with missing args.
    """

    name = "DirectIntentProvider"

    def propose(self, user_input: str, context_pack: ContextPack) -> list[RouteCandidate]:
        text = _norm(user_input)
        if not text:
            return []
        words = frozenset(re.findall(r"[a-z0-9]+", text))
        for tag, kws in _DIRECT_INTENT_KEYWORDS:
            if not any(_kw_matches(kw, text, words) for kw in kws):
                continue
            tool_name = _INTENT_TOOL_MAP.get(tag, "get_live_quote")
            symbols = _input_symbols(user_input) or _pack_symbols(context_pack)
            if symbols:
                tool_plan = _topic_tool_plan(tag, symbols[0])
                return [
                    RouteCandidate(
                        provider=self.name,
                        intent=f"direct_{tag}",
                        route_type="direct_tool_plan",
                        confidence="medium",
                        score=0.5,
                        reasons=(
                            f"Direct intent keyword for {tag!r}; "
                            f"bound to {symbols[0]!r} from "
                            f"{'input' if _input_symbols(user_input) else 'context'}",
                        ),
                        tool_plan=tool_plan,
                        evidence_requirements=(
                            EvidenceRequirement(
                                name=tag,
                                required_tools=tuple(spec.tool for spec in tool_plan),
                            ),
                        ),
                    )
                ]
            return [
                RouteCandidate(
                    provider=self.name,
                    intent=f"direct_{tag}_clarify",
                    route_type="clarification",
                    confidence="low",
                    score=0.5,
                    reasons=(
                        f"Direct intent keyword for {tag!r} but no symbol resolved",
                    ),
                )
            ]
        return []


# Default registration order; first provider wins ties.
# CompoundStockProvider runs early (high score 0.95) so multi-facet
# stock asks bypass the single-facet providers cleanly.
DEFAULT_PROVIDERS: tuple[type, ...] = (
    PendingOptionProvider,
    CouncilCommandProvider,
    ContextualFollowupProvider,
    _CompoundStockProvider,
    ReportProvider,
    VisualScanProvider,
    TopMoversProvider,
    MarketSituationProvider,
)


__all__ = [
    "ContextualFollowupProvider",
    "CouncilCommandProvider",
    "DEFAULT_PROVIDERS",
    "DirectIntentProvider",
    "EntityTopicProvider",
    "MarketSituationProvider",
    "PendingOptionProvider",
    "ReportProvider",
    "RouteProvider",
    "TopMoversProvider",
    "VisualScanProvider",
]
