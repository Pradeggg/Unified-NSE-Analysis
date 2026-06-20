from __future__ import annotations


def test_bound_confirmation_executes_before_generic_routing(monkeypatch):
    import terminal.agent as agent_mod
    from terminal.agentic_orchestrator import AgenticTurnState, BoundNextAction

    monkeypatch.setenv("AGENT_ADDA_AGENTIC_ORCHESTRATOR", "1")
    monkeypatch.setenv("AGENT_ADDA_MEMORY_PG", "0")

    captured: dict[str, object] = {}

    def fake_execute_plan(plan):
        captured["plan"] = plan
        return [
            {
                "tool": "get_last_report",
                "args": {},
                "result": {
                    "status": "ok",
                    "report": {
                        "path": "reports/latest/top_picks.html",
                        "report_type": "top_picks",
                    },
                },
            }
        ]

    monkeypatch.setattr(agent_mod, "_execute_plan", fake_execute_plan)
    monkeypatch.setattr(
        agent_mod,
        "_synthesize_and_narrate",
        lambda intent, query, tool_results, backend, assessment_plan=None: "Bound action executed.",
    )

    agent = agent_mod.Agent()
    agent._agentic_turn_state = AgenticTurnState(
        user_goal="review top picks",
        workflow="report_generation",
        next_actions=[
            BoundNextAction(
                id="open_latest",
                label="Open latest report",
                description="Open latest top-picks report",
                action_type="tool_plan",
                tool_plan=[("get_last_report", {})],
            )
        ],
    )

    result = agent._query_single("sure go ahead")

    assert captured["plan"] == [("get_last_report", {})]
    assert result["intent"] == "agentic_bound_action"
    assert "Bound action executed." in result["answer"]


def test_artifact_reference_executes_open_report(monkeypatch):
    import terminal.agent as agent_mod
    from terminal.agentic_orchestrator import AgenticTurnState, ArtifactRef

    monkeypatch.setenv("AGENT_ADDA_AGENTIC_ORCHESTRATOR", "1")
    monkeypatch.setenv("AGENT_ADDA_MEMORY_PG", "0")

    captured: dict[str, object] = {}

    def fake_execute_plan(plan):
        captured["plan"] = plan
        return [
            {
                "tool": "open_report",
                "args": {"path": "reports/latest/top_picks.html"},
                "result": {
                    "status": "ok",
                    "path": "reports/latest/top_picks.html",
                    "message": "Opening report",
                },
            }
        ]

    monkeypatch.setattr(agent_mod, "_execute_plan", fake_execute_plan)
    monkeypatch.setattr(
        agent_mod,
        "_synthesize_and_narrate",
        lambda intent, query, tool_results, backend, assessment_plan=None: "Opened latest report.",
    )

    agent = agent_mod.Agent()
    agent._agentic_turn_state = AgenticTurnState(
        user_goal="review top picks",
        workflow="report_generation",
        artifacts=[
            ArtifactRef(
                id="artifact_1",
                kind="html_report",
                title="Top picks",
                path="reports/latest/top_picks.html",
                symbols=[],
                created_by_workflow="report_generation",
            )
        ],
    )

    result = agent._query_single("open it")

    assert captured["plan"] == [("open_report", {"path": "reports/latest/top_picks.html"})]
    assert result["intent"] == "agentic_bound_action"
    assert "Opened latest report." in result["answer"]


def test_agentic_next_action_block_is_added_from_market_scan(monkeypatch):
    import terminal.agent as agent_mod

    monkeypatch.setenv("AGENT_ADDA_AGENTIC_ORCHESTRATOR", "1")
    monkeypatch.setenv("AGENT_ADDA_MEMORY_PG", "0")

    agent = agent_mod.Agent()
    tool_results = [
        {
            "tool": "run_quality_breakout_screener",
            "args": {},
            "result": {
                "items": [
                    {"symbol": "VBL"},
                    {"symbol": "CEMPRO"},
                    {"symbol": "ASTRAMICRO"},
                    {"symbol": "RATEGAIN"},
                ]
            },
        }
    ]

    answer = agent._apply_agentic_next_action_block(
        "Market answer.",
        "what is strong today",
        "market_swing_candidates",
        tool_results,
    )

    assert "▶ NEXT ACTION" in answer
    assert "VBL, CEMPRO, ASTRAMICRO, RATEGAIN" in answer
    assert agent._agentic_turn_state is not None
    assert agent._memory.agentic_state["workflow"] == "market_scan"


def test_unbound_confirmation_does_not_become_symbol_query(monkeypatch):
    import terminal.agent as agent_mod

    monkeypatch.setenv("AGENT_ADDA_AGENTIC_ORCHESTRATOR", "1")
    monkeypatch.setenv("AGENT_ADDA_MEMORY_PG", "0")

    def fail_execute_plan(plan):
        raise AssertionError(f"unexpected plan execution: {plan!r}")

    monkeypatch.setattr(agent_mod, "_execute_plan", fail_execute_plan)

    agent = agent_mod.Agent()
    agent._agentic_turn_state = None

    result = agent._query_single("sure go ahead")

    assert result["intent"] == "agentic_unbound_confirmation"
    assert "do not have a bound next action" in result["answer"]
