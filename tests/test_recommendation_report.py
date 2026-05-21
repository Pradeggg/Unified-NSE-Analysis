import pandas as pd

from terminal.recommendation_report import (
    TechnicalProfile,
    build_technical_profile,
    pct_change_from_lookback,
)


def test_pct_change_from_lookback_uses_nearest_prior_bar():
    frame = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "close": 100.0},
            {"trade_date": "2026-01-08", "close": 110.0},
            {"trade_date": "2026-02-01", "close": 121.0},
        ]
    )

    assert pct_change_from_lookback(frame, "2026-02-01", days=7) == 10.0


def test_build_technical_profile_computes_grounded_fields():
    rows = []
    for idx in range(240):
        close = 100.0 + idx
        rows.append(
            {
                "trade_date": pd.Timestamp("2025-09-01") + pd.Timedelta(days=idx),
                "open": close - 1,
                "high": close + 2,
                "low": close - 2,
                "close": close,
                "volume": 1000 + idx,
            }
        )
    frame = pd.DataFrame(rows)

    profile = build_technical_profile("AAA", frame, benchmark_frame=frame)

    assert isinstance(profile, TechnicalProfile)
    assert profile.subject == "AAA"
    assert profile.latest_close == 339.0
    assert profile.sma20 is not None
    assert profile.sma50 is not None
    assert profile.sma200 is not None
    assert profile.price_above_sma20 is True
    assert profile.price_above_sma50 is True
    assert profile.price_above_sma200 is True
    assert profile.rsi14 is not None
    assert profile.macd_hist is not None
    assert profile.trend_label in {"bullish", "constructive"}
    assert profile.missing_evidence == []
