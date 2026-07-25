from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from typing import Any

import pandas as pd


DEFAULT_STRESS_EXTRA_BPS = 15.0
DEFAULT_SEVERE_EXTRA_BPS = 30.0


@dataclass(frozen=True)
class CostSensitivityScenario:
    name: str
    total_cost_bps: float
    incremental_cost_bps: float
    return_erosion_pct: float
    adjusted_return_pct: float
    adjusted_excess_return_pct: float

    def as_dict(self) -> dict[str, float | str]:
        return asdict(self)


def evaluate_strategy_robustness(
    row: dict[str, Any],
    *,
    base_slippage_bps: float,
    base_brokerage_bps: float,
    stress_extra_bps: float = DEFAULT_STRESS_EXTRA_BPS,
    severe_extra_bps: float = DEFAULT_SEVERE_EXTRA_BPS,
) -> dict[str, Any]:
    """Evaluate a Strategy Lab leaderboard row with deterministic critic rules."""

    strategy_id = str(row.get("strategy_id") or "n/a")
    total_return_pct = _number(row.get("total_return_pct")) or 0.0
    excess_return_pct = _number(row.get("excess_return_pct")) or 0.0
    max_drawdown_pct = _number(row.get("max_drawdown_pct")) or 0.0
    profit_factor = _number(row.get("profit_factor")) or 0.0
    turnover_pct = _number(row.get("turnover_pct")) or 0.0
    cost_drag_pct = _number(row.get("cost_drag_pct")) or 0.0
    fills = _int(row.get("fills"))
    closed_trades = _int(row.get("closed_trades"))
    benchmark_observations = _int(row.get("benchmark_observation_count"), default=None)
    base_cost_bps = _number(base_slippage_bps) + _number(base_brokerage_bps)

    scenarios = {
        "base": _cost_scenario(
            "base",
            base_cost_bps=base_cost_bps,
            total_cost_bps=base_cost_bps,
            turnover_pct=turnover_pct,
            total_return_pct=total_return_pct,
            excess_return_pct=excess_return_pct,
        ),
        "stress": _cost_scenario(
            "stress",
            base_cost_bps=base_cost_bps,
            total_cost_bps=base_cost_bps + _number(stress_extra_bps),
            turnover_pct=turnover_pct,
            total_return_pct=total_return_pct,
            excess_return_pct=excess_return_pct,
        ),
        "severe": _cost_scenario(
            "severe",
            base_cost_bps=base_cost_bps,
            total_cost_bps=base_cost_bps + _number(severe_extra_bps),
            turnover_pct=turnover_pct,
            total_return_pct=total_return_pct,
            excess_return_pct=excess_return_pct,
        ),
    }
    verdict, issues, score = _critic_verdict(
        fills=fills,
        closed_trades=closed_trades,
        profit_factor=profit_factor,
        total_return_pct=total_return_pct,
        excess_return_pct=excess_return_pct,
        max_drawdown_pct=max_drawdown_pct,
        turnover_pct=turnover_pct,
        cost_drag_pct=cost_drag_pct,
        stress_excess_pct=scenarios["stress"].adjusted_excess_return_pct,
        severe_return_pct=scenarios["severe"].adjusted_return_pct,
        benchmark_observations=benchmark_observations,
    )

    return {
        "strategy_id": strategy_id,
        "robustness_score": _round(score),
        "critic_verdict": verdict,
        "critic_issues": issues,
        "cost_scenarios": {name: scenario.as_dict() for name, scenario in scenarios.items()},
    }


def build_strategy_lab_robustness_frame(
    leaderboard: pd.DataFrame,
    *,
    base_slippage_bps: float,
    base_brokerage_bps: float,
) -> pd.DataFrame:
    if leaderboard.empty:
        return pd.DataFrame(
            columns=[
                "strategy_id",
                "robustness_score",
                "critic_verdict",
                "critic_issues",
                "cost_base_bps",
                "cost_stress_bps",
                "cost_severe_bps",
                "cost_stress_return_pct",
                "cost_stress_excess_return_pct",
                "cost_severe_return_pct",
                "cost_severe_excess_return_pct",
            ]
        )

    rows = []
    for row in leaderboard.to_dict(orient="records"):
        result = evaluate_strategy_robustness(
            row,
            base_slippage_bps=base_slippage_bps,
            base_brokerage_bps=base_brokerage_bps,
        )
        scenarios = result["cost_scenarios"]
        rows.append(
            {
                "strategy_id": result["strategy_id"],
                "robustness_score": result["robustness_score"],
                "critic_verdict": result["critic_verdict"],
                "critic_issues": json.dumps(result["critic_issues"], ensure_ascii=True),
                "cost_base_bps": scenarios["base"]["total_cost_bps"],
                "cost_stress_bps": scenarios["stress"]["total_cost_bps"],
                "cost_severe_bps": scenarios["severe"]["total_cost_bps"],
                "cost_stress_return_pct": scenarios["stress"]["adjusted_return_pct"],
                "cost_stress_excess_return_pct": scenarios["stress"]["adjusted_excess_return_pct"],
                "cost_severe_return_pct": scenarios["severe"]["adjusted_return_pct"],
                "cost_severe_excess_return_pct": scenarios["severe"]["adjusted_excess_return_pct"],
            }
        )
    return pd.DataFrame(rows)


def _cost_scenario(
    name: str,
    *,
    base_cost_bps: float,
    total_cost_bps: float,
    turnover_pct: float,
    total_return_pct: float,
    excess_return_pct: float,
) -> CostSensitivityScenario:
    incremental_cost_bps = max(total_cost_bps - base_cost_bps, 0.0)
    return_erosion_pct = turnover_pct * incremental_cost_bps / 10_000.0
    return CostSensitivityScenario(
        name=name,
        total_cost_bps=_round(total_cost_bps),
        incremental_cost_bps=_round(incremental_cost_bps),
        return_erosion_pct=_round(return_erosion_pct),
        adjusted_return_pct=_round(total_return_pct - return_erosion_pct),
        adjusted_excess_return_pct=_round(excess_return_pct - return_erosion_pct),
    )


def _critic_verdict(
    *,
    fills: int,
    closed_trades: int,
    profit_factor: float,
    total_return_pct: float,
    excess_return_pct: float,
    max_drawdown_pct: float,
    turnover_pct: float,
    cost_drag_pct: float,
    stress_excess_pct: float,
    severe_return_pct: float,
    benchmark_observations: int | None,
) -> tuple[str, list[str], float]:
    blockers: list[tuple[str, float]] = []
    warnings: list[tuple[str, float]] = []

    if fills <= 0 or closed_trades <= 0:
        blockers.append(("No completed trades fired in this Strategy Lab window.", 60.0))
    if benchmark_observations is not None and benchmark_observations <= 0:
        blockers.append(("Benchmark comparison has no overlapping observations.", 35.0))
    if turnover_pct >= 10_000:
        blockers.append(("Turnover exceeds 100x starting capital; execution assumptions dominate.", 35.0))

    if 0 < closed_trades < 10:
        warnings.append(("Trade sample is thin; require more observations before trusting the edge.", 12.0))
    if fills > 0 and profit_factor < 1.0:
        warnings.append(("Profit factor is below 1.0 after configured costs.", 18.0))
    if fills > 0 and excess_return_pct <= 0:
        warnings.append(("Strategy does not beat the benchmark in the base run.", 15.0))
    if fills > 0 and stress_excess_pct <= 0:
        warnings.append(("Stress cost scenario erases benchmark excess return.", 18.0))
    if fills > 0 and total_return_pct > 0 and severe_return_pct <= 0:
        warnings.append(("Severe cost scenario erases positive absolute return.", 12.0))
    if 5_000 <= turnover_pct < 10_000:
        warnings.append(("Turnover is high enough to make cost and slippage sensitivity material.", 12.0))
    if cost_drag_pct >= 5.0:
        warnings.append(("Modeled cost drag is elevated versus starting capital.", 10.0))
    if max_drawdown_pct >= 35.0:
        warnings.append(("Max drawdown is too high for primary paper allocation without tighter caps.", 14.0))

    penalty = sum(item[1] for item in blockers + warnings)
    score = max(0.0, 100.0 - penalty)
    if blockers:
        return "BLOCK", [issue for issue, _penalty in blockers + warnings], score
    if warnings:
        return "WARN", [issue for issue, _penalty in warnings], score
    return "PASS", ["No blocking robustness issues."], score


def _number(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(parsed):
        return 0.0
    return parsed


def _int(value: Any, *, default: int | None = 0) -> int | None:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return default
    return parsed


def _round(value: float) -> float:
    return round(float(value), 6)
