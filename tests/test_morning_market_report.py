"""Regression tests for the Agent Adda Morning Market report."""

from pathlib import Path


REPORT_BUILDER = Path(__file__).parents[1] / "scripts" / "build_morning_market_report.py"


def test_report_defines_readable_link_colors():
    source = REPORT_BUILDER.read_text(encoding="utf-8")

    assert "a {{ color:var(--blue);" in source
    assert "a:visited {{ color:var(--teal);" in source


def test_signal_labels_are_neutral_in_stock_tables():
    from scripts.build_morning_market_report import stock_signal_label

    assert stock_signal_label("STRONG_BUY") == "Strong bullish"
    assert stock_signal_label("BUY") == "Bullish"
    assert stock_signal_label("SELL") == "Bearish"
    assert stock_signal_label("STRONG_SELL") == "Strong bearish"
    assert stock_signal_label("HOLD") == "Watch"
    assert stock_signal_label("WEAK_HOLD") == "Cautious"
    assert stock_signal_label(None) == "No signal"


def test_fno_stock_read_uses_actual_price_and_pcr_context():
    from scripts.build_morning_market_report import fno_stock_read

    assert fno_stock_read({"futures_price_change_pct": 2.4, "pcr_oi": 0.74}) == (
        "Price up, PCR bearish — weak confirmation"
    )
    assert fno_stock_read({"futures_price_change_pct": -1.88, "pcr_oi": 0.663}) == (
        "Price down, PCR bearish — aligned pressure"
    )
    assert fno_stock_read({"futures_price_change_pct": 3.38, "pcr_oi": 1.014}) == (
        "Price up, PCR constructive — better alignment"
    )
    assert fno_stock_read({"futures_price_change_pct": 1.0, "pcr_oi": 0.9}) == (
        "Mixed PCR — wait for price confirmation"
    )


def test_fno_index_read_uses_pcr_when_buildup_is_unavailable():
    from scripts.build_morning_market_report import fno_read

    assert fno_read({"pcr_oi": 0.748, "buildup": "LIVE_CHAIN"}) == (
        "Bearish-leaning PCR; price confirmation needed"
    )
    assert fno_read({"pcr_oi": 1.091, "buildup": "LIVE_CHAIN"}) == (
        "Constructive PCR; price confirmation needed"
    )
