from __future__ import annotations

from terminal import tools


def test_get_cached_financials_returns_pg_source_and_section_counts(monkeypatch):
    def fake_read_financials(symbol: str, *, dsn: str | None = None):
        assert symbol == "DMART"
        return {
            "quarterly": [{"period_label": "Mar 2026", "revenue": 17684, "pat": 656}],
            "annual": [{"period_label": "Mar 2026", "revenue": 68821, "pat": 2970}],
            "balance_sheet": [{"period_label": "Mar 2026", "total_assets": 40500}],
            "cash_flow": [{"period_label": "Mar 2026", "operating_cf": 4100}],
        }

    monkeypatch.setattr(tools, "read_financials", fake_read_financials)

    result = tools.get_cached_financials("DMART", quarterly_limit=1, annual_limit=1)

    assert result["symbol"] == "DMART"
    assert result["data_source"] == "PostgreSQL financial statement cache"
    assert result["pg_sources"] == [
        "scores.quarterly_results",
        "scores.annual_results",
        "scores.balance_sheet",
        "scores.cash_flow",
    ]
    assert result["section_counts"] == {
        "quarterly": 1,
        "annual": 1,
        "balance_sheet": 1,
        "cash_flow": 1,
    }
    assert result["quarterly"][0]["period_label"] == "Mar 2026"
