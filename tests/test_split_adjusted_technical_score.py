from __future__ import annotations

import numpy as np
import pandas as pd

from fixed_nse_universe_analysis import calculate_tech_score, determine_trading_signal
from screeners import run_stage_screener
from terminal import tools as terminal_tools


def test_calculate_tech_score_adjusts_pre_split_history_for_rs_and_trend():
    dates = pd.bdate_range("2026-01-01", periods=90)
    adjusted_close = np.linspace(100.0, 150.0, len(dates))
    raw_close = adjusted_close.copy()
    raw_close[:50] *= 10.0

    stock_data = pd.DataFrame(
        {
            "SYMBOL": "SPLITCO",
            "TIMESTAMP": dates,
            "OPEN": raw_close * 0.99,
            "HIGH": raw_close * 1.02,
            "LOW": raw_close * 0.98,
            "CLOSE": raw_close,
            "LAST": raw_close,
            "PREVCLOSE": np.r_[np.nan, raw_close[:-1]],
            "TOTTRDQTY": np.r_[np.full(89, 100_000), 220_000],
        }
    )
    index_data = pd.DataFrame(
        {
            "SYMBOL": "NIFTY 500",
            "TIMESTAMP": dates,
            "CLOSE": np.linspace(20_000.0, 20_800.0, len(dates)),
        }
    )
    fundamental_data = pd.DataFrame(
        {"symbol": ["SPLITCO"], "ENHANCED_FUND_SCORE": [83.55]}
    )

    result = calculate_tech_score(stock_data, index_data, fundamental_data, "SPLITCO")

    assert result["relative_strength"] > 10.0
    assert result["trend"] in {"BULLISH", "STRONG_BULLISH"}
    assert result["score"] >= 65.0
    assert determine_trading_signal(result["score"]) == "BUY"


def test_stage_screener_adjusts_pre_split_history_for_stage_classification():
    dates = pd.bdate_range("2025-07-01", periods=220)
    adjusted_close = np.linspace(100.0, 180.0, len(dates))
    raw_close = adjusted_close.copy()
    raw_close[:120] *= 10.0

    history = pd.DataFrame(
        {
            "SYMBOL": "SPLITCO",
            "TIMESTAMP": dates,
            "OPEN": raw_close * 0.99,
            "HIGH": raw_close * 1.02,
            "LOW": raw_close * 0.98,
            "CLOSE": raw_close,
            "LAST": raw_close,
            "PREVCLOSE": np.r_[np.nan, raw_close[:-1]],
            "TOTTRDQTY": np.full(len(dates), 100_000),
        }
    )
    candidates = pd.DataFrame(
        {
            "SYMBOL": ["SPLITCO"],
            "CLOSE": [raw_close[-1]],
            "RELATIVE_STRENGTH": [25.0],
            "RSI": [62.0],
        }
    )

    result = run_stage_screener(candidates, history=history)

    assert result.loc[0, "STAGE"] == "STAGE_2"
    assert result.loc[0, "SMA_50"] > result.loc[0, "SMA_200"]


def test_terminal_technical_setup_adjusts_pre_split_history(monkeypatch):
    dates = pd.bdate_range("2025-07-01", periods=220)
    adjusted_close = np.linspace(100.0, 180.0, len(dates))
    raw_close = adjusted_close.copy()
    raw_close[:120] *= 10.0

    history = pd.DataFrame(
        {
            "SYMBOL": "SPLITCO",
            "TIMESTAMP": dates,
            "OPEN": raw_close * 0.99,
            "HIGH": raw_close * 1.02,
            "LOW": raw_close * 0.98,
            "CLOSE": raw_close,
            "TOTTRDQTY": np.full(len(dates), 100_000),
        }
    )

    monkeypatch.setattr(terminal_tools, "_pg_read_df", lambda *_args, **_kwargs: history)

    result = terminal_tools.get_technical_setup("SPLITCO")

    assert result["sma50"] > result["sma200"]
    assert result["sma200"] < result["price"]
