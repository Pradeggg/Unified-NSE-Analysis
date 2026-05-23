"""Contracts for hybrid NSE symbol resolution.

This module is intentionally dependency-light. It defines the rich resolver
result used by the new symbol-search package plus a legacy projection for
existing `terminal.tools.resolve_symbol` callers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


LEGACY_CONFIDENCE_VALUES = {"exact", "near-match", "fuzzy", "none"}
CONFIDENCE_BANDS = {"exact", "high", "medium", "low", "none"}
RESOLUTION_METHODS = {"dict", "trigram", "embedding", "hybrid", "live_api", "none"}


@dataclass(frozen=True)
class ResolveCandidate:
    symbol: str
    score: float
    raw_score: float
    methods: tuple[str, ...] = field(default_factory=tuple)
    matched: str = ""

    def __post_init__(self) -> None:
        _validate_symbol(self.symbol, field_name="symbol")
        _validate_score(self.score, field_name="score")
        _validate_non_negative(self.raw_score, field_name="raw_score")
        for method in self.methods:
            if method not in RESOLUTION_METHODS:
                raise ValueError(f"method must be one of {sorted(RESOLUTION_METHODS)}")

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "symbol": self.symbol,
            "score": self.score,
            "raw_score": self.raw_score,
            "methods": list(self.methods),
        }
        if self.matched:
            payload["matched"] = self.matched
        return payload


@dataclass(frozen=True)
class ResolveResult:
    symbol: str | None
    legacy_confidence: str
    confidence_band: str
    score: float
    raw_score: float
    query: str
    candidates: tuple[ResolveCandidate, ...] = field(default_factory=tuple)
    method: str = "none"
    matched: str = ""
    needs_clarification: bool | None = None

    def __post_init__(self) -> None:
        if self.symbol is not None:
            _validate_symbol(self.symbol, field_name="symbol")
        if self.legacy_confidence not in LEGACY_CONFIDENCE_VALUES:
            raise ValueError(
                f"legacy_confidence must be one of {sorted(LEGACY_CONFIDENCE_VALUES)}"
            )
        if self.confidence_band not in CONFIDENCE_BANDS:
            raise ValueError(f"confidence_band must be one of {sorted(CONFIDENCE_BANDS)}")
        _validate_score(self.score, field_name="score")
        _validate_non_negative(self.raw_score, field_name="raw_score")
        if self.method not in RESOLUTION_METHODS:
            raise ValueError(f"method must be one of {sorted(RESOLUTION_METHODS)}")
        if self.needs_clarification is None:
            object.__setattr__(
                self,
                "needs_clarification",
                self.confidence_band in {"medium", "low"},
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "legacy_confidence": self.legacy_confidence,
            "confidence_band": self.confidence_band,
            "score": self.score,
            "raw_score": self.raw_score,
            "query": self.query,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "method": self.method,
            "matched": self.matched,
            "needs_clarification": bool(self.needs_clarification),
        }


def project_legacy_result(result: ResolveResult) -> dict[str, Any]:
    """Project a rich ResolveResult into the existing resolve_symbol shape."""

    payload: dict[str, Any] = {
        "symbol": result.symbol,
        "confidence": result.legacy_confidence,
        "score": result.score,
        "confidence_band": result.confidence_band,
        "query": result.query,
        "candidates": [candidate.symbol for candidate in result.candidates],
        "method": result.method,
    }
    if result.matched:
        payload["matched"] = result.matched
    return payload


def _validate_symbol(value: str, *, field_name: str) -> None:
    if not value or not isinstance(value, str):
        raise ValueError(f"{field_name} must be a non-empty string")


def _validate_score(value: float, *, field_name: str) -> None:
    if not isinstance(value, int | float) or value < 0.0 or value > 1.0:
        raise ValueError(f"{field_name} must be between 0.0 and 1.0")


def _validate_non_negative(value: float, *, field_name: str) -> None:
    if not isinstance(value, int | float) or value < 0.0:
        raise ValueError(f"{field_name} must be non-negative")
