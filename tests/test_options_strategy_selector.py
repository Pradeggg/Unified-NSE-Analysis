from __future__ import annotations

from terminal.options_strategy_selector import select_options_strategy


def _execution(**overrides):
    base = {
        "status": "ok",
        "verdict": "BUY CE",
        "option_type": "CE",
        "moneyness": "ATM",
        "strike": 24500,
        "premium": 120.0,
        "breakeven": 24620.0,
        "expiry": "2026-06-30",
        "dte": 8,
        "iv_pct": 14.5,
        "delta": 0.51,
        "theta_per_day": -7.2,
        "expected_move": 310.0,
        "oi_wall": "CE wall 24600",
        "reasons": ["IV low", "DTE ideal"],
    }
    base.update(overrides)
    return base


def test_low_iv_index_directional_trade_allows_plain_long_option():
    decision = select_options_strategy(
        symbol="NIFTY",
        direction="LONG",
        execution=_execution(option_type="CE", iv_pct=14.5, dte=8, delta=0.52),
    )

    assert decision["verdict"] == "LONG OPTION OK"
    assert decision["structure"] == "Long Call"
    assert decision["risk_mode"] == "defined_premium"
    assert decision["naked_buy_allowed"] is True
    assert "cash-settled index option" in "; ".join(decision["reasons"])


def test_high_iv_stock_directional_trade_prefers_debit_spread():
    decision = select_options_strategy(
        symbol="TRENT",
        direction="SHORT",
        execution=_execution(
            verdict="USE SPREAD",
            option_type="PE",
            iv_pct=34.0,
            dte=8,
            delta=0.44,
            theta_per_day=-18.5,
        ),
    )

    assert decision["verdict"] == "USE DEBIT SPREAD"
    assert decision["structure"] == "Bear Put Debit Spread"
    assert decision["risk_mode"] == "defined_spread_debit"
    assert decision["naked_buy_allowed"] is False
    assert "stock-option physical settlement risk" in "; ".join(decision["reasons"])
    assert "high IV" in "; ".join(decision["reasons"])


def test_expiry_week_stock_option_is_blocked_for_physical_settlement_risk():
    decision = select_options_strategy(
        symbol="RELIANCE",
        direction="LONG",
        execution=_execution(option_type="CE", dte=2, iv_pct=18.0, delta=0.48),
    )

    assert decision["verdict"] == "NO OPTIONS STRATEGY"
    assert decision["structure"] == "Avoid stock option near expiry"
    assert decision["naked_buy_allowed"] is False
    assert "physical settlement risk" in "; ".join(decision["reasons"])


def test_non_trade_execution_preserves_no_strategy():
    decision = select_options_strategy(
        symbol="INFY",
        direction="LONG",
        execution=_execution(status="missing_evidence", verdict="NO OPTIONS TRADE"),
    )

    assert decision["verdict"] == "NO OPTIONS STRATEGY"
    assert decision["structure"] == "No options structure"
    assert decision["risk_mode"] == "none"
