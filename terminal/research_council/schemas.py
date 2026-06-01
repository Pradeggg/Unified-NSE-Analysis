"""Typed contracts for Research Council state and artifacts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields, is_dataclass
from datetime import date, datetime
from types import UnionType
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints


Stage = Literal[
    "intake",
    "route",
    "data_steward",
    "market_state",
    "specialist_pass",
    "branch_deliberation",
    "plan_build",
    "plan_execute",
    "plan_review",
    "critic_review",
    "revision",
    "synthesis",
    "render_html",
    "persistence",
    "abort_stale_data",
    "abort_budget",
    "escalate_human",
    "commit_no_trade",
]

CouncilMode = Literal[
    "market_council",
    "sector_opportunity",
    "stock_deep_dive",
    "strategy_build",
    "intraday_tactical",
    "report_review",
]

FinalLabel = Literal[
    "WATCHLIST",
    "RESEARCH_LONG",
    "WAIT_FOR_CONFIRMATION",
    "AVOID_FRESH_ENTRY",
    "REVIEW_MANUALLY",
    "NO_TRADE",
    "HEDGE_REQUIRED",
]

PlanStepStatus = Literal[
    "pending",
    "running",
    "success",
    "failed_retryable",
    "failed_terminal",
    "deliberate_skip",
]

CriticSeverity = Literal["info", "warn", "block"]


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {k: _jsonable(v) for k, v in asdict(value).items()}
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    return value


def _is_optional(annotation: Any) -> bool:
    return get_origin(annotation) in {Union, UnionType} and type(None) in get_args(annotation)


def _coerce(annotation: Any, value: Any) -> Any:
    if value is None:
        return None
    origin = get_origin(annotation)
    args = get_args(annotation)
    if _is_optional(annotation):
        non_none = [arg for arg in args if arg is not type(None)]
        return _coerce(non_none[0], value) if non_none else value
    if annotation is datetime:
        return value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if annotation is date:
        return value if isinstance(value, date) else date.fromisoformat(value)
    if origin is list and args:
        return [_coerce(args[0], item) for item in value]
    if origin is dict and len(args) == 2:
        return {_coerce(args[0], key): _coerce(args[1], item) for key, item in value.items()}
    if isinstance(annotation, type) and is_dataclass(annotation) and isinstance(value, dict):
        return annotation.from_dict(value)
    return value


class JsonDataclass:
    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]):
        kwargs = {}
        hints = get_type_hints(cls)
        for f in fields(cls):
            if f.name in data:
                kwargs[f.name] = _coerce(hints.get(f.name, f.type), data[f.name])
        return cls(**kwargs)


@dataclass(frozen=True)
class SourceTrailEntry(JsonDataclass):
    source: str
    rows: int | None = None
    latest_date: str | None = None
    freshness: str | None = None
    fallback: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MissingEvidence(JsonDataclass):
    scope: str
    subject: str
    field: str
    severity: CriticSeverity = "warn"
    reason: str | None = None


@dataclass(frozen=True)
class EvidencePack(JsonDataclass):
    pack_id: str
    as_of: date
    mode: CouncilMode
    universe_filter: str | None = None
    symbols: list[str] = field(default_factory=list)
    sections: dict[str, Any] = field(default_factory=dict)
    source_trail: list[SourceTrailEntry] = field(default_factory=list)
    missing_evidence: list[MissingEvidence] = field(default_factory=list)


@dataclass(frozen=True)
class StewardVerdict(JsonDataclass):
    as_of: date
    data_status: Literal["usable", "degraded", "blocked"]
    blocking_gaps: list[str] = field(default_factory=list)
    non_blocking_gaps: list[str] = field(default_factory=list)
    universe: dict[str, Any] = field(default_factory=dict)
    checks: list[dict[str, Any]] = field(default_factory=list)
    remediation: str | None = None


@dataclass(frozen=True)
class AgentFinding(JsonDataclass):
    finding_id: str
    agent: str
    stance: str
    confidence: float
    thesis: str
    evidence: list[str] = field(default_factory=list)
    candidates: list[str] = field(default_factory=list)
    rejects: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    required_next_steps: list[str] = field(default_factory=list)
    veto_reason: str | None = None
    body: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BranchSummary(JsonDataclass):
    summary_id: str
    branch: str
    stance: str
    supporting_agents: list[str] = field(default_factory=list)
    dissenting_agents: list[str] = field(default_factory=list)
    candidates: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    requires_quant: bool = False
    body: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolCall(JsonDataclass):
    tool_name: str
    args: dict[str, Any] = field(default_factory=dict)
    timeout_s: float = 60.0


@dataclass(frozen=True)
class SuccessCriterion(JsonDataclass):
    metric: str
    operator: Literal[">", ">=", "<", "<=", "==", "!=", "exists", "in"]
    value: Any = None
    source: str | None = None
    required: bool = True


@dataclass(frozen=True)
class PlanStep(JsonDataclass):
    step_id: str
    sequence: int
    question: str
    required_evidence: list[str] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    success_criteria: list[SuccessCriterion] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    status: PlanStepStatus = "pending"
    result_id: str | None = None


@dataclass(frozen=True)
class Plan(JsonDataclass):
    plan_id: str
    run_id: str
    iteration: int
    central_question: str
    steps: list[PlanStep] = field(default_factory=list)
    created_at: datetime | None = None


@dataclass(frozen=True)
class ExecutionResult(JsonDataclass):
    result_id: str
    step_id: str
    status: Literal["success", "failed_retryable", "failed_terminal", "deliberate_skip"]
    outputs: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    elapsed_ms: int | None = None


@dataclass(frozen=True)
class PlanReview(JsonDataclass):
    plan_id: str
    advance: bool
    step_verdicts: list[dict[str, Any]] = field(default_factory=list)
    new_questions: list[str] = field(default_factory=list)
    new_plan_steps: list[PlanStep] = field(default_factory=list)
    advance_rationale: str = ""


@dataclass(frozen=True)
class CriticFinding(JsonDataclass):
    finding_id: str
    severity: CriticSeverity
    target: dict[str, str]
    description: str
    recommendation: str


@dataclass(frozen=True)
class CriticReview(JsonDataclass):
    review_id: str
    critic: str
    run_id: str
    iteration: int
    findings: list[CriticFinding] = field(default_factory=list)
    severity_max: CriticSeverity = "info"
    summary: str = ""


@dataclass(frozen=True)
class RevisionResult(JsonDataclass):
    iteration: int
    converged: bool
    notes: list[str] = field(default_factory=list)
    unresolved_blocks: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Decision(JsonDataclass):
    final_label: FinalLabel
    confidence: float
    rationale: str
    candidates: list[dict[str, Any]] = field(default_factory=list)
    dissent_log: list[str] = field(default_factory=list)
    missing_evidence: list[MissingEvidence] = field(default_factory=list)


@dataclass(frozen=True)
class StrategyBuildRequest(JsonDataclass):
    source_branch: str
    strategy_family: str
    hypothesis: str
    required_features: list[str] = field(default_factory=list)
    allowed_horizons: list[int] = field(default_factory=lambda: [5, 10, 20])
    split_policy: str = "train_validation_test_time_ordered"


@dataclass(frozen=True)
class StrategyBuildResult(JsonDataclass):
    request: StrategyBuildRequest
    verdict: Literal["SUPPORTED", "REFUTED", "AMBIGUOUS", "UNTESTABLE"]
    metrics: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CouncilState(JsonDataclass):
    run_id: str
    session_id: str
    created_at: datetime
    mode: CouncilMode
    stage: Stage
    objective: str
    horizon: str
    risk_budget: str
    universe_filter: str
    symbols: list[str] = field(default_factory=list)
    route_decision: dict[str, Any] | None = None
    steward_verdict: StewardVerdict | None = None
    evidence_pack_id: str | None = None
    evidence_pack: EvidencePack | None = None
    specialist_findings: dict[str, AgentFinding] = field(default_factory=dict)
    branch_summaries: list[BranchSummary] = field(default_factory=list)
    plans: list[Plan] = field(default_factory=list)
    execution_results: dict[str, dict[str, ExecutionResult]] = field(default_factory=dict)
    plan_reviews: list[PlanReview] = field(default_factory=list)
    critic_reviews: list[list[CriticReview]] = field(default_factory=list)
    revision_history: list[RevisionResult] = field(default_factory=list)
    decision: Decision | None = None
    html_path: str | None = None
    flags: dict[str, Any] = field(default_factory=dict)
    budgets: dict[str, Any] = field(default_factory=lambda: {"wall_clock_s": 480, "tokens": 200_000})
    events: list[dict[str, Any]] = field(default_factory=list)
