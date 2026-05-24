"""Typed contracts for the unified Agent Adda router."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


RouteType = Literal[
    "direct_tool_plan",
    "contextual_answer",
    "clarification",
    "compound_plan",
    "fallback_llm",
    "blocked_ungrounded",
]
Confidence = Literal["low", "medium", "high"]

ROUTE_TYPES = {
    "direct_tool_plan",
    "contextual_answer",
    "clarification",
    "compound_plan",
    "fallback_llm",
    "blocked_ungrounded",
}
CONFIDENCE_VALUES = {"low", "medium", "high"}


@dataclass(frozen=True)
class ToolCallSpec:
    tool: str
    args: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.tool:
            raise ValueError("tool must be a non-empty string")
        object.__setattr__(self, "args", dict(self.args or {}))

    def to_tuple(self) -> tuple[str, dict[str, Any]]:
        return self.tool, dict(self.args)

    def to_dict(self) -> dict[str, Any]:
        return {"tool": self.tool, "args": dict(self.args)}


@dataclass(frozen=True)
class EvidenceRequirement:
    name: str
    required_tools: tuple[str, ...] = ()
    optional: bool = False

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("evidence requirement name must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "required_tools": list(self.required_tools),
            "optional": self.optional,
        }


@dataclass(frozen=True)
class ContextBinding:
    binding_type: str = "none"
    symbols: tuple[str, ...] = ()
    indices: tuple[str, ...] = ()
    sectors: tuple[str, ...] = ()
    report_paths: tuple[str, ...] = ()
    workflow_id: str = ""
    freshness: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "binding_type": self.binding_type,
            "symbols": list(self.symbols),
            "indices": list(self.indices),
            "sectors": list(self.sectors),
            "report_paths": list(self.report_paths),
            "workflow_id": self.workflow_id,
            "freshness": self.freshness,
        }


@dataclass(frozen=True)
class NextOption:
    label: str
    text: str
    bound_action: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.label:
            raise ValueError("next option label must be non-empty")
        if not self.text:
            raise ValueError("next option text must be non-empty")
        object.__setattr__(self, "bound_action", dict(self.bound_action or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "text": self.text,
            "bound_action": dict(self.bound_action),
        }


@dataclass(frozen=True)
class SourcePolicy:
    required_freshness: str = ""
    allow_stale: bool = True
    required_sources: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "required_freshness": self.required_freshness,
            "allow_stale": self.allow_stale,
            "required_sources": list(self.required_sources),
        }


@dataclass(frozen=True)
class RouteReasoningSummary:
    pot: tuple[str, ...] = ()
    selected_branch: str = ""
    rejected_branches: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "pot": list(self.pot),
            "selected_branch": self.selected_branch,
            "rejected_branches": list(self.rejected_branches),
        }


@dataclass(frozen=True)
class RouteValidation:
    ok: bool
    errors: tuple[str, ...] = ()
    checked_tools: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": list(self.errors),
            "checked_tools": list(self.checked_tools),
        }


@dataclass(frozen=True)
class RouteDecision:
    decision_id: str
    intent: str
    route_type: RouteType
    confidence: Confidence
    user_is_asking: str
    context_binding: ContextBinding
    evidence_requirements: tuple[EvidenceRequirement, ...] = ()
    tool_plan: tuple[ToolCallSpec, ...] = ()
    next_options: tuple[NextOption, ...] = ()
    source_policy: SourcePolicy = field(default_factory=SourcePolicy)
    reasoning_summary: RouteReasoningSummary = field(default_factory=RouteReasoningSummary)
    validation: RouteValidation = field(default_factory=lambda: RouteValidation(ok=False))

    def __post_init__(self) -> None:
        _validate_route_type(self.route_type)
        _validate_confidence(self.confidence)
        if not self.decision_id:
            raise ValueError("decision_id must be non-empty")
        if not self.intent:
            raise ValueError("intent must be non-empty")

    @property
    def is_executable(self) -> bool:
        return (
            self.validation.ok
            and self.route_type in {"direct_tool_plan", "compound_plan"}
            and bool(self.tool_plan)
        )

    def tool_plan_tuples(self) -> list[tuple[str, dict[str, Any]]]:
        return [item.to_tuple() for item in self.tool_plan]

    def to_debug_trace(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "intent": self.intent,
            "route_type": self.route_type,
            "confidence": self.confidence,
            "context": self.context_binding.to_dict(),
            "tools": [item.tool for item in self.tool_plan],
            "next_options": [item.label for item in self.next_options],
            "validation": self.validation.to_dict(),
            "selected_branch": self.reasoning_summary.selected_branch,
            "rejected_branches": list(self.reasoning_summary.rejected_branches),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "intent": self.intent,
            "route_type": self.route_type,
            "confidence": self.confidence,
            "user_is_asking": self.user_is_asking,
            "context_binding": self.context_binding.to_dict(),
            "evidence_requirements": [item.to_dict() for item in self.evidence_requirements],
            "tool_plan": [item.to_dict() for item in self.tool_plan],
            "next_options": [item.to_dict() for item in self.next_options],
            "source_policy": self.source_policy.to_dict(),
            "reasoning_summary": self.reasoning_summary.to_dict(),
            "validation": self.validation.to_dict(),
        }


@dataclass(frozen=True)
class RouteCandidate:
    provider: str
    intent: str
    route_type: RouteType
    confidence: Confidence
    score: float
    reasons: tuple[str, ...] = ()
    tool_plan: tuple[ToolCallSpec, ...] = ()
    next_options: tuple[NextOption, ...] = ()
    evidence_requirements: tuple[EvidenceRequirement, ...] = ()
    source_policy: SourcePolicy = field(default_factory=SourcePolicy)

    def __post_init__(self) -> None:
        _validate_route_type(self.route_type)
        _validate_confidence(self.confidence)
        if not self.provider:
            raise ValueError("provider must be non-empty")
        if not self.intent:
            raise ValueError("intent must be non-empty")
        if not isinstance(self.score, int | float) or not 0.0 <= self.score <= 1.0:
            raise ValueError("score must be between 0.0 and 1.0")

    def to_decision(
        self,
        *,
        decision_id: str,
        user_is_asking: str,
        context_binding: ContextBinding,
        validation: RouteValidation,
        rejected_branches: tuple[str, ...] = (),
    ) -> RouteDecision:
        return RouteDecision(
            decision_id=decision_id,
            intent=self.intent,
            route_type=self.route_type,
            confidence=self.confidence,
            user_is_asking=user_is_asking,
            context_binding=context_binding,
            evidence_requirements=self.evidence_requirements,
            tool_plan=self.tool_plan,
            next_options=self.next_options,
            source_policy=self.source_policy,
            reasoning_summary=RouteReasoningSummary(
                pot=self.reasons,
                selected_branch=self.provider,
                rejected_branches=rejected_branches,
            ),
            validation=validation,
        )


def _validate_route_type(value: str) -> None:
    if value not in ROUTE_TYPES:
        raise ValueError(f"route_type must be one of {sorted(ROUTE_TYPES)}")


def _validate_confidence(value: str) -> None:
    if value not in CONFIDENCE_VALUES:
        raise ValueError(f"confidence must be one of {sorted(CONFIDENCE_VALUES)}")
