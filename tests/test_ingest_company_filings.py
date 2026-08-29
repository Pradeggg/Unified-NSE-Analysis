from terminal import results_tools
from terminal import search_engine
from tools.ingest_company_filings import _clean_pg_value, ingest_company_filings


def test_dry_run_rejects_low_signal_candidate_even_when_it_is_first(monkeypatch):
    monkeypatch.setattr(
        results_tools,
        "discover_financial_filings",
        lambda symbol, max_results=10: {
            "status": "ok",
            "candidates": [
                {
                    "title": "Loss of share certificate",
                    "url": "https://exchange.example/certificate.pdf",
                    "source": "bse_filings",
                    "score": -80,
                }
            ],
            "source_trail": {},
        },
    )
    monkeypatch.setattr(search_engine, "search_nse_announcements", lambda symbol, max_results=15: {"bse_filings": []})

    result = ingest_company_filings(symbol="LT", max_docs=2, dry_run=True)

    assert result["picked"] == []


def test_dry_run_deduplicates_candidates_by_url(monkeypatch):
    shared_url = "https://exchange.example/results.pdf"
    monkeypatch.setattr(
        results_tools,
        "discover_financial_filings",
        lambda symbol, max_results=10: {
            "status": "ok",
            "candidates": [
                {"title": "Financial Results Q1", "url": shared_url, "source": "nse_announcements", "score": 140},
                {"title": "Unaudited Financial Results Q1", "url": shared_url, "source": "bse_filings", "score": 150},
            ],
            "source_trail": {},
        },
    )
    monkeypatch.setattr(search_engine, "search_nse_announcements", lambda symbol, max_results=15: {"bse_filings": []})

    result = ingest_company_filings(symbol="LT", max_docs=3, dry_run=True)

    assert len(result["picked"]) == 1
    assert result["picked"][0]["score"] == 150


def test_clean_pg_value_removes_nul_recursively_from_json_metadata():
    value = {"ti\x00tle": "Result\x00s", "raw": ["A\x00B", {"date": "2026\x00-08-29"}]}

    assert _clean_pg_value(value) == {
        "title": "Results",
        "raw": ["AB", {"date": "2026-08-29"}],
    }


def test_dry_run_cleans_nul_from_symbol_at_function_boundary(monkeypatch):
    seen = []

    def discover(symbol, max_results=10):
        seen.append(symbol)
        return {"status": "no_candidates", "candidates": [], "source_trail": {}}

    monkeypatch.setattr(results_tools, "discover_financial_filings", discover)

    result = ingest_company_filings(symbol="L\x00T", dry_run=True)

    assert seen == ["LT"]
    assert result["symbol"] == "LT"


def test_dry_run_uses_real_scoring_to_exclude_vote_and_newspaper_results(monkeypatch):
    monkeypatch.setattr(
        results_tools,
        "search_nse_announcements",
        lambda symbol, max_results=15: {
            "symbol": symbol,
            "nse_filings": [
                {"subject": "Postal Ballot Results", "url": "https://nse.example/postal.pdf"},
                {"subject": "Newspaper publication of Financial Results", "url": "https://nse.example/news.pdf"},
                {"subject": "Receipt of order from Indian Railways", "url": "https://nse.example/order.pdf"},
            ],
            "bse_filings": [],
        },
    )
    monkeypatch.setattr(results_tools, "search_bse_filings", lambda symbol, max_results=10: {"symbol": symbol, "results": {}})
    monkeypatch.setattr(results_tools, "_resolve_screener_data", lambda symbol: ({}, "ok"))

    result = ingest_company_filings(symbol="LT", max_docs=3, dry_run=True)

    assert [item["url"] for item in result["picked"]] == ["https://nse.example/order.pdf"]
