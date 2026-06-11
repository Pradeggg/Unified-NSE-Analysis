from datetime import date, datetime, timedelta, timezone

from terminal.skills.fundamental_driver import diagnose_fundamental_driver


def _row(label: str, end: date, **kwargs):
    return {
        "period_label": label,
        "period_end": end,
        "fetched_at": datetime(2026, 6, 4, tzinfo=timezone.utc),
        **kwargs,
    }


def test_eps_decline_identifies_margin_compression_as_primary_driver():
    financials = {
        "quarterly": [
            _row("Mar 2026", date(2026, 3, 31), revenue=120.0, pat=9.0, eps=0.9, opm_pct=12.0),
            _row("Dec 2025", date(2025, 12, 31), revenue=118.0, pat=10.0, eps=1.0, opm_pct=14.0),
            _row("Sep 2025", date(2025, 9, 30), revenue=116.0, pat=10.5, eps=1.05, opm_pct=15.0),
            _row("Jun 2025", date(2025, 6, 30), revenue=115.0, pat=11.0, eps=1.1, opm_pct=16.0),
            _row("Mar 2025", date(2025, 3, 31), revenue=100.0, pat=12.0, eps=1.2, opm_pct=18.0),
        ],
        "annual": [],
        "balance_sheet": [],
        "cash_flow": [],
    }

    result = diagnose_fundamental_driver("FOO", "eps", financials=financials)

    assert result.success is True
    assert result.metric == "eps"
    assert "margin compression" in result.short_answer.lower()
    assert result.metric_bridge["eps_change_pct"] == -25.0
    assert result.metric_bridge["revenue_change_pct"] == 20.0
    assert result.metric_bridge["opm_delta_pp"] == -6.0
    assert result.interpretation == "operating_margin_pressure"
    assert any("Margin recovery" in item for item in result.what_to_watch)


def test_eps_decline_identifies_interest_depreciation_and_tax_pressure():
    financials = {
        "quarterly": [
            _row(
                "Mar 2026",
                date(2026, 3, 31),
                revenue=130.0,
                operating_profit=26.0,
                opm_pct=20.0,
                other_income=2.0,
                interest=6.0,
                depreciation=8.0,
                pbt=14.0,
                tax_pct=35.0,
                pat=9.1,
                eps=0.91,
            ),
            _row(
                "Mar 2025",
                date(2025, 3, 31),
                revenue=100.0,
                operating_profit=20.0,
                opm_pct=20.0,
                other_income=3.0,
                interest=2.0,
                depreciation=3.0,
                pbt=18.0,
                tax_pct=20.0,
                pat=14.4,
                eps=1.44,
            ),
        ],
        "annual": [],
        "balance_sheet": [],
        "cash_flow": [],
    }

    result = diagnose_fundamental_driver("FOO", "eps", financials=financials)

    assert result.success is True
    assert "interest, depreciation, and tax pressure" in result.short_answer
    assert result.metric_bridge["operating_profit_change_pct"] == 30.0
    assert result.metric_bridge["other_income_change_pct"] == -33.33
    assert result.metric_bridge["interest_change_pct"] == 200.0
    assert result.metric_bridge["depreciation_change_pct"] == 166.67
    assert result.metric_bridge["tax_delta_pp"] == 15.0
    assert result.interpretation == "below_ebit_pressure"
    assert any("Interest cost" in item for item in result.what_to_watch)


def test_eps_decline_identifies_other_income_normalization():
    financials = {
        "quarterly": [
            _row(
                "Mar 2026",
                date(2026, 3, 31),
                revenue=120.0,
                operating_profit=24.0,
                opm_pct=20.0,
                other_income=1.0,
                interest=2.0,
                depreciation=3.0,
                pbt=20.0,
                tax_pct=25.0,
                pat=15.0,
                eps=1.5,
            ),
            _row(
                "Mar 2025",
                date(2025, 3, 31),
                revenue=100.0,
                operating_profit=20.0,
                opm_pct=20.0,
                other_income=10.0,
                interest=2.0,
                depreciation=3.0,
                pbt=25.0,
                tax_pct=25.0,
                pat=18.75,
                eps=1.875,
            ),
        ],
        "annual": [],
        "balance_sheet": [],
        "cash_flow": [],
    }

    result = diagnose_fundamental_driver("FOO", "eps", financials=financials)

    assert result.success is True
    assert "other income normalized" in result.short_answer
    assert result.metric_bridge["other_income_change_pct"] == -90.0
    assert result.interpretation == "other_income_normalization"


def test_roce_diagnosis_uses_ebit_and_capital_employed_bridge():
    financials = {
        "quarterly": [],
        "annual": [
            _row("Mar 2026", date(2026, 3, 31), revenue=500.0, operating_profit=100.0, pat=70.0),
            _row("Mar 2025", date(2025, 3, 31), revenue=450.0, operating_profit=72.0, pat=50.0),
        ],
        "balance_sheet": [
            _row("Mar 2026", date(2026, 3, 31), total_assets=600.0, borrowings=100.0, investments=50.0),
            _row("Mar 2025", date(2025, 3, 31), total_assets=560.0, borrowings=100.0, investments=40.0),
        ],
        "cash_flow": [],
    }

    result = diagnose_fundamental_driver("FOO", "roce", financials=financials)

    assert result.success is True
    assert result.metric == "roce"
    assert "EBIT grew faster than capital employed" in result.short_answer
    assert result.metric_bridge["ebit_change_pct"] == 38.89
    assert result.metric_bridge["capital_employed_change_pct"] == 5.77
    assert result.interpretation == "higher_operating_return_on_capital"


def test_missing_financials_returns_insufficient_evidence():
    result = diagnose_fundamental_driver(
        "FOO",
        "eps",
        financials={"quarterly": [], "annual": [], "balance_sheet": [], "cash_flow": []},
    )

    assert result.success is False
    assert result.interpretation == "insufficient_evidence"
    assert "financial" in result.short_answer.lower()


def test_diagnosis_warns_when_financial_rows_are_stale():
    old = datetime.now(timezone.utc) - timedelta(days=120)
    financials = {
        "quarterly": [
            {"period_label": "Mar 2026", "period_end": date(2026, 3, 31), "fetched_at": old, "revenue": 120.0, "pat": 9.0, "eps": 0.9, "opm_pct": 12.0},
            {"period_label": "Mar 2025", "period_end": date(2025, 3, 31), "fetched_at": old, "revenue": 100.0, "pat": 12.0, "eps": 1.2, "opm_pct": 18.0},
        ],
        "annual": [],
        "balance_sheet": [],
        "cash_flow": [],
    }

    result = diagnose_fundamental_driver("FOO", "eps", financials=financials, max_age_days=30)

    assert any("stale" in warning.lower() for warning in result.warnings)


def test_roce_diagnosis_warns_when_using_capital_employed_proxy():
    financials = {
        "quarterly": [],
        "annual": [
            _row("Mar 2026", date(2026, 3, 31), revenue=500.0, operating_profit=100.0, pat=70.0),
            _row("Mar 2025", date(2025, 3, 31), revenue=450.0, operating_profit=72.0, pat=50.0),
        ],
        "balance_sheet": [
            _row("Mar 2026", date(2026, 3, 31), total_assets=600.0, borrowings=100.0, investments=50.0),
            _row("Mar 2025", date(2025, 3, 31), total_assets=560.0, borrowings=100.0, investments=40.0),
        ],
        "cash_flow": [],
    }

    result = diagnose_fundamental_driver("FOO", "roce", financials=financials)

    assert any("capital employed proxy" in warning.lower() for warning in result.warnings)
