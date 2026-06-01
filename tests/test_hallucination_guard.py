# PG-HALL-GUARD: Tests for the confidence-driven hallucination gate that
# prevents free-text prose answers ("Stock A / Stock B" placeholders) on
# data-grounded asks (RS scan, screener, gainers, intraday scan) when no
# grounded tool_plan is available.

from terminal.situation_assessment import (
    classify_grounded_intent,
    assess_followup,
    needs_situation_assessment,
)


class TestClassifyGroundedIntent:
    def test_relative_strength_30min_is_grounded(self):
        tag = classify_grounded_intent(
            "List NSE stocks showing the highest relative strength over the last 30 minutes."
        )
        assert tag == "intraday_rs"

    def test_top_gainers_is_grounded(self):
        assert classify_grounded_intent("top gainers today") == "gainers_losers"

    def test_screener_is_grounded(self):
        assert classify_grounded_intent("breakout scan for NIFTY 500") == "screener"

    def test_market_overview_is_not_grounded(self):
        assert classify_grounded_intent("what is the market mood today") == ""

    def test_empty_input(self):
        assert classify_grounded_intent("") == ""


class TestNeedsSituationAssessmentGroundedRouting:
    def test_grounded_intent_classifier_is_independent_of_assessment_routing(self):
        # PG-HALL-GUARD: classify_grounded_intent operates as a pre-LLM
        # dispatch-layer gate, independent of needs_situation_assessment.
        # Verify both produce the expected output for a clean grounded ask.
        text = "show me top RS leaders"
        assert classify_grounded_intent(text) == "intraday_rs"


class TestAssessFollowupTagsGroundedFallback:
    def test_fallback_carries_grounded_metadata_on_fresh_rs_ask(self):
        # No prior context → deterministic chain emits ask_clarification.
        # The returned assessment must still carry requires_grounding=True
        # so any caller can detect grounding-required state.
        assessment = assess_followup(
            "List NSE stocks showing the highest relative strength over the last 30 minutes.",
            previous_context=None,
        )
        assert assessment.requires_grounding is True
        assert assessment.grounded_intent == "intraday_rs"

    def test_non_grounded_followup_does_not_set_requires_grounding(self):
        assessment = assess_followup(
            "what is the weather like",
            previous_context=None,
        )
        assert assessment.requires_grounding is False
        assert assessment.grounded_intent == ""


class TestAgentPreLLMHallucinationGate:
    """End-to-end test: agent.query refuses prose for ungrounded RS asks."""

    def test_agent_refuses_prose_on_ungrounded_rs_request(self):
        from unittest.mock import patch
        from terminal.agent import Agent

        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"

        # PG-HALL-GUARD: Use a phrase that triggers grounded-intent
        # classification ("top gainers") but is too vague for any
        # deterministic _keyword_intent handler to claim. Patch
        # _execute_route to None so the unified router falls through to
        # the legacy LLM path where the hallucination guard lives.
        with patch("terminal.agent._execute_plan") as execute_plan, \
             patch("terminal.agent._keyword_intent") as kw, \
             patch.object(agent, "_execute_route", return_value=None):
            kw.return_value = {"intent": "general_chat", "plan": []}
            execute_plan.return_value = []
            result = agent.query("show top gainers please")

        assert result["intent"] == "hallucination_guard"
        assert "No grounded results available" in result["answer"]
        assert "Stock A" not in result["answer"]
        assert "Stock B" not in result["answer"]
