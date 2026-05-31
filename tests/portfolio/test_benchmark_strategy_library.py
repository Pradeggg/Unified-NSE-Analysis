from __future__ import annotations

import json

import pandas as pd

from portfolio.engine.benchmark import compare_to_benchmark
from portfolio.engine.strategy_compiler import MAX_POSITION_PCT, MAX_RISK_PER_TRADE_PCT
from portfolio.engine.strategy_library import built_in_strategy_specs, get_strategy_spec
from portfolio.engine.strategy_schema import validate_strategy_spec


def test_compare_to_benchmark_calculates_relative_return_and_drawdown():
    nav = [
        {"timestamp": "2025-01-01", "equity": 100.0},
        {"timestamp": "2025-01-02", "equity": 110.0},
        {"timestamp": "2025-01-03", "equity": 105.0},
    ]
    benchmark = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-03"]),
            "close": [200.0, 210.0, 220.0],
        }
    )

    result = compare_to_benchmark(nav, benchmark, benchmark_id="NIFTY_TEST")

    assert result.benchmark_id == "NIFTY_TEST"
    assert round(result.portfolio_return_pct, 4) == 5.0
    assert round(result.benchmark_return_pct, 4) == 10.0
    assert round(result.excess_return_pct, 4) == -5.0
    assert round(result.portfolio_max_drawdown_pct, 4) == 4.5455
    assert round(result.benchmark_max_drawdown_pct, 4) == 0.0
    assert result.observation_count == 3


def test_compare_to_benchmark_returns_empty_metrics_when_dates_do_not_align():
    nav = [{"timestamp": "2025-01-01", "equity": 100.0}]
    benchmark = pd.DataFrame({"date": pd.to_datetime(["2025-01-02"]), "close": [200.0]})

    result = compare_to_benchmark(nav, benchmark, benchmark_id="NIFTY_TEST")

    assert result.as_dict() == {
        "benchmark_id": "NIFTY_TEST",
        "portfolio_return_pct": 0.0,
        "benchmark_return_pct": 0.0,
        "excess_return_pct": 0.0,
        "portfolio_max_drawdown_pct": 0.0,
        "benchmark_max_drawdown_pct": 0.0,
        "observation_count": 0,
    }


def test_compare_to_benchmark_is_deterministic_for_reordered_same_day_duplicates():
    nav = [
        {"timestamp": "2025-01-01", "equity": 100.0},
        {"timestamp": "2025-01-01", "equity": 200.0},
        {"timestamp": "2025-01-02", "equity": 120.0},
    ]
    reordered_nav = [
        {"timestamp": "2025-01-01", "equity": 200.0},
        {"timestamp": "2025-01-02", "equity": 120.0},
        {"timestamp": "2025-01-01", "equity": 100.0},
    ]
    benchmark = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-01", "2025-01-01", "2025-01-02"]),
            "close": [200.0, 400.0, 240.0],
        }
    )
    reordered_benchmark = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-01"]),
            "close": [400.0, 240.0, 200.0],
        }
    )

    result = compare_to_benchmark(nav, benchmark, benchmark_id="NIFTY_TEST")
    reordered_result = compare_to_benchmark(
        reordered_nav,
        reordered_benchmark,
        benchmark_id="NIFTY_TEST",
    )

    assert result.as_dict() == reordered_result.as_dict()
    assert result.observation_count == 2
    assert round(result.portfolio_return_pct, 4) == -20.0
    assert round(result.benchmark_return_pct, 4) == -20.0


def test_compare_to_benchmark_keeps_extreme_computed_metrics_json_safe():
    nav = [
        {"timestamp": "2025-01-01", "equity": 1.0},
        {"timestamp": "2025-01-02", "equity": 1e308},
    ]
    benchmark = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-01", "2025-01-02"]),
            "close": [1.0, 1e308],
        }
    )

    result = compare_to_benchmark(nav, benchmark, benchmark_id="NIFTY_TEST")

    json.dumps(result.as_dict(), allow_nan=False)


def test_built_in_strategy_specs_cover_popular_families_and_validate():
    specs = built_in_strategy_specs()
    ids = {spec["strategy_id"] for spec in specs}

    assert {
        "stage2_continuation_v1",
        "donchian_turtle_breakout_v1",
        "moving_average_trend_v1",
        "momentum_rotation_v1",
        "vcp_breakout_v1",
        "darvas_box_breakout_v1",
        "mean_reversion_uptrend_v1",
        "minervini_trend_template_v1",
    }.issubset(ids)

    for spec in specs:
        validated = validate_strategy_spec(spec)

        assert validated.entry_all
        assert validated.exit_any
        assert validated.risk.initial_stop.type == "atr"
        assert validated.risk.initial_stop.indicator == "atr_14"
        assert validated.risk.initial_stop.multiple is not None
        assert validated.risk.risk_per_trade_pct <= MAX_RISK_PER_TRADE_PCT
        assert validated.risk.max_position_pct <= MAX_POSITION_PCT


def test_get_strategy_spec_returns_deep_copy():
    first = get_strategy_spec("stage2_continuation_v1")
    first["name"] = "mutated"
    first["entry"]["all"][0]["value"] = "MUTATED"
    second = get_strategy_spec("stage2_continuation_v1")

    assert second["name"] != "mutated"
    assert second["entry"]["all"][0]["value"] != "MUTATED"
