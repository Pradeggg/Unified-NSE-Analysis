"""Shared contracts for the Strategy Council simulation loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


Recommendation = Literal["TRADE_RESEARCH", "WAIT", "NO_TRADE"]


@dataclass(frozen=True)
class CouncilConfig:
    symbol: str
    horizons: tuple[int, ...] = (5, 10, 20)
    iterations: int = 3
    max_candidates: int = 5
    initial_capital: float = 100000.0
    from_date: str | None = None
    validation_from: str | None = None
    test_from: str | None = None
    allowed_strategies: tuple[str, ...] = (
        "stage2",
        "supertrend_continuation",
        "rsi_pullback_stage2",
        "52w_high",
        "vcp",
        "rule_composed",
    )
    recommendation_threshold: str = "validation_then_test"
    use_rule_composition: bool = True
    rule_llm_ratio: float = 0.4
    rule_generation_method: str = "sampled"


@dataclass
class EvidencePack:
    symbol: str
    as_of: str
    technical: dict[str, Any] = field(default_factory=dict)
    fundamental: dict[str, Any] = field(default_factory=dict)
    market: dict[str, Any] = field(default_factory=dict)
    news: list[dict[str, Any]] = field(default_factory=list)
    freshness: dict[str, str] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    source_trail: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class StrategySpec:
    strategy_id: str
    horizon_days: int
    entry_rules: tuple[str, ...]
    exit_rules: tuple[str, ...]
    risk_rules: tuple[str, ...]
    thesis: str
    params: dict[str, Any] = field(default_factory=dict)
    status: str = "candidate"
    origin: str = "unknown"


@dataclass(frozen=True)
class BacktestSliceResult:
    split: str
    strategy_id: str
    horizon_days: int
    metrics: dict[str, Any]
    trade_count: int


@dataclass(frozen=True)
class Critique:
    critic: str
    verdict: str
    issues: tuple[str, ...] = ()
    required_changes: tuple[str, ...] = ()
    confidence_delta: float = 0.0


@dataclass(frozen=True)
class CouncilIteration:
    index: int
    candidates: tuple[StrategySpec, ...]
    train_results: tuple[BacktestSliceResult, ...]
    validation_results: tuple[BacktestSliceResult, ...]
    critiques: tuple[Critique, ...]
    strategist_revision: str


@dataclass(frozen=True)
class CouncilResult:
    config: CouncilConfig
    evidence: EvidencePack
    iterations: tuple[CouncilIteration, ...]
    locked_strategy: StrategySpec | None
    test_results: tuple[BacktestSliceResult, ...]
    recommendation: Recommendation
    rationale: str
    report_path: str | None = None
