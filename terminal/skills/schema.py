from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SkillDefinition:
    id: str
    name: str
    description: str
    triggers: tuple[str, ...]
    entities_required: tuple[str, ...] = ()
    evidence_required: tuple[str, ...] = ()
    output_contract: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkillSelection:
    skill_id: str
    confidence: float
    reason: str
    symbol: str | None = None
    metric: str | None = None
