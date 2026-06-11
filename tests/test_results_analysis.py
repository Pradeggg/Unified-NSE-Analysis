"""Unit tests for the daily results-analysis pipeline."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

import pytest

from terminal import results_analysis as ra


# ---------------------------------------------------------------------------
# Numeric helpers
# ---------------------------------------------------------------------------

class TestGrowthMath:
    def test_compute_growth_yoy_qoq(self):
        quarters = [
            {"revenue": 110, "pat": 22, "eps": 5, "opm_pct": 18},  # Q0 (latest)
            {"revenue": 100, "pat": 20, "eps": 4, "opm_pct": 17},  # Q-1
            {"revenue":  95, "pat": 18, "eps": 4, "opm_pct": 16},
            {"revenue":  92, "pat": 17, "eps": 4, "opm_pct": 16},
            {"revenue":  88, "pat": 11, "eps": 3, "opm_pct": 15},  # Q-4 (YoY base)
        ]
        g = ra._compute_growth(quarters)
        assert g["yoy_revenue_pct"] == pytest.approx(25.0, abs=0.1)
        assert g["qoq_revenue_pct"] == pytest.approx(10.0, abs=0.1)
        assert g["yoy_pat_pct"] == pytest.approx(100.0, abs=0.1)
        assert g["qoq_pat_pct"] == pytest.approx(10.0, abs=0.1)
        assert g["opm_delta_yoy_pp"] == pytest.approx(3.0, abs=0.01)
        assert g["opm_delta_qoq_pp"] == pytest.approx(1.0, abs=0.01)

    def test_compute_growth_handles_short_history(self):
        g = ra._compute_growth([{"revenue": 100, "pat": 10}])
        # Without Q-1 / Q-4 baselines, deltas are None, not crashes.
        assert g["yoy_revenue_pct"] is None
        assert g["qoq_revenue_pct"] is None

    def test_compute_growth_empty(self):
        assert ra._compute_growth([]) == {}

    def test_pct_change_zero_base(self):
        assert ra._pct_change(10, 0) is None
        assert ra._pct_change(None, 5) is None


# ---------------------------------------------------------------------------
# Credit-rating extraction
# ---------------------------------------------------------------------------

class TestCreditRatingScan:
    def test_finds_crisil_mention(self):
        ann = [
            {"title": "Investor presentation", "url": "x.pdf"},
            {"title": "CRISIL revises long-term rating to AA Stable",
             "url": "https://crisil.example/note.pdf"},
        ]
        out = ra._scan_credit_rating(ann)
        assert out is not None
        note, src = out
        assert "CRISIL" in note
        assert src.endswith("note.pdf")

    def test_no_match_returns_none(self):
        assert ra._scan_credit_rating([{"title": "Board meeting"}]) is None
        assert ra._scan_credit_rating(None) is None
        assert ra._scan_credit_rating([]) is None


# ---------------------------------------------------------------------------
# Period-end resolution
# ---------------------------------------------------------------------------

class TestPeriodEnd:
    def test_parse_mar_2026(self):
        assert ra._parse_period_end("Mar 2026") == _dt.date(2026, 3, 31)

    def test_parse_iso(self):
        assert ra._parse_period_end("2026-03-31") == _dt.date(2026, 3, 31)

    def test_resolve_uses_quarterly_first(self):
        pack = {"quarterly": [{"period_end": _dt.date(2026, 3, 31)}]}
        assert ra._resolve_period_end(pack) == _dt.date(2026, 3, 31)

    def test_resolve_falls_back_to_period_label(self):
        pack = {"quarterly": [], "period_label": "Mar 2026"}
        assert ra._resolve_period_end(pack) == _dt.date(2026, 3, 31)

    def test_resolve_returns_none_when_unparseable(self):
        assert ra._resolve_period_end({"quarterly": [], "period_label": "??"}) is None


# ---------------------------------------------------------------------------
# Evidence pack — uses a fake conn so no PG required
# ---------------------------------------------------------------------------

class _FakeCursor:
    """A minimal RealDictCursor stand-in driven by a query-prefix routing dict."""

    def __init__(self, table_rows: dict[str, list[dict]]):
        self._table_rows = table_rows
        self._result: list[dict] = []

    def execute(self, sql, params=()):
        self._result = []
        for prefix, rows in self._table_rows.items():
            if prefix in sql:
                self._result = rows
                return

    def fetchall(self):
        return self._result

    def fetchone(self):
        return self._result[0] if self._result else None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeConn:
    def __init__(self, table_rows):
        self._table_rows = table_rows

    def cursor(self, cursor_factory=None):  # noqa: ARG002
        return _FakeCursor(self._table_rows)


def test_build_evidence_pack_assembles_all_sections():
    quarterly = [
        {"period_label": "Mar 2026", "period_end": _dt.date(2026, 3, 31),
         "revenue": 110, "pat": 22, "eps": 5, "opm_pct": 18,
         "operating_profit": 20, "expenses": 90, "other_income": 1,
         "interest": 2, "depreciation": 3, "pbt": 25, "tax_pct": 12},
        {"period_label": "Dec 2025", "period_end": _dt.date(2025, 12, 31),
         "revenue": 100, "pat": 20, "eps": 4, "opm_pct": 17},
        {"period_label": "Sep 2025", "period_end": _dt.date(2025, 9, 30),
         "revenue":  95, "pat": 18, "eps": 4, "opm_pct": 16},
        {"period_label": "Jun 2025", "period_end": _dt.date(2025, 6, 30),
         "revenue":  92, "pat": 17, "eps": 4, "opm_pct": 16},
        {"period_label": "Mar 2025", "period_end": _dt.date(2025, 3, 31),
         "revenue":  88, "pat": 11, "eps": 3, "opm_pct": 15},
    ]
    rows = {
        "scores.quarterly_results": quarterly,
        "scores.annual_results": [{"period_label": "Mar 2026", "revenue": 400}],
        "scores.balance_sheet": [{"period_label": "Mar 2026", "borrowings": 50}],
        "scores.cash_flow": [{"period_label": "Mar 2026", "operating_cf": 30}],
        "signals.insider_alerts": [],
        "signals.corporate_events": [],
        "signals.fii_dii_flows": [],
    }
    conn = _FakeConn(rows)

    pack = ra.build_evidence_pack(
        conn,
        symbol="acme",
        feed_row={
            "symbol": "ACME", "company": "Acme Ltd", "industry": "Widgets",
            "period": "Quarterly", "filing_date": "30-Apr-2026",
            "audited": "Audited", "consolidated": "Consolidated",
        },
        screener_data={
            "ratios": {"ROE": "18%", "Debt to equity": "0.4"},
            "shareholding": {"Promoters": "55%", "FIIs": "12%"},
            "announcements": [
                {"title": "ICRA reaffirms AA- Stable",
                 "url": "https://example.com/icra.pdf"},
            ],
        },
    )

    assert pack["symbol"] == "ACME"
    assert pack["company_name"] == "Acme Ltd"
    assert len(pack["quarterly"]) == 5
    assert pack["growth"]["yoy_revenue_pct"] == pytest.approx(25.0, abs=0.1)
    assert pack["credit_rating"]["note"].startswith("ICRA")
    assert pack["ratios"]["ROE"] == "18%"


# ---------------------------------------------------------------------------
# Persist (round-trip) — uses a fake conn that captures the SQL.
# ---------------------------------------------------------------------------

class _CapturingCursor:
    def __init__(self, store):
        self.store = store

    def execute(self, sql, params):
        self.store["sql"] = sql
        self.store["params"] = params

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _CapturingConn:
    def __init__(self):
        self.store: dict = {}

    def cursor(self, cursor_factory=None):  # noqa: ARG002
        return _CapturingCursor(self.store)


def test_persist_analysis_emits_upsert_with_period_end():
    pack = {
        "symbol": "ACME",
        "company_name": "Acme Ltd",
        "industry": "Widgets",
        "period_label": "Quarterly",
        "filing_date": "30-Apr-2026",
        "filing_url": "https://example.com/x.pdf",
        "audited": "Audited",
        "consolidated": "Consolidated",
        "quarterly": [{"period_end": _dt.date(2026, 3, 31)}],
        "growth": {"yoy_revenue_pct": 25.0, "qoq_revenue_pct": 10.0,
                   "yoy_pat_pct": 100.0, "qoq_pat_pct": 10.0,
                   "opm_delta_yoy_pp": 3.0, "yoy_eps_pct": 66.7},
        "ratios": {"ROE": "18%"},
        "credit_rating": {"note": "ICRA AA-", "source": "https://x"},
        "source_trail": {"discover_financial_filings": "ok"},
    }
    analysis = {
        "business_summary": "Widget maker.",
        "pl_commentary": "Strong YoY.",
        "bs_commentary": "Light debt.",
        "cf_commentary": "OCF positive.",
        "key_strengths": ["A", "B"],
        "key_risks": ["C"],
        "verdict": "beat",
        "score": 8.5,
    }
    conn = _CapturingConn()
    pe = ra.persist_analysis(conn, pack=pack, analysis=analysis,
                              report_path="reports/x.html",
                              llm_model="gpt-4o")

    assert pe == _dt.date(2026, 3, 31)
    sql = conn.store["sql"]
    assert "INSERT INTO scores.results_analysis" in sql
    assert "ON CONFLICT (symbol, period_end) DO UPDATE" in sql
    params = conn.store["params"]
    assert params[0] == "ACME"
    assert params[1] == _dt.date(2026, 3, 31)
    # verdict + score made it into the row
    assert "beat" in params
    assert 8.5 in params


def test_persist_analysis_returns_none_when_period_unresolvable():
    pack = {"symbol": "X", "quarterly": [], "period_label": ""}
    conn = _CapturingConn()
    pe = ra.persist_analysis(conn, pack=pack, analysis={"verdict": "unknown"})
    assert pe is None
    # No SQL should have been executed.
    assert "sql" not in conn.store


# ---------------------------------------------------------------------------
# HTML rendering smoke
# ---------------------------------------------------------------------------

def test_render_stock_html_contains_key_fields():
    pack = {
        "symbol": "ACME", "company_name": "Acme Ltd", "industry": "Widgets",
        "period_label": "Quarterly", "filing_date": "30-Apr-2026",
        "audited": "Audited", "consolidated": "Consolidated",
        "filing_url": "https://example.com/results.pdf",
        "growth": {"yoy_revenue_pct": 25.0, "yoy_pat_pct": 100.0},
        "quarterly": [{"period_label": "Mar 2026", "revenue": 110, "pat": 22,
                       "operating_profit": 20, "opm_pct": 18, "eps": 5}],
        "annual": [], "balance_sheet": [], "cash_flow": [],
    }
    analysis = {
        "business_summary": "Widget maker focused on India.",
        "pl_commentary": "Revenue +25% YoY.",
        "bs_commentary": "Light debt.",
        "cf_commentary": "OCF positive.",
        "key_strengths": ["Pricing power"],
        "key_risks": ["Input cost volatility"],
        "verdict": "beat", "score": 8.5,
    }
    html = ra.render_stock_html(pack, analysis)
    assert "<title>Results Analysis — ACME</title>" in html
    assert "Acme Ltd" in html
    assert "BEAT" in html
    assert "Widget maker" in html
    assert "Revenue +25%" in html
    assert "Pricing power" in html
    assert "Input cost volatility" in html


def test_render_index_html_lists_items():
    items = [
        {"symbol": "ACME", "company_name": "Acme Ltd", "period_label": "Q4",
         "verdict": "beat", "score": 8.5, "yoy_revenue_pct": 25.0,
         "yoy_pat_pct": 100.0, "report_path": "ACME.html"},
        {"symbol": "ZETA", "company_name": "Zeta Ltd", "period_label": "Q4",
         "verdict": "miss", "score": 3.0, "yoy_revenue_pct": -5.0,
         "yoy_pat_pct": -20.0, "report_path": "ZETA.html"},
    ]
    html = ra.render_index_html("2026-06-02", items)
    assert "Daily Results Analysis" in html
    assert "ACME.html" in html and "ZETA.html" in html
    assert "BEAT" in html and "MISS" in html


def test_insufficient_data_analysis_renders_warning_without_placeholders():
    pack = {
        "symbol": "NODATA",
        "company_name": "No Data Ltd",
        "period_label": "Q3",
        "quarterly": [],
        "annual": [],
        "balance_sheet": [],
        "cash_flow": [],
    }

    analysis = ra.insufficient_data_analysis(pack)
    html = ra.render_stock_html(pack, analysis)

    assert ra.has_structured_financials(pack) is False
    assert ra.analysis_has_placeholders({"pl_commentary": "Revenue was [revenue figure]."}) is True
    assert "Evidence warning" in html
    assert "No data." in html
    assert "[revenue figure]" not in html
    assert "UNKNOWN" in html


def test_deterministic_financial_analysis_uses_available_tables():
    pack = {
        "symbol": "DATA",
        "company_name": "Data Ltd",
        "period_label": "Q3",
        "growth": {"yoy_revenue_pct": 12.5, "yoy_pat_pct": 22.0},
        "quarterly": [{"revenue": 100, "operating_profit": 15, "pat": 8, "eps": 2}],
        "balance_sheet": [{"borrowings": 10, "net_debt": 5, "total_assets": 120}],
        "cash_flow": [{"operating_cf": 12, "investing_cf": -4, "financing_cf": 1, "net_cf": 9}],
    }

    analysis = ra.deterministic_financial_analysis(pack)
    html = ra.render_stock_html(pack, analysis)

    assert "Latest reported revenue is 100.00 crore" in html
    assert "The original LLM commentary contained template placeholders" in html
    assert "Structured financial statement data was insufficient" not in html
    assert "BEAT" in html


def test_latest_index_items_rewrite_relative_links():
    from scripts.analyze_daily_results import _latest_index_items

    items = [
        {"symbol": "ACME", "report_path": "ACME.html"},
        {"symbol": "REMOTE", "report_path": "https://example.com/report.html"},
    ]

    latest_items = _latest_index_items(
        items,
        out_dir=Path("reports/results_analysis/2026/20260603"),
        latest_dir=Path("reports/latest"),
    )

    assert latest_items[0]["report_path"] == "../results_analysis/2026/20260603/ACME.html"
    assert latest_items[1]["report_path"] == "https://example.com/report.html"
