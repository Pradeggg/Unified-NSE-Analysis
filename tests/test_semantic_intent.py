from terminal.agent import Agent
from terminal.semantic_intent import classify_semantic_intent, validate_semantic_intent


class FakeSemanticBackend:
    def __init__(self, content: str):
        self.content = content
        self.messages = []

    def chat(self, messages, tools=None):
        self.messages.append({"messages": messages, "tools": tools})
        return {
            "content": self.content,
            "tool_calls": [],
            "usage": {},
        }


def test_semantic_intent_classifier_maps_open_swing_query_to_fixed_plan():
    backend = FakeSemanticBackend(
        '{"intent":"market_swing_candidates","confidence":0.91,'
        '"reason":"open-ended swing opportunity request","horizon":"swing","universe":"NIFTY 500"}'
    )

    decision = classify_semantic_intent(
        "find actionable 2-3 week opportunities",
        backend,
        data_mode="historical",
    )

    assert decision is not None
    assert decision.intent == "market_swing_candidates"
    assert list(decision.plan) == [
        ("get_index_snapshot", {"index_name": "NIFTY 50"}),
        ("get_index_snapshot", {"index_name": "NIFTY MIDCAP 100"}),
        ("get_market_breadth", {"index": "NIFTY 500"}),
        ("run_quality_breakout_screener", {"top_n": 15, "mode": "balanced"}),
    ]
    assert backend.messages[0]["tools"] == []


def test_semantic_intent_rejects_low_confidence_and_no_route():
    low = validate_semantic_intent(
        {"intent": "market_swing_candidates", "confidence": 0.40},
        "find trades",
    )
    no_route = validate_semantic_intent(
        {"intent": "no_route", "confidence": 0.95},
        "analyze reliance",
    )

    assert low is None
    assert no_route is None


def test_agent_executes_semantic_intent_before_keyword_symbol_fallback(monkeypatch):
    agent = Agent()
    agent.backend = FakeSemanticBackend(
        '{"intent":"market_swing_candidates","confidence":0.94,'
        '"reason":"swing opportunity request","horizon":"swing","universe":"NIFTY 500"}'
    )
    agent.backend_name = "FakeSemantic"

    executed_plan = []

    def fake_execute_plan(plan):
        executed_plan.extend(plan)
        return [
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
                "args": {"index": "NIFTY 500"},
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
                    "source_counts": {
                        "new_highs": 20,
                        "momentum_52w": 15,
                        "tight_range": 8,
                        "breakouts": 5,
                    },
                    "merged_count": 35,
                    "passed_count": 1,
                    "count": 1,
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

    monkeypatch.setattr("terminal.agent._execute_plan", fake_execute_plan)

    result = agent.query("find actionable 2-3 week opportunities")

    assert result["intent"] == "market_swing_candidates"
    assert any(trace.get("step") == "semantic_intent" for trace in result["trace"])
    assert executed_plan[0] == ("get_index_snapshot", {"index_name": "NIFTY 50"})
    assert ("get_market_breadth", {"index": "NIFTY 500"}) in executed_plan
    assert ("resolve_symbol", {"query": "opportunities"}) not in executed_plan
    assert "MARKET + SWING CANDIDATES" in result["answer"]
    assert "NSE:AAA" in result["answer"]
