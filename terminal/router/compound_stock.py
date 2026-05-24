"""AA-UR-4 Compound stock provider.

Handles direct compound prompts that ask for several pieces of
information about *one specific stock* in a single utterance, e.g.::

    "live pricies for dixon tech and the analysis of the F&O data
     and intraday tradesetup in 5 mins"

The provider:

1. Detects that the prompt covers >=2 of {live quote, F&O, intraday
   setup} — i.e. it is *compound*.
2. Resolves the target symbol via the hybrid resolver
   (``terminal.symbol_search.resolve``) using sliding-window tokens
   after stripping the request vocabulary. **Index tickers
   (NIFTY/BANKNIFTY/etc.) are never preferred over a stock match** —
   this is the AA-UR-4 "never fall back to NIFTY" guarantee.
3. Emits a ``compound_plan`` RouteCandidate with the five-tool plan:
   ``resolve_symbol``, ``get_live_quote``, ``get_fno_overview``,
   ``explain_intraday_setup``, ``get_intraday_analysis``.
4. Marks ``get_fno_overview`` as an *optional* EvidenceRequirement so
   downstream execution can drop F&O cleanly when it is unavailable
   for this symbol, while live + intraday evidence is still
   collected for the resolved stock.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .context import ContextPack
from .schema import (
    EvidenceRequirement,
    RouteCandidate,
    SourcePolicy,
    ToolCallSpec,
)


# Phrases that indicate each evidence facet the prompt is asking for.
_LIVE_QUOTE_PHRASES = (
    "live price",
    "live prices",
    "live pricies",  # common typo
    "current price",
    "ltp",
    "quote",
    "spot price",
)
_FNO_PHRASES = (
    "f&o",
    "fno",
    "futures and options",
    "futures & options",
    "derivatives",
    "option chain",
    "options chain",
)
_INTRADAY_PHRASES = (
    "intraday",
    "trade setup",
    "tradesetup",
    "5 min",
    "5min",
    "5m",
    "15 min",
    "15min",
    "15m",
    "scalping",
)

# Tokens that should never be treated as symbol candidates because they
# are part of the request vocabulary, not the stock name.
_STOP_TOKENS = frozenset(
    {
        "a", "an", "and", "the", "of", "for", "in", "on", "to", "with",
        "please", "live", "price", "prices", "pricies", "ltp", "quote",
        "spot", "current", "fno", "f&o", "f", "o", "futures", "options",
        "derivatives", "option", "chain", "data", "analysis", "analyse",
        "analyze", "intraday", "trade", "setup", "tradesetup", "scalping",
        "min", "mins", "minute", "minutes", "5m", "15m", "5", "15", "30",
        "today", "todays", "now", "is", "are", "what", "how", "show",
        "give", "me", "us", "my", "do", "does", "the", "this", "that",
        "and/or", "or", "vs", "versus", "if", "then", "so",
    }
)

# Index tickers the resolver can return; these MUST NOT win when a
# stock match is also available. AA-UR-4: "never fall back to NIFTY".
_INDEX_TICKERS = frozenset(
    {
        "NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50",
        "SENSEX", "BANKEX", "INDIAVIX",
    }
)


def _norm(text: str) -> str:
    return (text or "").strip().lower()


def _present(text: str, phrases: tuple[str, ...]) -> str:
    for p in phrases:
        if p in text:
            return p
    return ""


@dataclass(frozen=True)
class _Facets:
    live_quote: str = ""
    fno: str = ""
    intraday: str = ""

    @property
    def count(self) -> int:
        return sum(1 for v in (self.live_quote, self.fno, self.intraday) if v)


def _detect_facets(text: str) -> _Facets:
    return _Facets(
        live_quote=_present(text, _LIVE_QUOTE_PHRASES),
        fno=_present(text, _FNO_PHRASES),
        intraday=_present(text, _INTRADAY_PHRASES),
    )


def _content_tokens(text: str) -> list[str]:
    """Tokenize ``text`` and drop request-vocabulary stop tokens."""
    raw = re.findall(r"[A-Za-z][A-Za-z0-9&]*", text or "")
    return [tok for tok in raw if tok.lower() not in _STOP_TOKENS]


def _resolve_symbol(text: str) -> tuple[str, str] | None:
    """Return (symbol, matched_phrase) or None.

    Tries sliding 3→2→1-token windows over the content tokens, prefers
    *non-index* hits, and never returns an index ticker if any stock
    ticker also matched.
    """
    try:
        from terminal.symbol_search import resolve as _resolve
    except Exception:  # pragma: no cover - resolver missing → degrade
        return None

    tokens = _content_tokens(text)
    if not tokens:
        return None

    best_stock: tuple[str, str, float] | None = None  # (symbol, phrase, score)
    best_index: tuple[str, str, float] | None = None

    for window_size in (3, 2, 1):
        for i in range(0, len(tokens) - window_size + 1):
            window = tokens[i : i + window_size]
            phrase = " ".join(window)
            try:
                result = _resolve(phrase)
            except Exception:
                continue
            symbol = (result.symbol or "").upper()
            if not symbol:
                continue
            # Treat exact/strong dict/typo matches as actionable; trigram
            # fuzzes need clarification.
            if result.confidence_band not in {"exact", "strong"}:
                continue
            score = float(result.score or 0.0)
            if symbol in _INDEX_TICKERS:
                if best_index is None or score > best_index[2]:
                    best_index = (symbol, phrase, score)
            else:
                if best_stock is None or score > best_stock[2]:
                    best_stock = (symbol, phrase, score)
        if best_stock is not None:
            break  # prefer the longest window that gave a stock hit

    if best_stock is not None:
        return best_stock[0], best_stock[1]
    if best_index is not None:
        # If the *only* match is an index AND the prompt explicitly
        # named it, surface it. We still won't fall back to NIFTY when
        # a stock-shaped query failed.
        return best_index[0], best_index[1]
    return None


class CompoundStockProvider:
    """Routes compound single-stock prompts to a five-tool ``compound_plan``."""

    name = "CompoundStockProvider"

    def propose(self, user_input: str, context_pack: ContextPack) -> list[RouteCandidate]:
        text = _norm(user_input)
        if not text:
            return []

        facets = _detect_facets(text)
        if facets.count < 2:
            # Not a compound ask — let the other providers handle it.
            return []

        resolution = _resolve_symbol(user_input)
        if resolution is None:
            # Compound shape detected but no symbol could be locked in.
            # Emit a clarification candidate so the router can ask which
            # symbol the user means rather than guessing (and certainly
            # never silently routing to NIFTY).
            return [
                RouteCandidate(
                    provider=self.name,
                    intent="compound_stock_clarify",
                    route_type="clarification",
                    confidence="low",
                    score=0.9,
                    reasons=(
                        "Compound stock ask detected but no symbol resolved.",
                        "Refusing to default to NIFTY (AA-UR-4 guarantee).",
                    ),
                )
            ]

        symbol, matched_phrase = resolution

        # The five-tool plan. resolve_symbol is included as the first
        # step so the validator/executor can re-verify the resolution
        # at run time without us baking the resolver into the router.
        tool_plan = (
            ToolCallSpec(tool="resolve_symbol", args={"query": matched_phrase}),
            ToolCallSpec(tool="get_live_quote", args={"symbol": symbol}),
            ToolCallSpec(tool="get_fno_overview", args={"symbol": symbol}),
            ToolCallSpec(tool="explain_intraday_setup", args={"symbol": symbol}),
            ToolCallSpec(
                tool="get_intraday_analysis",
                args={"symbol": symbol, "timeframe": _detect_timeframe(text)},
            ),
        )

        # Evidence map — F&O is optional so a downstream "unavailable"
        # outcome doesn't blow up the route.
        evidence = (
            EvidenceRequirement(name="live_quote", required_tools=("get_live_quote",)),
            EvidenceRequirement(name="fno_overview", required_tools=("get_fno_overview",), optional=True),
            EvidenceRequirement(
                name="intraday_setup",
                required_tools=("explain_intraday_setup", "get_intraday_analysis"),
            ),
        )

        reasons = (
            f"Compound facets matched: live={facets.live_quote!r} "
            f"fno={facets.fno!r} intraday={facets.intraday!r}",
            f"Resolved symbol {symbol!r} via phrase {matched_phrase!r}",
            "F&O kept optional so unavailability does not strip live/intraday evidence.",
        )

        return [
            RouteCandidate(
                provider=self.name,
                intent="compound_stock_overview",
                route_type="compound_plan",
                confidence="high",
                # Higher than EntityTopicProvider (0.85) and Market (0.65)
                # so compound asks win over single-facet providers.
                score=0.95,
                reasons=reasons,
                tool_plan=tool_plan,
                evidence_requirements=evidence,
                source_policy=SourcePolicy(allow_stale=False),
            )
        ]


def _detect_timeframe(text: str) -> str:
    """Best-effort timeframe extraction (5m / 15m / 30m). Defaults to ``5m``.

    Order matters: longer prefixes (15m/30m) are checked before 5m so
    that ``"15 min"`` is not accidentally matched as ``"5 min"``.
    """
    for tf in ("15m", "15min", "15 min", "15 mins"):
        if tf in text:
            return "15m"
    for tf in ("30m", "30min", "30 min", "30 mins"):
        if tf in text:
            return "30m"
    for tf in ("5m", "5min", "5 min", "5 mins"):
        if tf in text:
            return "5m"
    return "5m"


def coverage_map(candidate: RouteCandidate) -> dict[str, list[str]]:
    """Return {evidence_name: [tool, ...]} for a compound candidate.

    Used by tests and downstream validators (AA-UR-5) to confirm every
    requested facet is covered by at least one tool.
    """
    return {req.name: list(req.required_tools) for req in candidate.evidence_requirements}


__all__ = ["CompoundStockProvider", "coverage_map"]
