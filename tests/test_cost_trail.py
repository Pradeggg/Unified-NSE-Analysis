"""AA-CC-3: Source Trail Token + Cost Telemetry tests.

Covers:
  1. Usage captured from a direct LLM ask (accumulates across rounds).
  2. Usage accumulated across compound plan sub-queries.
  3. Missing/None usage degrades gracefully (no exception, empty block).
  4. _cost_trail_block renders expected fields when usage is present.
  5. _cost_trail_block is empty when usage is all-zero.
  6. agent.query() result carries 'usage' key for LLM-driven turns.
  7. Compound query aggregates usage from all parts.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from terminal.agent import (
    _accumulate_usage,
    _cost_trail_block,
    _tool_stats_from_results,
    _usd_cost_for_usage,
    Agent,
)


# ─── unit helpers ────────────────────────────────────────────────────────────

class TestAccumulateUsage:
    def test_sums_keys(self):
        acc = {"input_tokens": 100, "output_tokens": 50,
               "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
        _accumulate_usage(acc, {"input_tokens": 200, "output_tokens": 75,
                                "cache_read_input_tokens": 10, "cache_creation_input_tokens": 5})
        assert acc["input_tokens"] == 300
        assert acc["output_tokens"] == 125
        assert acc["cache_read_input_tokens"] == 10
        assert acc["cache_creation_input_tokens"] == 5

    def test_handles_missing_keys_in_new(self):
        acc = {"input_tokens": 10, "output_tokens": 5,
               "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
        _accumulate_usage(acc, {})
        assert acc["input_tokens"] == 10

    def test_handles_none_values(self):
        acc = {"input_tokens": 0, "output_tokens": 0,
               "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
        _accumulate_usage(acc, {"input_tokens": None, "output_tokens": None})
        assert acc["input_tokens"] == 0


class TestToolStats:
    def test_classifies_search_tools(self):
        trs = [
            {"tool": "search_latest_catalysts", "result": {}},
            {"tool": "search_yahoo_finance", "result": {}},
        ]
        stats = _tool_stats_from_results(trs)
        assert stats["searchCount"] == 2
        assert stats["readCount"] == 0

    def test_classifies_read_tools(self):
        trs = [
            {"tool": "get_symbol_snapshot", "result": {}},
            {"tool": "scrape_screener_in", "result": {}},
            {"tool": "run_screener_query", "result": {}},
        ]
        stats = _tool_stats_from_results(trs)
        assert stats["readCount"] == 3
        assert stats["searchCount"] == 0

    def test_empty_results(self):
        stats = _tool_stats_from_results([])
        assert stats == {"readCount": 0, "searchCount": 0}


class TestCostTrailBlock:
    def test_renders_in_out_and_tools(self):
        usage = {"input_tokens": 1000, "output_tokens": 400,
                 "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
        trs = [{"tool": "get_symbol_snapshot", "result": {}}]
        block = _cost_trail_block(usage, trs)
        assert "▶ COST" in block
        assert "in=1000" in block
        assert "out=400" in block
        assert "read=1" in block

    def test_includes_cache_read_when_nonzero(self):
        usage = {"input_tokens": 500, "output_tokens": 100,
                 "cache_read_input_tokens": 200, "cache_creation_input_tokens": 0}
        block = _cost_trail_block(usage, [])
        assert "cache_read=200" in block

    def test_omits_cache_fields_when_zero(self):
        usage = {"input_tokens": 500, "output_tokens": 100,
                 "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
        block = _cost_trail_block(usage, [])
        assert "cache_read" not in block
        assert "cache_create" not in block

    def test_empty_when_all_zero(self):
        usage = {"input_tokens": 0, "output_tokens": 0,
                 "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
        assert _cost_trail_block(usage, []) == ""

    def test_empty_when_usage_none(self):
        assert _cost_trail_block(None, []) == ""

    def test_empty_when_usage_empty_dict(self):
        assert _cost_trail_block({}, []) == ""


class TestUsdCostForUsage:
    def test_gpt_4o_pricing(self):
        # 1M input + 500k output on gpt-4o = $2.50 + $5.00 = $7.50
        usage = {"input_tokens": 1_000_000, "output_tokens": 500_000,
                 "cache_read_input_tokens": 0, "model": "gpt-4o"}
        cost = _usd_cost_for_usage(usage)
        assert cost is not None
        assert abs(cost - 7.50) < 0.001

    def test_gpt_4o_mini_pricing(self):
        # 1M input + 1M output on gpt-4o-mini = $0.15 + $0.60 = $0.75
        usage = {"input_tokens": 1_000_000, "output_tokens": 1_000_000,
                 "cache_read_input_tokens": 0, "model": "gpt-4o-mini"}
        cost = _usd_cost_for_usage(usage)
        assert cost is not None
        assert abs(cost - 0.75) < 0.001

    def test_longest_prefix_match_picks_mini(self):
        # "gpt-4o-mini-2024-07-18" must match gpt-4o-mini, not gpt-4o.
        usage = {"input_tokens": 1_000_000, "output_tokens": 0,
                 "cache_read_input_tokens": 0, "model": "gpt-4o-mini-2024-07-18"}
        cost = _usd_cost_for_usage(usage)
        assert cost is not None
        assert abs(cost - 0.15) < 0.001  # gpt-4o-mini price, not gpt-4o ($2.50)

    def test_cached_tokens_priced_at_discount(self):
        # 1M cached on gpt-4o = $1.25 (not $2.50)
        usage = {"input_tokens": 1_000_000, "output_tokens": 0,
                 "cache_read_input_tokens": 1_000_000, "model": "gpt-4o"}
        cost = _usd_cost_for_usage(usage)
        assert cost is not None
        assert abs(cost - 1.25) < 0.001

    def test_unknown_model_returns_none(self):
        usage = {"input_tokens": 100, "output_tokens": 50, "model": "mystery-llm-7b"}
        assert _usd_cost_for_usage(usage) is None

    def test_missing_model_returns_none(self):
        usage = {"input_tokens": 100, "output_tokens": 50}
        assert _usd_cost_for_usage(usage) is None

    def test_cost_appears_in_trail_block(self):
        usage = {"input_tokens": 1000, "output_tokens": 400,
                 "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0,
                 "model": "gpt-4o-mini"}
        block = _cost_trail_block(usage, [])
        assert "cost=$" in block


class TestAccumulateUsageModel:
    def test_model_carried_from_new(self):
        acc = {"input_tokens": 0, "output_tokens": 0,
               "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
        _accumulate_usage(acc, {"input_tokens": 10, "output_tokens": 5, "model": "gpt-4o"})
        assert acc["model"] == "gpt-4o"

    def test_model_preserved_when_new_lacks_it(self):
        acc = {"input_tokens": 0, "output_tokens": 0,
               "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0,
               "model": "gpt-4o"}
        _accumulate_usage(acc, {"input_tokens": 10, "output_tokens": 5})
        assert acc["model"] == "gpt-4o"


# ─── integration: agent.query() ──────────────────────────────────────────────

def _make_agent() -> Agent:
    agent = Agent()
    agent.backend = MagicMock()
    agent.backend_name = "MockBackend"
    return agent


class TestCostTrailIntegration:
    def test_llm_driven_result_carries_usage(self):
        agent = _make_agent()
        mock_usage = {"input_tokens": 800, "output_tokens": 300,
                      "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
        with patch("terminal.agent._execute_plan", return_value=[]), \
             patch("terminal.agent._keyword_intent",
                   return_value={"intent": "general_chat", "plan": []}), \
             patch.object(agent, "_execute_route", return_value=None), \
             patch.object(agent, "_llm_query",
                          return_value={
                              "answer": "Some LLM answer. ━━━ Not investment advice. For research and learning only. ━━━",
                              "trace": [{"tool": "get_symbol_snapshot", "result": {}}],
                              "backend": "MockBackend",
                              "intent": "llm_driven",
                              "has_source_trail": False,
                              "usage": mock_usage,
                              "catalysts": None,
                              "comparison": None,
                              "turn": 1,
                          }):
            result = agent.query("RELIANCE setup")

        assert "usage" in result
        assert result["usage"]["input_tokens"] == 800
        assert result["usage"]["output_tokens"] == 300
        assert "▶ COST" in result["answer"]

    def test_missing_usage_degrades_gracefully(self):
        agent = _make_agent()
        with patch("terminal.agent._execute_plan", return_value=[]), \
             patch("terminal.agent._keyword_intent",
                   return_value={"intent": "general_chat", "plan": []}), \
             patch.object(agent, "_execute_route", return_value=None), \
             patch.object(agent, "_llm_query",
                          return_value={
                              "answer": "Answer ━━━ Not investment advice. For research and learning only. ━━━",
                              "trace": [],
                              "backend": "MockBackend",
                              "intent": "llm_driven",
                              "has_source_trail": False,
                              # no "usage" key at all
                              "catalysts": None,
                              "comparison": None,
                              "turn": 1,
                          }):
            result = agent.query("market overview")

        # Must not raise; cost block should simply not appear
        assert "answer" in result
        assert "▶ COST" not in result["answer"]

    def test_compound_query_aggregates_usage(self):
        agent = _make_agent()

        sub_results = [
            {
                "answer": "Part 1 answer ━━━ Not investment advice. For research and learning only. ━━━",
                "trace": [{"tool": "get_live_market_overview", "result": {}}],
                "backend": "MockBackend",
                "intent": "llm_driven",
                "has_source_trail": False,
                "usage": {"input_tokens": 400, "output_tokens": 150,
                          "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
            },
            {
                "answer": "Part 2 answer ━━━ Not investment advice. For research and learning only. ━━━",
                "trace": [{"tool": "search_latest_catalysts", "result": {}}],
                "backend": "MockBackend",
                "intent": "llm_driven",
                "has_source_trail": False,
                "usage": {"input_tokens": 600, "output_tokens": 250,
                          "cache_read_input_tokens": 50, "cache_creation_input_tokens": 0},
            },
        ]

        with patch("terminal.agent._split_compound_query",
                   return_value=["Market overview", "latest news for DMART"]), \
             patch.object(agent, "_query_single", side_effect=sub_results):
            result = agent.query("Market overview and also latest news for DMART")

        assert result["intent"] == "compound"
        assert "usage" in result
        assert result["usage"]["input_tokens"] == 1000
        assert result["usage"]["output_tokens"] == 400
        assert result["usage"]["cache_read_input_tokens"] == 50
        assert "▶ COST" in result["answer"]


if __name__ == "__main__":
    import unittest

    loader = unittest.TestLoader()
    suite = loader.discover(str(ROOT / "tests"), pattern="test_cost_trail.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    print()
    print(f"── Summary ──")
    print(f"  RAN: {result.testsRun}    "
          f"FAIL: {len(result.failures)}    "
          f"ERR: {len(result.errors)}    "
          f"SKIP: {len(result.skipped)}")
    import sys as _sys
    _sys.exit(0 if result.wasSuccessful() else 1)
