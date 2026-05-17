from terminal import company_evidence_tools


def test_audit_company_search_records_attempts_and_failures(monkeypatch):
    monkeypatch.setattr(
        company_evidence_tools,
        "search_company_official_sources",
        lambda symbol, alias=None: {
            "status": "ok",
            "attempts": [{"query": "DMART investor relations", "source_group": "official", "result_count": 1, "parse_status": "ok"}],
            "results": [{"url": "https://www.dmartindia.com/investor", "category": "official_site"}],
        },
    )
    monkeypatch.setattr(
        company_evidence_tools,
        "search_company_filings",
        lambda symbol, alias=None: {
            "status": "no_results",
            "attempts": [{"query": "DMART filings", "source_group": "filings", "result_count": 0, "parse_status": "no_results", "failure_reason": "none found"}],
            "results": [],
        },
    )

    result = company_evidence_tools.audit_company_search("DMART")

    assert result["status"] == "partial"
    assert result["attempts"][0]["source_group"] == "official"
    assert result["attempts"][1]["failure_reason"] == "none found"
    assert "filings" in result["gaps"]


def test_official_sources_are_searched_before_external_sources():
    result = company_evidence_tools.audit_company_search("DMART", include_external=True)

    groups = [attempt["source_group"] for attempt in result["attempts"]]
    assert groups.index("official") < groups.index("filings")
    assert groups.index("filings") < groups.index("external")


def test_no_result_cases_produce_auditable_gaps(monkeypatch):
    monkeypatch.setattr(company_evidence_tools, "search_company_official_sources", lambda symbol, alias=None: {"status": "no_results", "attempts": [], "results": []})
    monkeypatch.setattr(company_evidence_tools, "search_company_filings", lambda symbol, alias=None: {"status": "no_results", "attempts": [], "results": []})

    result = company_evidence_tools.audit_company_search("DMART")

    assert result["status"] == "no_evidence"
    assert "official" in result["gaps"]
    assert "filings" in result["gaps"]


def test_promote_company_evidence_to_postgres_records_source_metadata():
    result = company_evidence_tools.promote_company_evidence_to_postgres(
        "DMART",
        evidence=[
            {"url": "https://example.com/results.pdf", "category": "results", "title": "Results"},
            {"path": "/tmp/report.md", "category": "report", "title": "Report"},
        ],
        dry_run=True,
    )

    assert result["status"] == "dry_run"
    assert result["records"][0]["source_url"] == "https://example.com/results.pdf"
    assert result["records"][1]["source_path"] == "/tmp/report.md"
    assert result["records"][0]["category"] == "results"


def test_get_company_evidence_coverage_reports_category_counts(monkeypatch):
    monkeypatch.setattr(
        company_evidence_tools,
        "audit_company_search",
        lambda symbol, alias=None, include_external=False: {
            "symbol": symbol,
            "status": "partial",
            "results": [
                {"category": "official_site", "url": "https://official.example"},
                {"category": "filing", "url": "https://filing.example"},
            ],
            "gaps": ["news"],
        },
    )

    result = company_evidence_tools.get_company_evidence_coverage("DMART")

    assert result["coverage"]["official_site"] == 1
    assert result["coverage"]["filing"] == 1
    assert result["gaps"] == ["news"]
