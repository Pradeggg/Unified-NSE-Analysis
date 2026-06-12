from pathlib import Path

from broker_research.discovery import DiscoveredReportLink, discover_report_links, score_report_match


FIXTURES = Path(__file__).parent / "fixtures" / "broker_research"


def test_icici_fixture_extracts_absolute_pdf_links():
    html = (FIXTURES / "icici_co_reports.html").read_text(encoding="utf-8")

    links = discover_report_links(
        html,
        base_url="https://www.icicidirect.com/mailcontent/co_reports.html",
        broker_code="icici",
    )

    urls = [link.pdf_url for link in links]
    assert "https://www.icicidirect.com/mailcontent/idirect_bel_shubhnivesh_apr26.pdf" in urls
    assert "https://www.icicidirect.com/mailcontent/idirect_bharatelectronics_q3fy26.pdf" in urls


def test_hdfc_fixture_extracts_timestamped_pdf_links():
    html = (FIXTURES / "hdfc_reports.html").read_text(encoding="utf-8")

    links = discover_report_links(
        html,
        base_url="https://www.hdfcsec.com/research/equity/stock-research-institutional-reports",
        broker_code="hdfc_hsie",
    )

    assert any(link.pdf_url.startswith("https://www.hdfcsec.com/hsl.docs/") for link in links)
    assert any("Bharat Electronics" in link.title for link in links)


def test_axis_fixture_extracts_download_report_and_image_pdf_links():
    html = (FIXTURES / "axis_fundamental.html").read_text(encoding="utf-8")

    links = discover_report_links(
        html,
        base_url="https://simplehai.axisdirect.in/app/index.php/insights/reports/fundamental",
        broker_code="axis",
    )

    urls = [link.pdf_url for link in links]
    assert any("/downloadReport/file/Bharat+Electronics_Q4FY26_20-05-2026.pdf/type/fundamental" in url for url in urls)
    assert any(url.endswith("Cipla-ResultUpdate--27012026.pdf") for url in urls)


def test_score_report_match_prefers_symbol_and_alias_hits():
    bel = DiscoveredReportLink(
        broker_code="icici",
        title="Bharat Electronics Q3FY26 Result Update",
        pdf_url="https://www.icicidirect.com/mailcontent/idirect_bharatelectronics_q3fy26.pdf",
        source_url="https://www.icicidirect.com/mailcontent/co_reports.html",
    )
    barometer = DiscoveredReportLink(
        broker_code="hdfc_hsie",
        title="Bharat barometer Apr26",
        pdf_url="https://www.hdfcsec.com/hsl.docs/Bharat-barometer-Apr26-HSIE.pdf",
        source_url="https://www.hdfcsec.com/research/equity/stock-research-institutional-reports",
    )

    assert score_report_match(bel, symbol="BEL", aliases=["Bharat Electronics"]) >= 0.8
    assert score_report_match(barometer, symbol="BEL", aliases=["Bharat Electronics"]) < 0.5
