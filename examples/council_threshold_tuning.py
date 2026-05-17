"""Demo: tune critic thresholds and watch verdicts change.

Runs the same synthetic scenario twice with different drawdown and beta
thresholds to show how Layer E critics respond. No real data needed.

Usage:
    python examples/council_threshold_tuning.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backtesting.strategy_council.critics_advanced import build_advanced_critics
from backtesting.strategy_council.types import (
    BacktestSliceResult,
    EvidencePack,
    StrategySpec,
)


def _spec(strategy_id: str = "stage2", horizon: int = 10) -> StrategySpec:
    return StrategySpec(
        strategy_id=strategy_id,
        horizon_days=horizon,
        entry_rules=("momentum entry",),
        exit_rules=("stop loss + horizon",),
        risk_rules=("research_only",),
        thesis="demo",
    )


def _slice(split: str, ret: float, dd: float | None = None, trades: int = 4) -> BacktestSliceResult:
    metrics: dict = {"total_return_pct": ret, "trade_count": trades}
    if dd is not None:
        metrics["max_drawdown_pct"] = dd
    return BacktestSliceResult(
        split=split,
        strategy_id="stage2",
        horizon_days=10,
        metrics=metrics,
        trade_count=trades,
    )


def run_scenario(label: str, *, evidence: EvidencePack, **thresholds) -> None:
    candidates = (_spec(),)
    train = (_slice("train", ret=8.0, dd=12.0),)
    val = (_slice("validation", ret=3.0, dd=20.0),)

    critics = build_advanced_critics(evidence=evidence, **thresholds)
    print(f"\n=== {label} ===")
    print(f"thresholds        : {thresholds}")
    for critic in critics:
        critique = critic.critique(candidates=candidates, train_results=train, validation_results=val)
        issues = "; ".join(critique.issues) or "-"
        print(f"  {type(critic).__name__:30s}  verdict={critique.verdict:7s}  issues={issues}")


def main() -> None:
    evidence = EvidencePack(symbol="DEMO", as_of="2024-12-31")
    evidence.market = {
        "regime": {"available": True, "regime": "bull", "bias_pct": 4.5},
        "factor_exposure": {"available": True, "beta": 2.2, "correlation": 0.85},
        "microstructure": {"available": True, "atr_pct": 2.4},
    }

    run_scenario(
        "STRICT thresholds (max_dd=15%, beta_threshold=1.5)",
        evidence=evidence,
        max_drawdown_pct=15.0,
        correlation_threshold=0.3,
        beta_threshold=1.5,
    )

    run_scenario(
        "LOOSE thresholds (max_dd=25%, beta_threshold=3.0)",
        evidence=evidence,
        max_drawdown_pct=25.0,
        correlation_threshold=0.3,
        beta_threshold=3.0,
    )

    evidence_bear = EvidencePack(symbol="DEMO", as_of="2024-12-31")
    evidence_bear.market = {
        "regime": {"available": True, "regime": "bear", "bias_pct": -5.0},
        "factor_exposure": {"available": False},
        "microstructure": {"available": False},
    }
    candidates = (_spec(),)
    train = (_slice("train", ret=-2.0),)
    val = (_slice("validation", ret=-4.0),)
    critics = build_advanced_critics(evidence=evidence_bear)
    print("\n=== BEAR regime with negative validation ===")
    for critic in critics:
        c = critic.critique(candidates=candidates, train_results=train, validation_results=val)
        issues = "; ".join(c.issues) or "-"
        print(f"  {type(critic).__name__:30s}  verdict={c.verdict:7s}  issues={issues}")


if __name__ == "__main__":
    main()
