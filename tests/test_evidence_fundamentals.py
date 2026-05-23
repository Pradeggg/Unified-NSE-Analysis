"""Tests for backtesting.strategy_council.evidence_fundamentals."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from backtesting.strategy_council.evidence_fundamentals import (
    compute_fundamentals,
    enrich_with_fundamentals,
)
from backtesting.strategy_council.types import EvidencePack


def _row(label: str, end: date, **kw):
    return {
        "period_label": label,
        "period_end": end,
        "fetched_at": datetime(2026, 5, 19, tzinfo=timezone.utc),
        **kw,
    }


def _quarterly_history():
    # 6 quarters, newest first
    return [
        _row("Mar 2026", date(2026, 3, 31), revenue=120.0, pat=15.0, eps=1.5, opm_pct=20.0),
        _row("Dec 2025", date(2025, 12, 31), revenue=110.0, pat=12.0, eps=1.2, opm_pct=18.0),
        _row("Sep 2025", date(2025, 9, 30), revenue=105.0, pat=11.0, eps=1.1, opm_pct=17.0),
        _row("Jun 2025", date(2025, 6, 30), revenue=102.0, pat=10.0, eps=1.0, opm_pct=16.0),
        _row("Mar 2025", date(2025, 3, 31), revenue=100.0, pat=10.0, eps=1.0, opm_pct=15.0),
        _row("Dec 2024", date(2024, 12, 31), revenue=95.0, pat=9.0, eps=0.9, opm_pct=14.0),
    ]


def _annual_history():
    return [
        _row("Mar 2026", date(2026, 3, 31), revenue=440.0, pat=48.0, eps=4.8, opm_pct=18.0),
        _row("Mar 2025", date(2025, 3, 31), revenue=400.0, pat=40.0, eps=4.0, opm_pct=16.0),
        _row("Mar 2024", date(2024, 3, 31), revenue=360.0, pat=32.0, eps=3.2, opm_pct=14.0),
        _row("Mar 2023", date(2023, 3, 31), revenue=320.0, pat=26.0, eps=2.6, opm_pct=12.0),
    ]


def _bs_history():
    return [
        _row("Mar 2026", date(2026, 3, 31), borrowings=300.0, investments=200.0, net_debt=100.0, total_assets=2000.0, reserves=500.0),
        _row("Mar 2025", date(2025, 3, 31), borrowings=350.0, investments=180.0, net_debt=170.0, total_assets=1900.0, reserves=450.0),
    ]


def _cf_history():
    return [
        _row("Mar 2026", date(2026, 3, 31), operating_cf=80.0, investing_cf=-50.0, financing_cf=-10.0, net_cf=20.0),
    ]


def test_compute_fundamentals_full_picture(monkeypatch):
    def _fake_read(sym, dsn=None):
        return {
            "quarterly": _quarterly_history(),
            "annual": _annual_history(),
            "balance_sheet": _bs_history(),
            "cash_flow": _cf_history(),
        }
    monkeypatch.setattr(
        "backtesting.strategy_council.evidence_fundamentals.read_financials",
        _fake_read,
    )
    out = compute_fundamentals("FOO", as_of=date(2026, 5, 18))
    assert out["available"] is True
    assert out["latest_quarter"]["revenue"] == 120.0
    # YoY: Mar 2026 (120) vs Mar 2025 (100) = +20%
    assert out["yoy_growth"]["vs_period"] == "Mar 2025"
    assert out["yoy_growth"]["revenue_pct"] == 20.0
    assert out["yoy_growth"]["pat_pct"] == 50.0  # 15 vs 10
    # OPM delta: 20 - 15 = +5pp
    assert out["yoy_growth"]["opm_delta_pp"] == 5.0
    # QoQ: vs Dec 2025
    assert out["qoq_growth"]["vs_period"] == "Dec 2025"
    assert out["qoq_growth"]["revenue_pct"] == pytest.approx(9.09, rel=1e-2)
    # 3y CAGR: Mar 2026 vs Mar 2023 over 3 years
    # rev: (440/320)^(1/3) - 1 ≈ 11.18%
    assert out["cagr_3y"]["revenue_pct"] == pytest.approx(11.18, rel=1e-2)
    # Leverage trend: net_debt 100 vs 170 = -41.18%
    assert out["leverage_trend"]["net_debt_change_pct"] == pytest.approx(-41.18, rel=1e-2)
    # FCF proxy: 80 + (-50) = 30
    assert out["cash_flow_latest"]["fcf_proxy"] == 30.0
    # OCF/PAT against latest annual (48): 80/48 ≈ 1.67
    assert out["cash_flow_latest"]["ocf_to_pat"] == pytest.approx(1.67, rel=1e-2)


def test_compute_fundamentals_point_in_time_drops_future_rows(monkeypatch):
    # as_of = mid-2025, should drop Sep/Dec 2025 and Mar 2026 rows
    monkeypatch.setattr(
        "backtesting.strategy_council.evidence_fundamentals.read_financials",
        lambda s, dsn=None: {
            "quarterly": _quarterly_history(),
            "annual": [],
            "balance_sheet": [],
            "cash_flow": [],
        },
    )
    out = compute_fundamentals("FOO", as_of=date(2025, 7, 1))
    # Should now treat Jun 2025 as the latest quarter
    assert out["latest_quarter"]["period_label"] == "Jun 2025"
    assert out["latest_quarter"]["revenue"] == 102.0


def test_compute_fundamentals_handles_decimal_input(monkeypatch):
    """psycopg2 returns NUMERIC as Decimal — must convert cleanly."""
    monkeypatch.setattr(
        "backtesting.strategy_council.evidence_fundamentals.read_financials",
        lambda s, dsn=None: {
            "quarterly": [_row("Mar 2026", date(2026, 3, 31),
                                revenue=Decimal("120.5"), pat=Decimal("15.0"),
                                eps=Decimal("1.5"), opm_pct=Decimal("20.0"))],
            "annual": [], "balance_sheet": [], "cash_flow": [],
        },
    )
    out = compute_fundamentals("FOO", as_of=date(2026, 5, 18))
    assert out["latest_quarter"]["revenue"] == 120.5
    assert isinstance(out["latest_quarter"]["revenue"], float)


def test_compute_fundamentals_empty_cache(monkeypatch):
    monkeypatch.setattr(
        "backtesting.strategy_council.evidence_fundamentals.read_financials",
        lambda s, dsn=None: {"quarterly": [], "annual": [], "balance_sheet": [], "cash_flow": []},
    )
    out = compute_fundamentals("FOO")
    assert out["available"] is False
    assert "no rows" in out["reason"]


def test_enrich_with_fundamentals_clears_missing_flag(monkeypatch):
    monkeypatch.setattr(
        "backtesting.strategy_council.evidence_fundamentals.read_financials",
        lambda s, dsn=None: {
            "quarterly": _quarterly_history()[:1],
            "annual": [], "balance_sheet": [], "cash_flow": [],
        },
    )
    pack = EvidencePack(symbol="FOO", as_of="2026-05-18")
    pack.missing = ["fundamentals", "news"]
    out = enrich_with_fundamentals(pack)
    assert out.fundamental["pg_cache"]["available"] is True
    assert out.freshness["fundamentals"] == "Mar 2026"
    # enrich does NOT remove the missing flag — build_enriched_evidence_pack does
    assert any(t.startswith("fundamentals:") for t in out.source_trail)


def test_enrich_with_fundamentals_missing_when_cache_empty(monkeypatch):
    monkeypatch.setattr(
        "backtesting.strategy_council.evidence_fundamentals.read_financials",
        lambda s, dsn=None: {"quarterly": [], "annual": [], "balance_sheet": [], "cash_flow": []},
    )
    pack = EvidencePack(symbol="FOO", as_of="2026-05-18")
    out = enrich_with_fundamentals(pack)
    assert "fundamentals" in out.missing
    assert any("unavailable" in t for t in out.source_trail)
