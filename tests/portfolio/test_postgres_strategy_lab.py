from __future__ import annotations

import json
from types import SimpleNamespace

import pandas as pd

from portfolio import cli
from portfolio.data_sources.postgres import prepare_replay_frame
from portfolio.engine import paper_portfolio
from portfolio.engine.leaderboard import calculate_strategy_diagnostics
from portfolio.engine.order_types import Fill, OrderSide
from portfolio.engine.strategy_library import built_in_strategy_specs


def _eod_rows(symbol: str, start: float, count: int = 260) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for idx in range(count):
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


def test_prepare_replay_frame_keeps_short_pg_history_without_200dma():
    eod = pd.DataFrame(_eod_rows("AAA", 100.0, count=90))
    stage = pd.DataFrame(
        {
            "date": eod["date"],
            "symbol": ["AAA"] * len(eod),
            "stage": ["STAGE_2"] * len(eod),
            "snapshot_relative_strength": [78.0] * len(eod),
            "snapshot_rsi": [58.0] * len(eod),
        }
    )

    features = prepare_replay_frame(eod, stage, start_date="2024-03-01")

    assert not features.empty
    latest = features.iloc[-1]
    assert latest["stage"] == "STAGE_2"
    assert pd.notna(latest["sma_20"])
    assert pd.notna(latest["sma_50"])
    assert pd.notna(latest["atr_14"])
    assert pd.isna(latest["sma_100"])
    assert pd.isna(latest["sma_200"])


def test_prepare_replay_frame_marks_persisted_vcp_picks_point_in_time():
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
    vcp_picks = pd.DataFrame(
        [
            {
                "date": "2024-09-10",
                "symbol": "AAA",
                "vcp_rank": 3,
                "vcp_score": 91.5,
                "vcp_breakout_pct": 2.7,
                "vcp_contraction_pct": 1.9,
            }
        ]
    )

    features = prepare_replay_frame(
        eod,
        stage,
        vcp_picks=vcp_picks,
        start_date="2024-09-01",
    )
    picked = features.loc[features["date"] == "2024-09-10"].iloc[0]
    not_picked = features.loc[features["date"] == "2024-09-11"].iloc[0]

    assert picked["vcp_pick"] == 1
    assert picked["vcp_rank"] == 3
    assert picked["vcp_score"] == 91.5
    assert picked["vcp_breakout_pct"] == 2.7
    assert picked["vcp_contraction_pct"] == 1.9
    assert not_picked["vcp_pick"] == 0
    assert not_picked["vcp_score"] == 0.0


def test_built_in_strategies_include_persisted_vcp_pick_strategy():
    ids = {spec["strategy_id"] for spec in built_in_strategy_specs()}

    assert "persisted_vcp_picks_v1" in ids


def test_prepare_replay_frame_uses_point_in_time_quarterly_fundamentals():
    eod = pd.DataFrame(_eod_rows("AAA", 100.0, count=360))
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
        [
            {"symbol": "AAA", "period_end": "2023-09-30", "revenue": 80.0, "pat": 8.0, "eps": 0.8, "opm_pct": 10.0},
            {"symbol": "AAA", "period_end": "2023-12-31", "revenue": 90.0, "pat": 9.0, "eps": 0.9, "opm_pct": 11.0},
            {"symbol": "AAA", "period_end": "2024-03-31", "revenue": 95.0, "pat": 10.0, "eps": 1.0, "opm_pct": 12.0},
            {"symbol": "AAA", "period_end": "2024-06-30", "revenue": 100.0, "pat": 11.0, "eps": 1.1, "opm_pct": 13.0},
            {"symbol": "AAA", "period_end": "2024-09-30", "revenue": 120.0, "pat": 15.0, "eps": 1.5, "opm_pct": 15.0},
        ]
    )

    features = prepare_replay_frame(eod, stage, fundamentals=fundamentals, start_date="2024-08-01")
    before_latest_available = features.loc[features["date"] == "2024-10-15"].iloc[0]
    after_latest_available = features.loc[features["date"] == "2024-11-20"].iloc[0]

    assert before_latest_available["latest_result_period"] == "2024-06-30"
    assert before_latest_available["sales_growth_pct"] == 0.0
    assert before_latest_available["eps_growth_pct"] == 0.0
    assert after_latest_available["latest_result_period"] == "2024-09-30"
    assert after_latest_available["sales_growth_pct"] == 50.0
    assert after_latest_available["pat_growth_pct"] == 87.5
    assert after_latest_available["eps_growth_pct"] == 87.5
    assert after_latest_available["opm_yoy_delta"] == 5.0
    assert after_latest_available["latest_result_age_days"] == 6


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


def test_persist_paper_portfolio_to_postgres_writes_all_paper_tables(monkeypatch):
    calls: list[tuple[str, object]] = []

    class FakeCursor:
        def execute(self, sql, params=None):
            calls.append((str(sql), params))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class FakeConn:
        def cursor(self):
            return FakeCursor()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        paper_portfolio,
        "_connect_postgres",
        lambda dsn: FakeConn(),
    )

    result = paper_portfolio.persist_paper_portfolio_to_postgres(
        dsn="postgres://unit-test",
        portfolio_state={
            "run_id": "RUN1",
            "as_of": "2026-05-29",
            "selected_strategy_id": "vcp_breakout_v1",
            "selected_strategy_name": "VCP Breakout",
            "source_run_state": "runs/vcp/state/replay_state.json",
            "account": {"cash": 1000},
        },
        positions=[
            {
                "symbol": "AAA",
                "quantity": 10,
                "avg_price": 100,
                "avg_cost": 101,
                "current_price": 110,
                "market_value": 1100,
                "unrealized_pnl": 90,
                "unrealized_pct": 8.9,
                "stage": "STAGE_2",
                "rsi_14": 60,
                "relative_strength": 80,
                "stop_price": 95,
                "target_price": 130,
                "reward_risk": 2,
                "exit_trigger": "strategy exit rules",
            }
        ],
        daily_pnl=[
            {
                "date": "2026-05-29",
                "cash": 1000,
                "market_value": 1100,
                "nav": 2100,
                "daily_pnl": 25,
                "daily_return_pct": 1.2,
                "cumulative_return_pct": 2.1,
                "drawdown_pct": -0.5,
                "open_positions": 1,
            }
        ],
        trades=[
            {
                "date": "2026-05-29",
                "strategy_id": "vcp_breakout_v1",
                "symbol": "AAA",
                "side": "BUY",
                "quantity": 10,
                "price": 100,
                "notional": 1000,
                "fees": 1,
                "slippage": 2,
                "cash_effect": -1001,
                "order_id": "ord1",
                "fill_id": "fill1",
            }
        ],
        next_orders=[
            {
                "date": "2026-05-29",
                "order_id": "ord-next",
                "strategy_id": "vcp_breakout_v1",
                "symbol": "BBB",
                "side": "BUY",
                "trade_intent": "ENTRY",
                "quantity": 5,
                "order_type": "MARKET_NEXT_OPEN",
                "signal_reason": "entry rule matched",
                "reference_price": 200,
                "stop_price": 180,
                "target_price": 240,
                "risk_per_share": 20,
                "estimated_risk": 100,
                "estimated_notional": 1000,
            }
        ],
        actions=[
            {
                "timestamp": "2026-05-29",
                "agent": "trading_agent",
                "action": "replay_eod_trades",
                "strategy_id": "vcp_breakout_v1",
                "reason": "unit test",
                "payload": {"fills": 1},
            }
        ],
    )

    sql_text = "\n".join(sql for sql, _ in calls)
    assert result["success"] is True
    assert result["positions"] == 1
    assert result["daily_pnl"] == 1
    assert result["transactions"] == 1
    assert result["next_orders"] == 1
    assert result["agent_actions"] == 1
    assert "portfolio.paper_runs" in sql_text
    assert "portfolio.paper_positions" in sql_text
    assert "portfolio.paper_daily_pnl" in sql_text
    assert "portfolio.paper_transactions" in sql_text
    assert "portfolio.paper_next_orders" in sql_text
    assert "portfolio.paper_agent_actions" in sql_text
    assert "DELETE FROM portfolio.paper_next_orders" in sql_text
    assert "DELETE FROM portfolio.paper_transactions" in sql_text


def test_publish_daily_paper_portfolio_writes_attributed_trades_and_current_book(tmp_path):
    output_dir = tmp_path / "lab"
    strategy_id = "stage2_continuation_v1"
    state_dir = output_dir / "runs" / strategy_id / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "replay_state.json").write_text(
        json.dumps(
            {
                "run_id": "RUN1-stage2",
                "account": {"initial_capital": 100000, "cash": 90000, "realized_pnl": 500},
                "nav_history": [
                    {
                        "timestamp": "2026-05-28",
                        "cash": 90000,
                        "market_value": 10000,
                        "nav": 100000,
                        "open_positions": 1,
                    },
                    {
                        "timestamp": "2026-05-29",
                        "cash": 92000,
                        "market_value": 9500,
                        "nav": 101500,
                        "open_positions": 1,
                    },
                ],
                "positions": [
                    {
                        "symbol": "AAA",
                        "quantity": 10,
                        "avg_price": 100,
                        "avg_cost": 100,
                        "strategy_ids": [strategy_id],
                    }
                ],
                "orders": [
                    {
                        "order_id": "ord-buy",
                        "strategy_id": strategy_id,
                        "symbol": "AAA",
                        "side": "BUY",
                        "submitted_at": "2026-05-27",
                        "order_type": "MARKET_NEXT_OPEN",
                        "reason": "stage2 breakout with volume confirmation",
                    },
                    {
                        "order_id": "ord-sell",
                        "strategy_id": strategy_id,
                        "symbol": "AAA",
                        "side": "SELL",
                        "submitted_at": "2026-05-28",
                        "order_type": "MARKET_NEXT_OPEN",
                        "reason": "exit rule matched",
                    },
                    {
                        "order_id": "ord-next-buy",
                        "strategy_id": strategy_id,
                        "symbol": "BBB",
                        "side": "BUY",
                        "quantity": 5,
                        "submitted_at": "2026-05-29",
                        "order_type": "MARKET_NEXT_OPEN",
                        "reason": "entry rule matched",
                        "status": "SUBMITTED",
                    },
                    {
                        "order_id": "ord-next-sell",
                        "strategy_id": strategy_id,
                        "symbol": "AAA",
                        "side": "SELL",
                        "quantity": 5,
                        "submitted_at": "2026-05-29",
                        "order_type": "MARKET_NEXT_OPEN",
                        "reason": "exit rule matched",
                        "status": "SUBMITTED",
                    },
                ],
                "fills": [
                    {
                        "fill_id": "fill-buy",
                        "order_id": "ord-buy",
                        "strategy_id": strategy_id,
                        "symbol": "AAA",
                        "side": "BUY",
                        "timestamp": "2026-05-28",
                        "price": 100,
                        "quantity": 10,
                        "fees": 1,
                        "slippage": 0.5,
                    },
                    {
                        "fill_id": "fill-sell",
                        "order_id": "ord-sell",
                        "strategy_id": strategy_id,
                        "symbol": "AAA",
                        "side": "SELL",
                        "timestamp": "2026-05-29",
                        "price": 110,
                        "quantity": 5,
                        "fees": 1,
                        "slippage": 0.5,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    features = pd.DataFrame(
        [
            {
                "date": "2026-05-28",
                "symbol": "AAA",
                "close": 100,
                "atr_14": 5,
                "stage": "STAGE_2",
                "rsi_14": 62,
                "relative_strength": 85,
                "sma_20": 95,
                "sma_50": 90,
            },
            {
                "date": "2026-05-29",
                "symbol": "AAA",
                "close": 110,
                "atr_14": 5,
                "stage": "STAGE_2",
                "rsi_14": 68,
                "relative_strength": 88,
                "sma_20": 98,
                "sma_50": 92,
            },
            {
                "date": "2026-05-29",
                "symbol": "BBB",
                "close": 200,
                "atr_14": 10,
                "stage": "STAGE_2",
                "rsi_14": 70,
                "relative_strength": 90,
                "sma_20": 180,
                "sma_50": 170,
            },
        ]
    )
    leaderboard = pd.DataFrame(
        [{"rank": 1, "strategy_id": strategy_id, "name": "Stage 2 Continuation", "rank_score": 10.0}]
    )

    paper = paper_portfolio.publish_daily_paper_portfolio(
        output_dir=output_dir,
        summary={"run_id": "RUN1", "latest_eod_date": "2026-05-29"},
        leaderboard=leaderboard,
        features=features,
        dsn=None,
    )

    trades = pd.read_csv(output_dir / "paper" / "trades.csv")
    next_orders = pd.read_csv(output_dir / "paper" / "next_orders.csv")
    report = (output_dir / "reports" / "paper_portfolio_report.md").read_text(encoding="utf-8")
    sell = trades.loc[trades["side"] == "SELL"].iloc[0]

    assert paper["selected_strategy_id"] == strategy_id
    assert "trade_intent" in trades.columns
    assert "signal_reason" in trades.columns
    assert "entry_price" in trades.columns
    assert "holding_period_days" in trades.columns
    assert "realized_pnl" in trades.columns
    assert "next_orders" in paper["artifacts"]
    assert {"trade_intent", "signal_reason", "reference_price", "estimated_risk"} <= set(next_orders.columns)
    assert set(next_orders["trade_intent"]) == {"ENTRY", "EXIT"}
    assert next_orders.loc[next_orders["symbol"] == "BBB", "estimated_risk"].iloc[0] == 100
    assert trades.loc[trades["side"] == "BUY", "signal_reason"].iloc[0] == "stage2 breakout with volume confirmation"
    assert sell["trade_intent"] == "EXIT"
    assert sell["holding_period_days"] == 1
    assert sell["realized_pnl"] == 49
    assert "## Current Paper Book" in report
    assert "## Today Trade Blotter" in report
    assert "## Next Session Orders" in report
    assert "ord-next-buy" in report
    assert "stage2 breakout with volume confirmation" in report


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
    summary = json.loads((tmp_path / "lab" / "reports" / "strategy_comparison_summary.json").read_text(encoding="utf-8"))
    paper = summary["paper_portfolio"]

    assert result == 0
    assert not leaderboard.empty
    assert "profit_factor" in leaderboard.columns
    assert "cost_drag_pct" in leaderboard.columns
    assert "risk_blocks" in leaderboard.columns
    assert "risk_trims" in leaderboard.columns
    assert summary["stage_source"] == "scores.stage_snapshots"
    assert summary["risk_policy"]["max_gross_exposure_pct"] == 95
    assert "fundamental_coverage" in summary
    assert "rows_with_latest_result" in summary["fundamental_coverage"]
    assert paper["selected_strategy_id"] == leaderboard.iloc[0]["strategy_id"]
    paper_report = (tmp_path / "lab" / "reports" / "paper_portfolio_report.md").read_text(encoding="utf-8")
    assert "| NAV | ₹" in paper_report
    assert "| Cash | ₹" in paper_report
    assert "| Daily P&L | ₹" in paper_report
    comparison_report = (tmp_path / "lab" / "reports" / "strategy_comparison_report.md").read_text(encoding="utf-8")
    assert "## Risk Governance" in comparison_report
    assert "Confidence split" in comparison_report
    assert (tmp_path / "lab" / "paper" / "portfolio_state.json").exists()
    assert (tmp_path / "lab" / "paper" / "positions.csv").exists()
    assert (tmp_path / "lab" / "paper" / "daily_pnl.csv").exists()
    assert (tmp_path / "lab" / "paper" / "trades.csv").exists()
    assert (tmp_path / "lab" / "paper" / "agent_actions.jsonl").exists()
    assert (tmp_path / "lab" / "reports" / "paper_portfolio_report.md").exists()


def test_strategy_lab_governance_ranking_demotes_blocked_strategies():
    leaderboard = pd.DataFrame(
        [
            {
                "rank": 1,
                "strategy_id": "blocked_high_score",
                "critic_verdict": "BLOCK",
                "rank_score": 100.0,
                "total_return_pct": 120.0,
            },
            {
                "rank": 2,
                "strategy_id": "warn_lower_score",
                "critic_verdict": "WARN",
                "rank_score": 10.0,
                "total_return_pct": 15.0,
            },
            {
                "rank": 3,
                "strategy_id": "pass_low_score",
                "critic_verdict": "PASS",
                "rank_score": 1.0,
                "total_return_pct": 2.0,
            },
        ]
    )

    ranked = cli._strategy_lab_governance_rank(leaderboard)

    assert ranked.iloc[0]["strategy_id"] == "pass_low_score"
    assert ranked.iloc[-1]["strategy_id"] == "blocked_high_score"


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
