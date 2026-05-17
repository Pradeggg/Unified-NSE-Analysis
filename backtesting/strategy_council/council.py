"""Iterative Strategy Council orchestration."""

from __future__ import annotations

import pandas as pd

from backtesting.engine import compute_stage2_features
from backtesting.strategy_council.llm import (
    RuleBasedDataLeakageCritic,
    RuleBasedRiskCritic,
    RuleBasedStrategist,
)
from backtesting.strategy_council.runner import run_strategy_spec_on_split
from backtesting.strategy_council.splits import build_time_splits
from backtesting.strategy_council.types import (
    CouncilConfig,
    CouncilIteration,
    CouncilResult,
    Critique,
    EvidencePack,
    Recommendation,
    StrategySpec,
)


def _score_result(result) -> float:
    ret = result.metrics.get("total_return_pct")
    trades = result.trade_count
    if not isinstance(ret, (int, float)):
        return -999.0
    trade_penalty = 10.0 if trades == 0 else 0.0
    return float(ret) - trade_penalty


def _select_best(
    candidates: tuple[StrategySpec, ...],
    validation_results: tuple,
) -> StrategySpec | None:
    if not candidates or not validation_results:
        return candidates[0] if candidates else None
    best_result = max(validation_results, key=_score_result)
    for candidate in candidates:
        if candidate.strategy_id == best_result.strategy_id and candidate.horizon_days == best_result.horizon_days:
            return candidate
    return candidates[0]


def _recommend(test_results: tuple) -> Recommendation:
    if not test_results:
        return "NO_TRADE"
    best = max(test_results, key=_score_result)
    ret = best.metrics.get("total_return_pct")
    if not isinstance(ret, (int, float)) or best.trade_count == 0:
        return "NO_TRADE"
    if ret > 2:
        return "TRADE_RESEARCH"
    return "WAIT"


def run_strategy_council(
    eod_data: pd.DataFrame,
    *,
    evidence: EvidencePack,
    config: CouncilConfig,
    strategist=None,
    critics=None,
) -> CouncilResult:
    strategist = strategist or RuleBasedStrategist()
    critics = critics or (RuleBasedDataLeakageCritic(), RuleBasedRiskCritic())
    try:
        eod_data = compute_stage2_features(eod_data)
    except Exception:
        pass
    splits = build_time_splits(
        eod_data,
        validation_from=config.validation_from,
        test_from=config.test_from,
    )

    iterations: list[CouncilIteration] = []
    prior_feedback: tuple[Critique, ...] = ()
    last_candidates: tuple[StrategySpec, ...] = ()
    last_validation_results: tuple = ()

    for idx in range(1, max(config.iterations, 0) + 1):
        candidates = strategist.propose(evidence=evidence, config=config, prior_feedback=prior_feedback)
        train_results = tuple(
            run_strategy_spec_on_split(splits["train"], spec, split_name="train", initial_capital=config.initial_capital)
            for spec in candidates
        )
        validation_results = tuple(
            run_strategy_spec_on_split(splits["validation"], spec, split_name="validation", initial_capital=config.initial_capital)
            for spec in candidates
        )
        critiques = tuple(
            critic.critique(
                candidates=candidates,
                train_results=train_results,
                validation_results=validation_results,
            )
            for critic in critics
        )
        revision = "; ".join(
            change for critique in critiques for change in critique.required_changes
        ) or "No forced revision; continue with strongest validation candidate."
        iterations.append(
            CouncilIteration(
                index=idx,
                candidates=candidates,
                train_results=train_results,
                validation_results=validation_results,
                critiques=critiques,
                strategist_revision=revision,
            )
        )
        prior_feedback = critiques
        last_candidates = candidates
        last_validation_results = validation_results

    locked = _select_best(last_candidates, last_validation_results)
    test_results = ()
    if locked is not None:
        test_results = (
            run_strategy_spec_on_split(
                splits["test"],
                locked,
                split_name="test",
                initial_capital=config.initial_capital,
            ),
        )

    recommendation = _recommend(test_results)
    rationale = (
        "Final recommendation is based on validation-selected strategy and one-shot test results. "
        "This is research-only output, not investment advice."
    )
    return CouncilResult(
        config=config,
        evidence=evidence,
        iterations=tuple(iterations),
        locked_strategy=locked,
        test_results=test_results,
        recommendation=recommendation,
        rationale=rationale,
    )
