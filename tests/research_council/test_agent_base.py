import pytest

from terminal.research_council.agents.base import Agent, AgentValidationError
from terminal.research_council.mode_profiles import load_mode_profile
from terminal.research_council.schemas import AgentFinding


class GoodAgent(Agent):
    name = "technical"

    def run_deterministic(self, evidence, mode_profile=None):
        return {
            "finding_id": "technical_1",
            "agent": "technical",
            "stance": "selective",
            "confidence": 0.7,
            "thesis": "Two setups are actionable.",
            "evidence": ["scores.daily_scores"],
            "candidates": ["ABC"],
        }

    def format_evidence_for_llm(self, evidence, mode_profile=None):
        return "evidence"


class BadAgent(Agent):
    name = "technical"

    def run_deterministic(self, evidence, mode_profile=None):
        return {"agent": "technical"}

    def format_evidence_for_llm(self, evidence, mode_profile=None):
        return "evidence"


def test_agent_run_validates_and_returns_agent_finding():
    result = GoodAgent().run({"stocks": []}, load_mode_profile("market_council"))

    assert isinstance(result, AgentFinding)
    assert result.agent == "technical"
    assert result.confidence == 0.7


def test_agent_validation_rejects_missing_required_fields():
    with pytest.raises(AgentValidationError):
        BadAgent().run({"stocks": []}, load_mode_profile("market_council"))


def test_agent_validation_rejects_wrong_agent_name():
    agent = GoodAgent()
    payload = {
        "finding_id": "wrong_1",
        "agent": "fundamental",
        "stance": "neutral",
        "confidence": 0.5,
        "thesis": "Wrong name.",
    }

    with pytest.raises(AgentValidationError):
        agent.validate_output(payload)


def test_prompt_fragments_are_versioned_dict():
    from terminal.research_council.agents.prompts import PROMPT_FRAGMENTS

    assert isinstance(PROMPT_FRAGMENTS, dict)
