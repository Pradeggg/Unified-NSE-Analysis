from __future__ import annotations

import importlib.util
from pathlib import Path

from tools.midcap_daily_monitor import build_monitor_summary, parse_rows


ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = ROOT / "Mutual Funds" / "working" / "build_midcap_leaders.py"


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_midcap_leaders", BUILDER_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_midcap_score_rewards_stage2_growth_eps_sales_theme_and_government_alignment() -> None:
    builder = _load_builder()
    row = {
        "symbol": "BHEL",
        "company": "Bharat Heavy Electricals",
        "index_membership": "NIFTY MIDCAP 100; NIFTY MIDCAP SELECT",
        "sector": "Capital Goods",
        "stage": "STAGE_2",
        "trend_signal": "STRONG_BULLISH",
        "trading_signal": "BUY",
        "rsi": "62",
        "relative_strength": "34",
        "six_month_return_pct": "42",
        "enhanced_fund_score": "72",
        "earnings_quality": "76",
        "sales_growth": "82",
        "eps_growth_proxy": "76",
        "trading_value_cr": "58",
    }

    scored = builder.score_candidate(row)

    assert scored["stage2_gate"] == "PASS"
    assert scored["growth_gate"] == "PASS"
    assert scored["high_eps_gate"] == "PASS"
    assert scored["yoy_sales_gate"] == "PASS"
    assert scored["theme_gate"] == "PASS"
    assert scored["government_investment_gate"] == "PASS"
    assert scored["decision_bucket"] == "CORE CANDIDATE"
    assert float(scored["overall_score_100"]) >= 80


def test_midcap_score_blocks_missing_eps_and_sales_growth_even_when_theme_is_good() -> None:
    builder = _load_builder()
    row = {
        "symbol": "ABC",
        "company": "Alpha Beta",
        "index_membership": "NIFTY MIDCAP 150",
        "sector": "Defence",
        "stage": "STAGE_2",
        "trend_signal": "BULLISH",
        "trading_signal": "BUY",
        "rsi": "64",
        "relative_strength": "28",
        "six_month_return_pct": "30",
        "enhanced_fund_score": "58",
        "earnings_quality": "",
        "sales_growth": "",
        "eps_growth_proxy": "",
        "trading_value_cr": "40",
    }

    scored = builder.score_candidate(row)

    assert scored["stage2_gate"] == "PASS"
    assert scored["theme_gate"] == "PASS"
    assert scored["government_investment_gate"] == "PASS"
    assert scored["growth_gate"] == "REFRESH_REQUIRED"
    assert scored["high_eps_gate"] == "REFRESH_REQUIRED"
    assert scored["decision_bucket"] == "REFRESH FIRST"


def test_midcap_monitor_summary_tracks_required_gates_and_blocks_orders() -> None:
    csv_text = """symbol,decision_bucket,overall_score_100,stage2_gate,growth_gate,high_eps_gate,yoy_sales_gate,theme_gate,government_investment_gate,trigger_state
BHEL,CORE CANDIDATE,84.2,PASS,PASS,PASS,PASS,PASS,PASS,WAIT
GLENMARK,REFRESH FIRST,70.1,PASS,REFRESH_REQUIRED,REFRESH_REQUIRED,REFRESH_REQUIRED,PASS,IDEA,WAIT
"""
    rows = parse_rows(csv_text)

    summary = build_monitor_summary(rows)

    assert summary["total_symbols"] == 2
    assert summary["paper_order_allowed"] is False
    assert summary["core_candidates"] == ["BHEL"]
    assert summary["refresh_first_symbols"] == ["GLENMARK"]
    assert summary["stage2_pass_symbols"] == ["BHEL", "GLENMARK"]
    assert summary["government_aligned_symbols"] == ["BHEL"]
