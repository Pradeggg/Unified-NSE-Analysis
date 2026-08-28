"""Unit tests for terminal.financials_cache (parsers only — no PG required)."""

from __future__ import annotations

from datetime import date

from terminal import financials_cache as fc


def test_parse_period_end_handles_screener_labels():
    assert fc.parse_period_end("Mar 2026") == date(2026, 3, 31)
    assert fc.parse_period_end("Jun 2025") == date(2025, 6, 30)
    assert fc.parse_period_end("Dec 2024") == date(2024, 12, 31)
    assert fc.parse_period_end("TTM") is None
    assert fc.parse_period_end("FY26") is None
    assert fc.parse_period_end("") is None
    assert fc.parse_period_end(None) is None  # type: ignore[arg-type]


def test_to_number_parses_screener_formats():
    assert fc.to_number("294,059") == 294059.0
    assert fc.to_number("1,234.56") == 1234.56
    assert fc.to_number("12.54%") == 12.54
    assert fc.to_number("(45.6)") == -45.6
    assert fc.to_number("\u20b9 1,500") == 1500.0
    assert fc.to_number("") is None
    assert fc.to_number("-") is None
    assert fc.to_number("n/a") is None
    assert fc.to_number(None) is None
    assert fc.to_number(42) == 42.0


def test_build_pnl_rows_quarterly_and_annual():
    payload = {
        "source_url": "https://www.screener.in/company/FOO/",
        "quarterly": {
            "_headers": ["Dec 2025", "Mar 2026"],
            "Sales+": ["100", "120"],
            "Net Profit+": ["10", "15"],
            "EPS in Rs": ["1.0", "1.5"],
        },
        "annual_pl": {
            "_headers": ["Mar 2025", "Mar 2026"],
            "Sales": ["400", "500"],
            "Net Profit": ["40", "60"],
            "EPS in Rs": ["4.0", "6.0"],
            "Dividend Payout %": ["10", "12"],
        },
    }
    q, a = fc.build_pnl_rows("FOO", payload)
    assert len(q) == 2 and len(a) == 2
    assert q[1]["period_label"] == "Mar 2026"
    assert q[1]["revenue"] == 120.0
    assert q[1]["pat"] == 15.0
    assert q[1]["eps"] == 1.5
    assert q[1]["period_type"] == "quarter"
    assert q[1]["source"] == "screener"
    assert q[1]["source_url"] == payload["source_url"]
    assert a[1]["period_label"] == "Mar 2026"
    assert a[1]["revenue"] == 500.0
    assert a[1]["dividend_payout_pct"] == 12.0
    assert a[1]["period_type"] == "annual"


def test_build_balance_sheet_rows_derives_net_debt():
    payload = {
        "balance_sheet": {
            "_headers": ["Mar 2025", "Mar 2026"],
            "Borrowings+": ["300,000", "398,000"],
            "Investments": ["200,000", "248,332"],
            "Total Assets": ["1,900,000", "2,178,140"],
        },
    }
    rows = fc.build_balance_sheet_rows("FOO", payload)
    assert len(rows) == 2
    assert rows[1]["borrowings"] == 398000.0
    assert rows[1]["investments"] == 248332.0
    assert rows[1]["net_debt"] == 398000.0 - 248332.0
    assert rows[1]["total_assets"] == 2178140.0


def test_build_cash_flow_rows():
    payload = {
        "cash_flow": {
            "_headers": ["Mar 2025", "Mar 2026"],
            "Cash from Operating Activity+": ["150,000", "192,113"],
            "Cash from Investing Activity+": ["-180,000", "-200,000"],
        "Cash from Financing Activity+": ["20,000", "47,362"],
        "Net Cash Flow": ["-10,000", "39,475"],
        "Free Cash Flow": ["-30,000", "-7,887"],
        },
    }
    rows = fc.build_cash_flow_rows("FOO", payload)
    assert len(rows) == 2
    assert rows[1]["operating_cf"] == 192113.0
    assert rows[1]["investing_cf"] == -200000.0
    assert rows[1]["financing_cf"] == 47362.0
    assert rows[1]["net_cf"] == 39475.0
    assert rows[1]["free_cash_flow"] == -7887.0


def test_build_rows_skips_all_null_periods():
    payload = {
        "quarterly": {
            "_headers": ["Dec 2025", "Mar 2026"],
            "Sales+": ["-", "120"],
            "Net Profit+": ["", "15"],
        },
    }
    q, _ = fc.build_pnl_rows("FOO", payload)
    assert len(q) == 1
    assert q[0]["period_label"] == "Mar 2026"


def test_build_rows_empty_payload():
    assert fc.build_pnl_rows("FOO", {}) == ([], [])
    assert fc.build_balance_sheet_rows("FOO", {}) == []
    assert fc.build_cash_flow_rows("FOO", {}) == []
    assert fc.build_pnl_rows("FOO", {"quarterly": {}}) == ([], [])


def test_zip_columns_handles_leading_extra_column():
    # Screener sometimes prefixes value list with one extra leading entry.
    payload = {
        "quarterly": {
            "_headers": ["Mar 2026"],
            "Sales+": ["X", "120"],  # one more value than headers
        },
    }
    q, _ = fc.build_pnl_rows("FOO", payload)
    assert len(q) == 1
    assert q[0]["revenue"] == 120.0


# ---------------------------------------------------------------------------
# screener_payload_from_cache (DB-mocked) + read-through resolver
# ---------------------------------------------------------------------------


from datetime import datetime, timedelta, timezone
from unittest.mock import patch


def _row(label: str, **kw):
    return {"period_label": label, "fetched_at": datetime.now(timezone.utc), **kw}


def test_screener_payload_from_cache_reconstructs_sections(monkeypatch):
    monkeypatch.setattr(fc, "read_quarterly", lambda s, **_: [
        _row("Mar 2026", revenue=120.0, pat=15.0, eps=1.5, source_url="X"),
        _row("Dec 2025", revenue=100.0, pat=10.0, eps=1.0, source_url="X"),
    ])
    monkeypatch.setattr(fc, "read_annual", lambda s, **_: [])
    monkeypatch.setattr(fc, "read_balance_sheet", lambda s, **_: [
        _row("Mar 2026", borrowings=300.0, investments=200.0, total_assets=2000.0),
    ])
    monkeypatch.setattr(fc, "read_cash_flow", lambda s, **_: [
        _row("Mar 2026", operating_cf=50.0, net_cf=10.0),
    ])
    payload = fc.screener_payload_from_cache("FOO")
    assert payload is not None
    assert payload["_source"] == "pg_cache"
    assert payload["source_url"] == "X"
    assert payload["quarterly"]["_headers"] == ["Dec 2025", "Mar 2026"]
    assert payload["quarterly"]["Sales+"] == ["100", "120"]
    assert payload["quarterly"]["Net Profit+"] == ["10", "15"]
    assert payload["balance_sheet"]["Borrowings+"] == ["300"]
    assert payload["cash_flow"]["Cash from Operating Activity+"] == ["50"]


def test_screener_payload_from_cache_stale_returns_none(monkeypatch):
    old = datetime.now(timezone.utc) - timedelta(hours=48)
    monkeypatch.setattr(fc, "read_quarterly", lambda s, **_: [
        {"period_label": "Mar 2025", "fetched_at": old, "revenue": 1.0},
    ])
    monkeypatch.setattr(fc, "read_annual", lambda s, **_: [])
    monkeypatch.setattr(fc, "read_balance_sheet", lambda s, **_: [])
    monkeypatch.setattr(fc, "read_cash_flow", lambda s, **_: [])
    assert fc.screener_payload_from_cache("FOO", max_age_hours=24) is None
    # max_age_hours=None bypasses freshness check (used as fallback)
    payload = fc.screener_payload_from_cache("FOO", max_age_hours=None)
    assert payload is not None and payload["_source"] == "pg_cache"


def test_screener_payload_from_cache_empty(monkeypatch):
    for fn in ("read_quarterly", "read_annual", "read_balance_sheet", "read_cash_flow"):
        monkeypatch.setattr(fc, fn, lambda s, **_: [])
    assert fc.screener_payload_from_cache("FOO") is None


def test_resolve_screener_data_pg_hit_skips_live(monkeypatch):
    from terminal import results_tools as rt
    cached = {"_source": "pg_cache", "_cache_age_hours": 2.5, "quarterly": {"_headers": ["Mar 2026"]}}
    monkeypatch.setattr(rt, "screener_payload_from_cache", lambda s, **k: cached)
    def _boom(*a, **k):
        raise AssertionError("scrape_screener_in must not be called on cache hit")
    monkeypatch.setattr(rt, "scrape_screener_in", _boom)
    data, status = rt._resolve_screener_data("FOO")
    assert data is cached
    assert status == "pg_cache_hit:2.5h"


def test_resolve_screener_data_live_writeback(monkeypatch):
    from terminal import results_tools as rt
    # Miss on cache (TTL respected)
    monkeypatch.setattr(rt, "screener_payload_from_cache",
                        lambda s, **k: None if k.get("max_age_hours") else None)
    live_payload = {"status": "ok", "quarterly": {"_headers": ["Mar 2026"], "Sales+": ["1"]}}
    monkeypatch.setattr(rt, "scrape_screener_in", lambda s: live_payload)
    called = {}
    def _capture(sym, payload):
        called["sym"] = sym
        return {"quarterly": 1}
    monkeypatch.setattr(rt, "upsert_screener_payload", _capture)
    data, status = rt._resolve_screener_data("FOO")
    assert data is live_payload
    assert "writeback" in status
    assert called["sym"] == "FOO"


def test_resolve_screener_data_scrape_error_falls_back_to_stale_cache(monkeypatch):
    from terminal import results_tools as rt
    stale = {"_source": "pg_cache", "_cache_age_hours": 73.0, "quarterly": {"_headers": ["Mar 2026"]}}
    def _cache(sym, *, max_age_hours, **_):
        # Fresh check misses, stale fallback (max_age_hours=None) hits
        return None if max_age_hours is not None else stale
    monkeypatch.setattr(rt, "screener_payload_from_cache", _cache)
    monkeypatch.setattr(rt, "scrape_screener_in", lambda s: (_ for _ in ()).throw(RuntimeError("boom")))
    data, status = rt._resolve_screener_data("FOO")
    assert data is stale
    assert "fallback" in status and "boom" in status
