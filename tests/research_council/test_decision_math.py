from terminal.research_council.decision_math import atr_stop, atr_target, research_book_size, unavailable


def test_atr_stop_for_long_setup():
    result = atr_stop(entry=100, atr=4, multiple=2)

    assert result == {
        "available": True,
        "side": "long",
        "entry": 100.0,
        "atr": 4.0,
        "multiple": 2.0,
        "stop": 92.0,
        "risk_per_share": 8.0,
        "disclaimer": "Research-only calculation; not a live order instruction.",
    }


def test_atr_target_uses_reward_multiple():
    result = atr_target(entry=100, atr=4, multiple=2.5)

    assert result["available"] is True
    assert result["target"] == 110.0
    assert result["reward_per_share"] == 10.0


def test_research_book_size_uses_risk_budget_and_never_order_language():
    result = research_book_size(capital=100000, risk_pct=0.01, entry=100, stop=92)

    assert result["available"] is True
    assert result["risk_amount"] == 1000.0
    assert result["max_research_quantity"] == 125
    assert result["estimated_notional"] == 12500.0
    assert "order" not in result["notes"].lower()


def test_missing_price_or_atr_returns_unavailable():
    assert atr_stop(entry=None, atr=4) == unavailable("entry and atr are required")
    assert atr_target(entry=100, atr=0) == unavailable("entry and atr must be positive")


def test_research_book_size_rejects_invalid_inputs():
    assert research_book_size(capital=100000, risk_pct=0.01, entry=100, stop=100) == unavailable(
        "entry must be above stop for long research sizing"
    )
