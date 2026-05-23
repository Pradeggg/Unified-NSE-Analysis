"""Iterative Strategy Council orchestration."""

from __future__ import annotations

import pandas as pd

from backtesting.engine import compute_stage2_features
from backtesting.strategy_council.critics_advanced import build_advanced_critics
from backtesting.strategy_council.dashboard_generator import write_dashboard
from backtesting.strategy_council.evidence_enrichment import enrich_with_market_signals
from backtesting.strategy_council.llm import (
    RuleBasedDataLeakageCritic,
    RuleBasedRiskCritic,
    RuleBasedStrategist,
)
from backtesting.strategy_council.runner import run_strategy_spec_on_split
from backtesting.strategy_council.strategy_generator import CompositeStrategist
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


DEFAULT_BENCHMARK_INDEX = "Nifty 50"


def _load_default_benchmark_closes(eod_data: pd.DataFrame) -> pd.Series | None:
    """Best-effort load of Nifty 50 closes aligned to the symbol's date range.

    Returns ``None`` if Postgres or the benchmark series is unavailable so the
    enrichment step degrades gracefully.
    """
    import os

    try:
        import psycopg2  # type: ignore
    except Exception:
        return None

    try:
        date_col = "date" if "date" in eod_data.columns else None
        start = eod_data[date_col].min() if date_col else None
        end = eod_data[date_col].max() if date_col else None
        dsn = os.environ.get("AGENT_ADDA_PG_DSN") or "dbname=nse_market user=nse_admin host=/tmp"
        with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
            if start is not None and end is not None:
                cur.execute(
                    """
                    SELECT trade_date, close FROM market.index_eod
                    WHERE index_symbol = %s AND trade_date BETWEEN %s AND %s
                    ORDER BY trade_date
                    """,
                    (DEFAULT_BENCHMARK_INDEX, start, end),
                )
            else:
                cur.execute(
                    """
                    SELECT trade_date, close FROM market.index_eod
                    WHERE index_symbol = %s ORDER BY trade_date
                    """,
                    (DEFAULT_BENCHMARK_INDEX,),
                )
            rows = cur.fetchall()
        if not rows:
            return None
        df = pd.DataFrame(rows, columns=["date", "close"])
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        return df["close"].dropna().reset_index(drop=True)
    except Exception:
        return None


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


def _matching_validation_result(locked: StrategySpec | None, validation_results: tuple):
    if locked is None:
        return None
    for result in validation_results:
        if result.strategy_id == locked.strategy_id and result.horizon_days == locked.horizon_days:
            return result
    return None


def _recommend(
    *,
    locked: StrategySpec | None,
    validation_results: tuple,
    test_results: tuple,
    critiques: tuple[Critique, ...],
) -> tuple[Recommendation, str]:
    validation = _matching_validation_result(locked, validation_results)
    if validation is None:
        return "NO_TRADE", "No matching validation result for the locked strategy."
    validation_ret = validation.metrics.get("total_return_pct")
    if not isinstance(validation_ret, (int, float)):
        return "WAIT", "Locked strategy has no numeric validation return."
    if validation.trade_count == 0:
        return "WAIT", "Locked strategy had zero validation trades; positive one-shot test is not enough."
    if validation_ret <= 0:
        return "WAIT", "Locked strategy validation return was not positive; positive one-shot test is not enough."
    rejected = [critique.critic for critique in critiques if str(critique.verdict).lower() == "reject"]
    if rejected:
        return "WAIT", f"Blocking critic verdicts remain: {', '.join(rejected)}."
    if not test_results:
        return "NO_TRADE", "No final one-shot test result was produced."
    best = max(test_results, key=_score_result)
    ret = best.metrics.get("total_return_pct")
    if not isinstance(ret, (int, float)) or best.trade_count == 0:
        return "NO_TRADE", "Final one-shot test had no numeric return or no trades."
    if ret > 2:
        return "TRADE_RESEARCH", "Validation was positive and final one-shot test cleared the research threshold."
    return "WAIT", "Validation was positive, but final one-shot test did not clear the research threshold."


def run_strategy_council(
    eod_data: pd.DataFrame,
    *,
    evidence: EvidencePack,
    config: CouncilConfig,
    strategist=None,
    critics=None,
) -> CouncilResult:
    if strategist is None:
        base = RuleBasedStrategist()
        if config.use_rule_composition and "rule_composed" in config.allowed_strategies:
            strategist = CompositeStrategist(
                inner=base,
                llm_ratio=config.rule_llm_ratio,
                method=config.rule_generation_method,
            )
        else:
            strategist = base
    if config.include_enrichment:
        try:
            benchmark = _load_default_benchmark_closes(eod_data)
            enrich_with_market_signals(evidence, eod_data, benchmark=benchmark)
        except Exception:
            pass
    if critics is None:
        base_critics: tuple = (RuleBasedDataLeakageCritic(), RuleBasedRiskCritic())
        if config.use_advanced_critics:
            base_critics = base_critics + build_advanced_critics(
                evidence=evidence,
                max_drawdown_pct=config.max_drawdown_threshold_pct,
                correlation_threshold=config.train_val_corr_threshold,
                beta_threshold=config.beta_threshold,
            )
        critics = base_critics
    try:
        eod_data = compute_stage2_features(eod_data)
    except Exception:
        pass

    min_bars_required = getattr(config, "min_bars_required", 300)
    if len(eod_data) < min_bars_required:
        rationale = (
            f"Insufficient price history: only {len(eod_data)} EOD bars available "
            f"(need >= {min_bars_required} for reliable train/validation/test splits). "
            "Backfill via `/data-coverage <INDEX> --backfill` or wait for more "
            "trading history before running the council on this symbol. "
            "Research-only output, not investment advice."
        )
        return CouncilResult(
            config=config,
            evidence=evidence,
            iterations=(),
            locked_strategy=None,
            test_results=(),
            recommendation="NO_TRADE",
            rationale=rationale,
        )

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

    final_critiques = iterations[-1].critiques if iterations else ()
    recommendation, gate_reason = _recommend(
        locked=locked,
        validation_results=last_validation_results,
        test_results=test_results,
        critiques=final_critiques,
    )
    rationale = (
        f"Recommendation gate: {gate_reason} "
        "Final recommendation is based on validation-selected strategy and one-shot test results. "
        "This is research-only output, not investment advice."
    )
    result = CouncilResult(
        config=config,
        evidence=evidence,
        iterations=tuple(iterations),
        locked_strategy=locked,
        test_results=test_results,
        recommendation=recommendation,
        rationale=rationale,
    )
    if config.dashboard_output_dir:
        try:
            dashboard_path = write_dashboard(result, config.dashboard_output_dir)
            result = CouncilResult(
                config=result.config,
                evidence=result.evidence,
                iterations=result.iterations,
                locked_strategy=result.locked_strategy,
                test_results=result.test_results,
                recommendation=result.recommendation,
                rationale=result.rationale,
                report_path=result.report_path,
                dashboard_path=str(dashboard_path),
            )
        except Exception:
            pass
    return result
