import unittest
from unittest.mock import patch

from terminal.agent import Agent, SYSTEM_PROMPT, _keyword_intent, _required_tools_for_query
from terminal.tools import compare_stocks
from terminal.deliberation import build_hypotheses, build_plan, evaluate_evidence, render_final_answer
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

    def test_placeholder_symbol_request_does_not_run_stock_tools(self):
        routed = _keyword_intent("/assess SYMBOL")

        self.assertEqual(routed["intent"], "placeholder_symbol_request")
        self.assertEqual(routed["plan"], [])

    def test_placeholder_detection_does_not_block_prose_stock_or_symbol_words(self):
        education = _keyword_intent(
            "Teach me PE vs PB using TCS and INFY examples, but do not run a stock deep dive"
        )
        screener = _keyword_intent(
            "show stocks above VWAP bounce / vwap reclaim right now, not a single symbol",
            data_mode="intraday",
        )

        self.assertEqual(education["intent"], "market_knowledge")
        self.assertEqual(screener["intent"], "intraday_screener")
        self.assertEqual(screener["plan"], [("run_intraday_screener", {"screen_type": "vwap_reclaim"})])

    def test_document_link_followup_does_not_route_to_stock_brief(self):
        for query in (
            "check alternative document link",
            "find alternative PDF link for Diageo India audited financial results",
        ):
            with self.subTest(query=query):
                routed = _keyword_intent(query)
                self.assertEqual(routed["intent"], "document_link_help")
                self.assertEqual(routed["plan"], [])
                self.assertNotIn("resolve_symbol", str(routed))
                self.assertNotIn("TI", str(routed))

    def test_agent_explains_document_link_followup_without_resolving_symbol(self):
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"

        with patch("terminal.agent._execute_plan") as execute_plan:
            result = agent.query("check alternative document link")

        execute_plan.assert_called_once_with([])
        self.assertEqual(result["intent"], "document_link_help")
        self.assertIn("DOCUMENT LINK FOLLOW-UP", result["answer"])
        self.assertIn("/analyze <URL>", result["answer"])
        self.assertNotIn("TILAKNAGAR", result["answer"])

    def test_new_highs_query_routes_to_new_highs_screener(self):
        routed = _keyword_intent("companies creating new high")

        self.assertEqual(routed["intent"], "screener")
        self.assertEqual(routed["plan"], [("run_screener_query", {"screen_type": "new_highs"})])

    def test_agent_explains_placeholder_symbol_without_missing_evidence_report(self):
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"

        with patch("terminal.agent._execute_plan") as execute_plan:
            result = agent.query("/assess SYMBOL")

        execute_plan.assert_called_once_with([])
        self.assertEqual(result["intent"], "placeholder_symbol_request")
        self.assertIn("NEED A REAL NSE SYMBOL", result["answer"])
        self.assertIn("/assess RELIANCE", result["answer"])
        self.assertNotIn("SYMBOL (SYMBOL) — Market Brief", result["answer"])
        self.assertNotIn("MISSING EVIDENCE", result["answer"])

    def test_deliberation_package_builds_executable_plan_and_render(self):
        plan = build_plan("Assess RELIANCE technical setup")
        hypotheses = build_hypotheses(plan.intent)
        evidence = evaluate_evidence([{"tool": "resolve_symbol", "result": {"symbol": "RELIANCE"}}])
        rendered = render_final_answer(plan, hypotheses, evidence)

        self.assertEqual(plan.intent, "symbol_assessment")
        self.assertEqual(plan.executable()[0], ("resolve_symbol", {"query": "RELIANCE"}))
        self.assertIn("Deliberation Plan", rendered)
        self.assertIn("bullish_setup", rendered)

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
        self.assertFalse(routed["assessment_plan"]["show_plan"])
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
        self.assertNotIn("SITUATION ASSESSMENT PLAN", result["answer"])
        self.assertNotIn("derived_from=get_live_market_overview", result["answer"])
        self.assertNotIn("recovery/code plan", result["answer"])
        self.assertIn("LIVE MARKET", result["answer"])
        self.assertIn("Live breadth: 310 advances / 190 declines", result["answer"])
        self.assertIn("INDEX MOVERS", result["answer"])
        self.assertIn("NIFTY IT +1.45%", result["answer"])
        self.assertIn("TOP STOCK MOVERS", result["answer"])
        self.assertIn("AAA +5.20%", result["answer"])
        self.assertNotIn("INDIN", result["answer"].upper())

    def test_contextual_stage2_last_30_question_answers_from_prior_turn(self):
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"

        with patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.return_value = [
                {
                    "tool": "run_screener_query",
                    "args": {"screen_type": "stage2"},
                    "result": {
                        "screen_type": "stage2",
                        "count": 2,
                        "results": [{"symbol": "BLISSGVS"}, {"symbol": "IPCALAB"}],
                    },
                }
            ]
            first = agent.query("lets look at the Stage 2 uptrend stocks")
            second = agent.query("were these pulled from last 30mins")

        execute_plan.assert_called_once()
        self.assertEqual(first["intent"], "screener")
        self.assertEqual(second["intent"], "situation_assessment")
        self.assertIn("SITUATION ASSESSMENT", second["answer"])
        self.assertIn("No.", second["answer"])
        self.assertIn("EOD CSV + DB snapshot", second["answer"])
        self.assertIn("not from the last 30 minutes", second["answer"])
        self.assertNotIn("Last 30 Minutes", second["answer"])
        self.assertNotIn("get_intraday_market_recap", str(second["trace"]))

    def test_contextual_stage2_scan_these_uses_prior_symbols(self):
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"

        with patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.side_effect = [
                [
                    {
                        "tool": "run_screener_query",
                        "args": {"screen_type": "stage2"},
                        "result": {
                            "screen_type": "stage2",
                            "count": 2,
                            "results": [{"symbol": "BLISSGVS"}, {"symbol": "IPCALAB"}],
                        },
                    }
                ],
                [
                    {
                        "tool": "scan_symbols_intraday",
                        "args": {"symbols": ["BLISSGVS", "IPCALAB"], "interval": "15m"},
                        "result": {
                            "symbols_scanned": ["BLISSGVS", "IPCALAB"],
                            "interval": "15m",
                            "data_source": "PostgreSQL intraday.ohlcv_bars",
                            "top_buy": [
                                {
                                    "symbol": "BLISSGVS",
                                    "strategy": "supertrend",
                                    "entry": 289.0,
                                    "target": 296.0,
                                    "stoploss": 284.0,
                                    "rr": 1.4,
                                }
                            ],
                            "top_sell": [],
                        },
                    }
                ],
            ]
            agent.query("show Stage 2 stocks")
            result = agent.query("scan these for 15m intraday setups")

        self.assertEqual(execute_plan.call_count, 2)
        execute_plan.assert_any_call(
            [("scan_symbols_intraday", {"symbols": ["BLISSGVS", "IPCALAB"], "interval": "15m"})]
        )
        self.assertEqual(result["intent"], "contextual_tool_plan")
        self.assertIn("SITUATION ASSESSMENT", result["answer"])
        self.assertIn("INTRADAY SYMBOL SCAN", result["answer"])
        self.assertIn("BLISSGVS", result["answer"])
        self.assertIn("PostgreSQL intraday.ohlcv_bars", result["answer"])

    def test_market_situation_plan_is_shown_only_when_requested(self):
        routed = _keyword_intent(
            "show plan step by step for current market status breadth and top gainers",
            data_mode="intraday",
        )

        self.assertEqual(routed["intent"], "market_situation_assessment")
        self.assertTrue(routed["assessment_plan"]["show_plan"])

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
        self.assertNotIn("search_latest_catalysts", planned_tools)
        self.assertNotIn("search_market_knowledge", planned_tools)

    def test_startup_briefing_news_word_does_not_require_catalyst_search(self):
        query = """
        Give a comprehensive, investigative morning briefing before market open.
        Include key macro events or news overnight, any significant corporate news
        or events from yesterday, and 3-4 stocks or sectors to watch.
        (use multi_source_web_search or search_latest_catalysts to get current global data)
        """

        routed = _keyword_intent(query, data_mode="global")

        self.assertEqual(routed["intent"], "startup_morning_briefing")
        self.assertEqual(_required_tools_for_query(routed["intent"], query), ())

    def test_agent_startup_briefing_with_news_word_does_not_fail_required_tool_validation(self):
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"
        query = """
        Give a comprehensive, investigative morning briefing before market open.
        Include key macro events or news overnight, any significant corporate news
        or events from yesterday, and 3-4 stocks or sectors to watch.
        (use multi_source_web_search or search_latest_catalysts to get current global data)
        """

        with patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.return_value = [
                {
                    "tool": "get_global_market_assessment",
                    "args": {},
                    "result": {
                        "risk_regime": "mixed",
                        "as_of": "2026-05-15",
                        "regions": {"US": {"avg_pct_change": 0.1, "bias": "mixed"}},
                        "moves": {"S&P 500": {"pct_change": 0.1}},
                        "india_readthrough": ["Global cues are mixed."],
                    },
                },
                {"tool": "get_index_snapshot", "args": {"index_name": "NIFTY 50"}, "result": {"index": "NIFTY 50", "close": 23775.2, "chg_pct": 0.36}},
                {"tool": "get_index_snapshot", "args": {"index_name": "NIFTY BANK"}, "result": {"index": "NIFTY BANK", "close": 54250.2, "chg_pct": 0.22}},
                {
                    "tool": "get_live_market_overview",
                    "args": {},
                    "result": {
                        "source": "NSE live API",
                        "as_of": "2026-05-15 09:25:00",
                        "indices": {"NIFTY 50": {"last": 23775.2, "pct_change": 0.36}},
                        "adv_dec": {"advances": 249, "declines": 251},
                    },
                },
                {"tool": "get_market_breadth", "args": {}, "result": {"advances": 501, "declines": 409, "ad_ratio": 1.22}},
                {
                    "tool": "get_top_gainers_losers",
                    "args": {"index": "NIFTY 50", "top_n": 3, "direction": "both"},
                    "result": {"gainers": [{"symbol": "ABC", "pct_change": 2.0}], "losers": []},
                },
                {"tool": "get_fii_dii_activity", "args": {}, "result": {"data": [{"category": "FII", "net_crore": -100.0}]}},
            ]
            result = agent.query(query)

        self.assertEqual(result["intent"], "startup_morning_briefing")
        self.assertNotIn("REQUIRED TOOL VALIDATION FAILED", result["answer"])
        self.assertIn("Global Overnight Context", result["answer"])
        self.assertIn("Current Market Status", result["answer"])

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

    def test_forensic_prompt_routes_to_forensic_tool(self):
        routed = _keyword_intent(
            "Run run_forensic_analysis for TATASTEEL. Present Beneish M-score, "
            "Piotroski F-score and Altman Z-score clearly."
        )

        self.assertEqual(routed["intent"], "stock_brief")
        self.assertIn(("resolve_symbol", {"query": "TATASTEEL"}), routed["plan"])
        self.assertIn(("run_forensic_analysis", {"symbol": "TATASTEEL"}), routed["plan"])

    def test_agent_forensic_prompt_renders_three_scores_without_validation_failure(self):
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"

        with patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.return_value = [
                {"tool": "resolve_symbol", "args": {"query": "TATASTEEL"}, "result": {"symbol": "TATASTEEL"}},
                {"tool": "get_symbol_snapshot", "args": {"symbol": "TATASTEEL"}, "result": {"symbol": "TATASTEEL", "company_name": "Tata Steel"}},
                {"tool": "get_technical_setup", "args": {"symbol": "TATASTEEL"}, "result": {"symbol": "TATASTEEL"}},
                {"tool": "get_sector_context", "args": {"sector_or_symbol": "TATASTEEL"}, "result": {"symbol": "TATASTEEL"}},
                {
                    "tool": "run_forensic_analysis",
                    "args": {"symbol": "TATASTEEL"},
                    "result": {
                        "symbol": "TATASTEEL",
                        "source_url": "https://www.screener.in/company/TATASTEEL/consolidated/",
                        "overall_risk": "moderate",
                        "beneish": {
                            "score": -2.1,
                            "interpretation": "No clear manipulation signal",
                            "risk_flags": ["GMI elevated"],
                            "variables": {"DSRI": 0.9, "GMI": 1.2},
                        },
                        "piotroski": {
                            "score": 6,
                            "max_possible": 9,
                            "strength": "Average",
                            "signals": {"positive_roa": 1, "positive_operating_cashflow": 1},
                        },
                        "altman": {
                            "score": 2.4,
                            "zone": "grey zone",
                            "components": {"X1_working_capital_ratio": 0.1},
                        },
                        "summary": "Forensic summary",
                    },
                },
            ]
            result = agent.query(
                "Run run_forensic_analysis for TATASTEEL. Present Beneish M-score, "
                "Piotroski F-score and Altman Z-score clearly."
            )

        self.assertEqual(result["intent"], "stock_brief")
        self.assertNotIn("REQUIRED TOOL VALIDATION FAILED", result["answer"])
        self.assertIn("FORENSIC ACCOUNTING", result["answer"])
        self.assertIn("Beneish M-score", result["answer"])
        self.assertIn("Piotroski F-score", result["answer"])
        self.assertIn("Altman Z", result["answer"])
        self.assertIn("GMI elevated", result["answer"])

    def test_end_to_end_trade_research_routes_to_explicit_symbol_not_task_label(self):
        routed = _keyword_intent(
            "End-to-end trade research for THERMAX with technical setup, fundamentals and risk"
        )

        self.assertEqual(routed["intent"], "stock_brief")
        self.assertEqual(routed["plan"][0], ("resolve_symbol", {"query": "THERMAX"}))
        self.assertNotIn("END-TO-END", str(routed).upper())

    def test_detailed_fundamental_technical_analysis_routes_company_name(self):
        routed = _keyword_intent("detailed fundamental and technical analysis of Tata steel")

        self.assertEqual(routed["intent"], "stock_brief")
        self.assertEqual(routed["plan"][0], ("resolve_symbol", {"query": "TATASTEEL"}))
        self.assertIn(("scrape_screener_in", {"symbol": "TATASTEEL"}), routed["plan"])
        self.assertIn(("get_technical_setup", {"symbol": "TATASTEEL"}), routed["plan"])
        self.assertNotIn("'DETAILED'", str(routed).upper())
        self.assertNotIn("'TATA'", str(routed).upper())

    def test_earnings_playbook_routes_to_explicit_symbol_not_earnings_label(self):
        routed = _keyword_intent(
            "Earnings playbook for TCS after results with margin, valuation and risk"
        )

        self.assertEqual(routed["intent"], "stock_brief")
        self.assertEqual(routed["plan"][0], ("resolve_symbol", {"query": "TCS"}))
        self.assertNotIn("'EARNINGS'", str(routed).upper())

    def test_latest_results_routes_to_full_results_evidence_pack(self):
        routed = _keyword_intent("latest results for DMART")

        self.assertEqual(routed["intent"], "stock_results")
        self.assertEqual(routed["plan"][0], ("resolve_symbol", {"query": "DMART"}))
        self.assertIn(("get_latest_results", {"symbol": "DMART"}), routed["plan"])
        self.assertNotIn("'RESULTS'", str(routed).upper())

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

    def test_strength_question_routes_to_high_rs_screener_not_which_symbol(self):
        routed = _keyword_intent("which stocks are still showing strength")

        self.assertEqual(routed["intent"], "screener")
        self.assertEqual(routed["plan"], [("run_screener_query", {"screen_type": "high_rs"})])
        self.assertNotIn("'WHICH'", str(routed).upper())

    def test_explicit_eod_screener_high_rs_routes_to_screener(self):
        routed = _keyword_intent(
            "Run EOD screener high_rs and show the top results with technical context"
        )

        self.assertEqual(routed["intent"], "screener")
        self.assertEqual(routed["plan"], [("run_screener_query", {"screen_type": "high_rs"})])
        self.assertNotIn("NIFTY", str(routed).upper())
        self.assertNotIn("resolve_symbol", str(routed))

    def test_agent_executes_strength_screener_without_llm_symbol_guess(self):
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"

        with patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.return_value = [
                {
                    "tool": "run_screener_query",
                    "args": {"screen_type": "high_rs"},
                    "result": {
                        "screen_type": "high_rs",
                        "count": 1,
                        "results": [
                            {
                                "symbol": "INDOTECH",
                                "price": 1000,
                                "rs_pct": 88.0,
                                "trading_signal": "BUY",
                            }
                        ],
                    },
                }
            ]
            result = agent.query("which stocks are still showing strength")

        execute_plan.assert_called_once_with([("run_screener_query", {"screen_type": "high_rs"})])
        self.assertEqual(result["intent"], "screener")
        self.assertIn("SCREENER: HIGH_RS", result["answer"])
        self.assertIn("INDOTECH", result["answer"])
        self.assertNotIn("WHICH (WHICH) — Market Brief", result["answer"])

    def test_fno_overview_routes_to_derivatives_tools_not_market_overview(self):
        routed = _keyword_intent(
            "Give a comprehensive F&O overview for NIFTY: option chain PCR max pain top OI strikes, futures basis and cost of carry"
        )

        self.assertEqual(routed["intent"], "fno_overview")
        self.assertEqual(
            routed["plan"],
            [("get_fno_overview", {"symbol": "NIFTY", "expiry_index": 0})],
        )
        self.assertNotEqual(routed["intent"], "market_overview")
        self.assertNotIn("get_live_market_overview", str(routed))

    def test_fno_overview_with_strategy_request_stays_derivatives_route(self):
        routed = _keyword_intent(
            "Give a comprehensive F&O overview for NIFTY: option chain (PCR, max pain, top OI strikes), "
            "futures basis and cost of carry, and recommend the best options strategy based on current conditions.",
            data_mode="intraday",
        )

        self.assertEqual(routed["intent"], "fno_overview")
        self.assertEqual(
            routed["plan"],
            [("get_fno_overview", {"symbol": "NIFTY", "expiry_index": 0})],
        )
        self.assertNotIn("get_live_market_overview", str(routed))

    def test_options_strategy_phrase_routes_to_derivatives_tools(self):
        routed = _keyword_intent(
            "Build a long straddle options strategy for NIFTY. Show legs, strikes, entry cost, max risk, max reward, and breakevens.",
            data_mode="intraday",
        )

        self.assertEqual(routed["intent"], "fno_overview")
        self.assertIn(("get_fno_overview", {"symbol": "NIFTY", "expiry_index": 0}), routed["plan"])
        self.assertNotIn("explain_intraday_setup", str(routed))

    def test_intraday_nifty_uses_nse_snapshot_before_fallback(self):
        routed = _keyword_intent(
            "Intraday technical analysis of NIFTY50 right now. Use NSE website snapshot first, then yfinance only as fallback, and label stale data.",
            data_mode="intraday",
        )

        self.assertEqual(routed["intent"], "intraday_setup")
        self.assertIn(("get_nse_intraday_snapshot", {"symbol": "NIFTY50"}), routed["plan"])
        self.assertIn(("get_intraday_analysis", {"symbol": "NIFTY50"}), routed["plan"])

    def test_intraday_vcp_nifty500_scan_routes_to_index_scan_not_nifty_setup(self):
        routed = _keyword_intent(
            "Scan NIFTY 500 for VCP (Volatility Contraction Pattern) stocks ready for intraday breakout on 15m.",
            data_mode="intraday",
        )

        self.assertEqual(routed["intent"], "intraday_index_scan")
        self.assertEqual(
            routed["plan"],
            [
                (
                    "scan_intraday_market",
                    {
                        "index": "NIFTY 500",
                        "interval": "15m",
                        "strategies": ["vcp"],
                        "direction_filter": "buy",
                        "min_rr": 1.3,
                        "top_n": 10,
                    },
                )
            ],
        )
        self.assertNotIn("explain_intraday_setup", str(routed))

    def test_intraday_rsi_reversal_routes_to_screener_not_symbol_setup(self):
        routed = _keyword_intent("RSI reversal intraday", data_mode="intraday")

        self.assertEqual(routed["intent"], "intraday_screener")
        self.assertEqual(routed["plan"], [("run_intraday_screener", {"screen_type": "rsi_divergence"})])
        self.assertNotIn("resolve_symbol", str(routed))

    def test_intraday_source_health_routes_to_health_not_postgresql_symbol(self):
        routed = _keyword_intent("PostgreSQL intraday table health", data_mode="intraday")

        self.assertEqual(routed["intent"], "intraday_health")
        self.assertEqual(routed["plan"], [("get_intraday_source_health", {})])
        self.assertNotIn("resolve_symbol", str(routed))

    def test_intraday_bulk_and_most_active_utilities_route_before_symbol_setup(self):
        bulk = _keyword_intent("show bulk deals today", data_mode="intraday")
        active = _keyword_intent("most active stocks today", data_mode="intraday")

        self.assertEqual(bulk["intent"], "market_overview")
        self.assertEqual(bulk["plan"], [("get_bulk_block_deals", {})])
        self.assertEqual(active["intent"], "market_overview")
        self.assertEqual(active["plan"], [("get_most_active_stocks", {})])
        self.assertNotIn("resolve_symbol", str(bulk))
        self.assertNotIn("resolve_symbol", str(active))

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
                    "tool": "get_fno_overview",
                    "args": {"symbol": "NIFTY", "expiry_index": 0},
                    "result": {
                        "symbol": "NIFTY",
                        "status": "ok",
                        "option_chain": {"status": "ok"},
                        "atm": 23650,
                        "pcr": 0.82,
                        "max_pain": 23700,
                        "top_oi_strikes": {
                            "calls": [{"strike": 23700, "oi": 400000, "chg_oi": 25000}],
                            "puts": [{"strike": 23600, "oi": 350000, "chg_oi": 18000}],
                        },
                        "futures": {"status": "ok", "basis": 30.0, "cost_of_carry": 3.2},
                        "basis": 30.0,
                        "cost_of_carry": 3.2,
                        "recommendation": {
                            "status": "ok",
                            "strategy": "defined_risk_spread",
                            "conditions": ["PCR supportive"],
                            "invalidation": "Breakdown",
                            "max_loss": "Defined by spread",
                            "max_profit": "Defined by spread",
                        },
                        "source_trail": {
                            "get_options_chain": "ok",
                            "get_futures_analysis": "ok",
                            "get_strategy_recommendations": "ok",
                        },
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
        self.assertIn("Top call OI", result["answer"])
        self.assertIn("FUTURES BASIS & CARRY", result["answer"])
        self.assertIn("Basis: 30.0", result["answer"])
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

    def test_ric_sherlock_prompts_keep_requested_symbol(self):
        prompts = [
            "Live price and quote for TMPV — current price, % change, volume, day high/low vs 52-week range.",
            "Full technical setup for TMPV — Weinstein stage, RSI, ADX, MACD, supertrend direction, position vs 20/50/200 MA, RS rank vs Nifty 50.",
            "Fundamental analysis of TMPV from screener.in — P/E, P/B, ROE, ROCE, debt/equity, revenue growth, pros and cons.",
            "Latest news and catalysts for TMPV — recent announcements, results, management commentary, analyst views.",
            "Intraday trading setup for TMPV on 15m — entry price, target, stoploss, R:R ratio, key support/resistance levels, recommended strategy.",
        ]

        for prompt in prompts:
            with self.subTest(prompt=prompt):
                routed = _keyword_intent(prompt, data_mode="auto")
                self.assertIn(("resolve_symbol", {"query": "TMPV"}), routed["plan"])
                self.assertNotIn("LOTUSEYE", str(routed))
                self.assertNotIn("INDIACEM", str(routed))

    def test_intraday_mode_keeps_explicit_sherlock_technical_symbol_specific(self):
        routed = _keyword_intent(
            "Full technical setup for TMPV — Weinstein stage, RSI, ADX, MACD, "
            "supertrend direction, position vs 20/50/200 MA, RS rank vs Nifty 50.",
            data_mode="intraday",
        )

        self.assertEqual(routed["intent"], "intraday_setup")
        self.assertIn(("resolve_symbol", {"query": "TMPV"}), routed["plan"])
        self.assertIn(("explain_intraday_setup", {"symbol": "TMPV"}), routed["plan"])
        self.assertNotIn("run_intraday_screener", str(routed))

    def test_intraday_mode_keeps_explicit_sherlock_news_as_catalyst_lookup(self):
        routed = _keyword_intent(
            "Latest news and catalysts for TMPV — recent announcements, results, "
            "management commentary, analyst views.",
            data_mode="intraday",
        )

        self.assertEqual(routed["intent"], "stock_brief")
        self.assertIn(("resolve_symbol", {"query": "TMPV"}), routed["plan"])
        self.assertIn(("search_latest_catalysts", {"symbol": "TMPV"}), routed["plan"])
        self.assertNotIn("explain_intraday_setup", str(routed))

    def test_intraday_symbol_setup_ignores_timeframe_preposition(self):
        routed = _keyword_intent("RELIANCE intraday setup on 15m", data_mode="intraday")

        self.assertEqual(routed["intent"], "intraday_setup")
        self.assertEqual(routed["plan"][0], ("resolve_symbol", {"query": "RELIANCE"}))
        self.assertNotIn("M&M", str(routed))

    def test_intraday_levels_keep_symbol_before_level_terms(self):
        routed = _keyword_intent(
            "Intraday levels for TMPV support resistance pivots",
            data_mode="intraday",
        )

        self.assertEqual(routed["intent"], "intraday_levels")
        self.assertEqual(routed["plan"][0], ("resolve_symbol", {"query": "TMPV"}))

    def test_intraday_screener_phrases_do_not_fall_to_symbol_brief(self):
        cases = [
            ("show vwap reclaim intraday stocks", "vwap_reclaim"),
            ("opening range breakout stocks", "opening_range_breakout"),
        ]

        for query, screen_type in cases:
            with self.subTest(query=query):
                routed = _keyword_intent(query, data_mode="intraday")
                self.assertEqual(routed["intent"], "intraday_screener")
                self.assertEqual(
                    routed["plan"],
                    [("run_intraday_screener", {"screen_type": screen_type})],
                )

    def test_intraday_banknifty_scan_keeps_bank_index_and_sell_direction(self):
        routed = _keyword_intent(
            "Scan BANKNIFTY for short breakdown setups on 15m",
            data_mode="intraday",
        )

        self.assertEqual(routed["intent"], "intraday_index_scan")
        self.assertEqual(routed["plan"][0][1]["index"], "NIFTY BANK")
        self.assertEqual(routed["plan"][0][1]["direction_filter"], "sell")

    def test_intraday_postgres_health_wins_over_generic_data_health(self):
        routed = _keyword_intent("intraday data health postgres ohlcv table")

        self.assertEqual(routed["intent"], "intraday_health")
        self.assertEqual(routed["plan"], [("get_intraday_source_health", {})])

    def test_compare_slash_separated_symbols_routes_deterministically(self):
        routed = _keyword_intent("DMART/TRENT/VBL which is better")

        self.assertEqual(routed["intent"], "stock_comparison")
        self.assertEqual(
            routed["plan"],
            [("compare_stocks", {"symbols": ["DMART", "TRENT", "VBL"], "aspects": ["both"]})],
        )

    def test_compare_stocks_keeps_unresolved_exact_ticker_as_missing_row(self):
        result = compare_stocks(["ZZZNOTREAL"], aspects=["technical"])

        self.assertEqual(result["input_symbols"], ["ZZZNOTREAL"])
        self.assertEqual(result["symbols"], ["ZZZNOTREAL"])
        self.assertEqual(result["unresolved_symbols"], ["ZZZNOTREAL"])
        self.assertEqual(result["evidence_coverage"], "partial")
        self.assertIn("symbol_resolution", result["missing_evidence"])
        self.assertIn("resolution_error", result["stock_details"][0])

    def test_final_symbol_validator_blocks_unrequested_tool_symbol(self):
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"

        with patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.return_value = [
                {"tool": "resolve_symbol", "args": {"query": "NAVABUPA"}, "result": {"symbol": "TALBROAUTO"}},
                {"tool": "get_symbol_snapshot", "args": {"symbol": "TALBROAUTO"}, "result": {"symbol": "TALBROAUTO"}},
            ]
            result = agent.query("NAVABUPA technical setup")

        self.assertEqual(result["intent"], "stock_brief")
        self.assertIn("SYMBOL VALIDATION FAILED", result["answer"])
        self.assertIn("NAVABUPA->TALBROAUTO", result["answer"])
        self.assertNotIn("TALBROAUTO (TALBROAUTO) — Market Brief", result["answer"])

    def test_symbol_validator_ignores_uppercase_technical_terms(self):
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"

        with patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.return_value = [
                {"tool": "resolve_symbol", "args": {"query": "SAKAR"}, "result": {"symbol": "SAKAR"}},
                {"tool": "scrape_screener_in", "args": {"symbol": "SAKAR"}, "result": {"symbol": "SAKAR"}},
                {"tool": "get_symbol_snapshot", "args": {"symbol": "SAKAR"}, "result": {"symbol": "SAKAR", "price": 696.7}},
                {"tool": "get_technical_setup", "args": {"symbol": "SAKAR"}, "result": {"symbol": "SAKAR", "rsi": 52, "adx": 24}},
                {"tool": "get_sector_context", "args": {"sector_or_symbol": "SAKAR"}, "result": {"symbol": "SAKAR"}},
            ]
            result = agent.query("SAKAR technical setup with RSI, ADX, MACD and MA context")

        self.assertEqual(result["intent"], "stock_brief")
        self.assertNotIn("SYMBOL VALIDATION FAILED", result["answer"])
        self.assertNotIn("Requested symbol(s): SAKAR, ADX, MA", result["answer"])
        self.assertIn("SAKAR", result["answer"])

    def test_required_tool_validator_blocks_missing_screener_tool(self):
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"

        with patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.return_value = []
            result = agent.query("show me Stage 2 breakout stocks")

        self.assertEqual(result["intent"], "screener")
        self.assertIn("REQUIRED TOOL VALIDATION FAILED", result["answer"])
        self.assertIn("run_screener_query", result["answer"])

    def test_results_command_renders_latest_results_evidence(self):
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"

        with patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.return_value = [
                {"tool": "resolve_symbol", "args": {"query": "DMART"}, "result": {"symbol": "DMART"}},
                {
                    "tool": "get_latest_results",
                    "args": {"symbol": "DMART"},
                    "result": {
                        "symbol": "DMART",
                        "status": "ok",
                        "period": "latest",
                        "selected_filing": {
                            "title": "Audited financial results",
                            "url": "https://bse.example/results.pdf",
                            "source": "bse_filings",
                        },
                        "facts": {
                            "revenue": {"value": "14,000", "period": "Mar 2026", "source": "scrape_screener_in.quarterly"},
                            "pat": {"value": "800", "period": "Mar 2026", "source": "scrape_screener_in.quarterly"},
                        },
                        "missing_facts": ["eps"],
                        "summary": "Latest results evidence for DMART (latest).\nRevenue: 14,000 (Mar 2026)",
                        "source_trail": {
                            "discover_financial_filings": "ok",
                            "search_bse_filings": "ok",
                            "ingest_financial_filing": "ok",
                            "parse_financial_filing": "ok",
                            "reconcile_filing_facts": "ok",
                        },
                    },
                },
            ]
            result = agent.query("/results DMART")

        self.assertEqual(result["intent"], "entity_topic_command")
        self.assertIn("Latest Results Evidence", result["answer"])
        self.assertIn("Mar 2026", result["answer"])
        self.assertIn("Audited financial results", result["answer"])
        self.assertIn("search_bse_filings: ok", result["answer"])
        self.assertNotIn("REQUIRED TOOL VALIDATION FAILED", result["answer"])

    def test_latest_results_of_mixed_case_company_routes_to_stock_results(self):
        from terminal.agent import _keyword_intent

        routed = _keyword_intent("latest results of Delhivery")

        self.assertEqual(routed["intent"], "stock_results")
        self.assertEqual(routed["plan"][0], ("resolve_symbol", {"query": "Delhivery"}))
        self.assertEqual(routed["plan"][1], ("get_latest_results", {"symbol": "DELHIVERY"}))

    def test_required_tool_validator_blocks_unsupported_broker_claims(self):
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"

        with patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.return_value = [
                {"tool": "resolve_symbol", "args": {"query": "RELIANCE"}, "result": {"symbol": "RELIANCE"}},
                {"tool": "get_symbol_snapshot", "args": {"symbol": "RELIANCE"}, "result": {"symbol": "RELIANCE"}},
                {"tool": "get_technical_setup", "args": {"symbol": "RELIANCE"}, "result": {"symbol": "RELIANCE"}},
                {"tool": "get_sector_context", "args": {"sector_or_symbol": "RELIANCE"}, "result": {"symbol": "RELIANCE"}},
            ]
            result = agent.query("RELIANCE analyst target price and broker rating")

        self.assertEqual(result["intent"], "stock_brief")
        self.assertIn("REQUIRED TOOL VALIDATION FAILED", result["answer"])
        self.assertIn("search_broker_research", result["answer"])

    def test_missing_evidence_guard_is_rendered_for_partial_stock_evidence(self):
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"

        with patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.return_value = [
                {"tool": "resolve_symbol", "args": {"query": "RELIANCE"}, "result": {"symbol": "RELIANCE"}},
                {
                    "tool": "get_symbol_snapshot",
                    "args": {"symbol": "RELIANCE"},
                    "result": {
                        "symbol": "RELIANCE",
                        "company_name": "Reliance Industries",
                        "missing_evidence": ["fundamental_score"],
                        "evidence_coverage": "partial",
                    },
                },
                {"tool": "get_technical_setup", "args": {"symbol": "RELIANCE"}, "result": {"symbol": "RELIANCE"}},
                {"tool": "get_sector_context", "args": {"sector_or_symbol": "RELIANCE"}, "result": {"symbol": "RELIANCE"}},
            ]
            result = agent.query("RELIANCE technical setup")

        self.assertIn("MISSING EVIDENCE", result["answer"])
        self.assertIn("get_symbol_snapshot.fundamental_score", result["answer"])
        self.assertIn("No unsupported technical, fundamental, catalyst, forensic, broker, or sector conclusion", result["answer"])

    def test_analyze_document_does_not_require_concall_search_for_prompt_keywords(self):
        from terminal.agent import _validate_required_tools

        # /analyze <URL> expands to a prompt that mentions "concall transcript" and
        # "management commentary" as generic interpretation hints. The validator must
        # not require search_concall_transcripts when the user is analyzing a document.
        analyze_prompt = (
            "Use the analyze_document tool with source='https://example.com/doc.pdf'. "
            "Read the full document and provide: 1. Document Summary ... "
            "If this is a financial document (annual report, concall transcript, results), "
            "also evaluate: revenue/profit trends, management commentary, guidance changes, "
            "risk factors, and investment implications."
        )
        tool_results = [
            {"tool": "analyze_document",
             "args": {"source": "https://example.com/doc.pdf"},
             "result": {"text_length": 4500}},
        ]
        self.assertIsNone(_validate_required_tools(analyze_prompt, "llm_driven", tool_results))

    def test_llm_query_sends_only_analyze_document_schema_for_document_prompt(self):
        class CapturingBackend:
            def __init__(self):
                self.tool_names = []

            def chat(self, messages, tools=None):
                self.tool_names = [schema["function"]["name"] for schema in (tools or [])]
                return {"content": "Document analysis complete.", "tool_calls": [], "finish_reason": "stop"}

        schemas = [
            {"type": "function", "function": {"name": f"tool_{i}", "description": "x", "parameters": {"type": "object"}}}
            for i in range(137)
        ]
        schemas.append(
            {"type": "function", "function": {"name": "analyze_document", "description": "x", "parameters": {"type": "object"}}}
        )
        backend = CapturingBackend()
        agent = Agent.__new__(Agent)
        agent.backend = backend
        agent.backend_name = "TestBackend"
        agent.tool_schemas = schemas
        agent._history = []
        agent._last_symbols = []
        agent._last_turn_context = None

        result = agent._llm_query(
            "Use the analyze_document tool with source='https://example.com/doc.pdf', max_pages=60.",
            show_trace=False,
        )

        self.assertEqual(result["intent"], "llm_driven")
        self.assertEqual(backend.tool_names, ["analyze_document"])

    def test_llm_tool_schema_fallback_is_bounded_to_openai_limit(self):
        agent = Agent.__new__(Agent)
        agent.tool_schemas = [
            {"type": "function", "function": {"name": f"tool_{i}", "description": "x", "parameters": {"type": "object"}}}
            for i in range(138)
        ]

        selected = agent._tool_schemas_for_query("general market question")

        self.assertLessEqual(len(selected), 128)

    def test_llm_tool_schema_search_prefers_relevant_tools_by_description(self):
        agent = Agent.__new__(Agent)
        agent.tool_schemas = [
            {"type": "function", "function": {"name": f"tool_{i}", "description": "unrelated utility", "parameters": {"type": "object"}}}
            for i in range(136)
        ] + [
            {
                "type": "function",
                "function": {
                    "name": "search_concall_transcripts",
                    "description": "Search earnings call transcripts for management commentary, guidance, and Q&A.",
                    "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_broker_research",
                    "description": "Search broker research reports, analyst ratings, and target price changes.",
                    "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}}},
                },
            },
        ]

        selected = agent._tool_schemas_for_query("Find management commentary and guidance after latest results")
        names = [schema["function"]["name"] for schema in selected[:5]]

        self.assertIn("search_concall_transcripts", names)
        self.assertLessEqual(len(selected), 128)

    def test_llm_tool_schema_search_uses_prior_context_after_assessment(self):
        class PriorContext:
            intent = "document_analysis"
            result_summary = "Previous turn analyzed a Delhivery filing document."
            symbols = ["DELHIVERY"]
            tools = ["analyze_document"]

        agent = Agent.__new__(Agent)
        agent.tool_schemas = [
            {"type": "function", "function": {"name": f"tool_{i}", "description": "unrelated utility", "parameters": {"type": "object"}}}
            for i in range(137)
        ] + [
            {
                "type": "function",
                "function": {
                    "name": "analyze_document",
                    "description": "Read and extract text from PDFs, filings, reports, and web URLs.",
                    "parameters": {"type": "object", "properties": {"source": {"type": "string"}}},
                },
            },
        ]
        agent._last_turn_context = PriorContext()

        selection_text = agent._tool_selection_text("Follow up on the same report")
        selected = agent._tool_schemas_for_query(selection_text)

        self.assertEqual([schema["function"]["name"] for schema in selected], ["analyze_document"])

    def test_stock_brief_plan_includes_concall_when_management_commentary_requested(self):
        from terminal.agent import _keyword_intent

        routed = _keyword_intent(
            "Perform comprehensive 360 analysis of HDBFS including news, management commentary, guidance and analyst views"
        )
        tools = [name for name, _args in routed["plan"]]

        self.assertEqual(routed["intent"], "stock_brief")
        self.assertIn("search_latest_catalysts", tools)
        self.assertIn("search_concall_transcripts", tools)
        self.assertIn("search_broker_research", tools)

    def test_required_tool_validator_allows_stock_brief_when_dynamic_tools_run(self):
        from terminal.agent import _validate_required_tools

        query = "HDBFS news management commentary guidance analyst views"
        tool_results = [
            {"tool": "resolve_symbol", "args": {"query": "HDBFS"}, "result": {"symbol": "HDBFS"}},
            {"tool": "get_symbol_snapshot", "args": {"symbol": "HDBFS"}, "result": {"symbol": "HDBFS"}},
            {"tool": "search_latest_catalysts", "args": {"symbol": "HDBFS"}, "result": {"symbol": "HDBFS"}},
            {"tool": "search_concall_transcripts", "args": {"symbol": "HDBFS"}, "result": {"symbol": "HDBFS"}},
            {"tool": "search_broker_research", "args": {"symbol": "HDBFS"}, "result": {"symbol": "HDBFS"}},
        ]

        self.assertIsNone(_validate_required_tools(query, "stock_brief", tool_results))


if __name__ == "__main__":
    unittest.main()
