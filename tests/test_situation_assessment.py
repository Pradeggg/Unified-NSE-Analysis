from terminal.situation_assessment import (
    EntityTopicAssessment,
    SituationAssessment,
    TurnContext,
    assess_user_situation,
    assess_entity_topic_request,
    assess_followup,
    build_turn_context,
    request_clarification,
    resolve_conversation_reference,
    resolve_entity_context,
    validate_intent_evidence_plan,
    needs_situation_assessment,
    render_assessment_block,
    render_context_answer,
)


def test_turn_context_defaults_are_compact():
    ctx = TurnContext(
        user_input="show Stage 2 stocks",
        intent="screener",
        mode="historical",
        tools=["run_screener_query"],
        source_label="EOD CSV + DB snapshot",
        freshness="2026-05-14",
        result_type="stage2_screener",
        result_summary="Stage 2 screener returned 10 results.",
        symbols=["BLISSGVS", "IPCALAB"],
        result_items=["BLISSGVS", "IPCALAB"],
    )

    assert ctx.intent == "screener"
    assert ctx.tool_args == []
    assert ctx.result_items == ["BLISSGVS", "IPCALAB"]


def test_situation_assessment_defaults():
    assessment = SituationAssessment(applies=False, decision="fallback_to_router")

    assert assessment.confidence == "low"
    assert assessment.tool_plan == []
    assert assessment.plan == []

    entity_assessment = EntityTopicAssessment(applies=False, decision="fallback_to_router")
    assert entity_assessment.canonical_symbol == ""
    assert entity_assessment.topic == ""


def test_contextual_source_questions_trigger_assessment():
    assert needs_situation_assessment("were these pulled from last 30mins")
    assert needs_situation_assessment("what about these")
    assert needs_situation_assessment("scan these live")
    assert needs_situation_assessment("is this from PostgreSQL or fallback")
    assert needs_situation_assessment("what expiry was this from")
    assert needs_situation_assessment("/search USL growth strategy")
    assert needs_situation_assessment("/fno United Spirits")
    assert needs_situation_assessment("/report technical United Spirits pdf")
    assert needs_situation_assessment("/results United Spirits latest quarter")
    assert needs_situation_assessment("what would be your recommendation based on the above financial analysis")


def test_direct_queries_do_not_trigger_assessment():
    assert not needs_situation_assessment("show Stage 2 stocks")
    assert not needs_situation_assessment("RELIANCE technical setup")


def test_entity_topic_assessment_resolves_search_alias_before_topic():
    assessment = assess_entity_topic_request("/search USL growth strategy")

    assert assessment.applies
    assert assessment.decision == "route_with_entity_topic"
    assert assessment.canonical_symbol == "UNITDSPR"
    assert assessment.entity_query == "USL"
    assert assessment.topic == "growth strategy"
    assert "canonical symbol UNITDSPR" in assessment.plan[0]


def test_natural_search_assessment_resolves_entity_before_topic():
    assessment = assess_entity_topic_request("search USL growth strategy")

    assert assessment.applies
    assert assessment.decision == "route_with_entity_topic"
    assert assessment.command == "/search"
    assert assessment.canonical_symbol == "UNITDSPR"
    assert assessment.topic == "growth strategy"
    assert assessment.rewritten_input == "/search UNITDSPR growth strategy"


def test_entity_topic_assessment_handles_multiword_company_name_and_format():
    assessment = assess_entity_topic_request("/search United Spirits concall pdf")

    assert assessment.decision == "route_with_entity_topic"
    assert assessment.canonical_symbol == "UNITDSPR"
    assert assessment.entity_query == "United Spirits"
    assert assessment.topic == "concall"
    assert assessment.output_format == "pdf"


def test_entity_topic_assessment_handles_report_type_before_entity():
    assessment = assess_entity_topic_request("/report technical United Spirits pdf")

    assert assessment.decision == "route_with_entity_topic"
    assert assessment.canonical_symbol == "UNITDSPR"
    assert assessment.entity_query == "United Spirits"
    assert assessment.topic == "technical"
    assert assessment.output_format == "pdf"
    assert assessment.rewritten_input == "/report technical UNITDSPR pdf"


def test_entity_topic_assessment_handles_results_command_aliases():
    assessment = assess_entity_topic_request("/results United Spirits latest quarter")

    assert assessment.decision == "route_with_entity_topic"
    assert assessment.canonical_symbol == "UNITDSPR"
    assert assessment.entity_query == "United Spirits"
    assert assessment.topic == "latest quarter"
    assert assessment.rewritten_input == "/results UNITDSPR latest quarter"


def test_entity_topic_assessment_handles_fno_alias():
    assessment = assess_entity_topic_request("/fno United Spirits")

    assert assessment.decision == "route_with_entity_topic"
    assert assessment.canonical_symbol == "UNITDSPR"
    assert assessment.entity_query == "United Spirits"
    assert assessment.rewritten_input == "/fno UNITDSPR"


def test_build_context_from_stage2_screener_results():
    tool_results = [
        {
            "tool": "run_screener_query",
            "args": {"screen_type": "stage2"},
            "result": {
                "screen_type": "stage2",
                "count": 2,
                "results": [
                    {"symbol": "BLISSGVS"},
                    {"symbol": "IPCALAB"},
                ],
            },
        }
    ]

    ctx = build_turn_context(
        user_input="show Stage 2 stocks",
        intent="screener",
        mode="historical",
        source_label="EOD CSV + DB snapshot",
        tool_results=tool_results,
        answer="Data Freshness: snapshot 2026-05-14",
    )

    assert ctx.result_type == "stage2_screener"
    assert ctx.freshness == "2026-05-14"
    assert ctx.symbols == ["BLISSGVS", "IPCALAB"]
    assert "2 results" in ctx.result_summary


def test_build_context_from_fno_overview_results():
    tool_results = [
        {
            "tool": "get_options_chain",
            "args": {"symbol": "NIFTY", "expiry_index": 0},
            "result": {"symbol": "NIFTY", "expiry": "2026-05-21", "pcr": 0.9},
        },
        {
            "tool": "get_futures_analysis",
            "args": {"symbol": "NIFTY"},
            "result": {"symbol": "NIFTY", "as_of": "2026-05-15 13:45:00"},
        },
    ]

    ctx = build_turn_context(
        user_input="/fno NIFTY",
        intent="fno_overview",
        mode="intraday",
        source_label="NSE options/futures API + F&O EOD fallback",
        tool_results=tool_results,
        answer="",
    )

    assert ctx.result_type == "fno_overview"
    assert ctx.freshness == "2026-05-15 13:45:00"
    assert ctx.symbols == ["NIFTY"]
    assert "expiry 2026-05-21" in ctx.result_summary


def test_stage2_last_30_minutes_question_answers_from_context():
    ctx = TurnContext(
        user_input="show Stage 2 stocks",
        intent="screener",
        mode="historical",
        tools=["run_screener_query"],
        source_label="EOD CSV + DB snapshot",
        freshness="2026-05-14",
        result_type="stage2_screener",
        result_summary="stage2 screener returned 10 results.",
        result_items=["BLISSGVS", "IPCALAB"],
    )

    assessment = assess_followup("were these pulled from last 30mins", ctx)

    assert assessment.applies
    assert assessment.confidence == "high"
    assert assessment.decision == "answer_from_context"
    assert assessment.tool_plan == []
    assert "Stage 2" in assessment.user_is_asking
    assert "not generated from last-30-minute" in assessment.source_assessment


def test_postgres_or_fallback_question_answers_from_intraday_context():
    ctx = TurnContext(
        user_input="TMPV intraday setup",
        intent="intraday_setup",
        mode="intraday",
        tools=["resolve_symbol", "explain_intraday_setup", "get_nse_intraday_snapshot"],
        source_label="PG intraday.quote_snapshots + PG intraday.ohlcv_bars",
        freshness="2026-05-15 13:15:00",
        symbols=["TMPV"],
        result_type="intraday_setup",
        result_summary="TMPV intraday setup from PostgreSQL bars and NSE snapshot.",
    )

    assessment = assess_followup("is this from PostgreSQL or fallback", ctx)

    assert assessment.decision == "answer_from_context"
    assert "PostgreSQL" in assessment.source_assessment


def test_fno_expiry_question_answers_from_context():
    ctx = TurnContext(
        user_input="/fno NIFTY",
        intent="fno_overview",
        mode="intraday",
        tools=["get_options_chain", "get_futures_analysis"],
        source_label="NSE options/futures API + F&O EOD fallback",
        freshness="2026-05-15 13:45:00",
        symbols=["NIFTY"],
        result_type="fno_overview",
        result_summary="F&O overview for NIFTY, expiry 2026-05-21.",
    )

    assessment = assess_followup("what expiry was this from", ctx)

    assert assessment.decision == "answer_from_context"
    assert "2026-05-21" in assessment.source_assessment


def test_what_about_these_asks_clarification():
    ctx = TurnContext(
        user_input="show Stage 2 stocks",
        intent="screener",
        mode="historical",
        tools=["run_screener_query"],
        source_label="EOD CSV + DB snapshot",
        result_type="stage2_screener",
        result_summary="stage2 screener returned 10 results.",
        result_items=["BLISSGVS", "IPCALAB"],
    )

    assessment = assess_followup("what about these", ctx)

    assert assessment.decision == "ask_clarification"
    assert assessment.tool_plan == []
    assert "Do you mean" in assessment.clarification_question


def test_scan_these_live_asks_for_live_analysis_type():
    ctx = TurnContext(
        user_input="show Stage 2 stocks",
        intent="screener",
        mode="historical",
        tools=["run_screener_query"],
        source_label="EOD CSV + DB snapshot",
        result_type="stage2_screener",
        result_summary="stage2 screener returned 10 results.",
        result_items=["BLISSGVS", "IPCALAB"],
    )

    assessment = assess_followup("scan these live", ctx)

    assert assessment.decision == "ask_clarification"
    assert "live quotes" in assessment.clarification_question
    assert "last-30-minute momentum" in assessment.clarification_question


def test_render_assessment_block_is_comprehensive():
    assessment = SituationAssessment(
        applies=True,
        decision="answer_from_context",
        confidence="high",
        user_is_asking="Whether the prior Stage 2 list came from last-30-minute data.",
        context_found="Previous result was Stage 2 screener.",
        source_assessment="It came from EOD CSV + DB snapshot.",
        plan=["Answer from prior context.", "Do not run market recap."],
    )

    rendered = render_assessment_block(assessment)

    assert "▶ SITUATION ASSESSMENT" in rendered
    assert "User is asking:" in rendered
    assert "Context found:" in rendered
    assert "Source assessment:" in rendered
    assert "Decision:" in rendered
    assert "1. Answer from prior context." in rendered


def test_render_context_answer_for_stage2_last_30_question():
    ctx = TurnContext(
        user_input="show Stage 2 stocks",
        intent="screener",
        mode="historical",
        tools=["run_screener_query"],
        source_label="EOD CSV + DB snapshot",
        freshness="2026-05-14",
        result_type="stage2_screener",
        result_summary="stage2 screener returned 10 results.",
    )
    assessment = assess_followup("were these pulled from last 30mins", ctx)

    answer = render_context_answer("were these pulled from last 30mins", assessment, ctx)

    assert "No." in answer
    assert "2026-05-14" in answer
    assert "not from the last 30 minutes" in answer
    assert "Not investment advice" in answer


def test_recommendation_based_on_above_analysis_answers_from_context():
    ctx = TurnContext(
        user_input="HDBFS financial analysis",
        intent="stock_brief",
        mode="historical",
        tools=["resolve_symbol", "get_symbol_snapshot", "get_technical_setup", "scrape_screener_in"],
        source_label="EOD CSV + DB snapshot + screener.in",
        freshness="2026-05-15",
        result_type="stock_brief",
        result_summary="stock brief for HDBFS; price 674.95; signal SELL; stage UNKNOWN; risk: low interest coverage.",
        symbols=["HDBFS"],
    )

    assessment = assess_followup("what would be your recommendation based on the above financial analysis", ctx)
    answer = render_context_answer("what would be your recommendation based on the above financial analysis", assessment, ctx)

    assert assessment.decision == "answer_from_context"
    assert assessment.resolved_entities == ["HDBFS"]
    assert "CONTEXTUAL RECOMMENDATION" in answer
    assert "cautious / avoid fresh entry" in answer
    assert "Do not resolve words" in assessment.plan[1]


def test_stock_context_summary_preserves_decision_signals():
    ctx = build_turn_context(
        user_input="HDBFS financial analysis",
        intent="stock_brief",
        mode="historical",
        source_label="EOD CSV + DB snapshot",
        tool_results=[
            {
                "tool": "get_symbol_snapshot",
                "args": {"symbol": "HDBFS"},
                "result": {"symbol": "HDBFS", "price": 674.95, "signal": "SELL", "stage": "UNKNOWN", "rs": -5},
            },
            {
                "tool": "scrape_screener_in",
                "args": {"symbol": "HDBFS"},
                "result": {"symbol": "HDBFS", "cons": ["Company has low interest coverage ratio."]},
            },
        ],
        answer="Data Freshness: snapshot 2026-05-15",
    )

    assert "HDBFS" in ctx.result_summary
    assert "SELL" in ctx.result_summary
    assert "UNKNOWN" in ctx.result_summary
    assert "low interest coverage" in ctx.result_summary


def test_scan_these_for_15m_setups_builds_tool_plan():
    ctx = TurnContext(
        user_input="show Stage 2 stocks",
        intent="screener",
        mode="historical",
        tools=["run_screener_query"],
        source_label="EOD CSV + DB snapshot",
        result_type="stage2_screener",
        result_summary="stage2 screener returned 2 results.",
        result_items=["BLISSGVS", "IPCALAB"],
        symbols=["BLISSGVS", "IPCALAB"],
    )

    assessment = assess_followup("scan these for 15m intraday setups", ctx)

    assert assessment.decision == "run_tool_plan"
    assert assessment.tool_plan == [
        ("scan_symbols_intraday", {"symbols": ["BLISSGVS", "IPCALAB"], "interval": "15m"})
    ]


def test_open_report_after_strategy_council_uses_prior_report_context():
    ctx = TurnContext(
        user_input="/strategy-council KIRLOSENG llm",
        intent="strategy_council",
        mode="historical",
        tools=["run_strategy_council"],
        source_label="Strategy Council report",
        result_type="strategy_council_report",
        result_summary="Strategy Council report for KIRLOSENG recommendation NO_TRADE.",
        symbols=["KIRLOSENG"],
        result_items=["/tmp/strategy_council_KIRLOSENG.md"],
    )

    assessment = assess_followup("open the report", ctx)

    assert assessment.decision == "run_tool_plan"
    assert assessment.tool_plan == [("open_report", {"path": "/tmp/strategy_council_KIRLOSENG.md"})]
    assert assessment.resolved_entities == ["KIRLOSENG"]
    assert "open the prior report" in assessment.user_is_asking.lower()


def test_based_on_report_results_uses_report_context():
    ctx = TurnContext(
        user_input="/strategy-council KIRLOSENG llm",
        intent="strategy_council",
        mode="historical",
        tools=["run_strategy_council"],
        source_label="Strategy Council report",
        result_type="strategy_council_report",
        result_summary="Strategy Council report for KIRLOSENG recommendation NO_TRADE.",
        symbols=["KIRLOSENG"],
        result_items=["/tmp/strategy_council_KIRLOSENG.md"],
    )

    assessment = assess_followup("Based on the report how has been the results", ctx)

    assert assessment.decision == "run_tool_plan"
    assert assessment.tool_plan == [
        ("read_report", {"path": "/tmp/strategy_council_KIRLOSENG.md", "max_chars": 12000}),
        ("summarize_report", {"path": "/tmp/strategy_council_KIRLOSENG.md"}),
    ]
    assert "prior report context" in assessment.context_found.lower()


def test_assess_user_situation_returns_v2_contract_for_ambiguous_followup():
    assessment = assess_user_situation("what about these", previous_context=None)

    assert assessment["applies"] is True
    assert assessment["decision"] == "ask_clarification"
    assert assessment["user_is_asking"]
    assert assessment["context_found"]
    assert assessment["evidence_plan"] == []
    assert assessment["clarification_question"]


def test_resolve_conversation_reference_report_context():
    ctx = TurnContext(
        user_input="/report technical UNITDSPR",
        intent="report_lookup",
        mode="historical",
        tools=["open_report"],
        source_label="generated reports",
        result_type="report",
        result_items=["/tmp/UNITDSPR_report.html"],
    )

    result = resolve_conversation_reference("open the report", ctx)

    assert result["status"] == "resolved"
    assert result["reference_type"] == "report"
    assert result["path"] == "/tmp/UNITDSPR_report.html"


def test_resolve_entity_context_for_search_prompt():
    result = resolve_entity_context("search USL growth strategy")

    assert result["status"] == "resolved"
    assert result["canonical_symbol"] == "UNITDSPR"
    assert result["topic"] == "growth strategy"


def test_validate_intent_evidence_plan_identifies_missing_tools():
    result = validate_intent_evidence_plan(
        intent="stock_results",
        evidence_plan=["resolve_symbol", "scrape_screener_in"],
        required_tools=["resolve_symbol", "scrape_screener_in", "search_bse_filings"],
    )

    assert result["status"] == "missing_required_tools"
    assert result["missing_tools"] == ["search_bse_filings"]


def test_request_clarification_contract():
    result = request_clarification(
        question="Which report should I use?",
        reason="No prior report context.",
    )

    assert result["decision"] == "ask_clarification"
    assert result["clarification_question"] == "Which report should I use?"
