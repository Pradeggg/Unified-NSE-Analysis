import unittest
from unittest.mock import patch

from terminal.agent import Agent, SYSTEM_PROMPT, _keyword_intent
from voice_persona import normalize_spoken_query


class TerminalAgentMarketPromptTests(unittest.TestCase):
    def test_system_prompt_enforces_market_clock_and_fallback_labels(self):
        self.assertIn("MARKET CLOCK + DATA FRESHNESS RULES", SYSTEM_PROMPT)
        self.assertIn("Do not describe fallback/EOD data as \"current intraday\"", SYSTEM_PROMPT)
        self.assertIn("Only quote RSI, MACD, VWAP", SYSTEM_PROMPT)

    def test_market_overview_routes_to_market_tools_not_overview_symbol(self):
        routed = _keyword_intent("Market overview")

        self.assertEqual(routed["intent"], "market_overview")
        self.assertEqual(routed["plan"][0][0], "get_live_market_overview")
        self.assertNotIn("OVERVIEW", str(routed))

    def test_recent_minutes_question_routes_to_market_recap_not_happened_symbol(self):
        routed = _keyword_intent("what happened in the last 15 minutes")

        self.assertEqual(routed["intent"], "intraday_market_recap")
        self.assertEqual(routed["plan"][0], ("get_intraday_market_recap", {"minutes": 15}))
        self.assertNotIn("HAPPENED", str(routed).upper())

    def test_recent_minutes_question_handles_minute_typo(self):
        routed = _keyword_intent("what happened in the last 30 minites")

        self.assertEqual(routed["intent"], "intraday_market_recap")
        self.assertEqual(routed["plan"][0], ("get_intraday_market_recap", {"minutes": 30}))

    def test_agent_executes_market_overview_without_llm_symbol_guess(self):
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"

        with patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.return_value = [
                {
                    "tool": "get_live_market_overview",
                    "args": {},
                    "result": {
                        "source": "NSE live API",
                        "as_of": "2026-05-11 10:15:00",
                        "indices": {
                            "NIFTY 50": {
                                "last": 23898.95,
                                "pct_change": -1.15,
                                "day_high": 23986.8,
                                "day_low": 23864.1,
                            }
                        },
                        "adv_dec": {"advances": 101, "declines": 400},
                    },
                },
                {
                    "tool": "get_market_breadth",
                    "args": {},
                    "result": {"advances": 10, "declines": 5, "ad_ratio": 2.0, "avg_rs_pct": 1.2},
                },
            ]
            result = agent.query("Market overview")

        execute_plan.assert_called_once()
        self.assertEqual(result["intent"], "market_overview")
        self.assertIn("LIVE MARKET", result["answer"])
        self.assertIn("NIFTY 50: 23,898.95  (-1.15%)", result["answer"])
        self.assertIn("Source: NSE live API", result["answer"])
        self.assertIn("Sources: NSE live API + DB breadth", result["answer"])
        self.assertIn("Live breadth: 101 advances / 400 declines", result["answer"])
        self.assertIn("DB UNIVERSE CONTEXT", result["answer"])
        self.assertNotIn("▶ MARKET BREADTH", result["answer"])
        self.assertNotIn("OVERVIEW.NS", result["answer"])

    def test_voice_wrapped_stock_question_routes_to_actual_symbol_not_answer_prefix(self):
        query = normalize_spoken_query("what is your read on d mart after results")
        routed = _keyword_intent(query)

        self.assertEqual(routed["intent"], "stock_brief")
        self.assertEqual(routed["plan"][0], ("resolve_symbol", {"query": "DMART"}))
        self.assertNotIn("ANSWER", str(routed).upper())

    def test_low_information_voice_answer_word_does_not_route_as_answer_ticker(self):
        query = normalize_spoken_query("Answer")
        routed = _keyword_intent(query)

        self.assertNotEqual(routed["intent"], "stock_brief")
        self.assertNotIn("ANSWER", str(routed).upper())

    def test_midcap_supertrend_15m_scan_routes_to_intraday_index_scan(self):
        query = (
            "Scan NIFTY MIDCAP 100 for stocks with active Supertrend research setups "
            "on 15m with clear invalidation levels"
        )
        routed = _keyword_intent(query, data_mode="intraday")

        self.assertEqual(routed["intent"], "intraday_index_scan")
        self.assertEqual(
            routed["plan"],
            [
                (
                    "scan_intraday_market",
                    {
                        "index": "NIFTY MIDCAP 100",
                        "interval": "15m",
                        "strategies": ["supertrend"],
                        "direction_filter": "all",
                        "min_rr": 1.3,
                        "top_n": 10,
                    },
                )
            ],
        )
        self.assertNotIn(("resolve_symbol", {"query": "NIFTY"}), routed["plan"])

    def test_agent_executes_intraday_scan_deterministically_without_nifty_stock_brief(self):
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"
        query = (
            "Scan NIFTY MIDCAP 100 for stocks with active Supertrend research setups "
            "on 15m with clear invalidation levels"
        )

        with patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.return_value = [
                {
                    "tool": "scan_intraday_market",
                    "args": {
                        "index": "NIFTY MIDCAP 100",
                        "interval": "15m",
                        "strategies": ["supertrend"],
                        "direction_filter": "all",
                        "min_rr": 1.3,
                        "top_n": 10,
                    },
                    "result": {
                        "index": "NIFTY MIDCAP 100",
                        "interval": "15m",
                        "top_buy": [
                            {
                                "symbol": "ABC",
                                "strategy": "Supertrend",
                                "entry": 101.0,
                                "target": 108.0,
                                "stoploss": 97.5,
                                "rr": 1.9,
                            }
                        ],
                        "top_sell": [],
                        "buy_signals": [{"symbol": "ABC"}],
                        "sell_signals": [],
                    },
                }
            ]
            result = agent.query(query)

        execute_plan.assert_called_once()
        self.assertEqual(result["intent"], "intraday_index_scan")
        self.assertIn("INTRADAY INDEX SCAN", result["answer"])
        self.assertIn("NIFTY MIDCAP 100", result["answer"])
        self.assertIn("invalidation 97.5", result["answer"])
        self.assertNotIn("━━━ NIFTY (NIFTY) — Market Brief", result["answer"])


if __name__ == "__main__":
    unittest.main()
