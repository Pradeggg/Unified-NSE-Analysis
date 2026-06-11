from __future__ import annotations


def _candidate(skill_id: str, **overrides):
    value = {
        "skill_id": skill_id,
        "version": 1,
        "status": "validated",
        "domain": "market_analysis",
        "title": skill_id.replace("_", " ").title(),
        "score": 0.82,
        "confidence": 0.82,
        "vector_score": 0.72,
        "tag_score": 0.72,
        "intent_score": 0.75,
        "evidence_score": 1.0,
        "output_contract_score": 1.0,
        "matched_tags": ["market_regime", "swing", "3m"],
        "metadata": {
            "tags": ["market_regime", "swing", "3m"],
            "available_tables": ["market.index_eod", "scores.stage_snapshots"],
            "available_tools": ["get_live_market_overview"],
            "output_contract": ["as_of_date", "index_returns", "ranked_candidates", "risks"],
            "tool_plan_template": [
                {"name": "market", "tool_name": "get_live_market_overview", "required": True},
            ],
            "sql_templates": [
                {
                    "name": "index_history",
                    "sql": "SELECT trade_date, index_symbol, close FROM market.index_eod LIMIT :limit",
                    "required_params": ["limit"],
                    "safety_status": "passed",
                }
            ],
            "validation_rules": ["required_tables_exist", "sql_is_read_only"],
        },
    }
    metadata = dict(value["metadata"])
    metadata.update(overrides.pop("metadata", {}) or {})
    value.update(overrides)
    value["metadata"] = metadata
    return value


def test_reviewer_selects_valid_market_3m_skill_for_3m_swing_query():
    from terminal.skills.reviewer import review_skill_candidates

    decision = review_skill_candidates(
        "Find swing candidates from the last 3 months market rotation",
        [_candidate("market_3m_rotation_swing_v1")],
        required_tables=["market.index_eod", "scores.stage_snapshots"],
        available_tables=["market.index_eod", "scores.stage_snapshots"],
        required_tools=["get_live_market_overview"],
        available_tools=["get_live_market_overview"],
        required_output_contract=["ranked_candidates", "risks"],
    )

    assert decision.decision == "select"
    assert decision.selected_skill_id == "market_3m_rotation_swing_v1"
    assert decision.selected_version == 1
    assert decision.missing_inputs == ()
    assert "selected" in decision.reason


def test_reviewer_rejects_irrelevant_high_vector_candidate():
    from terminal.skills.reviewer import review_skill_candidates

    decision = review_skill_candidates(
        "latest quarterly results analysis",
        [
            _candidate(
                "portfolio_tax_lot_review_v1",
                domain="portfolio_review",
                vector_score=0.98,
                tag_score=0.0,
                intent_score=0.05,
                score=0.61,
                metadata={
                    "tags": ["portfolio", "tax_lot"],
                    "available_tables": ["portfolio.holdings"],
                    "output_contract": ["portfolio_actions"],
                },
            )
        ],
        required_output_contract=["latest_results", "earnings_narrative"],
    )

    assert decision.decision == "reject"
    assert decision.selected_skill_id is None
    assert "candidate_does_not_answer_query" in decision.findings


def test_reviewer_asks_clarification_when_required_timeframe_absent():
    from terminal.skills.reviewer import review_skill_candidates

    decision = review_skill_candidates(
        "Find swing candidates with good fundamentals",
        [
            _candidate(
                "swing_setup_with_timeframe_v1",
                metadata={"required_inputs": ["timeframe"]},
            )
        ],
    )

    assert decision.decision == "ask_clarification"
    assert decision.missing_inputs == ("timeframe",)
    assert decision.selected_skill_id is None


def test_reviewer_falls_back_when_deterministic_route_is_stronger():
    from terminal.skills.reviewer import review_skill_candidates

    decision = review_skill_candidates(
        "/research RELIANCE",
        [_candidate("generic_stock_research_v1")],
        deterministic_intent="research_command",
        deterministic_confidence=0.96,
    )

    assert decision.decision == "fallback_to_router"
    assert decision.metadata["deterministic_intent"] == "research_command"


def test_reviewer_rejects_unsafe_sql_template():
    from terminal.skills.reviewer import review_skill_candidates

    decision = review_skill_candidates(
        "market rotation",
        [
            _candidate(
                "unsafe_sql_v1",
                metadata={
                    "sql_templates": [
                        {
                            "name": "bad",
                            "sql": "DELETE FROM market.index_eod WHERE trade_date < CURRENT_DATE",
                            "safety_status": "passed",
                        }
                    ]
                },
            )
        ],
    )

    assert decision.decision == "reject"
    assert "unsafe_sql_template" in decision.findings


def test_reviewer_merges_close_complementary_candidates():
    from terminal.skills.reviewer import review_skill_candidates

    decision = review_skill_candidates(
        "Find 3 month swing breakouts with fundamentals",
        [
            _candidate("technical_breakout_v1", domain="screening", score=0.82),
            _candidate(
                "fundamental_quality_v1",
                domain="fundamentals",
                score=0.79,
                metadata={
                    "tags": ["fundamentals", "quality"],
                    "available_tables": ["market.index_eod", "scores.stage_snapshots", "fundamentals.company_metrics"],
                    "output_contract": ["ranked_candidates", "quality_filters", "risks"],
                },
            ),
        ],
        required_output_contract=["ranked_candidates", "risks"],
    )

    assert decision.decision == "merge"
    assert decision.candidate_ids == ("technical_breakout_v1", "fundamental_quality_v1")


def test_reviewer_decision_serializes_to_plain_dict():
    from terminal.skills.reviewer import ReviewDecision

    decision = ReviewDecision(
        decision="select",
        selected_skill_id="market_3m_rotation_swing_v1",
        selected_version=1,
        candidate_ids=("market_3m_rotation_swing_v1",),
        reason="selected",
        findings=("ok",),
        confidence=0.91,
        metadata={"x": 1},
    )

    assert decision.to_dict() == {
        "decision": "select",
        "selected_skill_id": "market_3m_rotation_swing_v1",
        "selected_version": 1,
        "candidate_ids": ["market_3m_rotation_swing_v1"],
        "reason": "selected",
        "missing_inputs": [],
        "findings": ["ok"],
        "confidence": 0.91,
        "metadata": {"x": 1},
    }
