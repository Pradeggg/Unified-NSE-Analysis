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

    def test_typo_market_status_breadth_and_gainers_routes_to_overview_with_movers(self):
        query = "what is the current indin market status and how is the breadth, which are the top gainers in stocks and indices"

        routed = _keyword_intent(query, data_mode="intraday")

        self.assertEqual(routed["intent"], "market_situation_assessment")
        self.assertEqual(
            routed["plan"],
            [
                ("get_live_market_overview", {}),
                ("get_market_breadth", {}),
                ("get_top_gainers_losers", {"index": "NIFTY 500", "top_n": 5, "direction": "both"}),
            ],
        )
        self.assertIn("assessment_plan", routed)
        derived_tasks = [
            task for task in routed["assessment_plan"]["tasks"]
            if task.get("derived_from") == "get_live_market_overview"
        ]
        self.assertTrue(derived_tasks)
        self.assertIn("recovery_plan", derived_tasks[0])
        self.assertNotIn("INDIN", str(routed).upper())

    def test_agent_market_status_breadth_and_gainers_renders_stock_and_index_movers(self):
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"
        query = "what is the current indin market status and how is the breadth, which are the top gainers in stocks and indices"

        with patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.return_value = [
                {
                    "tool": "get_live_market_overview",
                    "args": {},
                    "result": {
                        "source": "NSE live API",
                        "as_of": "2026-05-12 10:18:00",
                        "indices": {
                            "NIFTY 50": {"last": 23900.0, "pct_change": 0.21},
                            "NIFTY BANK": {"last": 54500.0, "pct_change": -0.11},
                            "NIFTY IT": {"last": 35000.0, "pct_change": 1.45},
                        },
                        "adv_dec": {"advances": 310, "declines": 190},
                    },
                },
                {"tool": "get_market_breadth", "args": {}, "result": {"advances": 600, "declines": 380, "ad_ratio": 1.58, "avg_rs_pct": 2.1}},
                {
                    "tool": "get_top_gainers_losers",
                    "args": {"index": "NIFTY 500", "top_n": 5, "direction": "both"},
                    "result": {
                        "gainers": [{"symbol": "AAA", "pct_change": 5.2}, {"symbol": "BBB", "pct_change": 4.1}],
                        "losers": [{"symbol": "ZZZ", "pct_change": -3.4}],
                    },
                },
            ]

            result = agent.query(query)

        execute_plan.assert_called_once()
        self.assertEqual(result["intent"], "market_situation_assessment")
        self.assertIn("SITUATION ASSESSMENT PLAN", result["answer"])
        self.assertIn("derived_from=get_live_market_overview", result["answer"])
        self.assertIn("recovery/code plan", result["answer"])
        self.assertIn("LIVE MARKET", result["answer"])
        self.assertIn("Live breadth: 310 advances / 190 declines", result["answer"])
        self.assertIn("INDEX MOVERS", result["answer"])
        self.assertIn("NIFTY IT +1.45%", result["answer"])
        self.assertIn("TOP STOCK MOVERS", result["answer"])
        self.assertIn("AAA +5.20%", result["answer"])
        self.assertNotIn("INDIN", result["answer"].upper())

    def test_market_dashboard_routes_to_dashboard_tool_plan(self):
        routed = _keyword_intent("current market dashboard with narrative", data_mode="intraday")

        self.assertEqual(routed["intent"], "market_dashboard")
        self.assertEqual(
            [name for name, _ in routed["plan"]],
            [
                "get_live_market_overview",
                "get_market_breadth",
                "get_top_gainers_losers",
                "get_fii_dii_activity",
                "get_global_market_assessment",
                "search_latest_catalysts",
            ],
        )

    def test_agent_market_dashboard_renders_comprehensive_sections(self):
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
                        "as_of": "2026-05-12 11:20:00",
                        "indices": {
                            "NIFTY 50": {"last": 23600.0, "pct_change": -0.4},
                            "NIFTY BANK": {"last": 54100.0, "pct_change": -0.2},
                            "NIFTY METAL": {"last": 13000.0, "pct_change": 1.1},
                            "NIFTY IT": {"last": 28200.0, "pct_change": -2.0},
                            "INDIA VIX": {"last": 18.7, "pct_change": 0.8},
                        },
                        "adv_dec": {"advances": 120, "declines": 380},
                    },
                },
                {
                    "tool": "get_market_breadth",
                    "args": {},
                    "result": {
                        "advances": 350,
                        "declines": 650,
                        "ad_ratio": 0.54,
                        "avg_rs_pct": -1.5,
                        "stage_distribution": {"STAGE_1": 100, "STAGE_2": 200, "STAGE_3": 300, "STAGE_4": 400},
                    },
                },
                {
                    "tool": "get_top_gainers_losers",
                    "args": {"index": "NIFTY 500", "top_n": 5, "direction": "both"},
                    "result": {
                        "gainers": [{"symbol": "AAA", "pct_change": 5.0}],
                        "losers": [{"symbol": "ZZZ", "pct_change": -4.0}],
                    },
                },
                {
                    "tool": "get_fii_dii_activity",
                    "args": {},
                    "result": {"data": [{"category": "FII", "net_crore": -1500.0, "sentiment": "SELLING"}]},
                },
                {
                    "tool": "get_global_market_assessment",
                    "args": {},
                    "result": {
                        "risk_regime": "risk-off",
                        "as_of": "2026-05-12",
                        "india_readthrough": ["USD/INR and crude remain key macro variables."],
                        "watch_items": ["IT weakness", "Metal resilience"],
                    },
                },
                {
                    "tool": "search_latest_catalysts",
                    "args": {"symbol": "NIFTY India market today"},
                    "result": {"results": [{"title": "Market headline", "url": "https://example.com"}]},
                },
            ]

            result = agent.query("current market dashboard with narrative")

        execute_plan.assert_called_once()
        self.assertEqual(result["intent"], "market_dashboard")
        self.assertIn("Current Market Dashboard", result["answer"])
        self.assertIn("Market Tape", result["answer"])
        self.assertIn("Index Leadership", result["answer"])
        self.assertIn("Breadth & Internal Health", result["answer"])
        self.assertIn("Stock Movers", result["answer"])
        self.assertIn("Flows", result["answer"])
        self.assertIn("Global Read-through", result["answer"])
        self.assertIn("Catalyst Tape", result["answer"])
        self.assertIn("Narrative", result["answer"])
        self.assertIn("Dashboard bias: defensive / risk-off", result["answer"])
        self.assertNotIn("LIVE MARKET", result["answer"])

    def test_greeting_does_not_route_to_hello_symbol(self):
        routed = _keyword_intent("Hello")

        self.assertEqual(routed["intent"], "greeting")
        self.assertEqual(routed["plan"], [])
        self.assertNotIn("HELLO", str(routed).upper())

    def test_agent_greeting_does_not_execute_symbol_tools(self):
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"

        with patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.return_value = []
            result = agent.query("Hello")

        execute_plan.assert_called_once_with([])
        self.assertEqual(result["intent"], "greeting")
        self.assertIn("Agent Adda is ready", result["answer"])
        self.assertNotIn("HELLO (HELLO)", result["answer"])
        self.assertNotIn("No NSE symbol found", result["answer"])

    def test_morning_briefing_routes_to_market_tools_not_knowledge_search(self):
        query = """
        You are starting a new trading session on Tuesday, 12 May 2026 at 09:25 IST.
        Give a comprehensive morning briefing.
        Global Overnight Context: US markets, Asian markets, USD/INR, crude oil.
        """

        routed = _keyword_intent(query, data_mode="global")

        self.assertEqual(routed["intent"], "startup_morning_briefing")
        planned_tools = [name for name, _ in routed["plan"]]
        self.assertIn("get_global_market_assessment", planned_tools)
        self.assertIn("get_live_market_overview", planned_tools)
        self.assertIn("get_fii_dii_activity", planned_tools)
        self.assertIn("get_top_gainers_losers", planned_tools)
        self.assertNotIn("search_market_knowledge", planned_tools)

    def test_agent_executes_morning_briefing_without_llm_knowledge_lookup(self):
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"

        with patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.return_value = [
                {
                    "tool": "get_global_market_assessment",
                    "args": {},
                    "result": {
                        "risk_regime": "mixed",
                        "as_of": "2026-05-11",
                        "regions": {"US": {"avg_pct_change": 0.4, "bias": "positive"}},
                        "moves": {"S&P 500": {"pct_change": 0.5}, "USDINR": {"pct_change": -0.1}},
                        "india_readthrough": ["Positive US cue but watch USD/INR."],
                        "watch_items": ["Crude oil and USD/INR are key macro variables."],
                    },
                },
                {
                    "tool": "get_index_snapshot",
                    "args": {"index_name": "NIFTY 50"},
                    "result": {"index": "NIFTY 50", "close": 23816.0, "chg_pct": -1.49},
                },
                {
                    "tool": "get_index_snapshot",
                    "args": {"index_name": "NIFTY BANK"},
                    "result": {"index": "NIFTY BANK", "close": 54440.0, "chg_pct": -1.57},
                },
                {
                    "tool": "get_live_market_overview",
                    "args": {},
                    "result": {
                        "source": "NSE live API",
                        "as_of": "2026-05-12 09:25:00",
                        "indices": {
                            "NIFTY 50": {"last": 23900.0, "pct_change": 0.21},
                            "NIFTY BANK": {"last": 54500.0, "pct_change": 0.11},
                        },
                        "adv_dec": {"advances": 280, "declines": 220},
                    },
                },
                {"tool": "get_market_breadth", "args": {}, "result": {"advances": 510, "declines": 470, "ad_ratio": 1.09}},
                {
                    "tool": "get_top_gainers_losers",
                    "args": {"index": "NIFTY 50", "top_n": 3, "direction": "both"},
                    "result": {
                        "gainers": [{"symbol": "ABC", "pct_change": 2.1}],
                        "losers": [{"symbol": "XYZ", "pct_change": -1.3}],
                    },
                },
                {"tool": "get_fii_dii_activity", "args": {}, "result": {"data": [{"category": "FII", "net_crore": -1000.0, "sentiment": "SELLING"}]}},
                {"tool": "search_latest_catalysts", "args": {"symbol": "NIFTY"}, "result": {"results": [{"title": "Market cues", "url": "https://example.com"}]}},
            ]

            result = agent.query("Morning briefing with Global Overnight Context and Current Market Status")

        execute_plan.assert_called_once()
        self.assertEqual(result["intent"], "startup_morning_briefing")
        self.assertIn("Global Overnight Context", result["answer"])
        self.assertIn("Current Market Status", result["answer"])
        self.assertIn("NIFTY 50: 23,900.00 (+0.21%)", result["answer"])
        self.assertIn("FII/DII", result["answer"])
        self.assertNotIn("No reliable Investopedia or Wikipedia source", result["answer"])

    def test_voice_wrapped_stock_question_routes_to_actual_symbol_not_answer_prefix(self):
        query = normalize_spoken_query("what is your read on d mart after results")
        routed = _keyword_intent(query)

        self.assertEqual(routed["intent"], "stock_brief")
        self.assertEqual(routed["plan"][0], ("resolve_symbol", {"query": "DMART"}))
        self.assertNotIn("ANSWER", str(routed).upper())

    def test_sector_context_for_symbol_routes_symbol_not_literal_sector(self):
        routed = _keyword_intent("What is the sector context for RELIANCE?")

        self.assertEqual(routed["intent"], "sector_scan")
        self.assertEqual(routed["plan"], [("get_sector_context", {"sector_or_symbol": "RELIANCE"})])
        self.assertNotIn("'Sector'", str(routed))

    def test_compare_query_routes_to_compare_stocks_not_sector(self):
        routed = _keyword_intent("Compare RELIANCE vs ONGC from technical and sector strength perspective")

        self.assertEqual(routed["intent"], "stock_comparison")
        self.assertEqual(
            routed["plan"],
            [("compare_stocks", {"symbols": ["RELIANCE", "ONGC"], "aspects": ["technical"]})],
        )

    def test_portfolio_wording_routes_symbols_not_own_ticker(self):
        routed = _keyword_intent("I own RELIANCE TCS INFY, check overlap, risk and what I should monitor today", data_mode="intraday")

        self.assertEqual(routed["intent"], "portfolio_review")
        self.assertEqual(
            routed["plan"],
            [("generate_portfolio_narratives", {"symbols": ["RELIANCE", "TCS", "INFY"], "top_n": 3})],
        )
        self.assertNotIn("'OWN'", str(routed))

    def test_deep_dive_into_symbol_ignores_preposition(self):
        routed = _keyword_intent("Deep dive into WELCORP including technicals, fundamentals, latest news and forensic red flags")

        self.assertEqual(routed["intent"], "stock_brief")
        self.assertEqual(routed["plan"][0], ("resolve_symbol", {"query": "WELCORP"}))
        self.assertNotIn("'INTO'", str(routed))

    def test_end_to_end_trade_research_routes_to_explicit_symbol_not_task_label(self):
        routed = _keyword_intent(
            "End-to-end trade research for THERMAX with technical setup, fundamentals and risk"
        )

        self.assertEqual(routed["intent"], "stock_brief")
        self.assertEqual(routed["plan"][0], ("resolve_symbol", {"query": "THERMAX"}))
        self.assertNotIn("END-TO-END", str(routed).upper())

    def test_earnings_playbook_routes_to_explicit_symbol_not_earnings_label(self):
        routed = _keyword_intent(
            "Earnings playbook for TCS after results with margin, valuation and risk"
        )

        self.assertEqual(routed["intent"], "stock_brief")
        self.assertEqual(routed["plan"][0], ("resolve_symbol", {"query": "TCS"}))
        self.assertNotIn("'EARNINGS'", str(routed).upper())

    def test_market_education_examples_do_not_route_teach_as_symbol(self):
        routed = _keyword_intent("Teach me PE with examples from TCS and INFY")

        self.assertEqual(routed["intent"], "market_knowledge")
        self.assertEqual(routed["plan"][0][0], "search_market_knowledge")
        self.assertNotIn("'TEACH'", str(routed).upper())

    def test_events_query_routes_to_event_calendar_not_events_ticker(self):
        routed = _keyword_intent("What events, results or corporate actions should I watch this week?")

        self.assertEqual(routed["intent"], "event_calendar")
        self.assertEqual(
            routed["plan"],
            [("get_event_calendar_summary", {"index": "NIFTY 50", "days_ahead": 14})],
        )
        self.assertNotIn("SABEVENTS", str(routed).upper())

    def test_fno_overview_routes_to_derivatives_tools_not_market_overview(self):
        routed = _keyword_intent(
            "Give a comprehensive F&O overview for NIFTY: option chain PCR max pain top OI strikes, futures basis and cost of carry"
        )

        self.assertEqual(routed["intent"], "fno_overview")
        self.assertEqual(
            routed["plan"],
            [
                ("get_options_chain", {"symbol": "NIFTY", "expiry_index": 0}),
                ("get_futures_analysis", {"symbol": "NIFTY"}),
            ],
        )
        self.assertNotEqual(routed["intent"], "market_overview")
        self.assertNotIn("get_live_market_overview", str(routed))

    def test_intraday_nifty_uses_nse_snapshot_before_fallback(self):
        routed = _keyword_intent(
            "Intraday technical analysis of NIFTY50 right now. Use NSE website snapshot first, then yfinance only as fallback, and label stale data.",
            data_mode="intraday",
        )

        self.assertEqual(routed["intent"], "intraday_setup")
        self.assertIn(("get_nse_intraday_snapshot", {"symbol": "NIFTY50"}), routed["plan"])
        self.assertIn(("get_intraday_analysis", {"symbol": "NIFTY50"}), routed["plan"])

    def test_sector_analysis_routes_to_sector_context_not_market_overview(self):
        routed = _keyword_intent("Sector analysis for IT: breadth, leaders, laggards, rotation, and risks.")

        self.assertEqual(routed["intent"], "sector_scan")
        self.assertEqual(routed["plan"], [("get_sector_context", {"sector_or_symbol": "IT"})])
        self.assertNotIn("get_live_market_overview", str(routed))

    def test_agent_carries_last_symbol_into_pronoun_comparison(self):
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"

        with patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.side_effect = [
                [
                    {"tool": "resolve_symbol", "args": {"query": "WELCORP"}, "result": {"symbol": "WELCORP"}},
                    {"tool": "get_symbol_snapshot", "args": {"symbol": "WELCORP"}, "result": {"symbol": "WELCORP"}},
                    {"tool": "get_technical_setup", "args": {"symbol": "WELCORP"}, "result": {"symbol": "WELCORP"}},
                    {"tool": "get_sector_context", "args": {"sector_or_symbol": "WELCORP"}, "result": {}},
                ],
                [
                    {
                        "tool": "compare_stocks",
                        "args": {"symbols": ["WELCORP", "NAVABUPA"], "aspects": ["both"]},
                        "result": {"symbols": ["WELCORP", "NAVABUPA"], "stock_details": []},
                    }
                ],
            ]

            agent.query("Analyze WELCORP as a company and stock")
            result = agent.query("Now compare it with NAVABUPA and tell me which one has better evidence quality")

        self.assertEqual(result["intent"], "stock_comparison")
        self.assertEqual(
            execute_plan.call_args_list[1].args[0],
            [("compare_stocks", {"symbols": ["WELCORP", "NAVABUPA"], "aspects": ["both"]})],
        )

    def test_agent_fno_overview_renders_option_chain_and_futures(self):
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"
        query = "Give a comprehensive F&O overview for NIFTY: option chain PCR max pain top OI strikes, futures basis and cost of carry"

        with patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.return_value = [
                {
                    "tool": "get_options_chain",
                    "args": {"symbol": "NIFTY", "expiry_index": 0},
                    "result": {
                        "symbol": "NIFTY",
                        "expiry": "2026-05-12",
                        "underlying": 23650.0,
                        "atm": 23650,
                        "pcr": 0.82,
                        "max_pain": 23700,
                        "total_call_oi": 1200000,
                        "total_put_oi": 984000,
                        "calls": [{"strike": 23700, "oi": 400000, "chg_oi": 25000}],
                        "puts": [{"strike": 23600, "oi": 350000, "chg_oi": 18000}],
                        "source": "NSE live API",
                    },
                },
                {
                    "tool": "get_futures_analysis",
                    "args": {"symbol": "NIFTY"},
                    "result": {
                        "symbol": "NIFTY",
                        "spot": 23650.0,
                        "source": "NSE live API",
                        "as_of": "2026-05-12 10:45:00",
                        "lot_size": 75,
                        "futures": [
                            {
                                "expiry": "2026-05-28",
                                "last_price": 23680.0,
                                "basis": 30.0,
                                "basis_pct": 0.127,
                                "cost_of_carry_annualised_pct": 3.2,
                                "oi": 100000,
                                "oi_change": 5000,
                            }
                        ],
                        "rollover": {"rollover_pct": 12.5, "interpretation": "Low rollover"},
                    },
                },
            ]

            result = agent.query(query)

        execute_plan.assert_called_once()
        self.assertEqual(result["intent"], "fno_overview")
        self.assertIn("F&O Overview", result["answer"])
        self.assertIn("OPTION CHAIN", result["answer"])
        self.assertIn("PCR: 0.82", result["answer"])
        self.assertIn("Max pain: 23700", result["answer"])
        self.assertIn("Top CE OI", result["answer"])
        self.assertIn("FUTURES BASIS & CARRY", result["answer"])
        self.assertIn("basis 30.00 (0.127%)", result["answer"])
        self.assertNotIn("LIVE MARKET", result["answer"])

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
