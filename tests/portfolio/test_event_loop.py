from __future__ import annotations

import pandas as pd

from portfolio.engine.event_loop import ReplayConfig, run_replay
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
