"""Typed data models for visual scan evidence and reports."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


class PatternStatus:
    CONFIRMED = "confirmed"
    CANDIDATE = "candidate"
    ABSENT = "absent"
    INSUFFICIENT_DATA = "insufficient_data"


PatternStatusValue = Literal["confirmed", "candidate", "absent", "insufficient_data"]


@dataclass
class Zones:
    pivot: float | None = None
    support: float | None = None
    invalidation: float | None = None
    target_1: float | None = None
    target_2: float | None = None

    def to_dict(self) -> dict[str, float | None]:
        return asdict(self)


@dataclass
class PatternEvidence:
    pattern: str
    status: PatternStatusValue
    confidence: float
    evidence: list[str] = field(default_factory=list)
    zones: Zones = field(default_factory=Zones)
    caveats: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["zones"] = self.zones.to_dict()
        return payload


@dataclass
class ChartAnnotation:
    kind: str
    label: str
    price: float | None = None
    start: str | None = None
    end: str | None = None
    color: str = "#0f766e"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VisualScanVerdict:
    stance: str
    score: float
    confidence: str
    trigger: str
    invalidation: str
    targets: list[str] = field(default_factory=list)
    summary: str = ""
    caveats: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VisualScanPack:
    run_id: str
    symbol: str
    as_of: str
    verdict: VisualScanVerdict
    patterns: list[PatternEvidence] = field(default_factory=list)
    annotations: list[ChartAnnotation] = field(default_factory=list)
    chart_paths: dict[str, str] = field(default_factory=dict)
    tradingview: dict[str, Any] = field(default_factory=dict)
    source_trail: dict[str, Any] = field(default_factory=dict)
    missing_evidence: list[str] = field(default_factory=list)
    raw_metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "symbol": self.symbol,
            "as_of": self.as_of,
            "verdict": self.verdict.to_dict(),
            "patterns": [pattern.to_dict() for pattern in self.patterns],
            "annotations": [annotation.to_dict() for annotation in self.annotations],
            "chart_paths": dict(self.chart_paths),
            "tradingview": dict(self.tradingview),
            "source_trail": dict(self.source_trail),
            "missing_evidence": list(self.missing_evidence),
            "raw_metrics": dict(self.raw_metrics),
        }
