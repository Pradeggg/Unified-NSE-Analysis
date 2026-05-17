from unittest.mock import patch

from terminal import tools


def test_resolve_embedded_pdf_url_from_corporate_viewer_src_param():
    url = (
        "https://www.diageoindia.com/pdf-viewer.aspx?gid=307336661&"
        "src=%2F%7E%2Fmedia%2FFiles%2FD%2FDiageo-V2%2FDiageo-India%2F"
        "news-and-media%2Fpress-release%2F2026%2Fdiageo-india-audited-"
        "financial-results-for-the-quarter-and-financial-year-ended-31-march-2026.pdf"
    )

    resolved = tools._resolve_embedded_pdf_url(url)

    assert resolved == (
        "https://www.diageoindia.com/~/media/Files/D/Diageo-V2/Diageo-India/"
        "news-and-media/press-release/2026/diageo-india-audited-financial-"
        "results-for-the-quarter-and-financial-year-ended-31-march-2026.pdf"
    )


def test_analyze_document_routes_pdf_viewer_url_to_pdf_extractor():
    url = (
        "https://www.example.com/pdf-viewer.aspx?"
        "src=%2Fmedia%2Fresults%2Fquarterly-results.pdf"
    )

    with patch.object(tools, "fetch_pdf_text") as fetch_pdf_text, patch.object(
        tools, "fetch_article_content"
    ) as fetch_article_content:
        fetch_pdf_text.return_value = {"source_type": "pdf", "text": "results"}
        result = tools.analyze_document(url)

    assert result == {"source_type": "pdf", "text": "results"}
    fetch_pdf_text.assert_called_once_with(url, max_pages=50, vision_fallback=True, vision_threshold=200)
    fetch_article_content.assert_not_called()


def test_fetch_pdf_text_downloads_resolved_viewer_pdf_url():
    url = (
        "https://www.example.com/pdf-viewer.aspx?"
        "src=%2Fmedia%2Fresults%2Fquarterly-results.pdf"
    )

    class FakeResponse:
        status_code = 500
        headers = {}
        content = b""

    with patch("requests.get", return_value=FakeResponse()) as mock_get:
        result = tools.fetch_pdf_text(url)

    mock_get.assert_called_once()
    assert mock_get.call_args.args[0] == "https://www.example.com/media/results/quarterly-results.pdf"
    assert result["url"] == url
    assert result["resolved_url"] == "https://www.example.com/media/results/quarterly-results.pdf"
    assert result["error"] == "HTTP 500"


def test_resolve_embedded_pdf_url_handles_wrapped_pasted_url():
    url = (
        "https://www.diageoindia.com/pdf-viewer.aspx?gid=307336661&"
        "src=%2F%7E%2Fmedia%2FFil\n"
        "es%2FD%2FDiageo-V2%2FDiageo-India%2Fnews-and-media%2Fpress-release%2F2026%2F"
        "diageo-india-audited-financial-results-for-the-quarter-and-financial-year-ended-31\n"
        "-march-2026.pdf"
    )

    resolved = tools._resolve_embedded_pdf_url(url)

    assert resolved == (
        "https://www.diageoindia.com/~/media/Files/D/Diageo-V2/Diageo-India/"
        "news-and-media/press-release/2026/diageo-india-audited-financial-results-"
        "for-the-quarter-and-financial-year-ended-31-march-2026.pdf"
    )


def test_fetch_pdf_text_downloads_resolved_url_for_wrapped_viewer_url():
    url = (
        "https://www.example.com/pdf-viewer.aspx?"
        "src=%2Fmedia%2Fresults%2Fquarterly-results-31\n"
        "-march-2026.pdf"
    )

    class FakeResponse:
        status_code = 500
        headers = {}
        content = b""

    with patch("requests.get", return_value=FakeResponse()) as mock_get:
        result = tools.fetch_pdf_text(url)

    assert mock_get.call_args.args[0] == (
        "https://www.example.com/media/results/quarterly-results-31-march-2026.pdf"
    )
    assert result["resolved_url"] == (
        "https://www.example.com/media/results/quarterly-results-31-march-2026.pdf"
    )
