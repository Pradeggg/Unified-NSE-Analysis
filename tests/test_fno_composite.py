from terminal import fno_composite


def test_get_fno_overview_requires_chain_and_futures_evidence(monkeypatch):
    monkeypatch.setattr(
        fno_composite,
        "_get_options_chain",
        lambda symbol, expiry_index=0: {
            "symbol": symbol,
            "pcr": 0.92,
            "max_pain": 23800,
            "top_call_oi": [{"strike": 24000, "oi": 1000}],
            "top_put_oi": [{"strike": 23500, "oi": 900}],
        },
    )
    monkeypatch.setattr(
        fno_composite,
        "_get_futures_analysis",
        lambda symbol: {"symbol": symbol, "spot": 23775, "future": 23810, "basis": 35, "cost_of_carry": 7.2},
    )
    monkeypatch.setattr(
        fno_composite,
        "_get_strategy_recommendations",
        lambda symbol: {"symbol": symbol, "recommended": "bull_call_spread", "reason": "mild bullish"},
    )

    result = fno_composite.get_fno_overview("NIFTY")

    assert result["status"] == "ok"
    assert result["option_chain"]["pcr"] == 0.92
    assert result["futures"]["basis"] == 35
    assert result["recommendation"]["strategy"] == "bull_call_spread"
    assert result["source_trail"]["get_options_chain"] == "ok"
    assert result["source_trail"]["get_futures_analysis"] == "ok"


def test_missing_chain_blocks_strategy_recommendation(monkeypatch):
    monkeypatch.setattr(fno_composite, "_get_options_chain", lambda symbol, expiry_index=0: {"error": "No chain"})
    monkeypatch.setattr(fno_composite, "_get_futures_analysis", lambda symbol: {"symbol": symbol, "basis": 20})

    result = fno_composite.get_fno_overview("NIFTY")

    assert result["status"] == "missing_evidence"
    assert "option_chain" in result["missing_evidence"]
    assert result["recommendation"]["status"] == "blocked"


def test_missing_futures_blocks_basis_and_carry_claim(monkeypatch):
    monkeypatch.setattr(fno_composite, "_get_options_chain", lambda symbol, expiry_index=0: {"symbol": symbol, "pcr": 1.0})
    monkeypatch.setattr(fno_composite, "_get_futures_analysis", lambda symbol: {"error": "No futures"})

    result = fno_composite.get_fno_overview("NIFTY")

    assert result["status"] == "missing_evidence"
    assert "futures" in result["missing_evidence"]
    assert result["futures"]["status"] == "missing"


def test_recommendation_contains_risk_framing_fields():
    result = fno_composite.recommend_options_strategy(
        symbol="NIFTY",
        option_chain={"pcr": 0.8, "max_pain": 23800},
        futures={"basis": 35, "cost_of_carry": 7.2},
        raw_strategy={"recommended": "bull_call_spread"},
    )

    assert result["strategy"] == "bull_call_spread"
    assert result["conditions"]
    assert result["invalidation"]
    assert "max_loss" in result
    assert "max_profit" in result
    assert "research-only" in result["framing"].lower()
