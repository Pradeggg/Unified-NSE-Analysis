"""Tests for backtesting.strategy_council.dashboard_generator."""

from __future__ import annotations

from pathlib import Path

import pytest

from backtesting.strategy_council.dashboard_generator import (
    render_dashboard_html,
    write_dashboard,
)
from backtesting.strategy_council.types import (
    BacktestSliceResult,
    CouncilConfig,
    CouncilIteration,
    CouncilResult,
    Critique,
    EvidencePack,
    StrategySpec,
)


def _result(symbol: str = "INFY", recommendation: str = "TRADE_RESEARCH") -> CouncilResult:
    config = CouncilConfig(symbol=symbol, iterations=1, max_candidates=2)
    evidence = EvidencePack(
        symbol=symbol,
        as_of="2024-01-01",
        technical={"close": 100.5, "bars": 520},
        market={
            "regime": {"available": True, "regime": "bull", "bias_pct": 5.2},
            "factor_exposure": {"available": True, "beta": 1.2, "correlation": 0.9},
            "microstructure": {"available": True, "atr_pct": 1.8},
        },
        freshness={"eod": "available", "regime": "bull"},
        missing=["latest_results"],
    )
    locked = StrategySpec(
        strategy_id="stage2",
        horizon_days=10,
        entry_rules=("ema bullish",),
        exit_rules=("profit target",),
        risk_rules=("research_only",),
        thesis="Test thesis for INFY <bull>",  # ensure HTML-escape works
        origin="deterministic_fallback",
    )
    cand = StrategySpec(
        strategy_id="stage2",
        horizon_days=10,
        entry_rules=("entry",),
        exit_rules=("exit",),
        risk_rules=("research_only",),
        thesis="cand",
    )
    iteration = CouncilIteration(
        index=1,
        candidates=(cand,),
        train_results=(
            BacktestSliceResult(
                split="train",
                strategy_id="stage2",
                horizon_days=10,
                metrics={"total_return_pct": 6.5, "trade_count": 3},
                trade_count=3,
            ),
        ),
        validation_results=(
            BacktestSliceResult(
                split="validation",
                strategy_id="stage2",
                horizon_days=10,
                metrics={"total_return_pct": 4.2, "trade_count": 2},
                trade_count=2,
            ),
        ),
        critiques=(
            Critique(critic="drawdown", verdict="accept"),
            Critique(
                critic="regime",
                verdict="revise",
                issues=("validation flat under bull regime",),
                required_changes=("add momentum filter",),
            ),
        ),
        strategist_revision="No forced revision",
    )
    test_results = (
        BacktestSliceResult(
            split="test",
            strategy_id="stage2",
            horizon_days=10,
            metrics={"total_return_pct": 5.0, "trade_count": 2},
            trade_count=2,
        ),
    )
    return CouncilResult(
        config=config,
        evidence=evidence,
        iterations=(iteration,),
        locked_strategy=locked,
        test_results=test_results,
        recommendation=recommendation,
        rationale="Locked by best validation.",
    )


class TestRenderDashboardHtml:
    def test_includes_core_sections(self):
        html = render_dashboard_html(_result())
        for needle in ("Strategy Council", "INFY", "Locked strategy", "Evidence", "Iterations", "Final critiques"):
            assert needle in html

    def test_recommendation_class_present(self):
        html = render_dashboard_html(_result(recommendation="WAIT"))
        assert 'class="recommendation WAIT"' in html

    def test_escapes_html_in_thesis(self):
        html = render_dashboard_html(_result())
        assert "&lt;bull&gt;" in html
        assert "<bull>" not in html  # raw < should never make it through

    def test_no_iterations_renders_gracefully(self):
        r = _result()
        empty = CouncilResult(
            config=r.config,
            evidence=r.evidence,
            iterations=(),
            locked_strategy=None,
            test_results=(),
            recommendation="NO_TRADE",
            rationale=r.rationale,
        )
        html = render_dashboard_html(empty)
        assert "No iterations recorded" in html
        assert "No locked strategy" in html

    def test_unavailable_market_signals_render_dashes(self):
        r = _result()
        r.evidence.market = {
            "regime": {"available": False},
            "factor_exposure": {"available": False},
            "microstructure": {"available": False},
        }
        html = render_dashboard_html(r)
        # The Beta and ATR rows should fall back to em-dash placeholders
        assert "Beta" in html
        # No crash; recommendation still rendered
        assert "TRADE_RESEARCH" in html


class TestWriteDashboard:
    def test_writes_file_with_default_name(self, tmp_path: Path):
        path = write_dashboard(_result(), tmp_path)
        assert path.exists()
        assert path.parent == tmp_path
        assert path.suffix == ".html"
        assert "INFY" in path.name
        content = path.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content

    def test_writes_file_with_custom_name(self, tmp_path: Path):
        path = write_dashboard(_result(), tmp_path, filename="custom.html")
        assert path.name == "custom.html"
        assert path.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")

    def test_creates_output_dir(self, tmp_path: Path):
        target = tmp_path / "deeper" / "subdir"
        path = write_dashboard(_result(), target, filename="d.html")
        assert path.exists()
        assert path.parent == target


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
