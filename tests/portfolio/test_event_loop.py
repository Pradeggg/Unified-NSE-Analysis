from __future__ import annotations

import pandas as pd

from portfolio.engine.event_loop import ReplayConfig, ReplayRiskPolicy, run_replay
from tests.portfolio.fixtures import sample_ohlcv, valid_strategy_spec


def _event_names(result) -> list[str]:
    return [event.event_type for event in result.events]


def _with_exit_fill_row() -> pd.DataFrame:
    rows = sample_ohlcv()
    return pd.concat(
        [
            rows,
            pd.DataFrame(
                {
                    "date": pd.to_datetime(["2025-01-09"]),
                    "symbol": ["AAA"],
                    "open": [99.0],
                    "high": [100.0],
                    "low": [95.0],
                    "close": [96.0],
                    "volume": [190000],
                    "stage": ["STAGE_3"],
                    "rsi_14": [35.0],
                    "sma_50": [103.0],
                    "atr_14": [5.0],
                    "volume_ratio_20d": [1.1],
                }
            ),
        ],
        ignore_index=True,
    )


def _strategy(strategy_id: str, *, stage_exit: bool = True) -> dict:
    spec = valid_strategy_spec()
    spec["strategy_id"] = strategy_id
    if not stage_exit:
        spec["exit"] = {"any": [{"indicator": "close", "operator": "below", "value": "sma_50"}]}
    return spec


def _multi_symbol_rows(symbols: list[str]) -> pd.DataFrame:
    template = sample_ohlcv()
    first_signal = template[template["date"].isin(pd.to_datetime(["2025-01-02", "2025-01-03"]))]
    frames = []
    for index, symbol in enumerate(symbols):
        rows = first_signal.copy()
        rows["symbol"] = symbol
        rows["open"] = rows["open"] + index
        rows["high"] = rows["high"] + index
        rows["low"] = rows["low"] + index
        rows["close"] = rows["close"] + index
        rows["sma_50"] = rows["sma_50"] + index
        frames.append(rows)
    return pd.concat(frames, ignore_index=True)


def _risk_rows(records: list[dict]) -> pd.DataFrame:
    defaults = {
        "open": 100.0,
        "high": 105.0,
        "low": 99.0,
        "close": 102.0,
        "volume": 100000,
        "stage": "STAGE_2",
        "rsi_14": 55.0,
        "sma_50": 90.0,
        "atr_14": 5.0,
        "volume_ratio_20d": 1.2,
        "sector": "Industrials",
    }
    rows = [{**defaults, **record} for record in records]
    out = pd.DataFrame(rows)
    out["date"] = pd.to_datetime(out["date"])
    return out


def test_replay_emits_deterministic_events_and_equity_snapshots():
    result = run_replay(
        sample_ohlcv(),
        [valid_strategy_spec()],
        ReplayConfig(initial_capital=100_000.0),
    )

    assert _event_names(result)[:4] == [
        "MarketDataEvent",
        "PortfolioSnapshotEvent",
        "MarketDataEvent",
        "SignalEvent",
    ]
    assert result.equity_snapshots == result.account.nav_history
    assert [row["timestamp"] for row in result.equity_snapshots] == [
        "2025-01-01",
        "2025-01-02",
        "2025-01-03",
        "2025-01-06",
        "2025-01-07",
        "2025-01-08",
    ]


def test_entry_signal_fills_on_next_symbol_row_open_without_same_bar_lookahead():
    rows = sample_ohlcv()
    rows.loc[rows["date"].eq(pd.Timestamp("2025-01-03")), "open"] = 107.0

    result = run_replay(rows, [valid_strategy_spec()], ReplayConfig(initial_capital=100_000.0))

    buy_order = result.orders[0]
    buy_fill = result.fills[0]
    assert buy_order.submitted_at == "2025-01-02"
    assert buy_fill.timestamp == "2025-01-03"
    assert buy_fill.price == 107.0
    assert buy_fill.timestamp != buy_order.submitted_at


def test_entry_and_exit_flow_round_trips_position_when_next_open_exists():
    result = run_replay(
        _with_exit_fill_row(),
        [valid_strategy_spec()],
        ReplayConfig(initial_capital=100_000.0),
    )

    assert [fill.side.value for fill in result.fills] == ["BUY", "SELL"]
    assert result.orders[1].submitted_at == "2025-01-08"
    assert result.fills[1].timestamp == "2025-01-09"
    assert result.fills[1].price == 99.0
    assert result.account.positions == {}
    assert result.equity_snapshots[-1]["open_positions"] == 0


def test_replay_is_exactly_repeatable_for_same_inputs():
    first = run_replay(sample_ohlcv(), [valid_strategy_spec()], ReplayConfig(initial_capital=100_000.0))
    second = run_replay(sample_ohlcv(), [valid_strategy_spec()], ReplayConfig(initial_capital=100_000.0))

    assert first.to_audit_dict() == second.to_audit_dict()


def test_two_strategies_on_same_symbol_exit_only_their_owned_quantities():
    rows = _with_exit_fill_row()

    result = run_replay(
        rows,
        [_strategy("stage2_fixture_a"), _strategy("stage2_fixture_b")],
        ReplayConfig(initial_capital=100_000.0),
    )

    sells = [fill for fill in result.fills if fill.side.value == "SELL"]
    buys = [fill for fill in result.fills if fill.side.value == "BUY"]
    assert len(buys) == 2
    assert len(sells) == 2
    assert [fill.strategy_id for fill in sells] == ["stage2_fixture_a", "stage2_fixture_b"]
    assert [fill.quantity for fill in sells] == [fill.quantity for fill in buys]
    assert sum(fill.quantity for fill in sells) == sum(fill.quantity for fill in buys)
    assert result.account.positions == {}


def test_pending_buys_reserve_cash_so_many_signals_do_not_overcommit_or_crash():
    spec = valid_strategy_spec()
    spec["risk"]["max_position_pct"] = 15.0

    result = run_replay(
        _multi_symbol_rows(["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH", "III", "JJJ", "KKK", "LLL"]),
        [spec],
        ReplayConfig(initial_capital=1_000.0, max_position_pct=50.0),
    )

    assert len(result.orders) < 12
    assert result.fills
    assert result.account.cash >= 0.0
    assert all(order.symbol not in {"KKK", "LLL"} for order in result.orders)


def test_risk_policy_blocks_entry_that_would_exceed_gross_exposure_cap():
    spec = valid_strategy_spec()
    spec["risk"]["max_position_pct"] = 50.0

    result = run_replay(
        _risk_rows(
            [
                {"date": "2025-01-02", "symbol": "AAA"},
                {"date": "2025-01-03", "symbol": "AAA"},
            ]
        ),
        [spec],
        ReplayConfig(
            initial_capital=100_000.0,
            risk_policy=ReplayRiskPolicy(max_gross_exposure_pct=10.0, max_single_stock_pct=100.0),
        ),
    )

    assert result.orders == []
    assert result.risk_events[-1]["reason_codes"] == ["GROSS_EXPOSURE_CAP"]


def test_risk_policy_blocks_entry_that_would_exceed_single_stock_cap():
    result = run_replay(
        _risk_rows(
            [
                {"date": "2025-01-02", "symbol": "AAA"},
                {"date": "2025-01-03", "symbol": "AAA"},
            ]
        ),
        [valid_strategy_spec()],
        ReplayConfig(
            initial_capital=100_000.0,
            risk_policy=ReplayRiskPolicy(max_single_stock_pct=5.0),
        ),
    )

    assert result.orders == []
    assert result.risk_events[-1]["reason_codes"] == ["STOCK_CAP"]


def test_risk_policy_counts_pending_orders_when_enforcing_sector_cap():
    spec = valid_strategy_spec()
    spec["risk"]["max_position_pct"] = 10.0

    result = run_replay(
        _risk_rows(
            [
                {"date": "2025-01-02", "symbol": "AAA", "sector": "Banks"},
                {"date": "2025-01-02", "symbol": "BBB", "sector": "Banks"},
                {"date": "2025-01-03", "symbol": "AAA", "sector": "Banks"},
                {"date": "2025-01-03", "symbol": "BBB", "sector": "Banks"},
            ]
        ),
        [spec],
        ReplayConfig(
            initial_capital=100_000.0,
            risk_policy=ReplayRiskPolicy(max_sector_pct=15.0),
        ),
    )

    assert [order.symbol for order in result.orders] == ["AAA"]
    assert result.risk_events[-1]["symbol"] == "BBB"
    assert result.risk_events[-1]["reason_codes"] == ["SECTOR_CAP"]


def test_risk_policy_pauses_new_buys_after_drawdown_threshold_is_breached():
    spec = _strategy("stage2_fixture_v1", stage_exit=False)
    spec["exit"] = {"any": [{"indicator": "close", "operator": "below", "value": 0.0}]}
    spec["risk"]["max_position_pct"] = 50.0

    result = run_replay(
        _risk_rows(
            [
                {"date": "2025-01-02", "symbol": "AAA", "close": 100.0},
                {"date": "2025-01-03", "symbol": "AAA", "open": 100.0, "low": 35.0, "close": 40.0},
                {"date": "2025-01-06", "symbol": "AAA", "low": 35.0, "close": 40.0},
                {"date": "2025-01-06", "symbol": "BBB", "close": 100.0},
                {"date": "2025-01-07", "symbol": "BBB", "close": 100.0},
            ]
        ),
        [spec],
        ReplayConfig(
            initial_capital=100_000.0,
            risk_policy=ReplayRiskPolicy(
                drawdown_pause_pct=-5.0,
                max_single_stock_pct=100.0,
                max_gross_exposure_pct=100.0,
                max_sector_pct=100.0,
                trim_when_position_pct_above=100.0,
            ),
        ),
    )

    assert [order.symbol for order in result.orders] == ["AAA"]
    assert any(event["symbol"] == "BBB" and event["reason_codes"] == ["DRAWDOWN_PAUSE"] for event in result.risk_events)


def test_risk_policy_blocks_new_buys_after_turnover_cap_is_reached():
    spec = valid_strategy_spec()
    spec["risk"]["max_position_pct"] = 20.0

    result = run_replay(
        _risk_rows(
            [
                {"date": "2025-01-02", "symbol": "AAA"},
                {"date": "2025-01-03", "symbol": "AAA"},
                {"date": "2025-01-06", "symbol": "BBB"},
                {"date": "2025-01-07", "symbol": "BBB"},
            ]
        ),
        [spec],
        ReplayConfig(
            initial_capital=100_000.0,
            risk_policy=ReplayRiskPolicy(
                max_turnover_pct=10.0,
                max_single_stock_pct=100.0,
                max_sector_pct=100.0,
                trim_when_position_pct_above=100.0,
            ),
        ),
    )

    assert [order.symbol for order in result.orders] == ["AAA"]
    assert any(event["symbol"] == "BBB" and event["reason_codes"] == ["TURNOVER_CAP"] for event in result.risk_events)


def test_risk_policy_blocks_add_when_stage2_position_drifts_to_stage1():
    spec = _strategy("stage2_fixture_v1", stage_exit=False)
    spec["exit"] = {"any": [{"indicator": "close", "operator": "below", "value": 0.0}]}
    spec["add_rules"] = [
        {
            "kind": "pullback_add",
            "indicator": "close",
            "operator": "above",
            "value": "sma_50",
            "size_pct": 5.0,
            "timeframe": "daily",
        }
    ]

    result = run_replay(
        _risk_rows(
            [
                {"date": "2025-01-02", "symbol": "AAA", "stage": "STAGE_2"},
                {"date": "2025-01-03", "symbol": "AAA", "stage": "STAGE_2", "low": 75.0, "close": 80.0},
                {"date": "2025-01-06", "symbol": "AAA", "stage": "STAGE_1"},
                {"date": "2025-01-07", "symbol": "AAA", "stage": "STAGE_1"},
            ]
        ),
        [spec],
        ReplayConfig(
            initial_capital=100_000.0,
            risk_policy=ReplayRiskPolicy(block_stage1_adds=True, max_single_stock_pct=100.0),
        ),
    )

    assert len([order for order in result.orders if order.side.value == "BUY"]) == 1
    assert any(event["symbol"] == "AAA" and event["reason_codes"] == ["STAGE_DRIFT"] for event in result.risk_events)


def test_risk_policy_generates_trim_order_for_overweight_position():
    spec = _strategy("stage2_fixture_v1", stage_exit=False)
    spec["exit"] = {"any": [{"indicator": "close", "operator": "below", "value": 0.0}]}
    spec["risk"]["max_position_pct"] = 50.0

    result = run_replay(
        _risk_rows(
            [
                {"date": "2025-01-02", "symbol": "AAA", "close": 100.0},
                {"date": "2025-01-03", "symbol": "AAA", "open": 100.0, "high": 205.0, "close": 200.0},
                {"date": "2025-01-06", "symbol": "AAA", "open": 200.0, "high": 205.0, "close": 200.0},
                {"date": "2025-01-07", "symbol": "AAA", "open": 200.0, "high": 205.0, "close": 200.0},
            ]
        ),
        [spec],
        ReplayConfig(
            initial_capital=100_000.0,
            risk_policy=ReplayRiskPolicy(
                trim_when_position_pct_above=20.0,
                trim_to_position_pct=10.0,
                max_single_stock_pct=100.0,
                max_gross_exposure_pct=100.0,
            ),
        ),
    )

    trim_orders = [order for order in result.orders if order.side.value == "SELL" and order.reason == "risk trim"]
    assert len(trim_orders) == 1
    assert trim_orders[0].quantity > 0


def test_sparse_multi_symbol_nav_uses_last_known_close_for_missing_held_symbols():
    rows = pd.concat(
        [
            _multi_symbol_rows(["AAA", "BBB"]),
            pd.DataFrame(
                {
                    "date": pd.to_datetime(["2025-01-06"]),
                    "symbol": ["BBB"],
                    "open": [110.0],
                    "high": [115.0],
                    "low": [109.0],
                    "close": [112.0],
                    "volume": [150000],
                    "stage": ["STAGE_2"],
                    "rsi_14": [60.0],
                    "sma_50": [100.0],
                    "atr_14": [5.0],
                    "volume_ratio_20d": [1.2],
                }
            ),
        ],
        ignore_index=True,
    )

    result = run_replay(rows, [valid_strategy_spec()], ReplayConfig(initial_capital=10_000.0))

    snapshot = result.equity_snapshots[-1]
    positions = result.account.positions
    expected_market_value = (
        positions["AAA"].quantity * 109.0
        + positions["BBB"].quantity * 112.0
    )
    assert snapshot["timestamp"] == "2025-01-06"
    assert snapshot["market_value"] == expected_market_value


def test_null_and_empty_symbols_are_dropped_before_event_or_order_generation():
    rows = pd.concat(
        [
            sample_ohlcv().iloc[[1, 2]],
            pd.DataFrame(
                {
                    "date": pd.to_datetime(["2025-01-02", "2025-01-02", "2025-01-02"]),
                    "symbol": [None, "", "   "],
                    "open": [100.0, 100.0, 100.0],
                    "high": [101.0, 101.0, 101.0],
                    "low": [99.0, 99.0, 99.0],
                    "close": [100.0, 100.0, 100.0],
                    "volume": [1, 1, 1],
                    "stage": ["STAGE_2", "STAGE_2", "STAGE_2"],
                    "rsi_14": [55.0, 55.0, 55.0],
                    "sma_50": [90.0, 90.0, 90.0],
                    "atr_14": [3.0, 3.0, 3.0],
                    "volume_ratio_20d": [1.0, 1.0, 1.0],
                }
            ),
        ],
        ignore_index=True,
    )

    result = run_replay(rows, [valid_strategy_spec()], ReplayConfig(initial_capital=100_000.0))

    emitted_symbols = {event.symbol for event in result.events if event.symbol is not None}
    ordered_symbols = {order.symbol for order in result.orders}
    assert "NAN" not in emitted_symbols
    assert "NONE" not in emitted_symbols
    assert "" not in emitted_symbols
    assert emitted_symbols == {"AAA"}
    assert ordered_symbols == {"AAA"}


def test_string_sentinel_symbols_are_dropped_without_cash_use():
    rows = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-02", "2025-01-02", "2025-01-03", "2025-01-03"]),
            "symbol": ["None", "nan", "NaN", "NULL"],
            "open": [100.0, 100.0, 101.0, 101.0],
            "high": [102.0, 102.0, 103.0, 103.0],
            "low": [99.0, 99.0, 100.0, 100.0],
            "close": [101.0, 101.0, 102.0, 102.0],
            "volume": [100000, 100000, 100000, 100000],
            "stage": ["STAGE_2", "STAGE_2", "STAGE_2", "STAGE_2"],
            "rsi_14": [55.0, 55.0, 55.0, 55.0],
            "sma_50": [90.0, 90.0, 90.0, 90.0],
            "atr_14": [3.0, 3.0, 3.0, 3.0],
            "volume_ratio_20d": [1.0, 1.0, 1.0, 1.0],
        }
    )

    result = run_replay(rows, [valid_strategy_spec()], ReplayConfig(initial_capital=100_000.0))

    emitted_symbols = {event.symbol for event in result.events if event.symbol is not None}
    assert emitted_symbols == set()
    assert result.orders == []
    assert result.fills == []
    assert result.account.cash == 100_000.0


def test_exposed_positions_remove_strategy_after_partial_multi_strategy_exit():
    rows = pd.concat(
        [
            sample_ohlcv().iloc[[1, 2]],
            pd.DataFrame(
                {
                    "date": pd.to_datetime(["2025-01-06", "2025-01-07"]),
                    "symbol": ["AAA", "AAA"],
                    "open": [109.0, 111.0],
                    "high": [113.0, 112.0],
                    "low": [108.0, 105.0],
                    "close": [96.0, 106.0],
                    "volume": [160000, 170000],
                    "stage": ["STAGE_2", "STAGE_2"],
                    "rsi_14": [65.0, 48.0],
                    "sma_50": [101.0, 102.0],
                    "atr_14": [5.0, 5.0],
                    "volume_ratio_20d": [1.1, 0.8],
                }
            ),
        ],
        ignore_index=True,
    )

    still_long_strategy = _strategy("stage2_fixture_b", stage_exit=False)
    still_long_strategy["exit"] = {"any": [{"indicator": "close", "operator": "below", "value": 0.0}]}

    result = run_replay(
        rows,
        [_strategy("stage2_fixture_a"), still_long_strategy],
        ReplayConfig(initial_capital=100_000.0),
    )

    assert [fill.side.value for fill in result.fills] == ["BUY", "BUY", "SELL"]
    remaining_buy = next(fill for fill in result.fills if fill.strategy_id == "stage2_fixture_b")
    assert result.positions == [
        {
            "symbol": "AAA",
            "quantity": remaining_buy.quantity,
            "avg_price": 105.0,
            "avg_cost": 105.0,
            "strategy_ids": ("stage2_fixture_b",),
        }
    ]
