"""Evidence scoring and contradiction checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EvidenceScore:
    usable: int
    missing: int
    errors: list[str]
    freshness: str
    contradictions: list[str]


def evaluate_evidence(tool_results: list[dict[str, Any]]) -> EvidenceScore:
    usable = 0
    errors: list[str] = []
    stale = False
    for item in tool_results or []:
        result = item.get("result") if isinstance(item, dict) else None
        tool = item.get("tool", "tool") if isinstance(item, dict) else "tool"
        if not isinstance(result, dict) or result.get("error"):
            errors.append(f"{tool}: {result.get('error', 'no result') if isinstance(result, dict) else 'no result'}")
            continue
        usable += 1
        source = str(result.get("source", "")).lower()
        if "eod" in source or "fallback" in source:
            stale = True
    missing = max(0, len(tool_results or []) - usable)
    return EvidenceScore(
        usable=usable,
        missing=missing,
        errors=errors,
        freshness="fallback_or_eod" if stale else "live_or_current",
        contradictions=[],
    )
