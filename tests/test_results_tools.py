from pathlib import Path

from terminal import results_tools


def test_discover_financial_filings_returns_ranked_candidates(monkeypatch):
    monkeypatch.setattr(
        results_tools,
        "search_nse_announcements",
        lambda symbol, max_results=15: {
            "symbol": symbol,
            "results": [{"title": "Financial Results Q4", "url": "https://nse.example/results.pdf"}],
        },
    )
    monkeypatch.setattr(
        results_tools,
        "search_bse_filings",
        lambda symbol, max_results=10: {
            "symbol": symbol,
            "results": [{"title": "Board meeting", "url": "https://bse.example/board.pdf"}],
        },
    )
    monkeypatch.setattr(results_tools, "scrape_screener_in", lambda symbol: {"symbol": symbol, "announcements": []})

    result = results_tools.discover_financial_filings("DMART")

    assert result["status"] == "ok"
    assert result["candidates"][0]["source"] == "nse_announcements"
    assert result["candidates"][0]["rank"] == 1
    assert result["source_trail"]["search_nse_announcements"] == "ok"


def test_ingest_financial_filing_wraps_existing_ingestor(monkeypatch, tmp_path):
    def fake_ingest(url, symbol=None, period=None, root_dir=None, force=False):
        return {
            "status": "ok",
            "source_url": url,
            "symbol": symbol,
            "period": period,
            "manifest_path": str(tmp_path / "manifest.json"),
            "document_type": "pdf",
        }

    monkeypatch.setattr(results_tools, "ingest_filing_url", fake_ingest)

    result = results_tools.ingest_financial_filing("https://example.com/results.pdf", symbol="DMART", period="Q4FY26")

    assert result["status"] == "ok"
    assert result["document_type"] == "pdf"
    assert result["source_url"] == "https://example.com/results.pdf"


def test_parse_pdf_only_filing_marks_partial_when_ocr_needed(monkeypatch, tmp_path):
    pdf_path = tmp_path / "results.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(
        results_tools,
        "_parse_pdf_filing",
        lambda path: {"status": "partial", "error_code": "OCR_REQUIRED", "evidence": [], "warnings": ["OCR required"]},
    )

    result = results_tools.parse_pdf_filing(str(pdf_path))

    assert result["status"] == "partial"
    assert result["error_code"] == "OCR_REQUIRED"


def test_reconcile_filing_facts_does_not_invent_missing_numbers():
    result = results_tools.reconcile_filing_facts(
        parsed_filing={"status": "partial", "evidence": []},
        screener_data={"symbol": "DMART", "quarterly": {"_headers": ["Mar 2026"]}},
    )

    assert result["status"] == "partial"
    assert result["facts"] == {}
    assert "revenue" in result["missing_facts"]
    assert "pat" in result["missing_facts"]
    assert "eps" in result["missing_facts"]


def test_get_latest_results_source_trail_includes_all_stages(monkeypatch):
    monkeypatch.setattr(
        results_tools,
        "discover_financial_filings",
        lambda symbol, max_results=10: {
            "status": "ok",
            "symbol": symbol,
            "candidates": [{"url": "https://example.com/results.pdf", "title": "Results", "source": "nse_announcements"}],
            "source_trail": {"search_nse_announcements": "ok", "search_bse_filings": "ok", "scrape_screener_in": "ok"},
            "screener_data": {
                "symbol": symbol,
                "quarterly": {"_headers": ["Mar 2026"], "Sales": ["14000"], "Net Profit": ["800"]},
                "ratios": {"EPS": "12.3"},
            },
        },
    )
    monkeypatch.setattr(
        results_tools,
        "ingest_financial_filing",
        lambda url, symbol="", period="latest", root_dir=None, force=False: {
            "status": "ok",
            "manifest_path": "/tmp/manifest.json",
            "document_type": "pdf",
            "source_url": url,
        },
    )
    monkeypatch.setattr(
        results_tools,
        "parse_financial_filing",
        lambda manifest_path: {"status": "ok", "evidence": [{"source_type": "pdf_page"}]},
    )

    result = results_tools.get_latest_results("DMART")

    assert result["status"] == "ok"
    assert result["facts"]["revenue"]["value"] == "14000"
    assert result["facts"]["pat"]["value"] == "800"
    assert result["source_trail"]["discover_financial_filings"] == "ok"
    assert result["source_trail"]["ingest_financial_filing"] == "ok"
    assert result["source_trail"]["parse_financial_filing"] == "ok"
    assert result["source_trail"]["reconcile_filing_facts"] == "ok"


def test_summarize_latest_results_never_invents_missing_facts():
    summary = results_tools.summarize_latest_results(
        {
            "symbol": "DMART",
            "period": "latest",
            "facts": {},
            "missing_facts": ["revenue", "pat", "eps"],
            "status": "partial",
            "source_trail": {"discover_financial_filings": "ok"},
        }
    )

    assert "Missing facts: revenue, pat, eps" in summary["summary"]
    assert "Revenue:" not in summary["summary"]
