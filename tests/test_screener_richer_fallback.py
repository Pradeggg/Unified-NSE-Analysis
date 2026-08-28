"""Tests for choosing a richer standalone Screener response."""


def test_financial_coverage_prefers_richer_standalone_payload():
    from terminal.web_research import _financial_coverage_score, _prefer_richer_payload

    sparse = {
        "quarterly": {"_headers": ["Jun 2026"]},
        "annual_pl": {"_headers": ["Mar 2026"]},
        "balance_sheet": {"_headers": ["Mar 2026"]},
        "cash_flow": {"_headers": ["Mar 2026"]},
    }
    rich = {
        "quarterly": {"_headers": ["Mar 2024", "Jun 2024", "Jun 2026"]},
        "annual_pl": {"_headers": ["Mar 2022", "Mar 2023", "Mar 2026", "TTM"]},
        "balance_sheet": {"_headers": ["Mar 2022", "Mar 2023", "Mar 2026"]},
        "cash_flow": {"_headers": ["Mar 2022", "Mar 2023", "Mar 2026"]},
    }

    assert _financial_coverage_score(rich) > _financial_coverage_score(sparse)
    assert _prefer_richer_payload(sparse, rich) is rich


def test_annual_report_link_detection_accepts_bse_pdf_links():
    from terminal.web_research import _is_annual_report_link

    assert _is_annual_report_link("Annual Report 2026 from bse", "https://www.bseindia.com/file.pdf")
    assert not _is_annual_report_link("Investor Presentation", "https://www.bseindia.com/file.pdf")
