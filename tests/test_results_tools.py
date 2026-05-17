from pathlib import Path
from datetime import date

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


def test_discover_financial_filings_filters_investor_meet_when_no_results(monkeypatch):
    monkeypatch.setattr(
        results_tools,
        "search_nse_announcements",
        lambda symbol, max_results=15: {
            "symbol": symbol,
            "bse_filings": [
                {"subject": "Announcement under Regulation 30 (LODR)-Analyst / Investor Meet - Outcome - Audio recording shared", "url": "https://bse.example/audio.pdf"},
                {"subject": "Change in Management", "url": "https://bse.example/management.pdf"},
            ],
            "nse_filings": [],
        },
    )
    monkeypatch.setattr(results_tools, "search_bse_filings", lambda symbol, max_results=10: {"symbol": symbol, "results": {}})
    monkeypatch.setattr(results_tools, "scrape_screener_in", lambda symbol: {"symbol": symbol, "announcements": []})

    result = results_tools.discover_financial_filings("DELHIVERY")

    assert result["status"] == "no_candidates"
    assert result["candidates"] == []


def test_discover_financial_filings_flattens_bse_categories_and_prefers_results(monkeypatch):
    monkeypatch.setattr(results_tools, "search_nse_announcements", lambda symbol, max_results=15: {"symbol": symbol, "bse_filings": [], "nse_filings": []})
    monkeypatch.setattr(
        results_tools,
        "search_bse_filings",
        lambda symbol, max_results=10: {
            "symbol": symbol,
            "results": {
                "concall_notice": [{"title": "Analyst / Investor Meet - Outcome - Audio recording", "url": "https://bse.example/audio.pdf"}],
                "board_meeting": [{"title": "Audited Financial Results for quarter ended March 2026", "url": "https://bse.example/results.pdf"}],
            },
        },
    )
    monkeypatch.setattr(results_tools, "scrape_screener_in", lambda symbol: {"symbol": symbol, "announcements": []})

    result = results_tools.discover_financial_filings("DELHIVERY")

    assert result["candidates"][0]["url"] == "https://bse.example/results.pdf"
    assert result["candidates"][0]["category"] == "board_meeting"


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


def test_reconcile_filing_facts_reads_latest_plus_labels_from_quarterly_table():
    result = results_tools.reconcile_filing_facts(
        parsed_filing={"status": "ok", "evidence": []},
        screener_data={
            "symbol": "DELHIVERY",
            "quarterly": {
                "_headers": ["Mar 2025", "Jun 2025"],
                "Sales+": ["2,000", "2,294"],
                "Net Profit+": ["10", "73"],
                "EPS in Rs": ["0.14", "0.98"],
            },
        },
    )

    assert result["status"] == "ok"
    assert result["facts"]["revenue"]["value"] == "2,294"
    assert result["facts"]["revenue"]["period"] == "Jun 2025"
    assert result["facts"]["pat"]["value"] == "73"
    assert result["facts"]["eps"]["value"] == "0.98"


def test_results_warning_when_no_filing_and_screener_quarter_is_stale():
    reconciliation = {
        "facts": {
            "revenue": {"value": "2,172", "period": "Jun 2024", "source": "scrape_screener_in.quarterly"},
            "pat": {"value": "54", "period": "Jun 2024", "source": "scrape_screener_in.quarterly"},
        }
    }

    warning = results_tools._results_warning(None, reconciliation, as_of=date(2026, 5, 17))

    assert warning["severity"] == "warning"
    assert warning["period"] == "Jun 2024"
    assert warning["latest_filing_found"] is False
    assert "Latest filing not found" in warning["message"]
    assert "Jun 2024" in warning["message"]


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


def test_get_latest_results_includes_warning_when_filing_missing(monkeypatch):
    monkeypatch.setattr(
        results_tools,
        "discover_financial_filings",
        lambda symbol, max_results=10: {
            "status": "no_candidates",
            "symbol": symbol,
            "candidates": [],
            "source_trail": {"search_nse_announcements": "ok", "search_bse_filings": "ok", "scrape_screener_in": "ok"},
            "screener_data": {
                "symbol": symbol,
                "quarterly": {"_headers": ["Jun 2024"], "Sales+": ["2172"], "Net Profit+": ["54"], "EPS in Rs": ["0.74"]},
            },
        },
    )

    result = results_tools.get_latest_results("DELHIVERY", ingest=False)

    assert result["status"] == "ok"
    assert result["selected_filing"] is None
    assert "Latest filing not found" in result["warning"]["message"]
    assert "Warning:" in result["summary"]


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
