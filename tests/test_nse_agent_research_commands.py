import nse_agent


def test_research_command_defaults_to_comprehensive_report_html():
    parsed = nse_agent._parse_research_report_command("/research CGPOWER")

    assert parsed == {"symbol": "CGPOWER", "format": "html"}


def test_research_command_accepts_report_format_positionally_or_flag():
    positional = nse_agent._parse_research_report_command("/research CGPOWER pdf")
    flagged = nse_agent._parse_research_report_command("/research CGPOWER --format md")

    assert positional == {"symbol": "CGPOWER", "format": "pdf"}
    assert flagged == {"symbol": "CGPOWER", "format": "md"}


def test_analyze_plain_symbol_uses_broker_ingest_critique_mode():
    parsed = nse_agent._parse_analyze_stock_research_command(
        "/analyze CGPOWER --brand icici --max 2 --skip-qa"
    )

    assert parsed["symbol"] == "CGPOWER"
    assert parsed["brand"] == "icici"
    assert parsed["max_results"] == 2
    assert parsed["skip_qa"] is True
    assert parsed["chat"] is False


def test_analyze_document_detection_is_preserved_for_urls_and_files():
    assert nse_agent._analyze_arg_is_document_source("https://example.com/report.pdf")
    assert nse_agent._analyze_arg_is_document_source("~/Downloads/report.pdf")
    assert not nse_agent._analyze_arg_is_document_source("CGPOWER")
