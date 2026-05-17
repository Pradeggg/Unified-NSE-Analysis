"""End-to-end integration test for council Layer D+E+F enhancements."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from backtesting.strategy_council.council import run_strategy_council
from backtesting.strategy_council.types import CouncilConfig, EvidencePack


def _synthetic_bullish_eod(n: int = 520) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.date_range("2023-01-01", periods=n, freq="B"),
            "symbol": ["TEST"] * n,
            "open": [100 + i * 0.4 for i in range(n)],
            "high": [101 + i * 0.4 for i in range(n)],
            "low": [99 + i * 0.4 for i in range(n)],
            "close": [100.5 + i * 0.4 for i in range(n)],
            "volume": [10_000] * n,
        }
    )


def test_full_enhancement_stack_runs_end_to_end(tmp_path: Path):
    df = _synthetic_bullish_eod()
    config = CouncilConfig(
        symbol="TEST",
        iterations=1,
        max_candidates=3,
        include_enrichment=True,
        use_advanced_critics=True,
        dashboard_output_dir=str(tmp_path),
    )
    evidence = EvidencePack(symbol="TEST", as_of="2024-01-01", technical={"close": 200, "bars": 520})

    result = run_strategy_council(df, evidence=evidence, config=config)

    # Layer D — enrichment populated market signals
    regime = (result.evidence.market or {}).get("regime") or {}
    assert regime.get("available") is True
    assert regime.get("regime") in {"bull", "bear", "sideways"}
    micro = (result.evidence.market or {}).get("microstructure") or {}
    assert micro.get("available") is True

    # Layer E — final iteration contains the advanced critic verdicts alongside the base ones
    assert result.iterations, "expected at least one iteration"
    final_critic_names = {c.critic for c in result.iterations[-1].critiques}
    for expected in ("data_leakage", "market_risk", "drawdown", "correlation", "factor", "regime"):
        assert expected in final_critic_names, f"missing critic: {expected}; got {final_critic_names}"

    # Layer F — dashboard HTML written to disk
    assert result.dashboard_path is not None
    dashboard_file = Path(result.dashboard_path)
    assert dashboard_file.exists()
    html = dashboard_file.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in html
    assert "TEST" in html
    assert "Iterations" in html


def test_enhancements_disabled_keeps_baseline_behavior(tmp_path: Path):
    df = _synthetic_bullish_eod(n=520)
    config = CouncilConfig(
        symbol="TEST",
        iterations=1,
        max_candidates=2,
        include_enrichment=False,
        use_advanced_critics=False,
        dashboard_output_dir=None,
    )
    evidence = EvidencePack(symbol="TEST", as_of="2024-01-01", technical={"close": 200, "bars": 520})

    result = run_strategy_council(df, evidence=evidence, config=config)

    # Layer D off — no regime injection
    assert "regime" not in (result.evidence.market or {})
    # Layer E off — only the two base critics
    final_critic_names = {c.critic for c in result.iterations[-1].critiques}
    assert final_critic_names == {"data_leakage", "market_risk"}
    # Layer F off — no dashboard
    assert result.dashboard_path is None
