"""Hybrid symbol resolver — network-free dict + typo + trigram tiers."""

from __future__ import annotations

import logging
import re
import time
from difflib import SequenceMatcher

from . import alias_source
from .schema import ResolveCandidate, ResolveResult
from .telemetry import emit as _emit_telemetry

log = logging.getLogger(__name__)


_CONTEXT_TOKENS: frozenset[str] = frozenset({
    "ABOUT", "ABOVE", "ACTION", "ANALYSIS", "ANALYZE", "ANALYSE", "BASED",
    "BRIEF", "CONTEXT", "FOR", "FROM", "IN", "INTRADAY", "LAST", "LOOK",
    "MARKET", "MIN", "MINS", "MINUTE", "MINUTES", "OF", "ON", "REPORT",
    "RECOMMENDATION", "SETUP", "SIGNAL", "SIGNALS", "STOCKS", "TECHNICAL",
    "THE", "THESE", "THIS", "TODAY", "TRADE", "WHAT", "WITH",
})


def band_for_score(score: float) -> str:
    """Map a normalized resolver score to a confidence band."""
    if score >= 1.0:
        return "exact"
    if score >= 0.85:
        return "high"
    if score >= 0.60:
        return "medium"
    if score >= 0.30:
        return "low"
    return "none"


def resolve(
    query: str,
    *,
    top_n: int = 10,
    alias_map: dict[str, str] | None = None,
    use_trigram: bool = True,
) -> ResolveResult:
    """Resolve ``query`` through local deterministic tiers.

    This function intentionally does not call the NSE live API. Live fallback
    stays in :func:`terminal.tools.resolve_symbol` so this resolver remains
    fast, deterministic, and safe for routing.
    """
    raw = str(query or "").strip()
    started = time.perf_counter()
    if not raw:
        return _finalize(_empty_result(query or ""), started, fallback_reason="empty_query")

    mapping = alias_map if alias_map is not None else alias_source.build_alias_map()
    dict_result = _dict_lookup(raw, mapping)
    if dict_result.symbol:
        return _finalize(dict_result, started, fallback_reason="dict_hit")

    typo_result = _prefix8_typo_lookup(raw, mapping)
    if typo_result.symbol:
        return _finalize(typo_result, started, fallback_reason="typo_hit")

    if not use_trigram:
        return _finalize(dict_result, started, fallback_reason="trigram_disabled")

    try:
        from . import trigram_index

        hits = trigram_index.lookup(raw, top_n=top_n)
    except Exception as exc:  # pragma: no cover - defensive degrade
        log.info("symbol_search.resolve: trigram lookup degraded for %r: %s", raw, exc)
        return _finalize(dict_result, started, fallback_reason="trigram_error")

    if hits:
        return _finalize(
            _from_trigram_hits(raw, hits, top_n=top_n),
            started,
            fallback_reason="trigram_hit",
        )
    return _finalize(dict_result, started, fallback_reason="no_match")


def _dict_lookup(query: str, alias_map: dict[str, str]) -> ResolveResult:
    q_key = _lookup_key(query)
    if not q_key:
        return _empty_result(query)
    normalized = _normalized_aliases(alias_map)
    hit = normalized.get(q_key)
    if hit:
        matched, symbol = hit
        candidate = ResolveCandidate(
            symbol=symbol,
            score=1.0,
            raw_score=1.0,
            methods=("dict",),
            matched=matched,
        )
        return ResolveResult(
            symbol=symbol,
            legacy_confidence="exact",
            confidence_band="exact",
            score=1.0,
            raw_score=1.0,
            query=query,
            candidates=(candidate,),
            method="dict",
            matched=matched,
        )

    tokens = _tokens(query)
    if _is_context_phrase(tokens):
        return _empty_result(query)
    if len(tokens) == 1 and tokens[0] in alias_source._GENERIC_NAME_TOKENS:
        return _empty_result(query)

    if len(tokens) >= 2 and not re.fullmatch(r"[A-Z0-9&-]{2,12}", str(query or "").strip().upper()):
        forward_hits = [
            (abs(len(key_norm) - len(q_key)), matched, symbol)
            for key_norm, (matched, symbol) in normalized.items()
            if len(q_key) >= 8 and q_key in key_norm
        ]
        if forward_hits:
            forward_hits.sort(key=lambda item: item[0])
            _distance, matched, symbol = forward_hits[0]
            candidate = ResolveCandidate(
                symbol=symbol,
                score=0.88,
                raw_score=0.88,
                methods=("dict",),
                matched=matched,
            )
            return ResolveResult(
                symbol=symbol,
                legacy_confidence="fuzzy",
                confidence_band="high",
                score=0.88,
                raw_score=0.88,
                query=query,
                candidates=(candidate,),
                method="dict",
                matched=matched,
            )
    return _empty_result(query)


def _prefix8_typo_lookup(query: str, alias_map: dict[str, str]) -> ResolveResult:
    q_key = _lookup_key(query)
    if not q_key or not re.fullmatch(r"[A-Z0-9&-]{2,12}", str(query or "").strip().upper()):
        return _empty_result(query)

    hits: list[tuple[float, str, str]] = []
    for key_norm, (matched, symbol) in _normalized_aliases(alias_map).items():
        if key_norm != _lookup_key(symbol):
            continue
        if len(key_norm) < 8 or len(q_key) < 8:
            continue
        ratio = SequenceMatcher(None, q_key, key_norm).ratio()
        prefix_contraction = len(q_key) > len(key_norm) and q_key[:8] == key_norm[:8] and ratio >= 0.90
        one_char_typo = q_key[:2] == key_norm[:2] and ratio >= 0.94
        if prefix_contraction or one_char_typo:
            hits.append((ratio, matched, symbol))
    if not hits:
        return _empty_result(query)

    hits.sort(key=lambda item: item[0], reverse=True)
    unique = list(dict.fromkeys(symbol for _ratio, _matched, symbol in hits))
    if len(unique) != 1:
        return _empty_result(query)

    score, matched, symbol = hits[0]
    candidates = tuple(
        ResolveCandidate(
            symbol=symbol,
            score=max(0.0, min(1.0, score)),
            raw_score=score,
            methods=("dict",),
            matched=matched,
        )
        for _score, matched, symbol in hits[:5]
    )
    return ResolveResult(
        symbol=unique[0],
        legacy_confidence="near-match",
        confidence_band="high",
        score=max(0.0, min(1.0, score)),
        raw_score=score,
        query=query,
        candidates=candidates,
        method="dict",
        matched=matched,
    )


def _from_trigram_hits(
    query: str,
    hits: list[ResolveCandidate],
    *,
    top_n: int,
) -> ResolveResult:
    top = hits[0]
    score = max(0.0, min(1.0, float(top.score or 0.0)))
    band = band_for_score(score)
    if band in {"none", "low"}:
        return ResolveResult(
            symbol=None,
            legacy_confidence="none",
            confidence_band=band,
            score=score,
            raw_score=float(top.raw_score or 0.0),
            query=query,
            candidates=(),
            method="trigram",
            matched="",
        )

    candidates = tuple(hits[:top_n])
    return ResolveResult(
        symbol=top.symbol,
        legacy_confidence="exact" if band == "exact" else "fuzzy",
        confidence_band=band,
        score=score,
        raw_score=float(top.raw_score or score),
        query=query,
        candidates=candidates,
        method="trigram",
        matched=top.matched,
    )


def _empty_result(query: str) -> ResolveResult:
    return ResolveResult(
        symbol=None,
        legacy_confidence="none",
        confidence_band="none",
        score=0.0,
        raw_score=0.0,
        query=query,
        candidates=(),
        method="none",
        matched="",
    )


def _finalize(result: ResolveResult, started: float, *, fallback_reason: str) -> ResolveResult:
    latency_ms = (time.perf_counter() - started) * 1000.0
    _emit_telemetry(result, latency_ms=latency_ms, fallback_reason=fallback_reason)
    return result


def _normalized_aliases(alias_map: dict[str, str]) -> dict[str, tuple[str, str]]:
    normalized: dict[str, tuple[str, str]] = {}
    for raw_name, raw_symbol in (alias_map or {}).items():
        symbol = str(raw_symbol or "").strip().upper()
        if not symbol:
            continue
        key = _lookup_key(raw_name)
        if key:
            normalized.setdefault(key, (str(raw_name).strip().upper(), symbol))
        symbol_key = _lookup_key(symbol)
        if symbol_key:
            normalized.setdefault(symbol_key, (symbol, symbol))
    return normalized


def _lookup_key(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _tokens(value: str) -> list[str]:
    return re.sub(r"[^A-Z0-9 ]", " ", str(value or "").upper()).split()


def _is_context_phrase(tokens: list[str]) -> bool:
    if len(tokens) <= 1:
        return False
    if all(tok in _CONTEXT_TOKENS or tok in alias_source._GENERIC_NAME_TOKENS for tok in tokens):
        return True
    return bool(set(tokens) & _CONTEXT_TOKENS) and not any(len(tok) >= 4 for tok in tokens if tok not in _CONTEXT_TOKENS)
