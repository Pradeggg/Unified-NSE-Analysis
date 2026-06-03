from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from portfolio.engine.managed_portfolio import ManagedPortfolioPolicy, build_managed_portfolio, load_policy


def test_load_policy_reads_default_yaml():
    policy = load_policy(Path("portfolio/config/portfolio_policy.yaml"))

    assert policy.start_date == "2025-01-01"
    assert policy.initial_capital == 1_000_000
    assert policy.max_single_stock_pct == 10
    assert policy.max_sector_pct == 25
    assert policy.risk_per_new_position_pct == 1.0
    assert policy.max_portfolio_open_risk_pct == 8


def test_policy_validation_rejects_invalid_risk():
    with pytest.raises(ValueError, match="risk_per_new_position_pct"):
        ManagedPortfolioPolicy(risk_per_new_position_pct=0)


@pytest.mark.parametrize(
    "field",
    [
        "first_add_pct_of_target",
        "second_add_pct_of_target",
        "trim_when_position_pct_above",
        "trim_to_position_pct",
    ],
)
def test_policy_validation_rejects_invalid_add_and_trim_fields(field):
    with pytest.raises(ValueError, match=field):
        ManagedPortfolioPolicy(**{field: 0})


def _features() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": "2025-01-02",
                "symbol": "AAA",
                "open": 101.0,
                "high": 103.0,
                "low": 99.0,
                "close": 100.0,
                "atr_14": 10.0,
                "sector": "Industrials",
                "stage": "STAGE_2",
                "relative_strength": 80.0,
                "rsi_14": 60.0,
            },
            {
                "date": "2025-01-03",
                "symbol": "AAA",
                "open": 111.0,
                "high": 113.0,
                "low": 108.0,
                "close": 110.0,
                "atr_14": 10.0,
                "sector": "Industrials",
                "stage": "STAGE_2",
                "relative_strength": 82.0,
                "rsi_14": 62.0,
            },
            {
                "date": "2025-01-04",
                "symbol": "AAA",
                "open": 89.0,
                "high": 91.0,
                "low": 86.0,
                "close": 88.0,
                "atr_14": 10.0,
                "sector": "Industrials",
                "stage": "STAGE_2",
                "relative_strength": 50.0,
                "rsi_14": 40.0,
            },
        ]
    )


def test_managed_portfolio_enters_with_risk_based_half_target(tmp_path):
    policy = ManagedPortfolioPolicy(initial_capital=100_000, max_single_stock_pct=20)
    orders = [
        {
            "order_id": "ord1",
            "strategy_id": "s1",
            "symbol": "AAA",
            "side": "BUY",
            "quantity": 999,
            "submitted_at": "2025-01-02",
            "reason": "entry rule matched",
        }
    ]

    result = build_managed_portfolio(
        output_dir=tmp_path,
        run_id="RUN1",
        selected_strategy_id="s1",
        selected_strategy_name="Strategy One",
        features=_features(),
        strategy_orders=orders,
        policy=policy,
        llm_council="off",
    )

    enter = [row for row in result["decisions"] if row["action"] == "ENTER"][0]
    assert enter["quantity"] == 25
    assert enter["stop_price"] == 80.0
    assert enter["target_price"] == 140.0
    assert enter["risk_amount"] == 500.0
    assert result["state"]["cash"] == 97_500.0


def test_managed_portfolio_skips_when_sector_cap_exceeded(tmp_path):
    policy = ManagedPortfolioPolicy(initial_capital=100_000, max_sector_pct=1, max_single_stock_pct=20)
    orders = [
        {
            "order_id": "ord1",
            "strategy_id": "s1",
            "symbol": "AAA",
            "side": "BUY",
            "quantity": 999,
            "submitted_at": "2025-01-02",
            "reason": "entry rule matched",
        }
    ]

    result = build_managed_portfolio(
        output_dir=tmp_path,
        run_id="RUN1",
        selected_strategy_id="s1",
        selected_strategy_name="Strategy One",
        features=_features(),
        strategy_orders=orders,
        policy=policy,
        llm_council="off",
    )

    skip = [row for row in result["decisions"] if row["action"] == "SKIP"][0]
    assert "SECTOR_CAP" in skip["reason_codes"]
    assert result["state"]["positions"] == {}


def test_managed_portfolio_uses_mark_to_market_prices_for_sector_cap(tmp_path):
    features = pd.DataFrame(
        [
            {
                "date": "2025-01-02",
                "symbol": "AAA",
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0,
                "atr_14": 10.0,
                "sector": "Industrials",
                "stage": "STAGE_2",
                "relative_strength": 80.0,
                "rsi_14": 60.0,
            },
            {
                "date": "2025-01-03",
                "symbol": "AAA",
                "open": 1000.0,
                "high": 1001.0,
                "low": 999.0,
                "close": 1000.0,
                "atr_14": 10.0,
                "sector": "Industrials",
                "stage": "STAGE_2",
                "relative_strength": 85.0,
                "rsi_14": 65.0,
            },
            {
                "date": "2025-01-03",
                "symbol": "BBB",
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0,
                "atr_14": 10.0,
                "sector": "Industrials",
                "stage": "STAGE_2",
                "relative_strength": 82.0,
                "rsi_14": 62.0,
            },
        ]
    )
    policy = ManagedPortfolioPolicy(initial_capital=100_000, max_sector_pct=20, max_single_stock_pct=50)
    orders = [
        {
            "order_id": "ord1",
            "strategy_id": "s1",
            "symbol": "AAA",
            "side": "BUY",
            "quantity": 999,
            "submitted_at": "2025-01-02",
            "reason": "entry rule matched",
        },
        {
            "order_id": "ord2",
            "strategy_id": "s1",
            "symbol": "BBB",
            "side": "BUY",
            "quantity": 999,
            "submitted_at": "2025-01-03",
            "reason": "entry rule matched",
        },
    ]

    result = build_managed_portfolio(
        output_dir=tmp_path,
        run_id="RUN1",
        selected_strategy_id="s1",
        selected_strategy_name="Strategy One",
        features=features,
        strategy_orders=orders,
        policy=policy,
        llm_council="off",
    )

    assert [row["action"] for row in result["decisions"]] == ["ENTER", "SKIP"]
    skip = result["decisions"][1]
    assert skip["symbol"] == "BBB"
    assert skip["reason_codes"] == "SECTOR_CAP"
    assert result["state"]["positions"].keys() == {"AAA"}


def test_managed_portfolio_skips_add_when_combined_position_exceeds_stock_cap(tmp_path):
    policy = ManagedPortfolioPolicy(initial_capital=100_000, max_single_stock_pct=3, max_sector_pct=20)
    orders = [
        {
            "order_id": "ord1",
            "strategy_id": "s1",
            "symbol": "AAA",
            "side": "BUY",
            "quantity": 999,
            "submitted_at": "2025-01-02",
            "reason": "entry rule matched",
        },
        {
            "order_id": "ord2",
            "strategy_id": "s1",
            "symbol": "AAA",
            "side": "BUY",
            "quantity": 999,
            "submitted_at": "2025-01-03",
            "reason": "add rule matched",
        },
    ]

    result = build_managed_portfolio(
        output_dir=tmp_path,
        run_id="RUN1",
        selected_strategy_id="s1",
        selected_strategy_name="Strategy One",
        features=_features(),
        strategy_orders=orders,
        policy=policy,
        llm_council="off",
    )

    assert [row["action"] for row in result["decisions"]] == ["ENTER", "SKIP"]
    skip = result["decisions"][1]
    assert "STOCK_CAP" in skip["reason_codes"]
    assert result["state"]["positions"]["AAA"]["quantity"] == 25


def test_managed_portfolio_audits_order_when_feature_date_is_missing(tmp_path):
    policy = ManagedPortfolioPolicy(initial_capital=100_000, max_single_stock_pct=20)
    orders = [
        {
            "order_id": "ord_missing",
            "strategy_id": "s1",
            "symbol": "AAA",
            "side": "BUY",
            "quantity": 999,
            "submitted_at": "2025-01-05",
            "reason": "entry rule matched",
        }
    ]

    result = build_managed_portfolio(
        output_dir=tmp_path,
        run_id="RUN1",
        selected_strategy_id="s1",
        selected_strategy_name="Strategy One",
        features=_features(),
        strategy_orders=orders,
        policy=policy,
        llm_council="off",
    )

    assert len(result["decisions"]) == 1
    skip = result["decisions"][0]
    assert skip["action"] == "SKIP"
    assert skip["reason_codes"] == "MISSING_FEATURE_DATE"
    assert result["state"]["positions"] == {}


def test_managed_portfolio_ignores_orders_before_policy_start_date(tmp_path):
    features = pd.concat(
        [
            pd.DataFrame(
                [
                    {
                        "date": "2024-12-31",
                        "symbol": "AAA",
                        "open": 100.0,
                        "high": 101.0,
                        "low": 99.0,
                        "close": 100.0,
                        "atr_14": 10.0,
                        "sector": "Industrials",
                        "stage": "STAGE_2",
                        "relative_strength": 80.0,
                        "rsi_14": 60.0,
                    }
                ]
            ),
            _features(),
        ],
        ignore_index=True,
    )
    policy = ManagedPortfolioPolicy(initial_capital=100_000, max_single_stock_pct=20, start_date="2025-01-01")
    orders = [
        {
            "order_id": "ord_before_start",
            "strategy_id": "s1",
            "symbol": "AAA",
            "side": "BUY",
            "quantity": 999,
            "submitted_at": "2024-12-31",
            "reason": "entry rule matched",
        }
    ]

    result = build_managed_portfolio(
        output_dir=tmp_path,
        run_id="RUN1",
        selected_strategy_id="s1",
        selected_strategy_name="Strategy One",
        features=features,
        strategy_orders=orders,
        policy=policy,
        llm_council="off",
    )

    assert result["decisions"] == []
    assert result["state"]["positions"] == {}
    assert result["state"]["as_of"] == "2025-01-04"


def test_managed_portfolio_exits_on_strategy_sell(tmp_path):
    policy = ManagedPortfolioPolicy(initial_capital=100_000, max_single_stock_pct=20)
    orders = [
        {
            "order_id": "ord1",
            "strategy_id": "s1",
            "symbol": "AAA",
            "side": "BUY",
            "quantity": 999,
            "submitted_at": "2025-01-02",
            "reason": "entry rule matched",
        },
        {
            "order_id": "ord2",
            "strategy_id": "s1",
            "symbol": "AAA",
            "side": "SELL",
            "quantity": 999,
            "submitted_at": "2025-01-04",
            "reason": "exit rule matched",
        },
    ]

    result = build_managed_portfolio(
        output_dir=tmp_path,
        run_id="RUN1",
        selected_strategy_id="s1",
        selected_strategy_name="Strategy One",
        features=_features(),
        strategy_orders=orders,
        policy=policy,
        llm_council="off",
    )

    actions = [row["action"] for row in result["decisions"]]
    assert "ENTER" in actions
    assert "EXIT" in actions
    assert result["state"]["positions"] == {}


def test_managed_portfolio_writes_artifacts(tmp_path):
    policy = ManagedPortfolioPolicy(initial_capital=100_000, max_single_stock_pct=20)
    orders = [{"order_id": "ord1", "strategy_id": "s1", "symbol": "AAA", "side": "BUY", "quantity": 999, "submitted_at": "2025-01-02", "reason": "entry rule matched"}]

    result = build_managed_portfolio(
        output_dir=tmp_path,
        run_id="RUN1",
        selected_strategy_id="s1",
        selected_strategy_name="Strategy One",
        features=_features(),
        strategy_orders=orders,
        policy=policy,
        llm_council="optional",
    )

    managed_dir = tmp_path / "managed"
    assert (managed_dir / "portfolio_policy.yaml").exists()
    assert (managed_dir / "managed_portfolio_state.json").exists()
    assert (managed_dir / "managed_positions.csv").exists()
    assert (managed_dir / "managed_orders.csv").exists()
    assert (managed_dir / "managed_decisions.csv").exists()
    assert (managed_dir / "managed_daily_pnl.csv").exists()
    assert (managed_dir / "llm_council_review.jsonl").exists()
    assert result["artifacts"]["state"].endswith("managed_portfolio_state.json")
