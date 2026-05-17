from terminal.evidence_gate import (
    build_evidence_matrix,
    render_missing_evidence_block,
    validate_answer_against_evidence,
    validate_required_tools_executed,
)


def test_build_evidence_matrix_groups_tool_results_by_category():
    matrix = build_evidence_matrix(
        [
            {"tool": "get_technical_setup", "result": {"symbol": "TCS"}},
            {"tool": "get_latest_results", "result": {"symbol": "TCS"}},
            {"tool": "run_forensic_analysis", "result": {"symbol": "TCS"}},
        ]
    )

    assert matrix["technical"]["status"] == "available"
    assert matrix["results"]["status"] == "available"
    assert matrix["forensic"]["status"] == "available"


def test_validate_answer_blocks_broker_claim_without_broker_evidence():
    result = validate_answer_against_evidence(
        "Broker targets suggest upside for TCS.",
        [{"tool": "get_symbol_snapshot", "result": {"symbol": "TCS"}}],
    )

    assert result["status"] == "missing_evidence"
    assert "broker" in result["missing_categories"]


def test_validate_answer_requires_latest_results_evidence_for_results_claim():
    result = validate_answer_against_evidence(
        "Latest results show revenue growth and PAT expansion.",
        [{"tool": "scrape_screener_in", "result": {"symbol": "DMART"}}],
    )

    assert result["status"] == "missing_evidence"
    assert "results" in result["missing_categories"]


def test_validate_answer_requires_forensic_evidence_for_forensic_claim():
    result = validate_answer_against_evidence(
        "Beneish and Piotroski indicate low manipulation risk.",
        [{"tool": "get_symbol_snapshot", "result": {"symbol": "TATASTEEL"}}],
    )

    assert "forensic" in result["missing_categories"]


def test_validate_answer_requires_sector_evidence_for_sector_claim():
    result = validate_answer_against_evidence(
        "The sector is leading the market.",
        [{"tool": "get_technical_setup", "result": {"symbol": "TCS"}}],
    )

    assert "sector" in result["missing_categories"]


def test_validate_answer_requires_fno_evidence_for_option_strategy_claim():
    result = validate_answer_against_evidence(
        "Best options strategy is a bull call spread based on max pain and futures basis.",
        [{"tool": "get_options_chain", "result": {"symbol": "NIFTY"}}],
    )

    assert "fno" in result["missing_categories"]


def test_validate_required_tools_executed_reports_missing_tools():
    result = validate_required_tools_executed(
        required_tools=["resolve_symbol", "get_latest_results"],
        tool_results=[{"tool": "resolve_symbol", "result": {"symbol": "DMART"}}],
    )

    assert result["status"] == "missing_required_tools"
    assert result["missing_tools"] == ["get_latest_results"]


def test_render_missing_evidence_block_lists_categories_and_tools():
    block = render_missing_evidence_block(
        intent="stock_results",
        missing_categories=["results"],
        missing_tools=["get_latest_results"],
    )

    assert "MISSING EVIDENCE" in block
    assert "results" in block
    assert "get_latest_results" in block
