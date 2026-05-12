import unittest
from unittest.mock import patch

from terminal.agent import SYSTEM_PROMPT
from terminal.agent import Agent
from terminal.tools import get_technical_setup, resolve_symbol


class TerminalSymbolResolutionTests(unittest.TestCase):
    def test_resolve_symbol_handles_common_nse_truncated_symbol_alias_locally(self):
        with patch(
            "terminal.tools._all_symbols_map",
            return_value={"DATAPATTNS": "DATAPATTNS", "DATAMATICS": "DATAMATICS"},
        ), patch("terminal.tools._get_live_session") as live_session:
            result = resolve_symbol("DATAPATTERNS")

        self.assertEqual(result["symbol"], "DATAPATTNS")
        self.assertIn(result["confidence"], {"fuzzy", "near-match"})
        live_session.assert_not_called()

    def test_resolve_symbol_does_not_substitute_exact_unknown_ticker(self):
        with patch(
            "terminal.tools._all_symbols_map",
            return_value={"NIVABUPA": "NIVABUPA", "NAVA": "NAVA"},
        ), patch("terminal.tools._get_live_session") as live_session:
            result = resolve_symbol("NAVABUPA")

        self.assertIsNone(result["symbol"])
        self.assertEqual(result["confidence"], "none")
        self.assertIn("No exact NSE symbol found", result["error"])
        live_session.assert_not_called()

    def test_get_technical_setup_uses_resolved_local_symbol_for_price_history(self):
        with patch(
            "terminal.tools._all_symbols_map",
            return_value={"DATAPATTNS": "DATAPATTNS", "DATAMATICS": "DATAMATICS"},
        ), patch("terminal.tools._load_price_history") as load_history:
            load_history.return_value.empty = True
            result = get_technical_setup("DATAPATTERNS")

        load_history.assert_called_once_with("DATAPATTNS", 400)
        self.assertEqual(result["symbol"], "DATAPATTNS")

    def test_llm_prompt_requires_symbol_resolution_before_stock_tools(self):
        self.assertIn("Always resolve the entity first with resolve_symbol", SYSTEM_PROMPT)
        self.assertIn("canonical NSE symbol", SYSTEM_PROMPT)

    def test_unresolved_exact_symbol_answer_reports_missing_evidence(self):
        agent = Agent()
        agent.backend = None

        with patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.return_value = [
                {
                    "tool": "resolve_symbol",
                    "args": {"query": "NAVABUPA"},
                    "result": {"symbol": None, "confidence": "none", "error": "No exact NSE symbol found for 'NAVABUPA'"},
                },
                {
                    "tool": "get_symbol_snapshot",
                    "args": {"symbol": "NAVABUPA"},
                    "result": {"error": "NAVABUPA not found in DB snapshot"},
                },
            ]

            result = agent.query("What about NAVABUPA? If data is not available, say exactly what is missing.")

        self.assertIn("Missing evidence", result["answer"])
        self.assertIn("resolve_symbol", result["answer"])


if __name__ == "__main__":
    unittest.main()
