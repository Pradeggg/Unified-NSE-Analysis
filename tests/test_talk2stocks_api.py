from __future__ import annotations

import sys
import types

import pytest
from fastapi.testclient import TestClient

from agent_adda.web_api.main import app
from agent_adda.web_api.routes.talk import (
    _SESSION_MEMORY,
    _fallback_answer,
    _is_local_symbol,
    _llm_synthesis,
    _resolve_query_symbols,
    _resolve_query_symbols_with_gaps,
)
from agent_adda.web_api.schemas import TalkEvidenceItem


@pytest.fixture(autouse=True)
def _disable_agent_bridge_for_talk_unit_tests(monkeypatch):
    monkeypatch.setenv("T2S_USE_AGENT_BRIDGE", "0")


def test_talk_defaults_route():
    client = TestClient(app)
    res = client.get("/api/talk/defaults")
    assert res.status_code == 200
    body = res.json()
    assert body["brand"] == "Agent Adda"
    assert body["product"] == "Talk 2 Stocks"
    assert body["router_model"] == "gpt-5-nano"
    assert body["default_model"] == "gpt-4o-mini"
    assert body["synthesis_policy"] == "llm_preferred"


def test_talk_market_context_route_returns_evidence(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = TestClient(app)
    res = client.post(
        "/api/talk/chat",
        json={"question": "What sectors are strong today?", "mode": "permissive"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["intent"] == "market_context"
    assert body["market_context"]
    assert body["evidence"]
    assert body["model_route"]["router"] == "gpt-5-nano"
    assert body["model_route"]["synthesis_policy"] == "llm_preferred"
    assert body["model_route"]["synthesis_status"] in {"succeeded", "missing_api_key", "failed"}


def test_talk_local_symbol_fallback_knows_large_it_symbols():
    assert _is_local_symbol("INFY")
    assert _is_local_symbol("HCLTECH")


def test_talk_llm_synthesis_uses_openai_when_configured(monkeypatch):
    class _Usage:
        prompt_tokens = 123
        completion_tokens = 45

    class _Message:
        content = "LLM synthesized answer"

    class _Choice:
        message = _Message()

    class _Response:
        choices = [_Choice()]
        usage = _Usage()

    class _Completions:
        def create(self, **kwargs):
            assert kwargs["model"] == "gpt-4o-mini"
            assert kwargs["max_tokens"] == 700
            assert "Evidence:" in kwargs["messages"][0]["content"]
            assert "Only call something an evidence gap if it appears in the Gaps block." in kwargs["messages"][0]["content"]
            assert "Structured gaps present: no." in kwargs["messages"][0]["content"]
            return _Response()

    class _OpenAI:
        def __init__(self, api_key: str):
            assert api_key == "test-key"
            self.chat = types.SimpleNamespace(completions=_Completions())

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("TALK2STOCKS_LLM_SYNTHESIS", "1")
    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=_OpenAI))

    answer, model, in_tok, out_tok, cost, status, error = _llm_synthesis(
        "Analyze TCS",
        "Deterministic fallback",
        [TalkEvidenceItem(label="TCS snapshot", source="get_symbol_snapshot", value={"price": 100})],
        [],
    )

    assert answer == "LLM synthesized answer"
    assert model == "gpt-4o-mini"
    assert in_tok == 123
    assert out_tok == 45
    assert cost > 0
    assert status == "succeeded"
    assert error == ""


def test_talk_multiturn_binds_pronoun_to_previous_symbol(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _SESSION_MEMORY.pop("test-pronoun-session", None)
    client = TestClient(app)

    first = client.post(
        "/api/talk/chat",
        json={
            "session_id": "test-pronoun-session",
            "question": "Analyze TCS briefly",
            "watchlist": ["TCS", "INFY"],
            "mode": "permissive",
        },
    )
    assert first.status_code == 200
    assert first.json()["symbols"] == ["TCS"]

    second = client.post(
        "/api/talk/chat",
        json={
            "session_id": "test-pronoun-session",
            "question": "Compare it with INFY",
            "watchlist": ["TCS", "INFY"],
            "mode": "permissive",
        },
    )
    assert second.status_code == 200
    body = second.json()
    assert body["intent"] == "compare"
    assert body["symbols"] == ["TCS", "INFY"]
    assert len(body["comparison"]) == 2


def test_talk_multiturn_evidence_review_uses_previous_context(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _SESSION_MEMORY.pop("test-evidence-session", None)
    client = TestClient(app)

    first = client.post(
        "/api/talk/chat",
        json={
            "session_id": "test-evidence-session",
            "question": "Analyze TCS briefly",
            "watchlist": ["TCS", "INFY"],
            "mode": "permissive",
        },
    )
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["evidence"]

    second = client.post(
        "/api/talk/chat",
        json={
            "session_id": "test-evidence-session",
            "question": "What are the key gaps in the evidence?",
            "watchlist": ["TCS", "INFY"],
            "mode": "permissive",
        },
    )
    assert second.status_code == 200
    body = second.json()
    assert body["intent"] == "evidence_review"
    assert body["symbols"] == ["TCS"]
    assert body["evidence"]
    assert "No symbol or market object" not in body["answer"]


def test_talk_stock_response_exposes_fundamental_and_technical_assessments(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = TestClient(app)

    res = client.post(
        "/api/talk/chat",
        json={
            "question": "Give me fundamental and technical information on TCS",
            "watchlist": ["TCS"],
            "mode": "permissive",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["intent"] == "financials_review"
    row = body["comparison"][0]
    assert "technical_score" in row
    assert row["technical_assessment"]
    assert "investment_score" in row
    assert "enhanced_fund_score" in row
    assert row["fundamental_assessment"]
    assert (
        any(item["source"] == "get_cached_financials" for item in body["evidence"])
        or any("financial" in gap.lower() for gap in body["gaps"])
    )


def test_talk_financial_fallback_formats_results_as_tables():
    answer = _fallback_answer(
        "financials_review",
        "TRENT latest financial results",
        ["TRENT"],
        [
            {
                "symbol": "TRENT",
                "latest_quarter": "Jun 2026",
                "revenue": 5755,
                "pat": 518,
                "eps": 9.73,
                "opm_pct": 19.0,
                "financial_unit": "INR crore",
                "financial_source": "Screener",
                "financial_source_url": "https://www.screener.in/company/TRENT/consolidated/",
                "latest_annual": {"period_label": "Mar 2026", "revenue": 20074, "pat": 1721, "eps": 32.25, "opm_pct": 19.0},
                "latest_balance_sheet": {"period_label": "Mar 2026", "net_debt": 1176, "borrowings": 2561, "reserves": 6949},
                "latest_cash_flow": {"period_label": "Mar 2026", "operating_cf": 2668, "net_cf": -57},
            }
        ],
        [],
        [],
    )

    assert "**TRENT Latest Financial Results**" in answer
    assert "| Period | Revenue (INR crore) | PAT (INR crore) | EPS | OPM |" in answer
    assert "| Jun 2026 | 5,755 | 518 | 9.73 | 19.0% |" in answer
    assert "| Mar 2026 | 20,074 | 1,721 | 32.25 | 19.0% |" in answer
    assert "| Metric | Value (INR crore) |" in answer
    assert "| Operating cash flow | 2,668 |" in answer
    assert "| Net cash flow | -57 |" in answer
    assert "[Screener](https://www.screener.in/company/TRENT/consolidated/)" in answer


def test_talk_banknifty_routes_as_index_not_stock(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = TestClient(app)

    res = client.post(
        "/api/talk/chat",
        json={
            "question": "Analyze BANKNIFTY",
            "watchlist": ["BANKNIFTY"],
            "mode": "permissive",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["intent"] == "index_context"
    assert body["symbols"] == []
    assert body["market_context"]
    assert any(item["source"] == "get_index_snapshot" for item in body["evidence"])
    assert any(item["source"] == "get_market_breadth" for item in body["evidence"])
    assert not any("price history" in gap.lower() for gap in body["gaps"])


def test_talk_hdfcbank_routes_as_stock_even_with_default_indices(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = TestClient(app)

    res = client.post(
        "/api/talk/chat",
        json={
            "question": "Fundamental and Technical Analysis of HDFCBANK",
            "watchlist": ["NIFTY", "BANKNIFTY", "RELIANCE", "HDFCBANK", "TCS", "INFY", "ICICIBANK", "SBIN"],
            "mode": "permissive",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["intent"] == "financials_review"
    assert body["symbols"] == ["HDFCBANK"]
    assert body["comparison"]
    assert not body["market_context"]
    assert any(item["source"] == "get_symbol_snapshot" for item in body["evidence"])
    assert any(item["source"] == "get_technical_setup" for item in body["evidence"])
    assert not any(item["source"] == "get_index_snapshot" for item in body["evidence"])


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("Analyze Tata Consultancy Services", ["TCS"]),
        ("Analyze Larsen and Toubro", ["LT"]),
        ("Analyze Mahindra and Mahindra", ["M&M"]),
        ("Analyze Bajaj Finance", ["BAJFINANCE"]),
        ("Analyze Hindustan Unilever", ["HINDUNILVR"]),
        ("Analyze Sun Pharma", ["SUNPHARMA"]),
        ("Analyze Asian Paints", ["ASIANPAINT"]),
        ("Analyze Axis Bank", ["AXISBANK"]),
        ("Analyze Kotak Mahindra Bank", ["KOTAKBANK"]),
        ("Analyze Tata Motors", ["TATAMOTORS"]),
        ("Analyze Tata Technologies", ["TATATECH"]),
    ],
)
def test_talk_resolves_multi_word_stock_names_before_tokens(prompt, expected):
    watchlist = ["NIFTY", "BANKNIFTY", "RELIANCE", "HDFCBANK", "TCS", "INFY", "ICICIBANK", "SBIN"]
    assert _resolve_query_symbols(prompt, watchlist) == expected


def test_talk_does_not_silently_resolve_ambiguous_single_token_prefixes():
    symbols, gaps = _resolve_query_symbols_with_gaps("Analyze Tata", [])
    assert symbols == []
    assert any("ambiguous company prefix" in gap for gap in gaps)
    assert not any("ANALYZE" in gap for gap in gaps)


def test_talk_does_not_fall_back_to_token_after_weak_phrase_match():
    symbols, gaps = _resolve_query_symbols_with_gaps("Analyze Titan Company", [])
    assert symbols == []
    assert any("TITAN COMPANY" in gap and "weak/ambiguous" in gap for gap in gaps)


def test_talk_index_partial_score_coverage_is_warning_not_gap(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def fake_index_snapshot(index_name):
        return {
            "index": index_name,
            "as_of": "2026-08-21",
            "close": 57761.95,
            "chg_pct": 0.46,
            "trend_10d": {"chg_pct": 1.2, "up_days": 6},
        }

    def fake_market_breadth(index):
        return {
            "scope": "index",
            "index": index,
            "snapshot_date": "2026-08-21",
            "total_stocks": 11,
            "advances": 8,
            "declines": 3,
            "ad_ratio": 2.67,
            "avg_rs_pct": 52.4,
            "stage_distribution": {"STAGE_2": 5, "STAGE_1": 4, "STAGE_4": 2},
            "composition_count": 12,
            "matched_count": 11,
            "coverage_pct": 91.67,
            "warnings": ["constituent_score_coverage:11/12"],
            "missing_evidence": ["complete_index_score_coverage"],
        }

    monkeypatch.setattr("terminal.tools.get_index_snapshot", fake_index_snapshot)
    monkeypatch.setattr("terminal.tools.get_market_breadth", fake_market_breadth)

    client = TestClient(app)
    res = client.post(
        "/api/talk/chat",
        json={
            "question": "Analyze BANKNIFTY",
            "watchlist": ["BANKNIFTY"],
            "mode": "permissive",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["intent"] == "index_context"
    assert not any("complete_index_score_coverage" in gap for gap in body["gaps"])
    row = body["market_context"][0]
    assert row["matched_count"] == 11
    assert row["composition_count"] == 12
    assert row["coverage_pct"] == 91.67
    assert row["warnings"] == ["constituent_score_coverage:11/12"]


def test_talk_chat_routes_high_rs_screener_without_symbol_noise(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def fake_run_screener_query(screen_type, top_n=10):
        assert screen_type == "high_rs"
        assert top_n == 5
        return {
            "description": "High RS leaders",
            "snapshot_date": "2026-08-21",
            "results": [
                {
                    "symbol": "AAA",
                    "company_name": "AAA Limited",
                    "sector": "Capital Goods",
                    "price": 123.4,
                    "stage": "STAGE_2",
                    "rsi": 61.2,
                    "rs_pct": 88.5,
                    "technical_score": 72,
                    "investment_score": 66,
                    "trading_signal": "BULLISH",
                    "setup_tags": ["high_rs", "stage2"],
                }
            ],
        }

    monkeypatch.setattr("terminal.tools.run_screener_query", fake_run_screener_query)

    client = TestClient(app)
    res = client.post(
        "/api/talk/chat",
        json={"question": "Show top 5 high RS leaders", "mode": "permissive"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["intent"] == "screener"
    assert body["symbols"] == ["AAA"]
    assert body["screener_results"][0]["symbol"] == "AAA"
    assert any(item["source"] == "run_screener_query" for item in body["evidence"])
    assert not any("HIGH" in gap or "LEADERS" in gap for gap in body["gaps"])


def test_talk_screener_endpoint_returns_structured_results(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def fake_run_screener_query(screen_type, top_n=10):
        assert screen_type == "stage2"
        assert top_n == 3
        return {
            "snapshot_date": "2026-08-21",
            "results": [
                {"symbol": "BBB", "company": "BBB Industries", "stage": "STAGE_2", "technical_score": 70}
            ],
        }

    monkeypatch.setattr("terminal.tools.run_screener_query", fake_run_screener_query)

    client = TestClient(app)
    res = client.post(
        "/api/talk/screener",
        json={"screen_type": "stage2", "top_n": 3, "mode": "permissive"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["intent"] == "screener"
    assert body["screener_results"][0]["symbol"] == "BBB"
    assert body["next_actions"][0]["action"] == "compare"


def test_talk_screener_endpoint_reports_unknown_screen_without_rows(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    client = TestClient(app)
    res = client.post(
        "/api/talk/screener",
        json={"screen_type": "unknown_screen", "top_n": 3, "mode": "permissive"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["intent"] == "screener"
    assert body["screener_results"] == []
    assert any("Unknown screener" in gap for gap in body["gaps"])


def test_talk_watchlist_strength_uses_watchlist_symbols(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    captured = {}

    def fake_validate_strength_watchlist(symbols, top_n=20):
        captured["symbols"] = symbols
        captured["top_n"] = top_n
        return {
            "snapshot_date": "2026-08-21",
            "results": [
                {"symbol": "TCS", "company_name": "TCS", "strength_score": 64, "verdict": "VALID"}
            ],
            "input_symbols": symbols,
        }

    monkeypatch.setattr("terminal.tools.validate_strength_watchlist", fake_validate_strength_watchlist)

    client = TestClient(app)
    res = client.post(
        "/api/talk/chat",
        json={
            "question": "Validate my watchlist strength",
            "watchlist": ["NIFTY", "BANKNIFTY", "TCS"],
            "mode": "permissive",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["intent"] == "screener"
    assert captured["symbols"] == ["TCS"]
    assert captured["top_n"] == 10
    assert body["screener_results"][0]["screen_type"] == "watchlist_strength"


def test_talk_intraday_health_gates_live_setups(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def fake_get_intraday_source_health(max_age_minutes=30):
        return {
            "data_mode": "intraday",
            "overall_status": "MISSING",
            "tables": {
                "intraday_bars": {"status": "MISSING", "rows": 0, "latest_ts": None}
            },
        }

    monkeypatch.setattr("terminal.tools.get_intraday_source_health", fake_get_intraday_source_health)

    client = TestClient(app)
    res = client.post(
        "/api/talk/chat",
        json={"question": "Check intraday source health", "mode": "permissive"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["intent"] == "intraday_health"
    assert body["symbols"] == []
    assert body["intraday_context"]["overall_status"] == "MISSING"
    assert any(item["source"] == "get_intraday_source_health" for item in body["evidence"])
    assert any("gated" in gap.lower() for gap in body["gaps"])
    assert not any("CHECK INTRADAY" in gap for gap in body["gaps"])
