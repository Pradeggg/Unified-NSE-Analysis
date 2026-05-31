from __future__ import annotations

import pandas as pd

from portfolio.engine.benchmark import compare_to_benchmark


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
