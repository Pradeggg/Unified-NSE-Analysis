from unittest.mock import patch

from terminal.agent import Agent, _keyword_intent
from terminal.renderers import render
from terminal.situation_assessment import TurnContext


def _tr(tool: str, result: dict) -> dict:
    return {"tool": tool, "args": {}, "result": result}


def test_bare_symbol_routes_to_symbol_quick_analysis():
    routed = _keyword_intent("gabriel")

    assert routed["intent"] == "symbol_quick_analysis"
    assert routed["plan"] == [
        ("resolve_symbol", {"query": "gabriel"}),
        ("get_symbol_quick_analysis", {"symbol": "gabriel"}),
    ]


def test_bare_portfolio_alias_routes_to_quick_analysis_and_canonicalizes():
    agent = Agent()
    agent.backend = None

    result = agent.query("VISRET")

    assert result["intent"] == "symbol_quick_analysis"
    assert "V2RETAIL - QUICK STOCK ANALYSIS" in result["answer"]
    assert "VISRET - QUICK STOCK ANALYSIS" not in result["answer"]


def test_results_followup_after_quick_analysis_uses_latest_results_tool():
    agent = Agent()
    agent.backend = object()
    agent._last_turn_context = TurnContext(
        user_input="VISRET",
        intent="symbol_quick_analysis",
        mode="historical",
        tools=["resolve_symbol", "get_symbol_quick_analysis"],
        source_label="EOD CSV + DB snapshot",
        result_type="symbol_quick_analysis",
        symbols=["V2RETAIL", "VISRET"],
    )

    with patch("terminal.agent._execute_plan") as execute_plan:
        execute_plan.return_value = [
            _tr("resolve_symbol", {"symbol": "V2RETAIL"}),
            _tr(
                "get_latest_results",
                {
                    "symbol": "V2RETAIL",
                    "period": "latest",
                    "source_trail": {"get_latest_results": "ok"},
                },
            ),
        ]
        result = agent.query("latest quarterly results analysis")

    planned = execute_plan.call_args.args[0]
    assert planned == [
        ("resolve_symbol", {"query": "V2RETAIL"}),
        ("get_latest_results", {"symbol": "V2RETAIL"}),
    ]
    assert result["intent"] == "contextual_tool_plan"
    assert "REQUIRED TOOL VALIDATION FAILED" not in result["answer"]
    assert "get_symbol_quick_analysis" not in [name for name, _args in planned]


def test_deep_stock_prompt_still_uses_stock_brief():
    routed = _keyword_intent("deep analysis of gabriel")

    assert routed["intent"] == "stock_brief"
    assert ("get_symbol_quick_analysis", {"symbol": "GABRIEL"}) not in routed["plan"]


def test_symbol_quick_analysis_renderer_sections():
    out = render(
        "symbol_quick_analysis",
        [
            _tr(
                "get_symbol_quick_analysis",
                {
                    "symbol": "GABRIEL",
                    "company_name": "Gabriel India Ltd",
                    "as_of": "2026-06-04",
                    "price": 910.0,
                    "chg_pct": 5.2,
                    "stage": "STAGE_2",
                    "trading_signal": "BUY",
                    "technical_score": 78,
                    "rsi": 62,
                    "relative_strength": 44.5,
                    "sector": "Auto Ancillaries",
                    "support": 865.0,
                    "resistance": 925.0,
                    "stop_loss": 842.0,
                    "volume_ratio": 2.1,
                    "fundamental_score": 72,
                    "fno": {"available": False},
                    "verdict": "Constructive Stage 2 setup.",
                    "source_trail": {"get_symbol_quick_analysis": "ok"},
                },
            )
        ],
    )

    for section in (
        "GABRIEL - QUICK STOCK ANALYSIS",
        "▶ CURRENT READ",
        "▶ INTERPRETATION",
        "▶ LEVELS",
        "▶ VOLUME",
        "▶ FUNDAMENTALS",
        "▶ VERDICT",
    ):
        assert section in out
    assert "Market Overview" not in out


def test_agent_bare_symbol_executes_quick_analysis_not_market_overview():
    agent = Agent()
    agent.backend = object()

    with patch("terminal.agent._execute_plan") as execute_plan:
        execute_plan.return_value = [
            _tr("resolve_symbol", {"symbol": "GABRIEL"}),
            _tr(
                "get_symbol_quick_analysis",
                {
                    "symbol": "GABRIEL",
                    "price": 900,
                    "stage": "STAGE_2",
                    "trading_signal": "BUY",
                    "verdict": "Constructive Stage 2 setup.",
                },
            ),
        ]
        result = agent.query("GABRIEL")

    planned = execute_plan.call_args.args[0]
    assert [name for name, _args in planned] == ["resolve_symbol", "get_symbol_quick_analysis"]
    assert result["intent"] == "symbol_quick_analysis"
    assert "Market Overview" not in result["answer"]
    assert "GABRIEL" in result["answer"]
