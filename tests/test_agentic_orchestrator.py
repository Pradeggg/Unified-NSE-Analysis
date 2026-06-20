from __future__ import annotations

from terminal.agentic_orchestrator import (
    AgenticTurnState,
    BoundNextAction,
    action_from_artifact_reference,
    action_from_confirmation,
    agentic_orchestrator_enabled,
    append_next_action_block,
    build_agentic_turn_state,
    extract_artifacts,
    render_bound_action_summary,
)


def test_enabled_flag_accepts_truthy_values(monkeypatch):
    monkeypatch.setenv("AGENT_ADDA_AGENTIC_ORCHESTRATOR", "1")

    assert agentic_orchestrator_enabled() is True


def test_confirmation_resolves_latest_bound_action():
    state = AgenticTurnState(
        user_goal="find market leaders",
        workflow="market_scan",
        next_actions=[
            BoundNextAction(
                id="next_deep_dive_top4",
                label="Deep dive top 4 with RIC-style evidence",
                description="Deep dive VBL, CEMPRO, ASTRAMICRO, RATEGAIN",
                action_type="tool_plan",
                tool_plan=[
                    ("get_symbol_snapshot", {"symbol": "VBL"}),
                    ("get_technical_setup", {"symbol": "VBL"}),
                ],
                entities=["VBL", "CEMPRO", "ASTRAMICRO", "RATEGAIN"],
            )
        ],
    )

    action = action_from_confirmation("sure go ahead", state)

    assert action is not None
    assert action.id == "next_deep_dive_top4"


def test_confirmation_ignores_slash_commands():
    state = AgenticTurnState(
        user_goal="find market leaders",
        workflow="market_scan",
        next_actions=[
            BoundNextAction(
                id="next_deep_dive",
                label="Deep dive",
                description="Deep dive",
                action_type="tool_plan",
                tool_plan=[("get_symbol_snapshot", {"symbol": "VBL"})],
            )
        ],
    )

    assert action_from_confirmation("/scan nifty 500", state) is None


def test_extract_artifacts_from_report_tool_result():
    artifacts = extract_artifacts(
        [
            {
                "tool": "run_portfolio_ric_sherlock",
                "result": {
                    "html_path": "reports/portfolio/latest_portfolio_ric_sherlock.html",
                    "json_path": "reports/portfolio/latest_portfolio_ric_sherlock.json",
                    "symbols": ["VBL", "CEMPRO"],
                },
            }
        ]
    )

    assert [a.kind for a in artifacts] == ["html_report", "json_evidence"]
    assert artifacts[0].path.endswith(".html")
    assert artifacts[0].symbols == ["VBL", "CEMPRO"]


def test_build_market_scan_binds_deep_dive_action_from_screen_result():
    state = build_agentic_turn_state(
        user_input="what is the market state and stocks to look at",
        intent="market_swing_candidates",
        tool_results=[
            {
                "tool": "run_quality_breakout_screener",
                "result": {
                    "items": [
                        {"symbol": "VBL"},
                        {"symbol": "CEMPRO"},
                        {"symbol": "ASTRAMICRO"},
                        {"symbol": "RATEGAIN"},
                    ]
                },
            }
        ],
        answer="Watch VBL, CEMPRO, ASTRAMICRO, RATEGAIN.",
    )

    assert state is not None
    assert state.workflow == "market_scan"
    assert state.next_actions
    assert state.next_actions[0].entities == ["VBL", "CEMPRO", "ASTRAMICRO", "RATEGAIN"]
    assert "Deep dive" in state.next_actions[0].label


def test_build_market_scan_binds_from_top_movers_and_filters_artifacts():
    state = build_agentic_turn_state(
        user_input="market state and stocks to look at",
        intent="market_situation_assessment",
        tool_results=[
            {"tool": "get_live_market_overview", "result": {}},
            {
                "tool": "get_top_gainers_losers",
                "result": {
                    "gainers": [
                        {"symbol": "SHAH-RE1"},
                        {"symbol": "SONATSOFTW"},
                        {"symbol": "RPTECH"},
                        {"symbol": "NIITLTD"},
                        {"symbol": "AARTECH"},
                    ],
                    "losers": [{"symbol": "SBIVALETF"}],
                },
            },
        ],
        answer="Top gainers: SHAH-RE1, SONATSOFTW, RPTECH, NIITLTD, AARTECH.",
    )

    assert state is not None
    assert state.workflow == "market_scan"
    assert state.next_actions[0].entities == ["SONATSOFTW", "RPTECH", "NIITLTD", "AARTECH"]


def test_build_screener_binds_deep_dive_action_from_results():
    state = build_agentic_turn_state(
        user_input="show Stage 2 stocks",
        intent="screener",
        tool_results=[
            {
                "tool": "run_screener_query",
                "result": {
                    "screen_type": "stage2",
                    "results": [
                        {"symbol": "DIACABS"},
                        {"symbol": "SANGHVIMOV"},
                        {"symbol": "GALAPREC"},
                        {"symbol": "BANDHANBNK"},
                    ],
                },
            }
        ],
        answer="Stage 2 screener results.",
    )

    assert state is not None
    assert state.workflow == "screener"
    assert state.next_actions[0].entities == ["DIACABS", "SANGHVIMOV", "GALAPREC", "BANDHANBNK"]


def test_state_round_trip_preserves_bound_action():
    state = AgenticTurnState(
        user_goal="email the latest report",
        workflow="email_dispatch",
        next_actions=[
            BoundNextAction(
                id="open_latest",
                label="Open latest report",
                description="Open latest HTML report",
                action_type="tool_plan",
                tool_plan=[("open_report", {"path": "reports/latest/top_picks.html"})],
            )
        ],
    )

    restored = AgenticTurnState.from_dict(state.to_dict())

    assert restored.next_actions[0].tool_plan == [
        ("open_report", {"path": "reports/latest/top_picks.html"})
    ]


def test_artifact_reference_binds_open_report():
    state = AgenticTurnState(
        user_goal="review report",
        workflow="report_generation",
        artifacts=[
            {
                "id": "artifact_latest_html",
                "kind": "html_report",
                "title": "Top picks",
                "path": "reports/latest/top_picks.html",
                "symbols": [],
                "created_by_workflow": "report_generation",
            }
        ],
    )

    action = action_from_artifact_reference("open it", state)

    assert action is not None
    assert action.tool_plan == [("open_report", {"path": "reports/latest/top_picks.html"})]


def test_append_next_action_block_is_concise_and_idempotent():
    state = AgenticTurnState(
        user_goal="find market leaders",
        workflow="market_scan",
        next_actions=[
            BoundNextAction(
                id="next_deep_dive",
                label="Deep dive top 4",
                description="Run a deeper evidence pass for VBL, CEMPRO, ASTRAMICRO, RATEGAIN",
                action_type="tool_plan",
                tool_plan=[("get_symbol_snapshot", {"symbol": "VBL"})],
                entities=["VBL", "CEMPRO", "ASTRAMICRO", "RATEGAIN"],
            )
        ],
    )

    answer = append_next_action_block("Answer body", state)
    answer_again = append_next_action_block(answer, state)

    assert "▶ NEXT ACTION" in answer
    assert "VBL, CEMPRO, ASTRAMICRO, RATEGAIN" in answer
    assert answer_again == answer


def test_render_bound_action_summary_covers_all_symbols():
    action = BoundNextAction(
        id="next_deep_dive",
        label="Deep dive top 2",
        description="Deep dive",
        action_type="tool_plan",
        entities=["SONATSOFTW", "RPTECH"],
    )
    summary = render_bound_action_summary(
        action,
        [
            {
                "tool": "get_symbol_snapshot",
                "args": {"symbol": "SONATSOFTW"},
                "result": {"symbol": "SONATSOFTW", "price": 260.35, "stage": "STAGE_4", "signal": "SELL", "rs": 6},
            },
            {
                "tool": "get_technical_setup",
                "args": {"symbol": "SONATSOFTW"},
                "result": {"symbol": "SONATSOFTW", "rsi": 18.1},
            },
            {
                "tool": "get_symbol_snapshot",
                "args": {"symbol": "RPTECH"},
                "result": {"symbol": "RPTECH", "price": 654.25, "stage": "STAGE_2", "signal": "BUY", "rs": 82},
            },
            {
                "tool": "scrape_screener_in",
                "args": {"symbol": "RPTECH"},
                "result": {"symbol": "RPTECH", "ratios": {"Stock P/E": "31.2", "ROCE": "18.4"}},
            },
        ],
    )

    assert "SONATSOFTW" in summary
    assert "RPTECH" in summary
    assert "Stage STAGE_2" in summary
    assert "P/E 31.2" in summary
