"""Quick demo: run the Strategy Council with all enhancement layers ON.

Generates synthetic bullish EOD data, runs the council with rule
composition + evidence enrichment + advanced critics + dashboard, and
prints a compact summary plus the dashboard path.

Usage:
    python examples/council_quick_demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pandas as pd

from backtesting.strategy_council.council import run_strategy_council
from backtesting.strategy_council.types import CouncilConfig, EvidencePack


def make_synthetic_eod(symbol: str = "DEMO", n: int = 520) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.date_range("2023-01-01", periods=n, freq="B"),
            "symbol": [symbol] * n,
            "open": [100 + i * 0.4 for i in range(n)],
            "high": [101 + i * 0.4 for i in range(n)],
            "low": [99 + i * 0.4 for i in range(n)],
            "close": [100.5 + i * 0.4 for i in range(n)],
            "volume": [10_000 + (i % 7) * 200 for i in range(n)],
        }
    )


def main() -> None:
    symbol = "DEMO"
    out_dir = Path("reports/dashboards")
    df = make_synthetic_eod(symbol)

    config = CouncilConfig(
        symbol=symbol,
        iterations=2,
        max_candidates=4,
        include_enrichment=True,
        use_advanced_critics=True,
        use_rule_composition=True,
        rule_llm_ratio=0.4,
        dashboard_output_dir=str(out_dir),
    )
    evidence = EvidencePack(
        symbol=symbol,
        as_of="2024-12-31",
        technical={"close": float(df["close"].iloc[-1]), "bars": len(df)},
    )

    result = run_strategy_council(df, evidence=evidence, config=config)

    print(f"Symbol            : {symbol}")
    print(f"Recommendation    : {result.recommendation}")
    locked = result.locked_strategy
    print(f"Locked strategy   : {locked.strategy_id} @ {locked.horizon_days}d" if locked else "Locked strategy   : -")

    market = result.evidence.market or {}
    regime = market.get("regime") or {}
    micro = market.get("microstructure") or {}
    print(f"Regime            : {regime.get('regime', '-')} (bias_pct={regime.get('bias_pct', '-')})")
    print(f"ATR%              : {micro.get('atr_pct', '-')}")

    final_critics = result.iterations[-1].critiques
    verdicts = ", ".join(f"{c.critic}={c.verdict}" for c in final_critics)
    print(f"Final critics     : {verdicts}")

    if result.dashboard_path:
        print(f"Dashboard         : {result.dashboard_path}")
        print("Open it in a browser to inspect iterations, evidence, and critique details.")


if __name__ == "__main__":
    main()
