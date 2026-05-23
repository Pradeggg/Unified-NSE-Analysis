import unittest
from unittest.mock import Mock, patch

import nse_agent


class RicCompanyXrayTests(unittest.TestCase):
    def test_company_xray_ric_recipe_exists(self):
        recipe = nse_agent.RIC_LIBRARY["company-xray"]

        self.assertEqual(recipe["arg"], "symbol")
        self.assertEqual(recipe["example"], "/ric company-xray DMART")
        self.assertGreaterEqual(len(recipe["steps"]), 8)
        labels = [step["label"] for step in recipe["steps"]]
        self.assertEqual(labels[0], "Resolve Identity")
        self.assertIn("Final Report", labels)
        self.assertTrue(any("/company-index {symbol}" in step["prompt"] for step in recipe["steps"]))
        self.assertTrue(any("/company-xray {symbol}" in step["prompt"] for step in recipe["steps"]))

    def test_stock_ric_canonicalizes_near_match_symbol_before_steps(self):
        agent = Mock()
        agent.query.return_value = {"answer": "ok"}

        with patch("terminal.tools.resolve_symbol") as resolve_symbol, patch("nse_agent._print_response"):
            resolve_symbol.return_value = {
                "symbol": "WAAREEENER",
                "confidence": "near-match",
                "query": "WAREEENER",
                "candidates": ["WAAREEENER"],
            }
            nse_agent._run_ric(agent, "sherlock", "WAREEENER", show_trace=False)

        prompts = [call.args[0] for call in agent.query.call_args_list]
        self.assertEqual(len(prompts), len(nse_agent.RIC_LIBRARY["sherlock"]["steps"]))
        self.assertTrue(all("WAAREEENER" in prompt for prompt in prompts))
        self.assertTrue(all("WAREEENER" not in prompt for prompt in prompts))

    def test_stock_ric_remembers_aggregate_sequence_context_for_followups(self):
        class DummyAgent:
            def __init__(self):
                self.calls = []
                self.remembered = []
                self.responses = [
                    {
                        "answer": "MANINDS intraday SHORT_SETUP at 564.05; bearish below 569.71.",
                        "trace": [{"tool": "explain_intraday_setup"}, {"tool": "get_nse_intraday_snapshot"}],
                    },
                    {
                        "answer": "MANINDS EOD STAGE_2 BUY; RSI snapshot 78 and technical RSI 73; supertrend SELL.",
                        "trace": [{"tool": "get_symbol_snapshot"}, {"tool": "get_technical_setup"}],
                    },
                    {
                        "answer": "MANINDS fundamentals: PE 22.5, ROCE 16, debtor days increased.",
                        "trace": [{"tool": "scrape_screener_in"}],
                    },
                    {
                        "answer": "MANINDS catalysts: board meeting and acquisition filing.",
                        "trace": [{"tool": "search_latest_catalysts"}],
                    },
                    {
                        "answer": "MANINDS intraday levels: support 561.35, resistance 569.71.",
                        "trace": [{"tool": "get_intraday_levels"}],
                    },
                ]

            def query(self, prompt, show_trace=False):
                self.calls.append(prompt)
                return self.responses[len(self.calls) - 1]

            def _remember_interaction(self, user_input, answer, tool_results, turn_context=None):
                self.remembered.append((user_input, answer, tool_results, turn_context))

        agent = DummyAgent()

        with patch("nse_agent._print_response"), patch("terminal.tools.resolve_symbol", return_value={"symbol": "MANINDS"}):
            nse_agent._run_ric(agent, "sherlock", "MANINDS", show_trace=False)

        assert agent.remembered
        ctx = agent.remembered[-1][3]
        assert ctx.result_type == "ric_sequence"
        assert ctx.intent == "ric_sherlock"
        assert ctx.symbols == ["MANINDS"]
        assert "Step 1 Live Quote" in ctx.result_summary
        assert "Step 5 Trade Setup" in ctx.result_summary
        assert "SHORT_SETUP" in ctx.result_summary
        assert "STAGE_2 BUY" in ctx.result_summary
        assert "explain_intraday_setup" in ctx.tools
        assert "get_technical_setup" in ctx.tools


if __name__ == "__main__":
    unittest.main()
