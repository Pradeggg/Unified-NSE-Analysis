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
    assert result["trace"][0]["step"] == "entity_topic_assessment"
    assert result["trace"][0]["result"]["canonical_symbol"] == "UNITDSPR"


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
