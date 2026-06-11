from unittest.mock import patch

from terminal.agent import Agent


def test_agent_api_routes_search_command_through_entity_topic_assessment():
    agent = Agent()
    agent.backend = None
    agent.backend_name = "Keyword (no LLM)"

    with patch("terminal.agent._execute_plan") as execute_plan:
        execute_plan.return_value = [
            {
                "tool": "deep_search",
                "args": {"symbol": "UNITDSPR", "context": "growth strategy"},
                "result": {"symbol": "UNITDSPR", "results": []},
            }
        ]

        result = agent.query("/search USL growth strategy")

    assert result["intent"] == "entity_topic_command"
    execute_plan.assert_called_once_with([
        ("deep_search", {"symbol": "UNITDSPR", "context": "growth strategy"})
    ])
    entity_step = next(
        (s for s in result["trace"] if isinstance(s, dict) and s.get("step") == "entity_topic_assessment"),
        None,
    )
    assert entity_step is not None
    assert entity_step["result"]["canonical_symbol"] == "UNITDSPR"


def test_agent_api_routes_natural_search_prompt_through_entity_topic_assessment():
    agent = Agent()
    agent.backend = None
    agent.backend_name = "Keyword (no LLM)"

    with patch("terminal.agent._execute_plan") as execute_plan:
        execute_plan.return_value = [
            {
                "tool": "deep_search",
                "args": {"symbol": "UNITDSPR", "context": "growth strategy"},
                "result": {"symbol": "UNITDSPR", "results": []},
            }
        ]

        result = agent.query("search USL growth strategy")

    assert result["intent"] == "entity_topic_command"
    execute_plan.assert_called_once_with([
        ("deep_search", {"symbol": "UNITDSPR", "context": "growth strategy"})
    ])
    entity_step = next(
        (s for s in result["trace"] if isinstance(s, dict) and s.get("step") == "entity_topic_assessment"),
        None,
    )
    assert entity_step is not None
    assert entity_step["result"]["canonical_symbol"] == "UNITDSPR"


def test_entity_topic_command_is_orchestrated_by_situation_assessment():
    agent = Agent()
    agent.backend = None
    agent.backend_name = "Keyword (no LLM)"

    with patch("terminal.agent._execute_plan") as execute_plan:
        execute_plan.return_value = [
            {
                "tool": "resolve_symbol",
                "args": {"query": "UNITDSPR"},
                "result": {"symbol": "UNITDSPR"},
            },
            {
                "tool": "get_latest_results",
                "args": {"symbol": "UNITDSPR"},
                "result": {"symbol": "UNITDSPR", "status": "ok", "period": "latest"},
            },
        ]

        result = agent.query("/results USL latest quarter")

    assert result["intent"] == "entity_topic_command"
    execute_plan.assert_called_once_with([
        ("resolve_symbol", {"query": "UNITDSPR"}),
        ("get_latest_results", {"symbol": "UNITDSPR"}),
    ])
    assert any(
        step.get("step") == "situation_assessment"
        and step.get("result", {}).get("decision") == "route_with_entity_topic"
        for step in result["trace"]
        if isinstance(step, dict)
    )
    assert any(
        step.get("step") == "entity_topic_assessment"
        for step in result["trace"]
        if isinstance(step, dict)
    )


def test_entity_topic_missing_symbol_clarifies_from_situation_assessment():
    agent = Agent()
    agent.backend = None
    agent.backend_name = "Keyword (no LLM)"

    result = agent.query("/results")

    assert result["intent"] == "situation_assessment"
    assert "Which NSE symbol or company should I use?" in result["answer"]
    assert "Which result should I use as the context" not in result["answer"]
    assert any(
        step.get("step") == "situation_assessment"
        and step.get("result", {}).get("decision") == "ask_clarification"
        for step in result["trace"]
        if isinstance(step, dict)
    )


def test_agent_uses_previous_conversation_when_structured_context_missing():
    agent = Agent()
    agent.backend = None
    agent.backend_name = "Keyword (no LLM)"
    agent._history = [
        {"role": "user", "content": "/strategy-council KIRLOSENG llm"},
        {
            "role": "assistant",
            "content": "Strategy Council — KIRLOSENG Recommendation: NO_TRADE Report: /tmp/report.md",
        },
    ]
    agent._last_turn_context = None

    result = agent.query("based on the report how has been the results")

    assert result["intent"] == "situation_assessment"
    assert "Previous conversation referenced a generated report" in result["answer"]
