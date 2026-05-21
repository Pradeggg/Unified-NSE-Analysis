import pandas as pd

from terminal.recommendation_report import (
    RecommendationLabel,
    RecommendationInputData,
    TechnicalProfile,
    build_recommendation_evidence_pack,
    build_technical_profile,
    classify_fundamentals,
    make_recommendation,
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


def test_watchlist_only_symbol_reports_missing_snapshot_and_fundamentals():
    data = RecommendationInputData(
        index_history=_history("NIFTY 50"),
        equity_history=_history("ZZZ"),
        watchlist=["ZZZ"],
    )

    pack = build_recommendation_evidence_pack(data)

    assert "ZZZ" in pack.portfolio
    assert "snapshot" in pack.portfolio["ZZZ"].missing_evidence
    assert "fundamentals" in pack.portfolio["ZZZ"].missing_evidence
    assert pack.source_trail["watchlist"]["rows"] == 1
    assert pack.source_trail["watchlist"]["status"] == "primary"


def test_malformed_snapshot_source_is_not_reported_as_primary():
    data = RecommendationInputData(
        index_history=_history("NIFTY 50"),
        equity_history=_history("AAA"),
        snapshots=pd.DataFrame([{"ticker": "AAA", "technical_score": 82}]),
        fundamentals=pd.DataFrame([{"symbol": "AAA", "roe": 18}]),
    )

    pack = build_recommendation_evidence_pack(data)

    assert pack.source_trail["snapshots"]["rows"] == 1
    assert pack.source_trail["snapshots"]["status"] == "degraded"
    assert pack.source_trail["snapshots"]["missing_columns"] == ["symbol"]
    assert pack.missing_evidence["snapshots"] == ["source_degraded"]


def test_portfolio_symbol_outside_top_n_uses_stock_missing_evidence_rules():
    data = RecommendationInputData(
        index_history=_history("NIFTY 50"),
        equity_history=pd.concat([_history("AAA"), _history("BBB", 80.0)]),
        snapshots=pd.DataFrame(
            [
                {"symbol": "AAA", "technical_score": 90, "investment_score": 80},
                {"symbol": "BBB", "technical_score": 10, "investment_score": 5},
            ]
        ),
        fundamentals=pd.DataFrame([{"symbol": "AAA", "roe": 18}]),
        portfolio=pd.DataFrame([{"symbol": "BBB", "qty": 3, "avg_cost": 75.0}]),
    )

    pack = build_recommendation_evidence_pack(data, top_n=1)

    assert "AAA" in pack.stocks
    assert "BBB" not in pack.stocks
    assert "BBB" in pack.portfolio
    assert "fundamentals" in pack.portfolio["BBB"].missing_evidence
    assert "snapshot" not in pack.portfolio["BBB"].missing_evidence


def test_policy_assigns_add_on_confirmation_for_grounded_strength():
    data = RecommendationInputData(
        index_history=_history("NIFTY 50"),
        equity_history=_history("AAA"),
        snapshots=pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "sector": "Capital Goods",
                    "stage": "STAGE_2",
                    "technical_score": 88,
                    "relative_strength": 32,
                    "trading_signal": "BUY",
                    "investment_score": 82,
                }
            ]
        ),
        fundamentals=pd.DataFrame(
            [{"symbol": "AAA", "roe": 18, "roce": 24, "stock_pe": 22, "interest_coverage": 9}]
        ),
    )
    pack = build_recommendation_evidence_pack(data)

    rec = make_recommendation(
        pack.stocks["AAA"],
        market_regime=pack.market_regime,
        sector=pack.sectors["Capital Goods"],
    )

    assert rec.label == RecommendationLabel.ADD_ON_CONFIRMATION
    assert rec.confidence in {"high", "medium"}
    assert rec.technical_evidence
    assert rec.fundamental_evidence
    assert rec.trigger
    assert rec.invalidation
    assert rec.risk


def test_policy_assigns_avoid_for_weak_stage_and_fundamentals():
    data = RecommendationInputData(
        index_history=_history("NIFTY 50"),
        equity_history=_history("BBB", start=300.0).assign(
            close=lambda df: list(reversed(df["close"].tolist()))
        ),
        snapshots=pd.DataFrame(
            [
                {
                    "symbol": "BBB",
                    "sector": "Chemicals",
                    "stage": "STAGE_4",
                    "technical_score": 18,
                    "relative_strength": -20,
                    "trading_signal": "SELL",
                    "investment_score": 25,
                }
            ]
        ),
        fundamentals=pd.DataFrame(
            [{"symbol": "BBB", "roe": 4, "roce": 6, "stock_pe": 60, "interest_coverage": 1.1}]
        ),
    )
    pack = build_recommendation_evidence_pack(data)

    rec = make_recommendation(
        pack.stocks["BBB"],
        market_regime=pack.market_regime,
        sector=pack.sectors["Chemicals"],
    )

    assert rec.label == RecommendationLabel.AVOID_FRESH_ENTRY
    assert "STAGE_4" in " ".join(rec.technical_evidence)
    assert rec.confidence in {"medium", "high"}


def test_fundamental_classification_marks_missing_as_unknown():
    assert classify_fundamentals({}) == "quality_unknown"


def test_fundamental_classification_marks_unscoreable_fields_as_unknown():
    assert classify_fundamentals({"symbol": "AAA", "company_name": "AAA Ltd"}) == "quality_unknown"
