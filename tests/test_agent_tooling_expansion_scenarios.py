from unittest.mock import patch

from terminal.agent import Agent, _keyword_intent


def test_scenario_stage2_then_scan_these_live_uses_prior_symbols():
    agent = Agent()
    agent.backend = object()
    with patch("terminal.agent._execute_plan") as execute_plan:
        execute_plan.side_effect = [
            [{"tool": "run_screener_query", "args": {"screen_type": "stage2"}, "result": {"screen_type": "stage2", "results": [{"symbol": "BLISSGVS"}, {"symbol": "IPCALAB"}]}}],
            [{"tool": "scan_symbols_intraday", "args": {"symbols": ["BLISSGVS", "IPCALAB"], "interval": "15m"}, "result": {"symbols_scanned": ["BLISSGVS", "IPCALAB"], "top_buy": [], "top_sell": []}}],
        ]
        first = agent.query("show Stage 2 stocks")
        second = agent.query("scan these for 15m intraday setups")

    assert first["intent"] == "screener"
    assert second["intent"] == "contextual_tool_plan"
    execute_plan.assert_any_call([("scan_symbols_intraday", {"symbols": ["BLISSGVS", "IPCALAB"], "interval": "15m"})])
    assert "SITUATION ASSESSMENT" in second["answer"]


def test_scenario_open_report_after_strategy_council_uses_report_context():
    agent = Agent()
    agent.backend = object()
    agent._last_turn_context = None
    agent._history = [
        {"role": "user", "content": "/strategy-council KIRLOSENG llm"},
        {"role": "assistant", "content": "Strategy Council — KIRLOSENG Recommendation: NO_TRADE Report: /tmp/strategy_council_KIRLOSENG.md"},
    ]

    result = agent.query("open the report")

    assert result["intent"] == "situation_assessment"
    assert "SITUATION ASSESSMENT" in result["answer"]
    assert "generated report" in result["answer"]


def test_scenario_report_results_followup_requests_specific_evaluation_when_context_is_incomplete():
    agent = Agent()
    agent.backend = object()
    agent._history = [
        {"role": "assistant", "content": "Strategy Council — KIRLOSENG Recommendation: NO_TRADE Report: /tmp/report.md"}
    ]

    result = agent.query("Based on the report how has been the results")

    assert result["intent"] == "situation_assessment"
    assert "CLARIFICATION NEEDED" in result["answer"]


def test_scenario_search_usl_growth_strategy_resolves_entity_not_topic():
    agent = Agent()
    agent.backend = object()
    with patch("terminal.agent._execute_plan") as execute_plan:
        execute_plan.return_value = [{"tool": "deep_search", "args": {"symbol": "UNITDSPR", "context": "growth strategy"}, "result": {"symbol": "UNITDSPR", "results": []}}]
        result = agent.query("search USL growth strategy")

    assert result["intent"] == "entity_topic_command"
    execute_plan.assert_called_once_with([("deep_search", {"symbol": "UNITDSPR", "context": "growth strategy"})])


def test_scenario_sakar_indicator_terms_do_not_trigger_symbol_validation_failure():
    agent = Agent()
    agent.backend = object()
    with patch("terminal.agent._execute_plan") as execute_plan:
        execute_plan.return_value = [
            {"tool": "resolve_symbol", "args": {"query": "SAKAR"}, "result": {"symbol": "SAKAR"}},
            {"tool": "get_symbol_snapshot", "args": {"symbol": "SAKAR"}, "result": {"symbol": "SAKAR"}},
            {"tool": "get_technical_setup", "args": {"symbol": "SAKAR"}, "result": {"symbol": "SAKAR", "adx": 24}},
            {"tool": "get_sector_context", "args": {"sector_or_symbol": "SAKAR"}, "result": {"symbol": "SAKAR"}},
        ]
        result = agent.query("SAKAR technical setup with ADX MA RSI MACD")

    assert "SYMBOL VALIDATION FAILED" not in result["answer"]


def test_scenario_deep_analysis_of_lowercase_stock_uses_stock_plan_not_market_overview():
    agent = Agent()
    agent.backend = object()
    with patch("terminal.agent._execute_plan") as execute_plan:
        execute_plan.return_value = [
            {"tool": "resolve_symbol", "args": {"query": "BAJAJCON"}, "result": {"symbol": "BAJAJCON"}},
            {"tool": "get_symbol_snapshot", "args": {"symbol": "BAJAJCON"}, "result": {"symbol": "BAJAJCON"}},
            {"tool": "get_technical_setup", "args": {"symbol": "BAJAJCON"}, "result": {"symbol": "BAJAJCON"}},
            {"tool": "get_sector_context", "args": {"sector_or_symbol": "BAJAJCON"}, "result": {"symbol": "BAJAJCON"}},
            {"tool": "scrape_screener_in", "args": {"symbol": "BAJAJCON"}, "result": {"symbol": "BAJAJCON"}},
            {"tool": "search_nse_announcements", "args": {"symbol": "BAJAJCON"}, "result": {"symbol": "BAJAJCON", "announcements": []}},
        ]
        result = agent.query("deep analysis of bajajcon")

    assert result["intent"] == "stock_brief"
    plan = execute_plan.call_args.args[0]
    assert ("resolve_symbol", {"query": "BAJAJCON"}) in plan
    assert ("get_live_market_overview", {}) not in plan


def test_scenario_comprehensive_fno_routes_to_composite_tool():
    routed = _keyword_intent("Give a comprehensive F&O overview for NIFTY with PCR max pain futures basis and best options strategy")

    assert routed["intent"] == "fno_overview"
    assert routed["plan"] == [("get_fno_overview", {"symbol": "NIFTY", "expiry_index": 0})]


def test_scenario_latest_results_routes_to_composite_tool():
    routed = _keyword_intent("latest results for DMART")

    assert routed["intent"] == "stock_results"
    assert routed["plan"] == [("resolve_symbol", {"query": "DMART"}), ("get_latest_results", {"symbol": "DMART"})]


def test_scenario_forensic_prompt_requires_forensic_tool():
    routed = _keyword_intent("Run forensic analysis for TATASTEEL with Beneish Piotroski and Altman")

    assert routed["intent"] == "stock_brief"
    assert ("run_forensic_analysis", {"symbol": "TATASTEEL"}) in routed["plan"]


def test_scenario_postgres_health_routes_to_intraday_health():
    routed = _keyword_intent("is PostgreSQL running and are intraday OHLCV tables healthy")

    assert routed["intent"] == "intraday_health"
    assert routed["plan"] == [("get_intraday_source_health", {})]


def test_scenario_eod_high_rs_prompt_routes_to_screener_not_nifty_symbol():
    routed = _keyword_intent("Run EOD screener high_rs and show top technical context")

    assert routed["intent"] == "screener"
    assert routed["plan"] == [("run_screener_query", {"screen_type": "high_rs"})]
    assert "NIFTY" not in str(routed)


def test_scenario_open_last_report_routes_to_report_lookup_not_high_rs_context():
    routed = _keyword_intent("open the report")

    assert routed["intent"] in {"report_lookup", "unknown"}
    assert "high_rs" not in str(routed)


def test_scenario_company_evidence_tools_are_available():
    from terminal.tools import TOOL_REGISTRY

    for tool in ("audit_company_search", "get_company_evidence_coverage", "promote_company_evidence_to_postgres"):
        assert tool in TOOL_REGISTRY
