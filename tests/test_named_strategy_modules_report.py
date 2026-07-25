from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from scripts.research_signal_effectiveness import build_named_strategy_modules_markdown, markdown_to_html
from terminal.strategy_modules import STRATEGY_MODULES


def _module_summary() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "module_id": module.module_id,
                "module_name": module.name,
                "source_setups": ", ".join(module.mapped_setups[:2]),
                "mapped_setup_count": min(2, len(module.mapped_setups)),
                "trades": 25,
                "win_rate_pct": 48.0,
                "expectancy_r": 0.12,
                "net_expectancy_r": 0.04,
                "net_profit_factor": 1.15,
                "avg_cost_r": 0.06,
                "sample_quality": "medium",
                "module_gate": "TRADE_CANDIDATE",
                "gate_reason": "Positive net evidence.",
            }
            for module in STRATEGY_MODULES
        ]
    )


def _module_candidates() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "module_id": "oneil_canslim_growth_breakout",
                "module_name": "O'Neil-Inspired CAN SLIM Growth Breakout",
                "symbol": "TEST",
                "sector": "Capital Goods",
                "setup": "combo_rs_volume_sector",
                "action": "TRADE_CANDIDATE",
                "decision_score": 72.5,
                "close": 101.25,
                "cost_profile": "liquid",
                "estimated_cost_r": 0.05,
                "market_regime": "confirmation",
                "breadth_positive_pct": 58.0,
                "fno_pcr": 0.92,
                "fno_buildup": "LONG_BUILDUP",
                "setup_expectancy_r": 0.12,
                "setup_net_expectancy_r": 0.04,
                "setup_win_rate_pct": 48.0,
                "module_gate": "TRADE_CANDIDATE",
                "gate_reason": "Positive net evidence.",
                "decision_reasons": "synthetic candidate",
            }
        ]
    )


def test_named_strategy_modules_markdown_contains_all_modules_and_candidates():
    paths = {
        "module_summary": Path("reports/strategy_modules/module_summary_test.csv"),
        "module_candidates": Path("reports/strategy_modules/module_candidates_test.csv"),
    }

    markdown = build_named_strategy_modules_markdown(
        module_summary=_module_summary(),
        module_candidates=_module_candidates(),
        latest_trade_date="2026-06-24",
        selected_symbols=["TEST"],
        args=SimpleNamespace(top_n=1, symbols=None, start="2026-01-01", horizon_days=10, target_r=2.0),
        paths=paths,
    )

    assert "# Agent Adda Named Strategy Modules" in markdown
    for module in STRATEGY_MODULES:
        assert module.name in markdown
    assert "Current Module Candidates" in markdown
    assert "Research only. Not investment advice." in markdown
    assert "reports/strategy_modules/module_summary_test.csv" in markdown
    assert "reports/strategy_modules/module_candidates_test.csv" in markdown


def test_named_strategy_modules_html_renders_tables():
    markdown = build_named_strategy_modules_markdown(
        module_summary=_module_summary(),
        module_candidates=_module_candidates(),
        latest_trade_date="2026-06-24",
        selected_symbols=["TEST"],
        args=SimpleNamespace(top_n=1, symbols=None, start="2026-01-01", horizon_days=10, target_r=2.0),
        paths={
            "module_summary": Path("reports/strategy_modules/module_summary_test.csv"),
            "module_candidates": Path("reports/strategy_modules/module_candidates_test.csv"),
        },
    )

    html = markdown_to_html(markdown)

    assert "<table>" in html
    assert "O&#x27;Neil-Inspired CAN SLIM Growth Breakout" in html
    assert "| ---" not in html
