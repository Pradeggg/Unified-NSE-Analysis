"""Advanced rule-based critics for the Strategy Council.

These critics complement :class:`RuleBasedDataLeakageCritic` and
:class:`RuleBasedRiskCritic` with quantitative checks that operate on the
backtest slice metrics and (optionally) the enriched evidence pack:

* :class:`DrawdownCritic` — flags candidates whose validation drawdown
  exceeds a threshold (derived from ``max_drawdown_pct`` or estimated from
  equity-curve metrics when present).
* :class:`CorrelationCritic` — flags candidates whose train and validation
  returns diverge sharply, indicating regime sensitivity / overfitting.
* :class:`FactorBasedCritic` — uses ``evidence.market["factor_exposure"]`` to
  warn when a strategy's edge appears to ride a strong benchmark beta.
* :class:`RegimeConditionalCritic` — uses ``evidence.market["regime"]`` to
  flag negative validation in the prevailing regime.

All critics are pure-Python and deterministic. :func:`build_advanced_critics`
returns the full tuple respecting caller-supplied thresholds.
:func:`merge_critique_issues` aggregates verdicts across critics for the
council loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from backtesting.strategy_council.types import (
    BacktestSliceResult,
    Critique,
    EvidencePack,
    StrategySpec,
)


def _val_returns(results: tuple[BacktestSliceResult, ...]) -> list[float]:
    out: list[float] = []
    for r in results:
        ret = r.metrics.get("total_return_pct")
        if isinstance(ret, (int, float)) and not pd.isna(ret):
            out.append(float(ret))
    return out


@dataclass
class DrawdownCritic:
    """Reject strategies whose worst loss exceeds ``threshold_pct``.

    Uses ``metrics["max_drawdown_pct"]`` when populated; otherwise treats a
    single large negative ``total_return_pct`` as a drawdown proxy.
    """

    threshold_pct: float = 15.0

    def critique(
        self,
        *,
        candidates: tuple[StrategySpec, ...],
        train_results: tuple[BacktestSliceResult, ...],
        validation_results: tuple[BacktestSliceResult, ...],
    ) -> Critique:
        issues: list[str] = []
        worst = 0.0
        for r in validation_results:
            dd = r.metrics.get("max_drawdown_pct")
            ret = r.metrics.get("total_return_pct")
            candidate_dd: float | None = None
            if isinstance(dd, (int, float)):
                candidate_dd = abs(float(dd))
            elif isinstance(ret, (int, float)) and ret < 0:
                candidate_dd = abs(float(ret))
            if candidate_dd is not None and candidate_dd > self.threshold_pct:
                issues.append(
                    f"{r.strategy_id}@{r.horizon_days}d drawdown {candidate_dd:.2f}% "
                    f"exceeds {self.threshold_pct:.2f}% threshold"
                )
                worst = max(worst, candidate_dd)
        verdict = "revise" if issues else "accept"
        required = (
            (f"tighten exits to cap drawdown below {self.threshold_pct:.1f}%",) if issues else ()
        )
        return Critique(
            critic="drawdown",
            verdict=verdict,
            issues=tuple(issues),
            required_changes=required,
            confidence_delta=-min(worst, 50.0) / 100.0 if issues else 0.0,
        )


@dataclass
class CorrelationCritic:
    """Flag candidates with low train-vs-validation return consistency.

    When the correlation between train and validation returns across the
    candidate set falls below ``threshold``, emits a single critic-level
    issue. When fewer than two candidates exist, the critic accepts trivially.
    """

    threshold: float = 0.3

    def critique(
        self,
        *,
        candidates: tuple[StrategySpec, ...],
        train_results: tuple[BacktestSliceResult, ...],
        validation_results: tuple[BacktestSliceResult, ...],
    ) -> Critique:
        train = _val_returns(train_results)
        val = _val_returns(validation_results)
        # Align by index ordering — assumes results align with candidates order.
        n = min(len(train), len(val))
        if n < 2:
            return Critique(critic="correlation", verdict="accept")
        train_s = pd.Series(train[:n])
        val_s = pd.Series(val[:n])
        if train_s.std() == 0 or val_s.std() == 0:
            return Critique(critic="correlation", verdict="accept")
        corr = float(train_s.corr(val_s))
        if pd.isna(corr):
            return Critique(critic="correlation", verdict="accept")
        if corr < self.threshold:
            return Critique(
                critic="correlation",
                verdict="revise",
                issues=(f"train/validation return correlation {corr:.2f} below {self.threshold:.2f}",),
                required_changes=("add filters to stabilize behavior across splits",),
                confidence_delta=-0.1,
            )
        return Critique(
            critic="correlation",
            verdict="accept",
            issues=(f"train/validation correlation {corr:.2f} acceptable",),
        )


@dataclass
class FactorBasedCritic:
    """Warn when |beta| against the benchmark exceeds ``beta_threshold``.

    Reads ``evidence.market["factor_exposure"]`` so this is a no-op unless
    :mod:`evidence_enrichment` has been run with a benchmark.
    """

    evidence: EvidencePack | None = None
    beta_threshold: float = 1.5

    def critique(
        self,
        *,
        candidates: tuple[StrategySpec, ...],
        train_results: tuple[BacktestSliceResult, ...],
        validation_results: tuple[BacktestSliceResult, ...],
    ) -> Critique:
        if self.evidence is None:
            return Critique(critic="factor", verdict="accept")
        factor = (self.evidence.market or {}).get("factor_exposure") or {}
        if not factor.get("available"):
            return Critique(
                critic="factor",
                verdict="accept",
                issues=("factor exposure unavailable; skipping",),
            )
        beta = factor.get("beta")
        if not isinstance(beta, (int, float)):
            return Critique(critic="factor", verdict="accept")
        if abs(beta) > self.beta_threshold:
            return Critique(
                critic="factor",
                verdict="revise",
                issues=(f"|beta|={abs(beta):.2f} exceeds {self.beta_threshold:.2f}; edge may be beta-driven",),
                required_changes=("add market-neutral overlays or reduce position size",),
                confidence_delta=-0.1,
            )
        return Critique(critic="factor", verdict="accept")


@dataclass
class RegimeConditionalCritic:
    """Reject negative validation in the prevailing regime.

    Uses ``evidence.market["regime"]`` from :mod:`evidence_enrichment`.
    When validation returns are universally negative under the detected
    regime, surfaces a strong revise verdict.
    """

    evidence: EvidencePack | None = None

    def critique(
        self,
        *,
        candidates: tuple[StrategySpec, ...],
        train_results: tuple[BacktestSliceResult, ...],
        validation_results: tuple[BacktestSliceResult, ...],
    ) -> Critique:
        if self.evidence is None:
            return Critique(critic="regime", verdict="accept")
        regime_info = (self.evidence.market or {}).get("regime") or {}
        if not regime_info.get("available"):
            return Critique(
                critic="regime",
                verdict="accept",
                issues=("regime unavailable; skipping",),
            )
        regime = regime_info.get("regime", "sideways")
        val = _val_returns(validation_results)
        if not val:
            return Critique(critic="regime", verdict="accept")
        max_val = max(val)
        if max_val < 0:
            return Critique(
                critic="regime",
                verdict="revise",
                issues=(
                    f"all validation returns negative under {regime} regime "
                    f"(max={max_val:.2f}%)",
                ),
                required_changes=(f"design strategies suited to {regime} conditions",),
                confidence_delta=-0.15,
            )
        return Critique(
            critic="regime",
            verdict="accept",
            issues=(f"prevailing regime: {regime}",),
        )


def build_advanced_critics(
    *,
    evidence: EvidencePack | None = None,
    max_drawdown_pct: float = 15.0,
    correlation_threshold: float = 0.3,
    beta_threshold: float = 1.5,
) -> tuple[Any, ...]:
    """Factory returning the standard advanced-critic suite."""
    return (
        DrawdownCritic(threshold_pct=max_drawdown_pct),
        CorrelationCritic(threshold=correlation_threshold),
        FactorBasedCritic(evidence=evidence, beta_threshold=beta_threshold),
        RegimeConditionalCritic(evidence=evidence),
    )


def merge_critique_issues(critiques: tuple[Critique, ...]) -> dict[str, Any]:
    """Aggregate verdicts/issues across critics for council-loop feedback."""
    verdicts = [c.verdict for c in critiques]
    revise_count = sum(1 for v in verdicts if v == "revise")
    reject_count = sum(1 for v in verdicts if v == "reject")
    if reject_count:
        overall = "reject"
    elif revise_count:
        overall = "revise"
    else:
        overall = "accept"
    return {
        "overall": overall,
        "verdicts": verdicts,
        "issues": tuple(issue for c in critiques for issue in c.issues),
        "required_changes": tuple(
            change for c in critiques for change in c.required_changes
        ),
        "confidence_delta": sum(c.confidence_delta for c in critiques),
    }


__all__ = [
    "DrawdownCritic",
    "CorrelationCritic",
    "FactorBasedCritic",
    "RegimeConditionalCritic",
    "build_advanced_critics",
    "merge_critique_issues",
]
