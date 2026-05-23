"""Tests for the Strategy Council tool-calling LLM strategist and critic.

The tool-calling loop is exercised with deterministic fakes — no OpenAI
client is invoked. The injected ``llm_call`` records the tool schemas it
received and the calls dispatched, then returns a final JSON dict.
"""

from __future__ import annotations

import json
import unittest
from typing import Any

from backtesting.strategy_council.llm import (
    ToolCallingLLMCritic,
    ToolCallingLLMStrategist,
)
from backtesting.strategy_council.tool_router import (
    COUNCIL_TOOL_HANDLERS,
    COUNCIL_TOOL_SCHEMAS,
    execute_tool,
)
from backtesting.strategy_council.types import (
    BacktestSliceResult,
    CouncilConfig,
    EvidencePack,
)


class ToolRouterTests(unittest.TestCase):
    def test_tool_schemas_and_handlers_align(self) -> None:
        names_in_schema = {entry["function"]["name"] for entry in COUNCIL_TOOL_SCHEMAS}
        self.assertEqual(names_in_schema, set(COUNCIL_TOOL_HANDLERS.keys()))

    def test_execute_tool_returns_error_for_unknown_tool(self) -> None:
        payload = execute_tool("does_not_exist", "{}")
        self.assertIn("unknown tool", payload)

    def test_execute_tool_handles_invalid_json(self) -> None:
        payload = execute_tool("get_symbol_snapshot", "not-json")
        self.assertIn("invalid arguments JSON", payload)


class ToolCallingStrategistTests(unittest.TestCase):
    def test_strategist_passes_tool_schemas_and_returns_compiled_specs(self) -> None:
        received: dict[str, Any] = {}

        def fake_llm_call(system: str, prompt: str, tools: list[dict[str, Any]]) -> dict[str, Any]:
            received["system"] = system
            received["prompt"] = prompt
            received["tool_names"] = [t["function"]["name"] for t in tools]
            return {
                "strategies": [
                    {
                        "strategy_id": "stage2",
                        "horizon_days": 10,
                        "entry_rules": ["stage == 2"],
                        "exit_rules": ["close < sma_50"],
                        "risk_rules": ["max_position_pct=10"],
                        "thesis": "Tool-calling stage2 continuation.",
                    }
                ]
            }

        strategist = ToolCallingLLMStrategist(llm_call=fake_llm_call)
        config = CouncilConfig(symbol="DMART", max_candidates=2)
        evidence = EvidencePack(
            symbol="DMART",
            as_of="2026-05-14",
            technical={"close": 100, "bars": 260},
        )

        candidates = strategist.propose(evidence=evidence, config=config, prior_feedback=())

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].strategy_id, "stage2")
        self.assertEqual(candidates[0].origin, "llm")
        self.assertIn("get_symbol_snapshot", received["tool_names"])
        self.assertIn("get_filing_extract", received["tool_names"])

    def test_strategist_falls_back_when_llm_returns_nothing_usable(self) -> None:
        def empty_llm_call(_s: str, _p: str, _t: list[dict[str, Any]]) -> dict[str, Any]:
            return {"strategies": []}

        strategist = ToolCallingLLMStrategist(llm_call=empty_llm_call)
        config = CouncilConfig(symbol="DMART", max_candidates=2)
        evidence = EvidencePack(symbol="DMART", as_of="2026-05-14")
        candidates = strategist.propose(evidence=evidence, config=config, prior_feedback=())
        self.assertGreaterEqual(len(candidates), 1)
        self.assertTrue(all(c.origin == "deterministic_fallback" for c in candidates))


class ToolCallingCriticTests(unittest.TestCase):
    def test_critic_returns_structured_critique(self) -> None:
        def fake_llm_call(_s: str, _p: str, _t: list[dict[str, Any]]) -> dict[str, Any]:
            return {
                "verdict": "revise",
                "issues": ["thin validation evidence"],
                "required_changes": ["consult get_latest_results"],
                "confidence_delta": -0.1,
            }

        critic = ToolCallingLLMCritic("data_leakage", llm_call=fake_llm_call)
        critique = critic.critique(
            candidates=(),
            train_results=(BacktestSliceResult("train", "stage2", 10, {"total_return_pct": 5.0}, 3),),
            validation_results=(),
        )
        self.assertEqual(critique.verdict, "revise")
        self.assertIn("thin validation evidence", critique.issues)
        self.assertAlmostEqual(critique.confidence_delta, -0.1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
