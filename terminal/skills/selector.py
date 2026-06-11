from __future__ import annotations

import re

from .schema import SkillSelection


_METRIC_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("eps", ("eps", "earnings per share")),
    ("roce", ("roce", "return on capital employed")),
    ("margin", ("margin", "opm", "operating margin", "ebitda margin")),
    ("debt", ("debt", "borrowings", "leverage")),
    ("cashflow", ("cash flow", "cashflow", "cfo", "operating cash")),
)


def _detect_metric(text: str) -> str | None:
    lowered = text.lower()
    for metric, aliases in _METRIC_PATTERNS:
        if any(alias in lowered for alias in aliases):
            return metric
    return None


def _detect_symbol(text: str) -> str | None:
    patterns = (
        r"\b(?:of|for|in)\s+([A-Z][A-Z0-9&.-]{1,14})\b",
        r"\b([A-Z][A-Z0-9&.-]{1,14})\s+(?:eps|roce|margin|debt|cash\s*flow)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).rstrip("?.!,").upper()
    return None


def _has_driver_intent(text: str) -> bool:
    lowered = text.lower()
    phrase_patterns = (
        r"\bwhy\b",
        r"\breason(?:s)?\b",
        r"\bgoing\s+down\b",
        r"\bfall(?:ing|en|s)?\b",
        r"\brising\b",
        r"\bweak(?:er|ness)?\b",
        r"\bhigh\b",
        r"\blow\b",
    )
    return any(re.search(pattern, lowered) for pattern in phrase_patterns)


def select_skills(text: str) -> list[SkillSelection]:
    query = str(text or "").strip()
    if not query or query.startswith("/"):
        return []

    metric = _detect_metric(query)
    if not metric:
        return []

    lowered = query.lower()
    if not _has_driver_intent(lowered):
        return []

    symbol = _detect_symbol(query)
    if not symbol:
        return []

    return [
        SkillSelection(
            skill_id="fundamental_driver_diagnosis",
            confidence=0.88,
            reason=f"Detected {metric.upper()} driver question for {symbol}",
            symbol=symbol,
            metric=metric,
        )
    ]
