from unittest.mock import patch

import nse_agent
from terminal.agent import Agent, _keyword_intent, _split_compound_query
from terminal.situation_assessment import TurnContext


def test_real_life_prompt_routing_matrix_covers_core_workflows():
    cases = [
        (
            "fundamentals",
            "ROE and PE for HDFCBANK",
            "stock_brief",
            [("resolve_symbol", {"query": "HDFCBANK"}), ("scrape_screener_in", {"symbol": "HDFCBANK"})],
        ),
        (
            "technical",
            "RELIANCE technical setup with RSI MACD",
            "stock_brief",
            [("resolve_symbol", {"query": "RELIANCE"}), ("get_technical_setup", {"symbol": "RELIANCE"})],
        ),
        (
            "forensic strategy",
            "Run forensic analysis for TATASTEEL with Beneish Piotroski and Altman",
            "stock_brief",
            [("run_forensic_analysis", {"symbol": "TATASTEEL"})],
        ),
        (
            "peer comparison",
            "compare TCS vs INFY on valuation and technical strength",
            "stock_comparison",
            [("compare_stocks", {"symbols": ["TCS", "INFY"], "aspects": ["both"]})],
        ),
        (
            "sector leadership",
            "which sectors are showing strength",
            "market_overview",
            [("get_live_market_overview", {}), ("get_market_breadth", {})],
        ),
        (
            "latest results feed",
            "results in last 2 weeks",
            "results_feed",
            [("get_latest_results_feed", {"days_back": 14, "limit": 50})],
        ),
        (
            "fno strategy",
            "Give a comprehensive F&O overview for NIFTY with PCR max pain futures basis and best options strategy",
            "fno_overview",
            [("get_fno_overview", {"symbol": "NIFTY", "expiry_index": 0})],
        ),
        (
            "superperformance stocks",
            "show superperformance stocks",
            "screener",
            [("run_screener_query", {"screen_type": "high_rs"})],
        ),
        (
            "minervini vcp stocks",
            "find Minervini superperformance VCP stocks",
            "screener",
            [("run_screener_query", {"screen_type": "tight_range"})],
        ),
        (
            "market education",
            "what is Minervini superperformance strategy",
            "market_knowledge",
            [("search_market_knowledge", {"query": "what is Minervini superperformance strategy"})],
        ),
        (
            "report lookup",
            "open the report",
            "report_lookup",
            [("find_latest_report", {})],
        ),
    ]

    for label, query, intent, expected_steps in cases:
        routed = _keyword_intent(query)
        assert routed["intent"] == intent, label
        for step in expected_steps:
            assert step in routed["plan"], label
        assert "SUPERPERFORMANCE" not in str(routed["plan"]), label
        assert "VCP" not in str(routed["plan"]) or intent == "market_knowledge", label


def test_real_life_stock_analysis_renders_technical_fundamental_and_sector_evidence():
    agent = Agent()
    agent.backend = object()
    agent.backend_name = "TestBackend"

    with patch("terminal.agent._execute_plan") as execute_plan:
        execute_plan.return_value = [
            {"tool": "resolve_symbol", "args": {"query": "RELIANCE"}, "result": {"symbol": "RELIANCE"}},
            {
                "tool": "scrape_screener_in",
                "args": {"symbol": "RELIANCE"},
                "result": {
                    "symbol": "RELIANCE",
                    "source_url": "https://www.screener.in/company/RELIANCE/",
                    "ratios": {"Market Cap": "₹20,00,000 Cr", "Stock P/E": "28.4", "ROE": "9.2%"},
                    "quarterly": {
                        "_headers": ["Dec 2025", "Mar 2026"],
                        "Sales": ["2,40,000", "2,50,000"],
                        "Net Profit": ["18,000", "19,000"],
                    },
                },
            },
            {
                "tool": "get_symbol_snapshot",
                "args": {"symbol": "RELIANCE"},
                "result": {
                    "symbol": "RELIANCE",
                    "price": 1420.5,
                    "stage": "STAGE_2",
                    "trading_signal": "BUY",
                    "relative_strength": 1.18,
                    "sector": "Energy - Oil & Gas",
                },
            },
            {
                "tool": "get_technical_setup",
                "args": {"symbol": "RELIANCE"},
                "result": {"symbol": "RELIANCE", "rsi": 62.5, "macd": "Bullish", "supertrend": "BUY"},
            },
            {
                "tool": "get_sector_context",
                "args": {"sector_or_symbol": "RELIANCE"},
                "result": {"sector": "Energy - Oil & Gas", "total_stocks": 22, "stage2_count": 8, "avg_rs_pct": 3.4},
            },
        ]

        result = agent.query("RELIANCE technical and fundamental setup with RSI MACD ROE PE")

    assert result["intent"] == "stock_brief"
    assert "RELIANCE (RELIANCE) — Market Brief" in result["answer"]
    assert "TECHNICAL SETUP" in result["answer"]
    assert "FUNDAMENTAL RATIOS" in result["answer"]
    assert "QUARTERLY RESULTS" in result["answer"]
    assert "SECTOR CONTEXT" in result["answer"]
    assert "SYMBOL VALIDATION FAILED" not in result["answer"]


def test_real_life_complex_compound_query_runs_each_part_with_separate_evidence():
    agent = Agent()
    agent.backend = object()
    agent.backend_name = "TestBackend"
    query = "Market overview and also latest results for DMART"

    assert _split_compound_query(query) == ["Market overview", "latest results for DMART"]

    with patch("terminal.agent._execute_plan") as execute_plan:
        execute_plan.side_effect = [
            [
                {
                    "tool": "get_live_market_overview",
                    "args": {},
                    "result": {
                        "indices": {"NIFTY 50": {"last": 24500.0, "pct_change": 0.25}},
                        "top_sectors": [{"name": "NIFTY IT", "pct_change": 0.8}],
                        "bottom_sectors": [{"name": "NIFTY MEDIA", "pct_change": -0.6}],
                        "adv_dec": {"advances": 300, "declines": 200},
                        "source": "NSE live API",
                        "as_of": "2026-05-18 10:45:00",
                    },
                },
                {"tool": "get_market_breadth", "args": {}, "result": {"advances": 310, "declines": 190, "ad_ratio": 1.63, "avg_rs_pct": 1.4}},
            ],
            [
                {"tool": "resolve_symbol", "args": {"query": "DMART"}, "result": {"symbol": "DMART"}},
                {
                    "tool": "get_latest_results",
                    "args": {"symbol": "DMART"},
                    "result": {"symbol": "DMART", "status": "ok", "period": "Q4 FY26", "summary": "Revenue grew; margins stable."},
                },
            ],
        ]

        result = agent.query(query)

    assert result["intent"] == "compound"
    assert "Part 1 of 2: Market overview" in result["answer"]
    assert "Part 2 of 2: latest results for DMART" in result["answer"]
    assert execute_plan.call_count == 2


def test_real_life_followup_after_screener_uses_prior_symbols_for_intraday_scan():
    agent = Agent()
    agent.backend = object()
    agent.backend_name = "TestBackend"

    with patch("terminal.agent._execute_plan") as execute_plan:
        execute_plan.side_effect = [
            [
                {
                    "tool": "run_screener_query",
                    "args": {"screen_type": "high_rs"},
                    "result": {"screen_type": "high_rs", "results": [{"symbol": "TRENT"}, {"symbol": "KAYNES"}]},
                }
            ],
            [
                {
                    "tool": "scan_symbols_intraday",
                    "args": {"symbols": ["TRENT", "KAYNES"], "interval": "15m"},
                    "result": {"symbols_scanned": ["TRENT", "KAYNES"], "top_buy": [{"symbol": "KAYNES"}], "top_sell": []},
                }
            ],
        ]

        first = agent.query("show superperformance stocks")
        second = agent.query("scan these for 15m intraday setups")

    assert first["intent"] == "screener"
    assert second["intent"] == "contextual_tool_plan"
    execute_plan.assert_any_call([("scan_symbols_intraday", {"symbols": ["TRENT", "KAYNES"], "interval": "15m"})])
    assert "SITUATION ASSESSMENT" in second["answer"]


def test_real_life_report_followup_yes_please_reads_and_summarizes_latest_report():
    agent = Agent()
    agent.backend = object()
    agent.backend_name = "TestBackend"
    agent._last_turn_context = TurnContext(
        user_input="/analyze SCHAEFFLER",
        intent="generated_report",
        mode="historical",
        tools=[],
        source_label="generated report",
        result_type="report",
        result_summary="Report generated for SCHAEFFLER",
        symbols=["SCHAEFFLER"],
        result_items=["/tmp/SCHAEFFLER_research.html"],
    )

    with patch("terminal.agent._execute_plan") as execute_plan:
        execute_plan.return_value = [
            {
                "tool": "read_report",
                "args": {"path": "/tmp/SCHAEFFLER_research.html", "max_chars": 12000},
                "result": {"status": "ok", "path": "/tmp/SCHAEFFLER_research.html", "content": "<h1>SCHAEFFLER</h1>"},
            },
            {
                "tool": "summarize_report",
                "args": {"path": "/tmp/SCHAEFFLER_research.html"},
                "result": {
                    "status": "ok",
                    "path": "/tmp/SCHAEFFLER_research.html",
                    "symbol": "SCHAEFFLER",
                    "recommendation": "HOLD",
                    "summary": "Recommendation: HOLD\nEvidence: results and technical context.",
                },
            },
        ]

        result = agent.query("yes please")

    assert result["intent"] == "contextual_tool_plan"
    assert execute_plan.call_args.args[0] == [
        ("read_report", {"path": "/tmp/SCHAEFFLER_research.html", "max_chars": 12000}),
        ("summarize_report", {"path": "/tmp/SCHAEFFLER_research.html"}),
    ]
    assert "Recommendation: HOLD" in result["answer"]


def test_real_life_ric_library_has_executable_prompt_recipes_for_major_workflows():
    expected = {"sherlock", "sector-xray", "breakout-hunter", "peer-battle", "risk-radar", "morning-intel", "company-xray"}

    assert expected.issubset(nse_agent.RIC_LIBRARY)
    for key in expected:
        recipe = nse_agent.RIC_LIBRARY[key]
        assert recipe["example"].startswith("/ric ")
        assert recipe["steps"], key
        for step in recipe["steps"]:
            assert step["label"]
            assert step["prompt"]

    company_xray_prompts = [step["prompt"] for step in nse_agent.RIC_LIBRARY["company-xray"]["steps"]]
    assert any("/company-index {symbol}" in prompt for prompt in company_xray_prompts)
    assert any("/company-xray {symbol}" in prompt for prompt in company_xray_prompts)
