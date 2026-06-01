from __future__ import annotations

import pandas as pd

from scripts.backfill_historical_stage_snapshots import (
    build_stage_change_rows,
    build_stage_snapshot_rows,
    compute_historical_stage_features,
)


def _rows(symbol: str, closes: list[float]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for idx, close in enumerate(closes):
        rows.append(
            {
                "date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=idx),
                "symbol": symbol,
                "company_name": f"{symbol} Ltd",
                "sector": "Industrials",
                "market_cap_cat": "Large",
                "open": close - 1,
                "high": close + 2,
                "low": close - 2,
                "close": close,
                "volume": 100_000 + idx,
            }
        )
    return rows


def test_compute_historical_stage_features_classifies_stage2_without_lookahead():
    leader = [100.0] * 260 + [101.0 + i for i in range(170)]
    laggard = [320.0 - i * 0.5 for i in range(430)]
    frame = pd.DataFrame(_rows("AAA", leader) + _rows("BBB", laggard))

    features = compute_historical_stage_features(frame, start_date="2025-01-01")
    latest = features.sort_values("date").groupby("symbol").tail(1).set_index("symbol")

    assert latest.loc["AAA", "stage"] == "STAGE_2"
    assert latest.loc["AAA", "stage_score"] > latest.loc["BBB", "stage_score"]
    assert latest.loc["AAA", "relative_strength"] > latest.loc["BBB", "relative_strength"]
    assert latest.loc["BBB", "stage"] in {"STAGE_3", "STAGE_4"}


def test_build_stage_snapshot_rows_emits_schema_ready_records():
    frame = pd.DataFrame(_rows("AAA", [100.0] * 260 + [101.0 + i for i in range(170)]))
    features = compute_historical_stage_features(frame, start_date="2025-01-01")

    rows = build_stage_snapshot_rows(features)

    assert rows
    row = rows[-1]
    assert row["snapshot_date"] == features["date"].max().date()
    assert row["symbol"] == "AAA"
    assert row["stage"] == "STAGE_2"
    assert row["price"] == row["live_price"]
    assert row["price_date"] == row["snapshot_date"]
    assert row["source_csv"] == "historical_stage_backfill:market.equity_eod"


def test_build_stage_change_rows_detects_enter_and_exit_stage2():
    features = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-03"]),
            "symbol": ["AAA", "AAA", "AAA"],
            "company_name": ["AAA Ltd"] * 3,
            "stage": ["STAGE_1", "STAGE_2", "STAGE_3"],
            "stage_score": [30.0, 80.0, 40.0],
            "close": [100.0, 110.0, 104.5],
            "trading_signal": ["HOLD", "BUY", "HOLD"],
        }
    )

    rows = build_stage_change_rows(features)

    assert [row["change_type"] for row in rows] == ["ENTER_STAGE2", "EXIT_STAGE2"]
    assert rows[0]["stage_prev"] == "STAGE_1"
    assert rows[0]["stage_now"] == "STAGE_2"
    assert rows[1]["stage_prev"] == "STAGE_2"
    assert rows[1]["stage_now"] == "STAGE_3"
