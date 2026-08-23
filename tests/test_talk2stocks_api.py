from __future__ import annotations

import sys
import types

from fastapi.testclient import TestClient

from agent_adda.web_api.main import app
from agent_adda.web_api.routes.talk import _SESSION_MEMORY, _is_local_symbol, _llm_synthesis
from agent_adda.web_api.schemas import TalkEvidenceItem


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
