from __future__ import annotations

import json
from types import SimpleNamespace

import pandas as pd

from portfolio import cli
from portfolio.data_sources.postgres import prepare_replay_frame
from portfolio.engine.leaderboard import calculate_strategy_diagnostics
from portfolio.engine.order_types import Fill, OrderSide


def _eod_rows(symbol: str, start: float) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for idx in range(260):
        close = start + idx
        rows.append(
            {
                "date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=idx),
                "symbol": symbol,
                "open": close - 1,
                "high": close + 1,
                "low": close - 2,
                "close": close,
                "volume": 100_000 + idx,
                "turnover_cr": 10.0,
            }
        )
    return rows


def test_prepare_replay_frame_uses_stage_snapshots_and_computes_strategy_columns():
    eod = pd.DataFrame(_eod_rows("AAA", 100.0))
    stage = pd.DataFrame(
        {
            "date": eod["date"],
            "symbol": ["AAA"] * len(eod),
            "stage": ["STAGE_2"] * len(eod),
            "snapshot_relative_strength": [82.0] * len(eod),
            "snapshot_rsi": [61.0] * len(eod),
        }
    )
    fundamentals = pd.DataFrame(
        {
            "symbol": ["AAA"],
            "eps_growth_pct": [25.0],
            "sales_growth_pct": [18.0],
            "roe_pct": [21.0],
            "debt_to_equity": [0.2],
        }
    )

    features = prepare_replay_frame(eod, stage, fundamentals=fundamentals, start_date="2024-09-01")

    assert not features.empty
    latest = features.iloc[-1]
    assert latest["stage"] == "STAGE_2"
    assert latest["weekly_stage"] == "STAGE_2"
    assert latest["relative_strength"] == 82.0
    assert latest["rsi_14"] == 61.0
    assert latest["eps_growth_pct"] == 25.0
    for column in ("sma_20", "sma_50", "sma_100", "sma_200", "atr_14", "volume_ratio_20d"):
        assert column in features.columns
        assert pd.notna(latest[column])


def test_strategy_diagnostics_calculates_trade_quality_and_cost_metrics():
    fills = [
        Fill("f1", "o1", "AAA", OrderSide.BUY, 10, 100.0, 1.0, 2.0, "2025-01-01", "s1"),
        Fill("f2", "o2", "AAA", OrderSide.SELL, 10, 110.0, 1.0, 2.0, "2025-01-02", "s1"),
        Fill("f3", "o3", "BBB", OrderSide.BUY, 10, 100.0, 1.0, 2.0, "2025-01-03", "s1"),
        Fill("f4", "o4", "BBB", OrderSide.SELL, 10, 95.0, 1.0, 2.0, "2025-01-04", "s1"),
    ]
    replay_result = SimpleNamespace(
        fills=fills,
        nav_history=[
            {"timestamp": "2025-01-01", "market_value": 1000.0},
            {"timestamp": "2025-01-02", "market_value": 0.0},
        ],
        account=SimpleNamespace(initial_capital=10_000.0),
    )

    diagnostics = calculate_strategy_diagnostics(
        replay_result,
        {"starting_equity": 10_000.0, "total_return_pct": 4.0, "max_drawdown_pct": 1.5},
    ).as_dict()

    assert diagnostics["profit_factor"] > 1.0
    assert diagnostics["average_win"] > 0
    assert diagnostics["average_loss"] < 0
    assert diagnostics["turnover_pct"] == 40.5
    assert diagnostics["cost_drag_pct"] == 0.12
    assert diagnostics["exposure_pct"] == 50.0
    assert diagnostics["rank_score"] == 2.5


def test_strategy_lab_command_writes_leaderboard_from_postgres_adapter(monkeypatch, tmp_path):
    eod = pd.DataFrame(_eod_rows("AAA", 100.0))
    stage = pd.DataFrame(
        {
            "date": eod["date"],
            "symbol": ["AAA"] * len(eod),
            "stage": ["STAGE_2"] * len(eod),
            "snapshot_relative_strength": [85.0] * len(eod),
            "snapshot_rsi": [62.0] * len(eod),
        }
    )
    features = prepare_replay_frame(eod, stage, start_date="2024-09-01")
    benchmark = pd.DataFrame({"date": pd.to_datetime(features["date"].unique()), "close": range(100, 100 + features["date"].nunique())})

    def fake_load_postgres_replay_data(**kwargs):
        assert kwargs["top_n"] == 1
        return SimpleNamespace(features=features, benchmark=benchmark, latest_eod_date="2024-09-16")

    monkeypatch.setattr(cli, "load_postgres_replay_data", fake_load_postgres_replay_data)

    result = cli._cmd_strategy_lab(
        SimpleNamespace(
            output_dir=tmp_path / "lab",
            source="postgres",
            dsn="unused",
            start="2024-09-01",
            lookback="2024-01-01",
            end=None,
            top_n=1,
            benchmark_id="Nifty 500",
            initial_capital=100_000.0,
            slippage_bps=5.0,
            brokerage_bps=3.0,
            run_id="TEST-LAB",
        )
    )

    leaderboard = pd.read_csv(tmp_path / "lab" / "reports" / "strategy_leaderboard.csv")
    summary = (tmp_path / "lab" / "reports" / "strategy_comparison_summary.json").read_text(encoding="utf-8")

    assert result == 0
    assert not leaderboard.empty
    assert "profit_factor" in leaderboard.columns
    assert "cost_drag_pct" in leaderboard.columns
    assert "scores.stage_snapshots" in summary


def test_strategy_lab_command_writes_managed_portfolio_when_enabled(monkeypatch, tmp_path):
    eod = pd.DataFrame(_eod_rows("AAA", 100.0))
    stage = pd.DataFrame(
        {
            "date": eod["date"],
            "symbol": ["AAA"] * len(eod),
            "stage": ["STAGE_2"] * len(eod),
            "snapshot_relative_strength": [85.0] * len(eod),
            "snapshot_rsi": [62.0] * len(eod),
        }
    )
    features = prepare_replay_frame(eod, stage, start_date="2024-09-01")
    benchmark = pd.DataFrame({"date": pd.to_datetime(features["date"].unique()), "close": range(100, 100 + features["date"].nunique())})

    def fake_load_postgres_replay_data(**kwargs):
        return SimpleNamespace(features=features, benchmark=benchmark, latest_eod_date="2024-09-16")

    monkeypatch.setattr(cli, "load_postgres_replay_data", fake_load_postgres_replay_data)

    code = cli.main(
        [
            "strategy-lab",
            "--output-dir",
            str(tmp_path),
            "--top-n",
            "1",
            "--no-db-persist",
            "--managed-portfolio",
            "--llm-council",
            "off",
        ]
    )

    summary = json.loads((tmp_path / "reports" / "strategy_comparison_summary.json").read_text())
    assert code == 0
    assert "managed_portfolio" in summary
    assert (tmp_path / "managed" / "managed_portfolio_state.json").exists()
