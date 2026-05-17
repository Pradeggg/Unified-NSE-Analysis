"""Tests for backtesting.strategy_council.critics_advanced."""

from __future__ import annotations

import pytest

from backtesting.strategy_council.critics_advanced import (
    CorrelationCritic,
    DrawdownCritic,
    FactorBasedCritic,
    RegimeConditionalCritic,
    build_advanced_critics,
    merge_critique_issues,
)
from backtesting.strategy_council.types import (
    BacktestSliceResult,
    Critique,
    EvidencePack,
    StrategySpec,
)


def _spec(sid: str = "stage2", h: int = 10) -> StrategySpec:
    return StrategySpec(
        strategy_id=sid,
        horizon_days=h,
        entry_rules=("entry",),
        exit_rules=("exit",),
        risk_rules=("research_only",),
        thesis="t",
    )


def _slice(split: str, sid: str, h: int, ret: float, dd: float | None = None, trades: int = 5) -> BacktestSliceResult:
    metrics: dict = {"total_return_pct": ret, "trade_count": trades}
    if dd is not None:
        metrics["max_drawdown_pct"] = dd
    return BacktestSliceResult(
        split=split, strategy_id=sid, horizon_days=h, metrics=metrics, trade_count=trades
    )


class TestDrawdownCritic:
    def test_accepts_when_below_threshold(self):
        critic = DrawdownCritic(threshold_pct=15.0)
        result = critic.critique(
            candidates=(_spec(),),
            train_results=(_slice("train", "stage2", 10, 5.0, dd=5.0),),
            validation_results=(_slice("validation", "stage2", 10, 4.0, dd=10.0),),
        )
        assert result.verdict == "accept"

    def test_revises_when_dd_exceeds_threshold(self):
        critic = DrawdownCritic(threshold_pct=15.0)
        result = critic.critique(
            candidates=(_spec(),),
            train_results=(_slice("train", "stage2", 10, 5.0),),
            validation_results=(_slice("validation", "stage2", 10, 5.0, dd=25.0),),
        )
        assert result.verdict == "revise"
        assert any("drawdown" in i.lower() for i in result.issues)
        assert result.confidence_delta < 0

    def test_uses_negative_return_as_proxy(self):
        critic = DrawdownCritic(threshold_pct=10.0)
        result = critic.critique(
            candidates=(_spec(),),
            train_results=(_slice("train", "stage2", 10, 5.0),),
            validation_results=(_slice("validation", "stage2", 10, -25.0),),
        )
        assert result.verdict == "revise"


class TestCorrelationCritic:
    def test_accepts_when_correlation_high(self):
        critic = CorrelationCritic(threshold=0.3)
        candidates = tuple(_spec(h=h) for h in (5, 10, 20))
        train = tuple(_slice("train", "stage2", h, ret) for h, ret in zip((5, 10, 20), [1.0, 5.0, 10.0]))
        val = tuple(_slice("validation", "stage2", h, ret) for h, ret in zip((5, 10, 20), [1.1, 4.8, 9.5]))
        result = critic.critique(candidates=candidates, train_results=train, validation_results=val)
        assert result.verdict == "accept"

    def test_revises_when_correlation_negative(self):
        critic = CorrelationCritic(threshold=0.3)
        candidates = tuple(_spec(h=h) for h in (5, 10, 20))
        train = tuple(_slice("train", "stage2", h, ret) for h, ret in zip((5, 10, 20), [10.0, 5.0, 1.0]))
        val = tuple(_slice("validation", "stage2", h, ret) for h, ret in zip((5, 10, 20), [1.0, 5.0, 10.0]))
        result = critic.critique(candidates=candidates, train_results=train, validation_results=val)
        assert result.verdict == "revise"

    def test_accepts_when_too_few_candidates(self):
        critic = CorrelationCritic()
        result = critic.critique(
            candidates=(_spec(),),
            train_results=(_slice("train", "stage2", 10, 1.0),),
            validation_results=(_slice("validation", "stage2", 10, 1.0),),
        )
        assert result.verdict == "accept"


class TestFactorBasedCritic:
    def test_accept_when_no_evidence(self):
        critic = FactorBasedCritic(evidence=None)
        result = critic.critique(candidates=(), train_results=(), validation_results=())
        assert result.verdict == "accept"

    def test_accept_when_factor_unavailable(self):
        pack = EvidencePack(symbol="X", as_of="2024-01-01")
        pack.market["factor_exposure"] = {"available": False}
        critic = FactorBasedCritic(evidence=pack)
        result = critic.critique(candidates=(), train_results=(), validation_results=())
        assert result.verdict == "accept"

    def test_revise_on_high_beta(self):
        pack = EvidencePack(symbol="X", as_of="2024-01-01")
        pack.market["factor_exposure"] = {"available": True, "beta": 2.5, "correlation": 0.9}
        critic = FactorBasedCritic(evidence=pack, beta_threshold=1.5)
        result = critic.critique(candidates=(), train_results=(), validation_results=())
        assert result.verdict == "revise"
        assert any("beta" in i for i in result.issues)


class TestRegimeConditionalCritic:
    def test_accept_when_no_regime(self):
        critic = RegimeConditionalCritic(evidence=None)
        result = critic.critique(candidates=(), train_results=(), validation_results=())
        assert result.verdict == "accept"

    def test_revise_when_all_negative(self):
        pack = EvidencePack(symbol="X", as_of="2024-01-01")
        pack.market["regime"] = {"available": True, "regime": "bear"}
        critic = RegimeConditionalCritic(evidence=pack)
        result = critic.critique(
            candidates=(_spec(),),
            train_results=(_slice("train", "stage2", 10, -1.0),),
            validation_results=(_slice("validation", "stage2", 10, -3.0),),
        )
        assert result.verdict == "revise"

    def test_accept_when_at_least_one_positive(self):
        pack = EvidencePack(symbol="X", as_of="2024-01-01")
        pack.market["regime"] = {"available": True, "regime": "bull"}
        critic = RegimeConditionalCritic(evidence=pack)
        result = critic.critique(
            candidates=(_spec(),),
            train_results=(_slice("train", "stage2", 10, -1.0),),
            validation_results=(_slice("validation", "stage2", 10, 2.0),),
        )
        assert result.verdict == "accept"


class TestBuildAdvancedCriticsFactory:
    def test_returns_four_critics(self):
        critics = build_advanced_critics()
        assert len(critics) == 4
        names = {type(c).__name__ for c in critics}
        assert names == {"DrawdownCritic", "CorrelationCritic", "FactorBasedCritic", "RegimeConditionalCritic"}

    def test_thresholds_passed_through(self):
        critics = build_advanced_critics(max_drawdown_pct=25.0, beta_threshold=2.0)
        dd = next(c for c in critics if isinstance(c, DrawdownCritic))
        fac = next(c for c in critics if isinstance(c, FactorBasedCritic))
        assert dd.threshold_pct == 25.0
        assert fac.beta_threshold == 2.0


class TestMergeCritiqueIssues:
    def test_all_accept(self):
        crits = (
            Critique(critic="a", verdict="accept"),
            Critique(critic="b", verdict="accept"),
        )
        merged = merge_critique_issues(crits)
        assert merged["overall"] == "accept"
        assert merged["issues"] == ()

    def test_any_revise_propagates(self):
        crits = (
            Critique(critic="a", verdict="accept"),
            Critique(critic="b", verdict="revise", issues=("x",), required_changes=("fix x",)),
        )
        merged = merge_critique_issues(crits)
        assert merged["overall"] == "revise"
        assert "x" in merged["issues"]
        assert "fix x" in merged["required_changes"]

    def test_reject_dominates(self):
        crits = (
            Critique(critic="a", verdict="revise"),
            Critique(critic="b", verdict="reject"),
        )
        merged = merge_critique_issues(crits)
        assert merged["overall"] == "reject"

    def test_confidence_delta_sums(self):
        crits = (
            Critique(critic="a", verdict="revise", confidence_delta=-0.1),
            Critique(critic="b", verdict="revise", confidence_delta=-0.2),
        )
        merged = merge_critique_issues(crits)
        assert abs(merged["confidence_delta"] - (-0.3)) < 1e-9


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
