from __future__ import annotations

import pandas as pd


def sample_ohlcv() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(
                [
                    "2025-01-01",
                    "2025-01-02",
                    "2025-01-03",
                    "2025-01-06",
                    "2025-01-07",
                    "2025-01-08",
                ]
            ),
            "symbol": ["AAA", "AAA", "AAA", "AAA", "AAA", "AAA"],
            "open": [100.0, 102.0, 105.0, 109.0, 111.0, 106.0],
            "high": [103.0, 106.0, 110.0, 113.0, 112.0, 108.0],
            "low": [99.0, 101.0, 104.0, 108.0, 105.0, 100.0],
            "close": [102.0, 105.0, 109.0, 111.0, 106.0, 101.0],
            "volume": [100000, 120000, 150000, 160000, 170000, 180000],
            "stage": ["STAGE_1", "STAGE_2", "STAGE_2", "STAGE_2", "STAGE_2", "STAGE_3"],
            "rsi_14": [45.0, 56.0, 61.0, 65.0, 48.0, 38.0],
            "sma_50": [98.0, 99.0, 100.0, 101.0, 102.0, 103.0],
            "atr_14": [4.0, 4.0, 4.5, 5.0, 5.0, 5.0],
            "volume_ratio_20d": [0.9, 1.2, 1.3, 1.1, 0.8, 1.4],
        }
    )


def valid_strategy_spec() -> dict:
    return {
        "strategy_id": "stage2_fixture_v1",
        "name": "Stage 2 Fixture Strategy",
        "universe": {"stage": "STAGE_2", "min_price": 50},
        "entry": {
            "all": [
                {"indicator": "stage", "operator": "eq", "value": "STAGE_2"},
                {"indicator": "close", "operator": "above", "value": "sma_50"},
                {"indicator": "rsi_14", "operator": "between", "value": [45, 70]},
            ]
        },
        "risk": {
            "initial_stop": {"type": "atr", "multiple": 2.0},
            "risk_per_trade_pct": 1.0,
            "max_position_pct": 10.0,
        },
        "add_rules": [],
        "exit": {
            "any": [
                {"indicator": "stage", "operator": "in", "value": ["STAGE_3", "STAGE_4"]},
                {"indicator": "close", "operator": "below", "value": "sma_50"},
            ]
        },
    }
