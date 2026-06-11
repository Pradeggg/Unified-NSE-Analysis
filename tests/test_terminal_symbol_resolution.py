import unittest
from unittest.mock import Mock, patch

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

    def test_resolve_symbol_picks_distinctive_name_token_over_generic_word(self):
        # Regression: a user query that includes a generic English word
        # (e.g. "invest") which happens to appear in another issuer's name
        # must not be silently resolved to that issuer. The distinctive
        # word in the query ("Premier Energies") should win.
        mapping = {
            "PREMIERENE": "PREMIERENE",
            "PREMIER ENERGIES LIMITED": "PREMIERENE",
            "PREMIER": "PREMIERENE",
            "AIIL": "AIIL",
            "AUTHUM INVESTMENT & INFRASTRUCTURE LTD": "AIIL",
            "AUTHUM": "AIIL",
        }
        with patch("terminal.tools._all_symbols_map", return_value=mapping), patch(
            "terminal.tools._get_live_session"
        ) as live_session:
            self.assertEqual(resolve_symbol("Premier Energies")["symbol"], "PREMIERENE")
            self.assertIsNone(resolve_symbol("invest")["symbol"])
            self.assertIsNone(resolve_symbol("INVEST")["symbol"])
            self.assertIsNone(resolve_symbol("energy")["symbol"])
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
        self.assertEqual(result["suggestion"], "NIVABUPA")
        self.assertIn("NIVABUPA", result["candidates"])

    def test_resolve_symbol_corrects_high_confidence_one_character_symbol_typo(self):
        with patch(
            "terminal.tools._all_symbols_map",
            return_value={"WAAREEENER": "WAAREEENER", "WAREHOUSE": "WAREHOUSE"},
        ), patch("terminal.tools._get_live_session") as live_session:
            result = resolve_symbol("WAREEENER")

        self.assertEqual(result["symbol"], "WAAREEENER")
        self.assertEqual(result["confidence"], "near-match")
        live_session.assert_not_called()

    def test_resolve_symbol_live_search_requires_exact_match_for_ticker_shape(self):
        search_response = Mock()
        search_response.raise_for_status.return_value = None
        search_response.json.return_value = {
            "results": [{"symbol": "NIVABUPA", "symbol_info": "Niva Bupa Health Insurance"}]
        }
        quote_response = Mock()
        quote_response.ok = False
        session = Mock()
        session.get.side_effect = [search_response, quote_response]

        with patch("terminal.tools._all_symbols_map", return_value={}), patch(
            "terminal.tools._get_live_session", return_value=session
        ):
            result = resolve_symbol("NAVABUPA")

        self.assertIsNone(result["symbol"])
        self.assertEqual(result["confidence"], "none")
        self.assertIn("No exact NSE symbol found", result["error"])

    def test_resolve_symbol_can_resolve_exact_ticker_from_live_quote_fallback(self):
        search_response = Mock()
        search_response.raise_for_status.return_value = None
        search_response.json.return_value = {"results": []}
        quote_response = Mock()
        quote_response.ok = True
        quote_response.json.return_value = {"info": {"symbol": "HDBFS", "companyName": "HDB Financial Services"}}
        session = Mock()
        session.get.side_effect = [search_response, quote_response]

        with patch("terminal.tools._all_symbols_map", return_value={}), patch(
            "terminal.tools._get_live_session", return_value=session
        ):
            result = resolve_symbol("HDBFS")

        self.assertEqual(result["symbol"], "HDBFS")
        self.assertEqual(result["confidence"], "nse-quote")

    def test_resolve_symbol_handles_usl_alias_locally(self):
        with patch("terminal.tools._get_live_session") as live_session:
            usl = resolve_symbol("USL")
            united_spirits = resolve_symbol("United Spirits")

        self.assertEqual(usl["symbol"], "UNITDSPR")
        self.assertEqual(united_spirits["symbol"], "UNITDSPR")
        live_session.assert_not_called()

    def test_resolve_symbol_handles_portfolio_broker_alias_visret(self):
        with patch("terminal.tools._get_live_session") as live_session:
            result = resolve_symbol("VISRET")

        self.assertEqual(result["symbol"], "V2RETAIL")
        live_session.assert_not_called()

    def test_resolve_symbol_handles_chennai_petroleum_aliases_locally(self):
        with patch("terminal.tools._get_live_session") as live_session:
            for query in ("Chennai Petroleum", "Chennai Petroleum Corporation", "CPCL", "CHENNPETRO"):
                with self.subTest(query=query):
                    result = resolve_symbol(query)
                    self.assertEqual(result["symbol"], "CHENNPETRO")

        live_session.assert_not_called()

    def test_resolve_symbol_projects_hybrid_confidence_fields(self):
        with patch(
            "terminal.tools._all_symbols_map",
            return_value={"TRENT": "TRENT", "TRENT LIMITED": "TRENT"},
        ), patch("terminal.tools._get_live_session") as live_session:
            result = resolve_symbol("TRENT")

        self.assertEqual(result["symbol"], "TRENT")
        self.assertEqual(result["confidence"], "exact")
        self.assertEqual(result["confidence_band"], "exact")
        self.assertEqual(result["score"], 1.0)
        self.assertEqual(result["method"], "dict")
        live_session.assert_not_called()

    def test_resolve_symbol_does_not_resolve_search_context_as_stock(self):
        with patch(
            "terminal.tools._all_symbols_map",
            return_value={
                "UNITDSPR": "UNITDSPR",
                "UNITED SPIRITS LIMITED": "UNITDSPR",
                "AURIGROW": "AURIGROW",
                "AURI GROW INDIA LIMITED": "AURIGROW",
            },
        ), patch("terminal.tools._get_live_session") as live_session:
            result = resolve_symbol("growth strategy")

        self.assertIsNone(result["symbol"])
        self.assertEqual(result["confidence"], "none")
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
