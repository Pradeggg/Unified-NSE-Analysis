import pandas as pd

from terminal.recommendation_report import (
    RecommendationInputData,
    TechnicalProfile,
    build_recommendation_evidence_pack,
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


def _history(symbol: str, start: float = 100.0, rows: int = 240) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": symbol,
                "trade_date": pd.Timestamp("2025-09-01") + pd.Timedelta(days=idx),
                "open": start + idx - 1,
                "high": start + idx + 2,
                "low": start + idx - 2,
                "close": start + idx,
                "volume": 1000 + idx,
            }
            for idx in range(rows)
        ]
    )


def test_build_evidence_pack_contains_indices_sectors_stocks_and_portfolio():
    data = RecommendationInputData(
        index_history=pd.concat([_history("NIFTY 50"), _history("NIFTY BANK", 120.0)]),
        equity_history=pd.concat([_history("AAA"), _history("BBB", 80.0)]),
        snapshots=pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "sector": "Capital Goods",
                    "stage": "STAGE_2",
                    "technical_score": 82,
                    "relative_strength": 24,
                    "trading_signal": "BUY",
                    "investment_score": 76,
                },
                {
                    "symbol": "BBB",
                    "sector": "Chemicals",
                    "stage": "STAGE_4",
                    "technical_score": 18,
                    "relative_strength": -12,
                    "trading_signal": "SELL",
                    "investment_score": 30,
                },
            ]
        ),
        fundamentals=pd.DataFrame(
            [
                {"symbol": "AAA", "roe": 18, "roce": 22, "stock_pe": 24, "interest_coverage": 8},
                {"symbol": "BBB", "roe": 5, "roce": 7, "stock_pe": 55, "interest_coverage": 1.2},
            ]
        ),
        portfolio=pd.DataFrame([{"symbol": "AAA", "qty": 10, "avg_cost": 150.0}]),
        watchlist=["BBB"],
    )

    pack = build_recommendation_evidence_pack(data, top_n=10)

    assert pack.as_of
    assert "NIFTY 50" in pack.indices
    assert "Capital Goods" in pack.sectors
    assert "AAA" in pack.stocks
    assert "BBB" in pack.stocks
    assert "AAA" in pack.portfolio
    assert "BBB" in pack.portfolio
    assert pack.source_trail["equity_history"]["rows"] == 480
    assert pack.missing_evidence == {}
