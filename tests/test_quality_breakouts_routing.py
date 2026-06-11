from terminal.agent import _keyword_intent
from terminal.renderers import render
from terminal.router import ContextPack, UnifiedRouter


def test_unified_router_routes_quality_breakout_language_to_composite_tool():
    decision = UnifiedRouter().route(
        "stocks creating new highs or VCP or breakouts with good fundamentals",
        ContextPack(session_id="quality-breakouts-test"),
    )

    assert decision.route_type == "direct_tool_plan"
    assert decision.intent == "quality_breakouts"
    assert decision.reasoning_summary.selected_branch == "MarketSituationProvider"
    assert decision.tool_plan_tuples() == [
        ("run_quality_breakout_screener", {"top_n": 15, "mode": "balanced"})
    ]


def test_quality_breakouts_natural_language_routes_to_composite_tool():
    routed = _keyword_intent(
        "stocks creating new highs or VCP or breakouts with good fundamentals",
        data_mode="historical",
    )

    assert routed["intent"] == "quality_breakouts"
    assert routed["plan"] == [("run_quality_breakout_screener", {"top_n": 15, "mode": "balanced"})]


def test_single_stock_breakout_still_routes_to_breakout_screener_or_stock_path():
    routed = _keyword_intent("RELIANCE breakout", data_mode="historical")

    assert routed["intent"] != "quality_breakouts"


def test_quality_breakouts_renderer_shows_tv_symbols():
    text = render(
        "quality_breakouts",
        [
            {
                "tool": "run_quality_breakout_screener",
                "result": {
                    "snapshot_date": "2026-06-03",
                    "mode": "balanced",
                    "source_counts": {"new_highs": 1, "momentum_52w": 0, "tight_range": 0, "breakouts": 1},
                    "merged_count": 1,
                    "passed_count": 1,
                    "tradingview_symbols": ["NSE:AAA"],
                    "results": [
                        {
                            "symbol": "AAA",
                            "price": 100,
                            "stage": "STAGE_2",
                            "trading_signal": "BUY",
                            "rs": 90,
                            "rsi": 64,
                            "enhanced_fund_score": 88,
                            "investment_score": 68,
                            "composite_score": 91,
                            "sector": "Capital Goods",
                            "setup_tags": ["breakout", "new_high"],
                            "reason_tags": ["Breakout", "Stage 2"],
                            "risk_flags": [],
                        }
                    ],
                },
            }
        ],
    )

    assert "QUALITY BREAKOUTS" in text
    assert "AAA" in text
    assert "NSE:AAA" in text
