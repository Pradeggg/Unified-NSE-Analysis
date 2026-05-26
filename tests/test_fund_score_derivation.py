"""Tests for terminal.fund_score_derivation.derive_fund_scores."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terminal.fund_score_derivation import (  # noqa: E402
    derive_fund_scores,
    _band_growth,
    _band_roce,
    _band_debt_equity,
    _to_float,
    _yoy_growth,
    _cagr,
)


# ─── helpers ─────────────────────────────────────────────────────────────────

def test_to_float_handles_commas_percent_currency():
    assert _to_float("1,23,456") == 123456.0
    assert _to_float("27%") == 27.0
    assert _to_float("₹1,234.50") == 1234.5
    assert _to_float("N/A") is None
    assert _to_float("--") is None
    assert _to_float(None) is None
    assert _to_float("") is None
    assert _to_float(42) == 42.0


def test_yoy_growth_basic():
    assert _yoy_growth(["100", "120"]) == pytest.approx(20.0)
    assert _yoy_growth(["100", "80"]) == pytest.approx(-20.0)
    assert _yoy_growth(["100"]) is None
    assert _yoy_growth([]) is None
    # Divide-by-zero guard
    assert _yoy_growth(["0", "100"]) is None


def test_cagr_three_years():
    # 100 → 200 over 3 periods → 26% CAGR
    g = _cagr(["100", "126", "159", "200"], 3)
    assert g == pytest.approx(25.99, abs=0.1)


# ─── banding ─────────────────────────────────────────────────────────────────

def test_band_growth_monotonic():
    assert _band_growth(35) > _band_growth(15) > _band_growth(5) > _band_growth(-5)
    assert _band_growth(None) is None


def test_band_roce_high_quality():
    assert _band_roce(45) == 95.0
    assert _band_roce(25) == 88.0
    assert _band_roce(3) == 35.0


def test_band_debt_equity_inverse():
    assert _band_debt_equity(0.05) > _band_debt_equity(0.5) > _band_debt_equity(2.5)


# ─── derivation end-to-end ───────────────────────────────────────────────────

def _high_quality_payload():
    """TCS-like: high ROCE/ROE, low debt, modest growth, strong promoter."""
    return {
        "annual_pl": {
            "Sales+": ["100", "115", "132", "152", "175"],       # +15% YoY
            "Net Profit+": ["20", "23", "27", "31", "36"],       # +16% YoY
            "EPS in Rs": ["20", "23", "27", "31", "36"],
            "OPM %": ["25%", "26%", "27%", "27%", "28%"],
        },
        "quarterly": {
            "Sales+": ["40", "42", "44", "46"],
            "Net Profit+": ["8", "9", "10", "11"],
            "OPM %": ["27%", "27%", "27%", "28%"],
        },
        "balance_sheet": {
            "Borrowings+": ["100", "90", "80"],
            "Equity Capital": ["400", "400", "400"],
            "Reserves": ["1000", "1100", "1200"],
        },
        "cash_flow": {"CFO/OP": ["92%", "93%", "94%"]},
        "ratios": {"ROCE": "45", "ROE": "30"},
        "shareholding": {"Promoters": "65%", "FIIs": "20%", "DIIs": "10%"},
    }


def test_high_quality_payload_yields_high_score():
    s = derive_fund_scores(_high_quality_payload())
    assert s["enhanced_fund_score"] >= 75
    assert s["financial_strength"] >= 80
    assert s["earnings_quality"] >= 70
    assert s["sales_growth"] >= 70
    assert s["institutional_backing"] >= 70


def test_low_quality_payload_yields_low_score():
    payload = {
        "annual_pl": {
            "Sales+": ["100", "95", "90", "85", "80"],        # declining
            "Net Profit+": ["10", "5", "0", "-3", "-5"],
            "EPS in Rs": ["10", "5", "0", "-3", "-5"],
            "OPM %": ["8%", "6%", "4%", "2%", "1%"],
        },
        "quarterly": {
            "Sales+": ["22", "20", "19", "18"],
            "Net Profit+": ["-1", "-2", "-2", "-3"],
            "OPM %": ["2%", "1%", "0%", "-1%"],
        },
        "balance_sheet": {
            "Borrowings+": ["500", "550", "600"],
            "Equity Capital": ["100", "100", "100"],
            "Reserves": ["100", "80", "60"],
        },
        "cash_flow": {"CFO/OP": ["30%", "25%", "20%"]},
        "ratios": {"ROCE": "3", "ROE": "2"},
        "shareholding": {"Promoters": "20%", "FIIs": "1%", "DIIs": "1%"},
    }
    s = derive_fund_scores(payload)
    assert s["enhanced_fund_score"] < 55
    assert s["earnings_quality"] < 55
    assert s["financial_strength"] < 55


def test_empty_payload_defaults_to_neutral():
    s = derive_fund_scores({})
    # Every sub-score falls back to 55 default
    assert s["enhanced_fund_score"] == 55.0
    assert s["earnings_quality"] == 55.0
    assert s["sales_growth"] == 55.0
    assert s["financial_strength"] == 55.0
    assert s["institutional_backing"] == 55.0


def test_partial_payload_only_ratios():
    """Just ratios — financial strength should compute, others fall back."""
    s = derive_fund_scores({"ratios": {"ROCE": "25", "ROE": "20"}})
    assert s["financial_strength"] > 70
    assert s["sales_growth"] == 55.0
    assert s["earnings_quality"] == 55.0


def test_minervini_weights_applied():
    """Final score = 0.40*earnings + 0.25*sales + 0.20*fin + 0.15*inst."""
    s = derive_fund_scores(_high_quality_payload())
    expected = (
        0.40 * s["earnings_quality"]
        + 0.25 * s["sales_growth"]
        + 0.20 * s["financial_strength"]
        + 0.15 * s["institutional_backing"]
    )
    assert s["enhanced_fund_score"] == pytest.approx(expected, abs=0.02)


def test_score_bounded_0_to_100():
    # Construct an absurd payload trying to push above 100
    payload = {
        "annual_pl": {
            "Sales+": ["1", "100"],
            "Net Profit+": ["1", "100"],
            "EPS in Rs": ["1", "100"],
            "OPM %": ["50%"],
        },
        "quarterly": {"Sales+": ["1", "100"], "Net Profit+": ["1", "100"], "OPM %": ["50%"]},
        "balance_sheet": {"Borrowings+": ["0"], "Equity Capital": ["1000"], "Reserves": ["10000"]},
        "ratios": {"ROCE": "100", "ROE": "100"},
        "shareholding": {"Promoters": "75%", "FIIs": "20%", "DIIs": "5%"},
    }
    s = derive_fund_scores(payload)
    for k in ("enhanced_fund_score", "earnings_quality", "sales_growth",
              "financial_strength", "institutional_backing"):
        assert 0.0 <= s[k] <= 100.0


def test_inputs_block_populated():
    s = derive_fund_scores(_high_quality_payload())
    inputs = s["inputs"]
    assert inputs["roce"] == 45.0
    assert inputs["promoter_pct"] == 65.0
    assert inputs["sales_yoy_pct"] is not None
    assert inputs["debt_equity"] is not None
    # Verify the debt/equity calculation: 80 / (400+1200) = 0.05
    assert inputs["debt_equity"] == pytest.approx(0.05, abs=0.001)
