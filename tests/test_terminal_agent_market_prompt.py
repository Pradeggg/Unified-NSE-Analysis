import os
import unittest
from unittest.mock import patch

from terminal.agent import (
    Agent,
    SYSTEM_PROMPT,
    _keyword_intent,
    _required_tools_for_query,
    _split_compound_query,
    _synthesis_intent_from_plan,
)
from terminal.renderers.narrator import NARRATION_INTENTS
from terminal.situation_assessment import TurnContext
from terminal.tools import compare_stocks
from terminal.deliberation import build_hypotheses, build_plan, evaluate_evidence, render_final_answer
from voice.voice_persona import normalize_spoken_query


class TerminalAgentMarketPromptTests(unittest.TestCase):
    def test_primary_symbol_query_trusts_high_band_hybrid_resolution(self):
        from terminal.agent import _primary_symbol_query

        with patch("terminal.agent._leading_company_phrase", return_value="Dixon Technologies"), patch(
            "terminal.agent.resolve_symbol",
            return_value={
                "symbol": "DIXON",
                "confidence": "fuzzy",
                "confidence_band": "high",
                "score": 0.91,
                "query": "Dixon Technologies",
            },
        ):
            selected = _primary_symbol_query(
                ["Dixon Technologies"],
                [],
                "live prices for Dixon Technologies and 5 min setup",
            )

        self.assertEqual(selected, "DIXON")

    def test_system_prompt_enforces_market_clock_and_fallback_labels(self):
        self.assertIn("MARKET CLOCK + DATA FRESHNESS RULES", SYSTEM_PROMPT)
        self.assertIn("Do not describe fallback/EOD data as \"current intraday\"", SYSTEM_PROMPT)
        self.assertIn("Only quote RSI, MACD, VWAP", SYSTEM_PROMPT)

    def test_market_overview_routes_to_market_tools_not_overview_symbol(self):
        routed = _keyword_intent("Market overview")

        self.assertEqual(routed["intent"], "market_overview")
        self.assertEqual(routed["plan"][0][0], "get_live_market_overview")
        self.assertNotIn("OVERVIEW", str(routed))

    def test_latest_market_pulse_routes_to_market_tools_not_market_symbol(self):
        for mode in ("historical", "intraday"):
            with self.subTest(mode=mode):
                routed = _keyword_intent("latest pulse on the market", data_mode=mode)
                tools = [tool for tool, _ in routed["plan"]]

                self.assertIn(routed["intent"], ("market_overview", "market_situation_assessment"))
                self.assertIn("get_live_market_overview", tools)
                self.assertIn("get_market_breadth", tools)
                self.assertNotIn("THE MARKET", str(routed).upper())

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

    def test_visual_scan_prompt_routes_to_visual_scan_tool(self):
        routed = _keyword_intent("Perform a visual scan of DMART", data_mode="historical")

        self.assertEqual(routed["intent"], "visual_scan")
        self.assertEqual(routed["plan"], [("run_visual_scan", {"symbol": "DMART"})])

    def test_visual_scan_slash_prompt_routes_to_visual_scan_tool(self):
        routed = _keyword_intent("/visual-scan DMART", data_mode="historical")

        self.assertEqual(routed["intent"], "visual_scan")
        self.assertEqual(routed["plan"], [("run_visual_scan", {"symbol": "DMART"})])

    def test_visual_scan_of_prompt_routes_to_visual_scan_tool(self):
        routed = _keyword_intent("visual scan of DMART", data_mode="historical")

        self.assertEqual(routed["intent"], "visual_scan")
        self.assertEqual(routed["plan"], [("run_visual_scan", {"symbol": "DMART"})])

    def test_visual_scan_answer_renders_report_and_evidence_paths(self):
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"

        with patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.return_value = [
                {
                    "tool": "run_visual_scan",
                    "args": {"symbol": "DMART"},
                    "result": {
                        "success": True,
                        "symbol": "DMART",
                        "summary": "DMART Visual Scan: Watchlist / base building | Score 68.",
                        "html_path": "/tmp/dmart_visual.html",
                        "json_path": "/tmp/dmart_visual.json",
                    },
                }
            ]
            result = agent.query("visual scan of DMART")

        self.assertEqual(result["intent"], "visual_scan")
        self.assertIn("DMART — Visual Scan", result["answer"])
        self.assertIn("Report: /tmp/dmart_visual.html", result["answer"])
        self.assertIn("Evidence: /tmp/dmart_visual.json", result["answer"])

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
        self.assertIn(result["intent"], ("market_overview", "market_situation"))
        self.assertIn("LIVE MARKET", result["answer"])
        self.assertIn("NIFTY 50: 23,898.95  (-1.15%)", result["answer"])
        self.assertIn("NSE live API", result["answer"])   # source label (format may vary)
        self.assertIn("Live breadth: 101 advances / 400 declines", result["answer"])
        self.assertIn("DB UNIVERSE CONTEXT", result["answer"])
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
        self.assertEqual(result["intent"], "market_situation")
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

    def test_market_breadth_question_gets_direct_breadth_verdict(self):
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
                        "as_of": "2026-06-08 09:30:00",
                        "indices": {
                            "NIFTY 50": {"last": 25100.0, "pct_change": 0.1},
                        },
                        "adv_dec": {"advances": 1101, "declines": 1317},
                        "top_sectors": [{"name": "NIFTY PSU BANK", "pct_change": 1.2}, {"name": "NIFTY PHARMA", "pct_change": 0.8}],
                    },
                },
                {
                    "tool": "get_market_breadth",
                    "args": {},
                    "result": {
                        "snapshot_date": "2026-06-05",
                        "total_stocks": 2457,
                        "advances": 1101,
                        "declines": 1317,
                        "ad_ratio": 0.84,
                        "avg_rs_pct": -0.4,
                        "rs_percentiles": {"p10": -12.0, "p25": -4.0, "p50": 8.0, "p75": 35.0, "p90": 72.0},
                        "rs_distribution": {
                            "negative": {"label": "RS < 0", "count": 620, "pct": 25.2},
                            "neutral_0_25": {"label": "RS 0-25", "count": 840, "pct": 34.2},
                            "positive_25_50": {"label": "RS 25-50", "count": 540, "pct": 22.0},
                            "strong_50_plus": {"label": "RS >= 50", "count": 457, "pct": 18.6},
                        },
                        "stage_distribution": {
                            "STAGE_1": 600,
                            "STAGE_2": 344,
                            "STAGE_3": 899,
                            "STAGE_4": 614,
                        },
                    },
                },
            ]

            result = agent.query("how is the market breadth")

        self.assertIn(result["intent"], ("market_situation", "market_situation_assessment", "market_overview"))
        self.assertIn("▶ BREADTH VERDICT", result["answer"])
        self.assertIn("Market breadth is weak/negative", result["answer"])
        self.assertIn("1101 advances vs 1317 declines", result["answer"])
        self.assertIn("A/D ratio is 0.84", result["answer"])
        self.assertIn("Stage 2 uptrends are 14%", result["answer"])
        self.assertIn("Stage 4 downtrends are 25%", result["answer"])
        self.assertIn("▶ RS DISTRIBUTION", result["answer"])
        self.assertIn("p50 8.0%", result["answer"])
        self.assertIn("RS >= 50: 457", result["answer"])
        self.assertIn("NIFTY PSU BANK", result["answer"])
        self.assertIn("NIFTY PHARMA", result["answer"])

    def test_market_situation_intents_are_eligible_for_llm_narration(self):
        self.assertIn("market_situation_assessment", NARRATION_INTENTS)
        self.assertIn("market_overview", NARRATION_INTENTS)
        self.assertIn("market_situation", NARRATION_INTENTS)

    def test_market_analysis_with_swing_candidates_routes_to_market_swing_plan(self):
        examples = [
            "last 3 months market analysis and swing candidates",
            "swing trades opportunities",
            "swing trade opportunities",
            "swing trading opportunities",
            "swing opportunities",
        ]

        for query in examples:
            with self.subTest(query=query):
                routed = _keyword_intent(query, data_mode="historical")

                self.assertEqual(routed["intent"], "market_swing_candidates")
                self.assertEqual(
                    routed["plan"],
                    [
                        ("get_index_snapshot", {"index_name": "NIFTY 50"}),
                        ("get_index_snapshot", {"index_name": "NIFTY MIDCAP 100"}),
                        ("get_market_breadth", {}),
                        ("run_quality_breakout_screener", {"top_n": 15, "mode": "balanced"}),
                    ],
                )
                self.assertNotIn("resolve_symbol", str(routed))
                self.assertNotIn("'and'", str(routed).lower())
                self.assertNotIn("TRADES", str(routed))
                self.assertNotIn("OPPORTUNITIES", str(routed))

    def test_agent_market_swing_candidates_renders_market_and_candidate_evidence(self):
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"

        with patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.return_value = [
                {
                    "tool": "get_index_snapshot",
                    "args": {"index_name": "NIFTY 50"},
                    "result": {
                        "index": "NIFTY 50",
                        "as_of": "2026-06-05",
                        "close": 25100.0,
                        "chg_pct": 0.45,
                        "trend_10d": {"chg_pct": 2.1, "up_days": 7, "closes": [1, 2]},
                    },
                },
                {
                    "tool": "get_index_snapshot",
                    "args": {"index_name": "NIFTY MIDCAP 100"},
                    "result": {
                        "index": "NIFTY MIDCAP 100",
                        "as_of": "2026-06-05",
                        "close": 58000.0,
                        "chg_pct": 0.8,
                        "trend_10d": {"chg_pct": 3.4, "up_days": 8, "closes": [1, 2]},
                    },
                },
                {
                    "tool": "get_market_breadth",
                    "args": {},
                    "result": {
                        "snapshot_date": "2026-06-05",
                        "advances": 900,
                        "declines": 500,
                        "ad_ratio": 1.8,
                        "avg_rs_pct": 6.1,
                        "stage_distribution": {"STAGE_2": 640},
                    },
                },
                {
                    "tool": "run_quality_breakout_screener",
                    "args": {"top_n": 15, "mode": "balanced"},
                    "result": {
                        "screen_type": "quality_breakouts",
                        "snapshot_date": "2026-06-05",
                        "mode": "balanced",
                        "source_counts": {"new_highs": 20, "momentum_52w": 15, "tight_range": 8, "breakouts": 5},
                        "merged_count": 35,
                        "passed_count": 2,
                        "count": 2,
                        "results": [
                            {
                                "symbol": "AAA",
                                "setup_tags": ["Breakout"],
                                "stage": "STAGE_2",
                                "trading_signal": "BUY",
                                "rs": 42.0,
                                "rsi": 63.0,
                                "enhanced_fund_score": 78.0,
                                "investment_score": 81.0,
                                "composite_score": 88.5,
                                "sector": "Capital Goods",
                                "reason_tags": ["stage 2", "quality"],
                                "risk_flags": [],
                            }
                        ],
                        "tradingview_symbols": ["NSE:AAA"],
                    },
                },
            ]

            result = agent.query("last 3 months market analysis and swing candidates")

        execute_plan.assert_called_once()
        self.assertEqual(result["intent"], "market_swing_candidates")
        self.assertIn("MARKET + SWING CANDIDATES", result["answer"])
        self.assertIn("NIFTY 50", result["answer"])
        self.assertIn("NIFTY MIDCAP 100", result["answer"])
        self.assertIn("QUALITY BREAKOUTS", result["answer"])
        self.assertIn("NSE:AAA", result["answer"])
        self.assertNotIn("AND (AND)", result["answer"])

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
        self.assertIn("NEXT OPTIONS", second["answer"])
        self.assertIn("Check last-30-minute intraday movement", second["answer"])
        self.assertIn("Run 15m intraday setups", second["answer"])
        self.assertIn("Refresh Stage 2 EOD scan", second["answer"])
        self.assertNotIn("Last 30 Minutes", second["answer"])
        self.assertNotIn("get_intraday_market_recap", str(second["trace"]))

    def test_contextual_stage2_last_30_option_b_runs_intraday_setup_scan(self):
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
                        "result": {"symbols_scanned": ["BLISSGVS", "IPCALAB"], "top_buy": [], "top_sell": []},
                    }
                ],
            ]
            agent.query("lets look at the Stage 2 uptrend stocks")
            agent.query("were these pulled from last 30mins")
            third = agent.query("B")

        self.assertEqual(third["intent"], "clarification_reply_binding")
        execute_plan.assert_any_call([
            ("scan_symbols_intraday", {"symbols": ["BLISSGVS", "IPCALAB"], "interval": "15m"})
        ])

    def test_next_options_follow_on_matrix_executes_bound_actions(self):
        cases = [
            ("stage2", "A", [("scan_symbols_intraday", {"symbols": ["BLISSGVS", "IPCALAB"], "interval": "5m"})]),
            ("stage2", "B", [("scan_symbols_intraday", {"symbols": ["BLISSGVS", "IPCALAB"], "interval": "15m"})]),
            ("stage2", "C", [("run_screener_query", {"screen_type": "stage2", "top_n": 10})]),
            ("stage2", "1", [("scan_symbols_intraday", {"symbols": ["BLISSGVS", "IPCALAB"], "interval": "5m"})]),
            ("stage2", "2", [("scan_symbols_intraday", {"symbols": ["BLISSGVS", "IPCALAB"], "interval": "15m"})]),
            ("stage2", "Check last-30-minute intraday movement", [("scan_symbols_intraday", {"symbols": ["BLISSGVS", "IPCALAB"], "interval": "5m"})]),
            ("report", "A", [("open_report", {"path": "/tmp/SWELECTES_research.html"})]),
            ("report", "B", [("read_report", {"path": "/tmp/SWELECTES_research.html", "max_chars": 12000}), ("summarize_report", {"path": "/tmp/SWELECTES_research.html"})]),
            ("report", "C", [("read_report", {"path": "/tmp/SWELECTES_research.html", "max_chars": 12000})]),
            ("report", "Read report contents", [("read_report", {"path": "/tmp/SWELECTES_research.html", "max_chars": 12000})]),
        ]

        for setup, reply, expected_plan in cases:
            agent = Agent()
            agent.backend = object()
            agent.backend_name = "TestBackend"
            if setup == "stage2":
                first_result = [
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
                second_result = [
                    {
                        "tool": expected_plan[0][0],
                        "args": expected_plan[0][1],
                        "result": {"ok": True},
                    }
                ]
                with patch("terminal.agent._execute_plan") as execute_plan:
                    execute_plan.side_effect = [first_result, second_result]
                    agent.query("lets look at the Stage 2 uptrend stocks")
                    prompt = agent.query("were these pulled from last 30mins")
                    result = agent.query(reply)
            else:
                agent._last_turn_context = TurnContext(
                    user_input="/analyze SWELECTES",
                    intent="entity_topic_command",
                    mode="research",
                    tools=["comprehensive_stock_research"],
                    source_label="EOD CSV + DB snapshot",
                    result_type="stock_analysis",
                    result_summary="Report saved for SWELECTES.",
                    symbols=["SWELECTES"],
                    result_items=["/tmp/SWELECTES_research.html"],
                )
                second_result = [
                    {
                        "tool": expected_plan[0][0],
                        "args": expected_plan[0][1],
                        "result": {"ok": True, "path": expected_plan[0][1].get("path")},
                    }
                ]
                with patch("terminal.agent._execute_plan") as execute_plan:
                    prompt = agent.query("the report")
                    execute_plan.side_effect = [second_result]
                    result = agent.query(reply)

            self.assertIn("NEXT OPTIONS", prompt["answer"], msg=(setup, reply))
            self.assertEqual(result["intent"], "clarification_reply_binding", msg=(setup, reply))
            execute_plan.assert_any_call(expected_plan)

    def test_direct_last_30_market_recap_after_market_overview_bypasses_situation_llm(self):
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"

        with patch("terminal.agent._execute_plan") as execute_plan, patch(
            "terminal.assessment_llm.llm_assess_followup"
        ) as llm_assess:
            execute_plan.side_effect = [
                [
                    {
                        "tool": "get_live_market_overview",
                        "args": {},
                        "result": {
                            "indices": {"NIFTY 50": {"last": 23415.35, "pct_change": -0.96}},
                            "adv_dec": {"advances": 41, "declines": 460},
                            "source": "NSE live API",
                            "as_of": "2026-05-18 14:14:00",
                        },
                    },
                    {"tool": "get_market_breadth", "args": {}, "result": {"advances": 41, "declines": 460, "ad_ratio": 0.09}},
                ],
                [
                    {
                        "tool": "get_intraday_market_recap",
                        "args": {"minutes": 30},
                        "result": {
                            "minutes": 30,
                            "as_of": "2026-05-18 14:14:40",
                            "source": "NSE live API + PG intraday.quote_snapshots",
                            "index_moves": [
                                {"symbol": "NIFTY 50", "last": 23415.35, "delta_pct": -0.25, "day_pct": -0.96},
                            ],
                            "live_breadth": {"advances": 41, "declines": 460},
                        },
                    },
                    {"tool": "get_market_breadth", "args": {}, "result": {"advances": 41, "declines": 460, "ad_ratio": 0.09}},
                ],
            ]

            first = agent.query("market overview")
            second = agent.query("what happened in the market in the last 30 minutes")

        self.assertIn(first["intent"], ("market_overview", "market_situation"))
        self.assertEqual(second["intent"], "intraday_market_recap")
        self.assertEqual(execute_plan.call_args_list[-1].args[0][0], ("get_intraday_market_recap", {"minutes": 30}))
        llm_assess.assert_not_called()
        self.assertNotIn("SITUATION ASSESSMENT", second["answer"])
        self.assertNotIn("scan_symbols_intraday", second["answer"])
        self.assertIn("Last 30 Minutes", second["answer"])

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

    def test_agent_startup_briefing_prompt_does_not_ask_for_prior_context(self):
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"
        query = """
        You are starting a new trading session on Monday, 18 May 2026 at 10:51 IST (live market).
        NSE equity market is OPEN.
        Give a comprehensive, investigative morning briefing in this EXACT order:

        ## Good Morning — Market Intelligence Briefing

        ### Global Overnight Context
        ### Previous Trading Day Recap (NSE)
        ### Current Market Status
        """

        with patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.return_value = [
                {"tool": "get_global_market_assessment", "args": {}, "result": {"risk_regime": "mixed"}},
                {"tool": "get_index_snapshot", "args": {"index_name": "NIFTY 50"}, "result": {"index": "NIFTY 50", "close": 23415.35, "chg_pct": -0.96}},
                {"tool": "get_index_snapshot", "args": {"index_name": "NIFTY BANK"}, "result": {"index": "NIFTY BANK", "close": 52934.25, "chg_pct": -1.44}},
                {
                    "tool": "get_live_market_overview",
                    "args": {},
                    "result": {
                        "source": "NSE live API",
                        "as_of": "2026-05-18 10:51:31",
                        "indices": {"NIFTY 50": {"last": 23415.35, "pct_change": -0.96}},
                        "adv_dec": {"advances": 41, "declines": 460},
                    },
                },
                {"tool": "get_market_breadth", "args": {}, "result": {"advances": 41, "declines": 460, "ad_ratio": 0.09}},
                {"tool": "get_top_gainers_losers", "args": {"index": "NIFTY 50", "top_n": 3, "direction": "both"}, "result": {"gainers": [], "losers": []}},
                {"tool": "get_fii_dii_activity", "args": {}, "result": {"data": []}},
            ]
            result = agent.query(query)

        self.assertEqual(result["intent"], "startup_morning_briefing")
        self.assertNotIn("CLARIFICATION NEEDED", result["answer"])
        self.assertNotIn("Which result should I use", result["answer"])
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

    def test_analyze_multi_symbol_command_routes_to_comparison(self):
        routed = _keyword_intent("/analyze SWELECTES, SCHAEFFLER")

        self.assertEqual(routed["intent"], "stock_comparison")
        self.assertEqual(
            routed["plan"],
            [("compare_stocks", {"symbols": ["SWELECTES", "SCHAEFFLER"], "aspects": ["both"]})],
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

    def test_forensic_screen_my_portfolio_typo_routes_to_portfolio_tool_not_screen_symbol(self):
        for query in ("forensic screen my portfolio", "forensic screen my porfolio"):
            with self.subTest(query=query):
                routed = _keyword_intent(query)

                self.assertEqual(routed["intent"], "portfolio_forensic_review")
                self.assertEqual(routed["plan"], [("screen_portfolio_forensic_watchlist", {})])
                self.assertNotIn("'SCREEN'", str(routed).upper())
                self.assertNotIn("resolve_symbol", str(routed))

    def test_agent_forensic_screen_my_portfolio_renders_portfolio_watchlist(self):
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"

        with patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.return_value = [
                {
                    "tool": "screen_portfolio_forensic_watchlist",
                    "args": {},
                    "result": {
                        "portfolio_source": "portfolio-analyzer/output/holdings.csv",
                        "symbols": ["ALKEM", "RELIANCE"],
                        "count": 2,
                        "high_risk": ["ALKEM"],
                        "moderate_risk": [],
                        "low_risk": ["RELIANCE"],
                        "results": [
                            {
                                "symbol": "ALKEM",
                                "overall_risk": "high",
                                "risk_score": 80,
                                "beneish_score": -1.2,
                                "piotroski_score": 4,
                                "altman_score": 1.0,
                            },
                            {
                                "symbol": "RELIANCE",
                                "overall_risk": "low",
                                "risk_score": 20,
                                "beneish_score": -2.8,
                                "piotroski_score": 8,
                                "altman_score": 3.2,
                            },
                        ],
                    },
                }
            ]

            result = agent.query("forensic screen my porfolio")

        self.assertEqual(result["intent"], "portfolio_forensic_review")
        self.assertIn("PORTFOLIO FORENSIC", result["answer"])
        self.assertIn("ALKEM", result["answer"])
        self.assertIn("RELIANCE", result["answer"])
        self.assertNotIn("SCREEN — FORENSIC", result["answer"])

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
        self.assertIn(("get_cached_financials", {"symbol": "TATASTEEL"}), routed["plan"])
        self.assertIn(("scrape_screener_in", {"symbol": "TATASTEEL"}), routed["plan"])
        self.assertIn(("get_latest_results", {"symbol": "TATASTEEL"}), routed["plan"])
        self.assertIn(("get_technical_setup", {"symbol": "TATASTEEL"}), routed["plan"])
        planned_tools = [name for name, _args in routed["plan"]]
        self.assertLess(planned_tools.index("get_cached_financials"), planned_tools.index("scrape_screener_in"))
        self.assertLess(planned_tools.index("scrape_screener_in"), planned_tools.index("get_latest_results"))
        self.assertNotIn("'DETAILED'", str(routed).upper())
        self.assertNotIn("'TATA'", str(routed).upper())

    def test_deep_stock_analysis_uses_pg_screener_then_latest_results_fallback(self):
        routed = _keyword_intent("perform a deep analysis of chennai petroleum")

        self.assertEqual(routed["intent"], "stock_brief")
        planned_tools = [name for name, _args in routed["plan"]]
        for tool in ("get_cached_financials", "scrape_screener_in", "get_latest_results"):
            self.assertIn(tool, planned_tools)
        self.assertLess(planned_tools.index("get_cached_financials"), planned_tools.index("scrape_screener_in"))
        self.assertLess(planned_tools.index("scrape_screener_in"), planned_tools.index("get_latest_results"))

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

    def test_event_calendar_query_with_results_word_does_not_route_to_results_feed(self):
        routed = _keyword_intent("events, results and corporate actions this week")

        self.assertEqual(routed["intent"], "event_calendar")
        self.assertEqual(routed["plan"][0][0], "get_event_calendar_summary")

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

    def test_sector_strength_query_routes_to_live_sector_overview_not_high_rs_screener(self):
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"

        with patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.return_value = [
                {
                    "tool": "get_live_market_overview",
                    "args": {},
                    "result": {
                        "indices": {},
                        "top_sectors": [
                            {"name": "NIFTY REALTY", "pct_change": 1.25},
                            {"name": "NIFTY AUTO", "pct_change": 0.85},
                        ],
                        "bottom_sectors": [
                            {"name": "NIFTY IT", "pct_change": -0.45},
                        ],
                        "source": "NSE live API",
                        "as_of": "2026-05-18 10:26:10",
                    },
                },
                {
                    "tool": "get_market_breadth",
                    "args": {},
                    "result": {"advances": 250, "declines": 220, "ad_ratio": 1.14, "avg_rs_pct": 1.8},
                },
            ]

            result = agent.query("which sectors are showing strength")

        execute_plan.assert_called_once()
        # Plan must start with market overview + breadth; get_top_gainers_losers is optional 3rd
        called_plan = execute_plan.call_args.args[0]
        self.assertIn(("get_live_market_overview", {}), called_plan)
        self.assertIn(("get_market_breadth", {}), called_plan)
        self.assertNotIn(("run_screener_query", {"screen_type": "high_rs"}), called_plan)
        self.assertIn(result["intent"], ("market_overview", "market_situation"))
        self.assertIn("SECTOR STRENGTH", result["answer"])
        self.assertIn("NIFTY REALTY +1.25%", result["answer"])
        self.assertNotIn("SCREENER: HIGH_RS", result["answer"])

    def test_live_mode_sector_strength_query_does_not_treat_which_as_symbol(self):
        routed = _keyword_intent("which sectors are showing strength", data_mode="intraday")

        self.assertEqual(routed["intent"], "market_overview")
        self.assertEqual(routed["plan"], [
            ("get_live_market_overview", {}),
            ("get_market_breadth", {}),
        ])
        self.assertNotIn("resolve_symbol", str(routed))
        self.assertNotIn("WHICH", str(routed))

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

    def test_live_stock_fno_and_5m_intraday_request_routes_to_same_stock_not_nifty(self):
        routed = _keyword_intent(
            "live pricies for dixon tech and the analysis of the F&O data and intraday tradesetup in 5 mins",
            data_mode="intraday",
        )

        self.assertEqual(routed["intent"], "intraday_setup")
        self.assertIn(("resolve_symbol", {"query": "DIXON"}), routed["plan"])
        self.assertIn(("get_nse_intraday_snapshot", {"symbol": "DIXON"}), routed["plan"])
        self.assertIn(("get_fno_overview", {"symbol": "DIXON", "expiry_index": 0}), routed["plan"])
        self.assertIn(("explain_intraday_setup", {"symbol": "DIXON", "timeframe": "5m"}), routed["plan"])
        self.assertIn(("get_intraday_analysis", {"symbol": "DIXON", "interval": "5m"}), routed["plan"])
        self.assertNotIn(("get_fno_overview", {"symbol": "NIFTY", "expiry_index": 0}), routed["plan"])

    def test_live_stock_fno_intraday_request_preserves_company_names_with_and(self):
        routed = _keyword_intent(
            "current price for Mahindra and Mahindra F&O and intraday setup in 15 mins",
            data_mode="intraday",
        )

        self.assertEqual(routed["intent"], "intraday_setup")
        self.assertIn(("resolve_symbol", {"query": "M&M"}), routed["plan"])
        self.assertIn(("get_fno_overview", {"symbol": "M&M", "expiry_index": 0}), routed["plan"])
        self.assertIn(("explain_intraday_setup", {"symbol": "M&M", "timeframe": "15m"}), routed["plan"])
        self.assertNotIn("M&MFIN", str(routed["plan"]))

    def test_intraday_option_trading_bank_name_routes_to_options_trade_plan(self):
        routed = _keyword_intent("intraday analysis option trading INDUSIND BANK", data_mode="intraday")

        self.assertEqual(routed["intent"], "intraday_options_trade_plan")
        self.assertIn(("resolve_symbol", {"query": "INDUSINDBK"}), routed["plan"])
        self.assertIn(("get_nse_intraday_snapshot", {"symbol": "INDUSINDBK"}), routed["plan"])
        self.assertIn(("get_intraday_levels", {"symbol": "INDUSINDBK", "timeframe": "15m"}), routed["plan"])
        self.assertIn(("get_fno_overview", {"symbol": "INDUSINDBK", "expiry_index": 0}), routed["plan"])
        self.assertIn(("get_options_chain", {"symbol": "INDUSINDBK", "expiry_index": 0}), routed["plan"])
        self.assertIn(("get_intraday_analysis", {"symbol": "INDUSINDBK", "interval": "15m"}), routed["plan"])
        self.assertNotIn("INDUSIND BANK", str(routed["plan"]))

        axis = _keyword_intent(
            "is AXIS BANK good for options now support resistance stop loss target",
            data_mode="intraday",
        )
        self.assertEqual(axis["intent"], "intraday_options_trade_plan")
        self.assertIn(("resolve_symbol", {"query": "AXISBANK"}), axis["plan"])
        self.assertIn(("get_options_chain", {"symbol": "AXISBANK", "expiry_index": 0}), axis["plan"])

    def test_agent_backend_path_uses_intraday_options_trade_plan_before_llm(self):
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"

        with patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.return_value = [
                {"tool": "resolve_symbol", "args": {"query": "INDUSINDBK"}, "result": {"symbol": "INDUSINDBK"}},
                {"tool": "get_nse_intraday_snapshot", "args": {"symbol": "INDUSINDBK"}, "result": {"symbol": "INDUSINDBK", "last_price": 931.35}},
                {"tool": "get_intraday_levels", "args": {"symbol": "INDUSINDBK", "timeframe": "15m"}, "result": {"symbol": "INDUSINDBK", "supports": [928.97], "resistances": [931.85], "pivot": 929.73}},
                {"tool": "get_fno_overview", "args": {"symbol": "INDUSINDBK", "expiry_index": 0}, "result": {"symbol": "INDUSINDBK", "pcr": 0.91, "max_pain": 930.0}},
                {"tool": "get_options_chain", "args": {"symbol": "INDUSINDBK", "expiry_index": 0}, "result": {"symbol": "INDUSINDBK", "pcr": 0.91, "max_pain": 930.0}},
                {"tool": "explain_intraday_setup", "args": {"symbol": "INDUSINDBK", "timeframe": "15m"}, "result": {"symbol": "INDUSINDBK", "setup_label": "LONG_SETUP"}},
                {"tool": "get_intraday_analysis", "args": {"symbol": "INDUSINDBK", "interval": "15m"}, "result": {"symbol": "INDUSINDBK"}},
            ]

            result = agent.query("intraday analysis option trading INDUSIND BANK")

        self.assertEqual(result["intent"], "intraday_options_trade_plan")
        self.assertIn("▶ CE SETUP", result["answer"])
        execute_plan.assert_called_once()

    def test_mtf_detector_defers_when_options_trade_plan_requested(self):
        from nse_agent import _detect_mtf_intent_scored

        rewrite, confidence = _detect_mtf_intent_scored(
            "latest on INDUSINDBK intraday multi timeframe analysis options F&O buildup support resistance target stop loss"
        )

        self.assertIsNone(rewrite)
        self.assertIsNone(confidence)

    def test_live_stock_fno_intraday_answer_renders_both_derivatives_and_setup(self):
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"

        with patch("terminal.agent._execute_plan_layered") as execute_plan:
            execute_plan.return_value = [
                {"tool": "resolve_symbol", "args": {"query": "DIXON"}, "result": {"symbol": "DIXON"}},
                {
                    "tool": "get_nse_intraday_snapshot",
                    "args": {"symbol": "DIXON"},
                    "result": {
                        "symbol": "DIXON",
                        "source": "NSE live API",
                        "as_of": "22-May-2026 09:35:00",
                        "last_price": 11258,
                        "pct_change": 1.2,
                        "day_low": 11100,
                        "day_high": 11300,
                    },
                },
                {
                    "tool": "get_fno_overview",
                    "args": {"symbol": "DIXON", "expiry_index": 0},
                    "result": {
                        "symbol": "DIXON",
                        "pcr": 0.91,
                        "max_pain": 11200,
                        "option_chain": {},
                        "top_oi_strikes": {"calls": [], "puts": []},
                        "futures": {},
                        "basis": 22.5,
                        "cost_of_carry": 8.1,
                        "recommendation": {"strategy": "defined_risk_spread"},
                        "source_trail": {"get_options_chain": "ok", "get_futures_analysis": "ok"},
                    },
                },
                {
                    "tool": "explain_intraday_setup",
                    "args": {"symbol": "DIXON", "timeframe": "5m"},
                    "result": {
                        "symbol": "DIXON",
                        "timeframe": "5m",
                        "setup_label": "WATCH",
                        "score": 55,
                        "latest_close": 11258,
                        "latest_timestamp": "2026-05-22 09:35:00",
                        "indicators": {},
                        "levels": {},
                    },
                },
            ]
            result = agent.query(
                "live pricies for dixon tech and the analysis of the F&O data and intraday tradesetup in 5 mins"
            )

        # AA-UR-6 wires AA-UR-4's CompoundStockProvider into Agent. The
        # prompt now routes through ``compound_plan`` with intent
        # ``compound_stock_overview`` instead of the legacy
        # ``intraday_setup`` keyword path. Both render the same
        # NSE / F&O / intraday-setup evidence via ``_synthesize_no_llm``.
        self.assertEqual(result["intent"], "compound_stock_overview")
        self.assertIn("DIXON — F&O Overview", result["answer"])
        self.assertIn("▶ INTRADAY SETUP", result["answer"])
        self.assertIn("Timeframe: 5m", result["answer"])
        self.assertIn("▶ NSE LIVE SNAPSHOT", result["answer"])
        self.assertNotIn("NIFTY — F&O Overview", result["answer"])

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
        self.assertIn("23700 (OI 400,000, chg +25,000)", result["answer"])
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
        self.assertEqual(result["intent"], "market_situation")
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

    def test_agent_sherlock_fundamentals_prompt_uses_stock_plan_not_market_dashboard(self):
        agent = Agent()
        agent.backend = None
        agent.set_permission_mode("plan")
        prompt = (
            "Fundamental analysis of RIC from screener.in — P/E, P/B, ROE, "
            "ROCE, debt/equity, revenue growth, pros and cons."
        )

        result = agent.query(prompt, show_trace=True)

        self.assertEqual(result["intent"], "plan_preview:stock_brief")
        self.assertIn("scrape_screener_in", result["answer"])
        self.assertNotIn("get_live_market_overview", result["answer"])

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

    def test_unresolved_symbol_response_suggests_near_matches(self):
        agent = Agent()
        agent.backend = None
        with patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.return_value = [
                {
                    "tool": "resolve_symbol",
                    "args": {"query": "WAREEENER"},
                    "result": {
                        "symbol": None,
                        "confidence": "none",
                        "query": "WAREEENER",
                        "error": "No exact NSE symbol found for 'WAREEENER'",
                        "candidates": ["WAAREEENER"],
                        "suggestion": "WAAREEENER",
                    },
                }
            ]
            result = agent.query("WAREEENER technical setup")

        self.assertIn("Did you mean: WAAREEENER", result["answer"])
        self.assertIn("Suggestions: WAAREEENER", result["answer"])

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
                {"tool": "get_technical_setup", "args": {"symbol": "TALBROAUTO"}, "result": {"symbol": "TALBROAUTO"}},
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

    def test_bare_symbol_route_runs_quick_analysis_plan(self):
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"

        with patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.return_value = [
                {"tool": "resolve_symbol", "args": {"query": "PERSISTENT"}, "result": {"symbol": "PERSISTENT"}},
                {"tool": "get_symbol_quick_analysis", "args": {"symbol": "PERSISTENT"}, "result": {"symbol": "PERSISTENT", "price": 100}},
            ]
            result = agent.query("PERSISTENT")

        planned = execute_plan.call_args.args[0]
        self.assertEqual(
            [name for name, _args in planned],
            [
                "resolve_symbol",
                "get_symbol_quick_analysis",
            ],
        )
        self.assertEqual(result["intent"], "symbol_quick_analysis")
        self.assertNotIn("REQUIRED TOOL VALIDATION FAILED", result["answer"])

    def test_entity_topic_technical_route_runs_stock_brief_required_tools(self):
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"

        with patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.return_value = [
                {"tool": "resolve_symbol", "args": {"query": "PERSISTENT"}, "result": {"symbol": "PERSISTENT"}},
                {"tool": "get_symbol_snapshot", "args": {"symbol": "PERSISTENT"}, "result": {"symbol": "PERSISTENT", "price": 100}},
                {"tool": "get_technical_setup", "args": {"symbol": "PERSISTENT"}, "result": {"symbol": "PERSISTENT", "rsi": 55}},
            ]
            result = agent.query("PERSISTENT technical setup")

        planned = execute_plan.call_args.args[0]
        planned_tools = [name for name, _args in planned]
        self.assertIn("resolve_symbol", planned_tools)
        self.assertIn("get_symbol_snapshot", planned_tools)
        self.assertIn("get_technical_setup", planned_tools)
        self.assertEqual(result["intent"], "stock_brief")
        self.assertNotIn("REQUIRED TOOL VALIDATION FAILED", result["answer"])

    def test_symbol_validator_ignores_generated_stock_360_instruction_words(self):
        from terminal.agent import _validate_symbol_grounding

        query = (
            "Perform a comprehensive 360° analysis of SCHAEFFLER. Execute these tools IN ORDER:\n\n"
            "1. **get_technical_setup** for SCHAEFFLER — trend, RSI, MACD, support/resistance, stage\n"
            "2. **comprehensive_stock_research** for SCHAEFFLER — fundamentals, valuations, peer comparison\n"
            "Then synthesize ALL results into a unified report with BUY/HOLD/AVOID verdict."
        )
        tool_results = [
            {"tool": "resolve_symbol", "args": {"query": "SCHAEFFLER"}, "result": {"symbol": "SCHAEFFLER"}},
            {"tool": "get_symbol_snapshot", "args": {"symbol": "SCHAEFFLER"}, "result": {"symbol": "SCHAEFFLER"}},
            {"tool": "get_technical_setup", "args": {"symbol": "SCHAEFFLER"}, "result": {"symbol": "SCHAEFFLER"}},
            {"tool": "comprehensive_stock_research", "args": {"symbol": "SCHAEFFLER"}, "result": {"symbol": "SCHAEFFLER"}},
        ]

        self.assertIsNone(_validate_symbol_grounding(query, "stock_brief", tool_results))

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
        self.assertEqual(routed["plan"][1], ("get_cached_financials", {"symbol": "DELHIVERY"}))
        self.assertEqual(routed["plan"][2], ("scrape_screener_in", {"symbol": "DELHIVERY"}))
        self.assertEqual(routed["plan"][3], ("get_latest_results", {"symbol": "DELHIVERY"}))

    def test_latest_quarterly_results_for_symbol_routes_full_evidence_chain(self):
        from terminal.agent import _keyword_intent, _required_tools_for_query

        query = "latest quarterly results for reliance"
        routed = _keyword_intent(query)

        self.assertEqual(routed["intent"], "stock_results")
        self.assertEqual(routed["plan"], [
            ("resolve_symbol", {"query": "reliance"}),
            ("get_cached_financials", {"symbol": "RELIANCE"}),
            ("scrape_screener_in", {"symbol": "RELIANCE"}),
            ("get_latest_results", {"symbol": "RELIANCE"}),
        ])
        required = _required_tools_for_query(routed["intent"], query)
        self.assertLess(
            routed["plan"].index(("get_cached_financials", {"symbol": "RELIANCE"})),
            routed["plan"].index(("scrape_screener_in", {"symbol": "RELIANCE"})),
        )
        self.assertLess(
            routed["plan"].index(("scrape_screener_in", {"symbol": "RELIANCE"})),
            routed["plan"].index(("get_latest_results", {"symbol": "RELIANCE"})),
        )
        self.assertTrue(set(required).issubset({name for name, _args in routed["plan"]}))

    def test_report_plus_results_analysis_plan_prefers_stock_results_synthesis(self):
        plan = [
            ("read_report", {"path": "/tmp/AEROENTER_research.html", "max_chars": 12000}),
            ("get_latest_results", {"symbol": "AEROENTER"}),
        ]

        intent = _synthesis_intent_from_plan(
            plan,
            query="analyze this report and perform a deep analysis of the quarterly results",
        )

        self.assertEqual(intent, "stock_results")

    def test_larsen_and_toubro_deep_analysis_routes_to_lt_not_larsen(self):
        from terminal.agent import _keyword_intent

        routed = _keyword_intent("perform a deep analysis of larsen and toubro")

        self.assertEqual(routed["intent"], "stock_brief")
        self.assertIn(("resolve_symbol", {"query": "LT"}), routed["plan"])
        self.assertIn(("get_cached_financials", {"symbol": "LT"}), routed["plan"])
        self.assertIn(("scrape_screener_in", {"symbol": "LT"}), routed["plan"])
        self.assertIn(("get_latest_results", {"symbol": "LT"}), routed["plan"])

    def test_sbi_deep_analysis_routes_to_sbin_not_sbi(self):
        from terminal.agent import _keyword_intent

        routed = _keyword_intent("perform a deep analysis of sbi")

        self.assertEqual(routed["intent"], "stock_brief")
        self.assertIn(("resolve_symbol", {"query": "SBIN"}), routed["plan"])
        self.assertIn(("get_cached_financials", {"symbol": "SBIN"}), routed["plan"])
        self.assertIn(("scrape_screener_in", {"symbol": "SBIN"}), routed["plan"])
        self.assertIn(("get_latest_results", {"symbol": "SBIN"}), routed["plan"])

    def test_llm_deep_analysis_supplements_missing_latest_results_chain(self):
        from terminal.agent import _missing_fundamental_chain_plan

        tool_results = [
            {"tool": "resolve_symbol", "args": {"query": "sun pharma"}, "result": {"symbol": "SUNPHARMA"}},
            {"tool": "get_cached_financials", "args": {"symbol": "SUNPHARMA"}, "result": {"symbol": "SUNPHARMA"}},
            {"tool": "scrape_screener_in", "args": {"symbol": "SUNPHARMA"}, "result": {"symbol": "SUNPHARMA"}},
        ]

        plan = _missing_fundamental_chain_plan(tool_results, "perform a deep analysis of sun pharma")

        self.assertEqual(plan, [("get_latest_results", {"symbol": "SUNPHARMA"})])

    def test_results_in_last_two_weeks_routes_to_results_feed_not_symbol_in(self):
        from terminal.agent import _keyword_intent

        routed = _keyword_intent("results in last 2 weeks")

        self.assertEqual(routed["intent"], "results_feed")
        self.assertEqual(routed["plan"], [("get_latest_results_feed", {"days_back": 14, "limit": 50})])

    def test_results_feed_slash_command_accepts_weeks_parameter(self):
        from terminal.agent import _keyword_intent

        cases = {
            "/results-feed": 14,
            "/results-feed 2": 14,
            "/results-feed 4w": 28,
            "/results-feed --weeks 6": 42,
            "/results-feed --weeks=8": 56,
            "/latest-results 3": 21,
        }

        for query, days in cases.items():
            with self.subTest(query=query):
                routed = _keyword_intent(query)

                self.assertEqual(routed["intent"], "results_feed")
                self.assertEqual(routed["plan"], [("get_latest_results_feed", {"days_back": days, "limit": 50})])

    def test_results_feed_slash_command_is_exposed_in_terminal_browser(self):
        import nse_agent

        slash_commands = [cmd for cmd, _desc in nse_agent._SLASH_COMMANDS]

        self.assertIn("/results-feed", slash_commands)
        self.assertEqual(nse_agent._CMD_CATEGORIES["/results-feed"][0], "Latest Results")

    def test_results_feed_slash_command_runs_without_llm(self):
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"

        with patch("terminal.agent._execute_plan") as execute_plan, patch.object(agent, "_llm_query") as llm_query:
            execute_plan.return_value = [
                {
                    "tool": "get_latest_results_feed",
                    "args": {"days_back": 28, "limit": 50},
                    "result": {"results": [], "days_back": 28, "source": "nse", "total_in_window": 0, "total_available": 0},
                }
            ]
            result = agent.query("/results-feed 4")

        execute_plan.assert_called_once_with([("get_latest_results_feed", {"days_back": 28, "limit": 50})])
        self.assertEqual(result["intent"], "results_feed")
        self.assertIn("last 28 day(s)", result["answer"])
        llm_query.assert_not_called()

    def test_generated_deep_search_prompt_does_not_split_or_resolve_use_as_symbol(self):
        prompt = (
            "Run a comprehensive deep search for SCHAEFFLER. "
            "Use deep_search with all default verticals. "
            "Context: 'results'. "
            "Present results section-by-section: NSE announcements, corporate actions, insider trades. "
            "Include dates, real URLs, and actionable insights."
        )

        self.assertEqual(_split_compound_query(prompt), [prompt])
        routed = _keyword_intent(prompt)

        self.assertEqual(routed["intent"], "entity_topic_command")
        self.assertEqual(routed["plan"], [("deep_search", {"symbol": "SCHAEFFLER", "context": "results"})])
        self.assertNotIn("USE", str(routed))

    def test_company_identity_instruction_does_not_split_or_route_keep_as_symbol(self):
        prompt = (
            "Resolve KIMS to its company identity, aliases, sector, industry, "
            "and official website. Keep the answer evidence-first."
        )

        self.assertEqual(_split_compound_query(prompt), [prompt])
        routed = _keyword_intent(prompt)

        self.assertEqual(routed["intent"], "company_identity")
        self.assertEqual(routed["plan"][0], ("resolve_symbol", {"query": "KIMS"}))
        self.assertTrue(any(tool == "get_sector_context" for tool, _ in routed["plan"]))
        self.assertNotIn("KEEP", str(routed["plan"]))

    def test_company_identity_instruction_runs_once_for_requested_symbol(self):
        prompt = (
            "Resolve KIMS to its company identity, aliases, sector, industry, "
            "and official website. Keep the answer evidence-first."
        )
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"

        with patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.return_value = [
                {"tool": "resolve_symbol", "args": {"query": "KIMS"}, "result": {"symbol": "KIMS"}},
                {"tool": "get_symbol_snapshot", "args": {"symbol": "KIMS"}, "result": {"symbol": "KIMS"}},
                {"tool": "get_sector_context", "args": {"sector_or_symbol": "KIMS"}, "result": {"symbol": "KIMS"}},
            ]
            result = agent.query(prompt)

        execute_plan.assert_called_once_with([
            ("resolve_symbol", {"query": "KIMS"}),
            ("get_symbol_snapshot", {"symbol": "KIMS"}),
            ("get_sector_context", {"sector_or_symbol": "KIMS"}),
        ])
        self.assertEqual(result["intent"], "company_identity")
        self.assertNotIn("Part 2", result["answer"])
        self.assertNotIn("KEEPLEARN", result["answer"])

    def test_agent_generated_deep_search_prompt_runs_as_single_deep_search(self):
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"
        prompt = (
            "Run a comprehensive deep search for SCHAEFFLER. "
            "Use deep_search with all default verticals. "
            "Context: 'results'. "
            "Present results section-by-section: NSE announcements, corporate actions, insider trades. "
            "Include dates, real URLs, and actionable insights."
        )

        with patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.return_value = [
                {"tool": "deep_search", "args": {"symbol": "SCHAEFFLER", "context": "results"}, "result": {"symbol": "SCHAEFFLER", "results": []}},
            ]
            result = agent.query(prompt)

        execute_plan.assert_called_once_with([("deep_search", {"symbol": "SCHAEFFLER", "context": "results"})])
        self.assertEqual(result["intent"], "entity_topic_command")
        self.assertNotIn("Part 2 of", result["answer"])
        self.assertNotIn("USE (USE)", result["answer"])

    def test_result_announcement_time_window_phrasings_route_to_results_feed(self):
        from terminal.agent import _keyword_intent

        cases = {
            "latest results last two weeks": 14,
            "results during last 2 weeks": 14,
            "results over the past fortnight": 14,
            "results for last 14 days": 14,
            "results in last 10 days": 10,
            "results submitted last month": 30,
            "BSE results announcements in past two weeks": 14,
            "announcements of latest results submitted by various companies in last 2 weeks": 14,
            "latest result announcements in past two weeks": 14,
            "companies that filed results during previous 10 days": 10,
        }

        for query, days in cases.items():
            with self.subTest(query=query):
                routed = _keyword_intent(query)

                self.assertEqual(routed["intent"], "results_feed")
                self.assertEqual(routed["plan"], [("get_latest_results_feed", {"days_back": days, "limit": 50})])

    def test_symbol_less_latest_results_runs_results_feed_not_llm(self):
        agent = Agent()
        agent.backend = object()
        agent.backend_name = "TestBackend"

        with patch("terminal.agent._execute_plan") as execute_plan, patch.object(agent, "_llm_query") as llm_query:
            execute_plan.return_value = [
                {
                    "tool": "get_latest_results_feed",
                    "args": {"days_back": 7, "limit": 50},
                    "result": {"status": "ok", "count": 0, "results": []},
                }
            ]
            result = agent.query("latest results")

        self.assertEqual(result["intent"], "results_feed")
        self.assertIn("Latest Quarterly Results Feed", result["answer"])
        self.assertNotIn("REQUIRED TOOL VALIDATION FAILED", result["answer"])
        llm_query.assert_not_called()

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
            "If this is a financial document (annual report, concall transcript, quarterly results), "
            "also evaluate: revenue/profit trends, management commentary, guidance changes, "
            "financial statements, latest results, risk factors, and investment implications."
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

    def test_analyze_stock_360_prompt_does_not_route_to_market_situation(self):
        from terminal.agent import _keyword_intent

        routed = _keyword_intent(
            "Perform a comprehensive 360° analysis of SCHAEFFLER. Execute these tools IN ORDER:\n\n"
            "1. **get_technical_setup** for SCHAEFFLER — trend, RSI, MACD, support/resistance, stage\n"
            "2. **comprehensive_stock_research** for SCHAEFFLER — fundamentals, valuations, peer comparison\n"
            "3. **run_forensic_analysis** for SCHAEFFLER — Beneish M-score, Piotroski F-score, Altman Z'-score\n"
            "4. **search_latest_catalysts** for SCHAEFFLER — latest news, read top 2 articles for sentiment\n"
            "5. **get_sector_context** for SCHAEFFLER — sector rotation status and relative strength\n"
            "6. **deep_search** for SCHAEFFLER verticals=['shareholding','insider_trades','analyst_targets'] — institutional & insider activity\n\n"
            "Then synthesize ALL results into a unified report with News & Sentiment and FII/DII changes."
        )
        tools = [name for name, _args in routed["plan"]]

        self.assertEqual(routed["intent"], "stock_brief")
        self.assertNotIn("get_live_market_overview", tools)
        self.assertIn("get_symbol_snapshot", tools)
        self.assertIn("comprehensive_stock_research", tools)
        self.assertIn("run_forensic_analysis", tools)
        self.assertIn("deep_search", tools)

    def test_report_research_prompt_routes_to_full_360_plan(self):
        from terminal.agent import _keyword_intent
        from terminal.reports import get_report_prompt

        prompt = get_report_prompt("research", "MODISONLTD", "html")
        routed = _keyword_intent(prompt)
        tools = [name for name, _args in routed["plan"]]

        self.assertEqual(routed["intent"], "stock_brief")
        self.assertIn(("resolve_symbol", {"query": "MODISONLTD"}), routed["plan"])
        self.assertIn("get_symbol_snapshot", tools)
        self.assertIn("scrape_screener_in", tools)
        self.assertIn("get_technical_setup", tools)
        self.assertIn("comprehensive_stock_research", tools)
        self.assertIn("run_forensic_analysis", tools)
        self.assertIn("search_shareholding_analysis", tools)
        self.assertIn("search_concall_transcripts", tools)
        self.assertIn("analyze_concall_sentiment", tools)
        self.assertIn("search_latest_catalysts", tools)
        self.assertIn("get_sector_context", tools)
        self.assertIn("search_broker_research", tools)
        self.assertIn("get_latest_results", tools)

    def test_agent_research_report_prompt_is_not_hijacked_by_visual_scan_router(self):
        from terminal.reports import get_report_prompt

        agent = Agent()
        agent.backend = None
        agent.set_permission_mode("plan")
        prompt = get_report_prompt("research", "RELIANCE", "html")

        result = agent.query(prompt, show_trace=True)

        self.assertEqual(result["intent"], "plan_preview:stock_brief")
        self.assertIn("get_symbol_snapshot", result["answer"])
        self.assertIn("scrape_screener_in", result["answer"])
        self.assertNotIn("run_visual_scan", result["answer"])

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

    def test_required_tool_validator_allows_ric_step_with_prevalidated_symbol(self):
        from terminal.agent import _validate_required_tools

        marker = "[[RIC_STEP_PREVALIDATED_SYMBOL=AEROFLEX]]"
        cases = [
            (
                f"{marker} Full technical setup for AEROFLEX — Weinstein stage, RSI, ADX, MACD.",
                [
                    {"tool": "get_technical_setup", "args": {"symbol": "AEROFLEX"}, "result": {"symbol": "AEROFLEX"}},
                    {"tool": "get_symbol_snapshot", "args": {"symbol": "AEROFLEX"}, "result": {"symbol": "AEROFLEX"}},
                ],
            ),
            (
                f"{marker} Fundamental analysis of AEROFLEX from screener.in — P/E, P/B, ROE, ROCE.",
                [
                    {"tool": "get_cached_financials", "args": {"symbol": "AEROFLEX"}, "result": {"symbol": "AEROFLEX"}},
                    {"tool": "scrape_screener_in", "args": {"symbol": "AEROFLEX"}, "result": {"symbol": "AEROFLEX"}},
                ],
            ),
            (
                f"{marker} Latest news and catalysts for AEROFLEX — recent announcements, results, management commentary.",
                [
                    {"tool": "search_latest_catalysts", "args": {"symbol": "AEROFLEX"}, "result": {"symbol": "AEROFLEX"}},
                    {"tool": "search_nse_announcements", "args": {"symbol": "AEROFLEX"}, "result": {"symbol": "AEROFLEX"}},
                    {"tool": "search_bse_filings", "args": {"symbol": "AEROFLEX"}, "result": {"symbol": "AEROFLEX"}},
                    {"tool": "get_latest_results", "args": {"symbol": "AEROFLEX"}, "result": {"symbol": "AEROFLEX"}},
                ],
            ),
        ]

        for query, tool_results in cases:
            with self.subTest(query=query):
                self.assertIsNone(_validate_required_tools(query, "stock_brief", tool_results))

    def test_required_tool_validator_allows_setup_review_backed_by_intraday_setup(self):
        from terminal.agent import _validate_required_tools

        query = "Review short setups"
        tool_results = [
            {
                "tool": "explain_intraday_setup",
                "args": {"symbol": "EXIDEIND", "timeframe": "15m"},
                "result": {"symbol": "EXIDEIND", "timeframe": "15m", "setup_label": "SHORT_SETUP"},
            },
            {
                "tool": "explain_intraday_setup",
                "args": {"symbol": "SBICARD", "timeframe": "15m"},
                "result": {"symbol": "SBICARD", "timeframe": "15m", "setup_label": "SHORT_SETUP"},
            },
        ]

        self.assertIsNone(_validate_required_tools(query, "stock_brief", tool_results))
        self.assertIsNone(_validate_required_tools(
            query,
            "stock_brief",
            [
                {
                    "tool": "get_intraday_levels",
                    "args": {"symbol": "EXIDEIND"},
                    "result": {"symbol": "EXIDEIND", "supports": [100], "resistances": [110]},
                }
            ],
        ))


class UnifiedRouterAgentWiringTests(unittest.TestCase):
    """AA-UR-6: Agent ↔ UnifiedRouter wiring parity tests."""

    def _make_agent(self):
        agent = Agent()
        agent.backend = None  # force no-LLM path so router/legacy decide
        agent.backend_name = "TestBackend"
        return agent

    def test_unified_router_executes_compound_stock_plan_for_dixon_prompt(self):
        agent = self._make_agent()

        with patch("terminal.agent._execute_plan_layered") as execute_plan:
            execute_plan.return_value = [
                {"tool": "resolve_symbol", "args": {"query": "dixon"}, "result": {"symbol": "DIXON"}},
                {"tool": "get_live_quote", "args": {"symbol": "DIXON"}, "result": {"symbol": "DIXON", "last_price": 11258}},
                {"tool": "get_fno_overview", "args": {"symbol": "DIXON", "expiry_index": 0}, "result": {"symbol": "DIXON", "pcr": 0.91}},
                {"tool": "explain_intraday_setup", "args": {"symbol": "DIXON", "timeframe": "5m"}, "result": {"symbol": "DIXON", "timeframe": "5m", "setup_label": "WATCH"}},
                {"tool": "get_intraday_analysis", "args": {"symbol": "DIXON"}, "result": {"symbol": "DIXON"}},
            ]
            result = agent.query(
                "live pricies for dixon tech and the analysis of the F&O data and intraday tradesetup in 5 mins"
            )

        self.assertEqual(result["intent"], "compound_stock_overview")
        ur_steps = [s for s in result["trace"] if isinstance(s, dict) and s.get("step") == "unified_router"]
        self.assertEqual(len(ur_steps), 1)
        decision = ur_steps[0]["decision"]
        self.assertEqual(decision["selected_branch"], "CompoundStockProvider")
        self.assertEqual(decision["route_type"], "compound_plan")
        self.assertIn("DIXON", decision["context"]["symbols"])
        execute_plan.assert_called_once()

    def test_unified_router_kill_switch_disables_router(self):
        agent = self._make_agent()

        with patch.dict(os.environ, {"NSE_UNIFIED_ROUTER": "0"}), \
             patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.return_value = [
                {"tool": "resolve_symbol", "args": {"query": "dixon"}, "result": {"symbol": "DIXON"}},
                {"tool": "get_nse_intraday_snapshot", "args": {"symbol": "DIXON"}, "result": {"symbol": "DIXON"}},
                {"tool": "get_fno_overview", "args": {"symbol": "DIXON", "expiry_index": 0}, "result": {"symbol": "DIXON"}},
                {"tool": "explain_intraday_setup", "args": {"symbol": "DIXON", "timeframe": "5m"}, "result": {"symbol": "DIXON"}},
            ]
            result = agent.query(
                "live pricies for dixon tech and the analysis of the F&O data and intraday tradesetup in 5 mins"
            )

        # With the router disabled, no `unified_router` trace step should appear
        # and the legacy keyword-intent path should claim the prompt.
        ur_steps = [s for s in result["trace"] if isinstance(s, dict) and s.get("step") == "unified_router"]
        self.assertEqual(ur_steps, [])
        self.assertEqual(result["intent"], "intraday_setup")

    def test_unified_router_executes_pending_option_bound_plan(self):
        from terminal.router import PendingOption

        agent = self._make_agent()
        # Pre-register a pending option that binds to a concrete tool plan,
        # mimicking what a future renderer will do after showing NEXT OPTIONS.
        agent._memory.register_pending_options([
            PendingOption(
                label="A",
                text="Run the deep DIXON setup",
                bound_action={
                    "intent": "intraday_setup",
                    "tool_plan": [
                        {"tool": "resolve_symbol", "args": {"query": "DIXON"}},
                        {"tool": "explain_intraday_setup", "args": {"symbol": "DIXON", "timeframe": "5m"}},
                    ],
                },
            ),
        ])

        with patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.return_value = [
                {"tool": "resolve_symbol", "args": {"query": "DIXON"}, "result": {"symbol": "DIXON"}},
                {"tool": "explain_intraday_setup", "args": {"symbol": "DIXON", "timeframe": "5m"}, "result": {"symbol": "DIXON", "timeframe": "5m", "setup_label": "WATCH"}},
            ]
            result = agent.query("A")

        self.assertEqual(result["intent"], "intraday_setup")
        ur_steps = [s for s in result["trace"] if isinstance(s, dict) and s.get("step") == "unified_router"]
        self.assertEqual(len(ur_steps), 1)
        self.assertEqual(ur_steps[0]["decision"]["selected_branch"], "PendingOptionProvider")
        # The bound plan executed verbatim — no symbol resolution against "A".
        executed_plan = execute_plan.call_args[0][0]
        self.assertEqual([t for t, _ in executed_plan], ["resolve_symbol", "explain_intraday_setup"])
        # Consumed: a second "A" reply must no longer match.
        self.assertIsNone(agent._memory.consume_pending_option("A"))

    def test_unified_router_falls_through_for_greeting(self):
        agent = self._make_agent()

        with patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.return_value = []
            result = agent.query("Hello")

        # Router records its decision (DirectIntent / blocked / none), but
        # the legacy greeting branch still owns the answer.
        self.assertEqual(result["intent"], "greeting")
        execute_plan.assert_called_once_with([])

    def test_unified_router_skipped_for_morning_briefing_prompt(self):
        """Regression: the synthetic startup briefing prompt mentions
        "F&O expiry", "intraday" and "Global Overnight Context", and was
        being mis-routed by CompoundStockProvider to compound_stock_overview
        with a bogus GLOBAL ticker. The router must skip this prompt and
        let the legacy `_keyword_intent` morning-briefing branch own it."""
        agent = self._make_agent()
        briefing_prompt = (
            "You are starting a new trading session on Monday at 09:40 IST (live market).\n"
            "Give a comprehensive, investigative morning briefing in this EXACT order:\n"
            "### 🌍 Global Overnight Context\n"
            "- US markets, Asian markets, SGX Nifty / GIFT Nifty\n"
            "- USD/INR direction, crude oil price\n"
            "### 📅 Previous Trading Day Recap (NSE)\n"
            "- How did NIFTY 50 and NIFTY BANK close yesterday\n"
            "### 📊 Current Market Status\n"
            "- Top gainers and losers so far today\n"
            "### 🎯 Today's Watchlist & Themes\n"
            "- F&O expiry\n"
            "- Key support/resistance levels for NIFTY 50 intraday\n"
        )

        with patch("terminal.agent._execute_plan") as execute_plan:
            execute_plan.return_value = []
            result = agent.query(briefing_prompt)

        # The unified_router step must NOT appear — the synthetic briefing
        # prompt is routed deterministically by _keyword_intent.
        ur_steps = [s for s in result["trace"] if isinstance(s, dict) and s.get("step") == "unified_router"]
        self.assertEqual(ur_steps, [])
        self.assertEqual(result["intent"], "startup_morning_briefing")


if __name__ == "__main__":
    unittest.main()
