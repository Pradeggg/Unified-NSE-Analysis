"""Unified router contracts."""

from .context import (
    ActiveReport,
    ActiveWorkflow,
    ContextPack,
    PendingOption,
    RecentTurn,
    WorkflowStep,
)
from .providers import (
    ContextualFollowupProvider,
    DEFAULT_PROVIDERS,
    DirectIntentProvider,
    EntityTopicProvider,
    MarketSituationProvider,
    PendingOptionProvider,
    ReportProvider,
    RouteProvider,
    VisualScanProvider,
)
from .router import UnifiedRouter
from .schema import (
    ContextBinding,
    EvidenceRequirement,
    NextOption,
    RouteCandidate,
    RouteDecision,
    RouteReasoningSummary,
    RouteValidation,
    SourcePolicy,
    ToolCallSpec,
)

__all__ = [
    "ActiveReport",
    "ActiveWorkflow",
    "ContextBinding",
    "ContextPack",
    "ContextualFollowupProvider",
    "DEFAULT_PROVIDERS",
    "DirectIntentProvider",
    "EntityTopicProvider",
    "EvidenceRequirement",
    "MarketSituationProvider",
    "NextOption",
    "PendingOption",
    "PendingOptionProvider",
    "RecentTurn",
    "ReportProvider",
    "RouteCandidate",
    "RouteDecision",
    "RouteProvider",
    "RouteReasoningSummary",
    "RouteValidation",
    "SourcePolicy",
    "ToolCallSpec",
    "UnifiedRouter",
    "VisualScanProvider",
    "WorkflowStep",
]
