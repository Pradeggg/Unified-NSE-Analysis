from __future__ import annotations

import json
from unittest.mock import patch

from terminal.agent import Agent
from terminal.llm_situation_assessment import classify_llm_situation_assessment
from terminal.situation_assessment import TurnContext


class FakeBackend:
    def __init__(self, payload: dict | str):
        self.payload = payload
        self.calls: list[tuple[list[dict], list | None]] = []

    def chat(self, messages, tools=None):
        self.calls.append((messages, tools))
        if isinstance(self.payload, str):
            content = self.payload
        else:
            content = json.dumps(self.payload)
        return {"content": content}


def _stock_context(symbol: str = "BAJAJCON") -> TurnContext:
    return TurnContext(
        user_input=f"analyze sales and EPS growth of {symbol}",
        intent="stock_brief",
        mode="historical",
        tools=["resolve_symbol", "scrape_screener_in", "get_symbol_snapshot"],
        source_label="EOD CSV + DB snapshot + screener.in",
        freshness="snapshot 2026-06-09",
        result_type="stock_analysis",
        result_summary=f"{symbol} had quarterly and annual sales/EPS tables available.",
        symbols=[symbol],
        result_items=[symbol],
        result_groups={"primary": [symbol]},
    )


def test_llm_situation_assessment_builds_market_aware_context_prompt():
    backend = FakeBackend(
        {
            "applies": True,
            "decision": "run_tool_plan",
            "confidence": 0.92,
            "user_is_asking": "Analyze sales and EPS growth for the prior BAJAJCON context.",
            "context_found": "Previous turn contains BAJAJCON stock analysis with screener evidence.",
            "resolved_entities": ["BAJAJCON"],
            "evidence_plan": ["cached financial statements", "screener fundamentals"],
            "tool_plan": [
                {"tool": "get_cached_financials", "args": {"symbol": "BAJAJCON"}},
                {"tool": "scrape_screener_in", "args": {"symbol": "BAJAJCON"}},
            ],
            "synthesis_intent": "stock_brief",
        }
    )

    assessment = classify_llm_situation_assessment(
        "what about its EPS growth now?",
        _stock_context(),
        backend,
        data_mode="historical",
        market_status={"is_open": False, "clock": "2026-06-11 19:30:00 IST"},
    )

    assert assessment is not None
    assert assessment.decision == "run_tool_plan"
    assert assessment.resolved_entities == ["BAJAJCON"]
    assert assessment.tool_plan == [
        ("get_cached_financials", {"symbol": "BAJAJCON"}),
        ("scrape_screener_in", {"symbol": "BAJAJCON"}),
    ]
    assert assessment.synthesis_intent == "stock_brief"

    prompt = backend.calls[0][0][1]["content"]
    assert "BAJAJCON" in prompt
    assert "conversation_context" in prompt
    assert "market_status" in prompt
    assert "EOD CSV + DB snapshot + screener.in" in prompt
    assert backend.calls[0][1] == []


def test_llm_situation_assessment_rejects_unsafe_tool_plan():
    backend = FakeBackend(
        {
            "applies": True,
            "decision": "run_tool_plan",
            "confidence": 0.98,
            "tool_plan": [{"tool": "delete_database", "args": {"confirm": True}}],
        }
    )

    assessment = classify_llm_situation_assessment(
        "do the same for it",
        _stock_context(),
        backend,
        data_mode="historical",
    )

    assert assessment is None


def test_llm_situation_assessment_rejects_unresolved_symbol_placeholder():
    backend = FakeBackend(
        {
            "applies": True,
            "decision": "run_tool_plan",
            "confidence": 0.98,
            "user_is_asking": "Fetch latest financial results.",
            "context_found": "No prior context.",
            "resolved_entities": ["<RESOLVED_NSE_SYMBOL>"],
            "tool_plan": [
                {"tool": "get_latest_results", "args": {"symbol": "<RESOLVED_NSE_SYMBOL>"}},
            ],
            "synthesis_intent": "stock_results",
        }
    )

    assessment = classify_llm_situation_assessment(
        "Can you pull the latest financial results and technical analysis of LTFoods",
        None,
        backend,
        data_mode="historical",
    )

    assert assessment is None


def test_agent_situation_stage_uses_llm_before_deterministic_followup():
    agent = Agent()
    agent.backend = FakeBackend(
        {
            "applies": True,
            "decision": "run_tool_plan",
            "confidence": 0.9,
            "user_is_asking": "Fetch current BAJAJCON financial evidence.",
            "context_found": "Previous BAJAJCON analysis is the active context.",
            "resolved_entities": ["BAJAJCON"],
            "tool_plan": [
                {"tool": "get_cached_financials", "args": {"symbol": "BAJAJCON"}},
            ],
            "synthesis_intent": "stock_brief",
        }
    )
    agent._last_turn_context = _stock_context()

    with patch("terminal.agent._execute_plan") as execute_plan, patch(
        "terminal.agent._synthesize_and_narrate", return_value="LLM grounded answer"
    ):
        execute_plan.return_value = [
            {
                "tool": "get_cached_financials",
                "args": {"symbol": "BAJAJCON"},
                "result": {"status": "ok", "symbol": "BAJAJCON"},
            }
        ]
        result = agent.query("what about its EPS growth now?")

    assert result["intent"] == "contextual_tool_plan"
    assert execute_plan.call_args.args[0] == [
        ("get_cached_financials", {"symbol": "BAJAJCON"})
    ]
    assert any(item.get("step") == "llm_situation_assessment" for item in result["trace"])


def test_agent_situation_stage_falls_back_when_llm_plan_is_invalid():
    agent = Agent()
    agent.backend = FakeBackend(
        {
            "applies": True,
            "decision": "run_tool_plan",
            "confidence": 0.99,
            "tool_plan": [{"tool": "delete_database", "args": {}}],
        }
    )
    agent._last_turn_context = TurnContext(
        user_input="/analyze SCHAEFFLER",
        intent="generated_report",
        mode="historical",
        tools=["generate_report"],
        source_label="generated report",
        result_type="report",
        result_summary="Report generated for SCHAEFFLER",
        symbols=["SCHAEFFLER"],
        result_items=["/tmp/SCHAEFFLER_research.html"],
    )

    with patch("terminal.agent._execute_plan") as execute_plan, patch(
        "terminal.agent._synthesize_and_narrate", return_value="Deterministic answer"
    ):
        execute_plan.return_value = [
            {
                "tool": "open_report",
                "args": {"path": "/tmp/SCHAEFFLER_research.html"},
                "result": {"status": "ok", "path": "/tmp/SCHAEFFLER_research.html"},
            }
        ]
        result = agent.query("open it")

    assert result["intent"] == "contextual_tool_plan"
    assert execute_plan.call_args.args[0] == [
        ("open_report", {"path": "/tmp/SCHAEFFLER_research.html"})
    ]
    llm_trace = [item for item in result["trace"] if item.get("step") == "llm_situation_assessment"]
    assert llm_trace
    assert llm_trace[0]["result"]["used"] is False
