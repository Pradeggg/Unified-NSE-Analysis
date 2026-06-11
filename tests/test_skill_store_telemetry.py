from __future__ import annotations

import json


class FakeTelemetryRepo:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.retrieval_events = []
        self.execution_events = []

    def log_retrieval(self, event):
        if self.fail:
            raise RuntimeError("db unavailable")
        self.retrieval_events.append(dict(event))
        return 11

    def log_execution(self, event):
        if self.fail:
            raise RuntimeError("db unavailable")
        self.execution_events.append(dict(event))
        return 22

    def query_logs_by_skill(self, skill_id, *, limit=50):
        if self.fail:
            raise RuntimeError("db unavailable")
        return [
            {"kind": "retrieval", "skill_id": skill_id, "retrieval_id": 11},
            {"kind": "execution", "skill_id": skill_id, "execution_id": 22},
        ][:limit]


def test_retrieval_telemetry_is_json_serializable_and_hashes_query():
    from terminal.skills.telemetry import build_retrieval_event

    event = build_retrieval_event(
        "  Last 3 months MARKET analysis  ",
        candidates=[
            {
                "skill_id": "market_3m_rotation_swing_v1",
                "version": 1,
                "score": 0.87,
                "metadata": {"embedding": [0.1, 0.2], "notes": {"ok"}},
            }
        ],
        reviewer_decision={
            "decision": "select",
            "selected_skill_id": "market_3m_rotation_swing_v1",
            "selected_version": 1,
            "confidence": 0.87,
        },
        elapsed_ms=12,
    )

    json.dumps(event)
    assert len(event["query_hash"]) == 64
    assert event["normalized_query"] == "last 3 months market analysis"
    assert event["selected_skill_id"] == "market_3m_rotation_swing_v1"
    assert "embedding" not in json.dumps(event).lower()
    assert event["candidates"][0]["metadata"]["notes"] == ["ok"]


def test_log_retrieval_swallows_repository_failures():
    from terminal.skills.telemetry import build_retrieval_event, log_retrieval_event

    event = build_retrieval_event(
        "portfolio add trim",
        candidates=[],
        reviewer_decision={"decision": "reject"},
    )

    assert log_retrieval_event(FakeTelemetryRepo(fail=True), event) is None


def test_execution_telemetry_logs_validation_status_and_final_intent():
    from terminal.skills.telemetry import build_execution_event, log_execution_event

    repo = FakeTelemetryRepo()
    event = build_execution_event(
        skill_id="market_3m_rotation_swing_v1",
        skill_version=1,
        steps=[{"name": "index_returns", "status": "passed", "rows": [{"x": 1}]}],
        validation_status="passed",
        validation_findings=[],
        final_intent="skill_store",
        retrieval_id=11,
        elapsed_ms=8,
    )

    execution_id = log_execution_event(repo, event)

    assert execution_id == 22
    assert repo.execution_events[0]["skill_id"] == "market_3m_rotation_swing_v1"
    assert repo.execution_events[0]["validation_status"] == "passed"
    assert repo.execution_events[0]["metadata"]["final_intent"] == "skill_store"
    assert "rows" not in json.dumps(repo.execution_events[0]["steps"]).lower()


def test_query_logs_by_skill_delegates_to_repository_without_raising():
    from terminal.skills.telemetry import query_logs_by_skill

    rows = query_logs_by_skill(FakeTelemetryRepo(), "market_3m_rotation_swing_v1")

    assert [row["kind"] for row in rows] == ["retrieval", "execution"]
    assert query_logs_by_skill(FakeTelemetryRepo(fail=True), "market_3m_rotation_swing_v1") == []


def test_runtime_assessment_logs_reviewer_decision_without_breaking_on_log_failure(monkeypatch):
    from terminal.skills.runtime_assessment import stage_skill_store_assessment

    class Repo(FakeTelemetryRepo):
        def list_runtime_eligible(self, domain=None):
            return [
                {
                    "id": "market_3m_rotation_swing_v1",
                    "version": 1,
                    "status": "validated",
                    "domain": "market_analysis",
                    "title": "Market Rotation",
                    "tags": ["market_regime", "swing", "3m"],
                    "input_patterns": ["last 3 months market analysis"],
                    "metadata": {
                        "intent_score": 0.9,
                        "output_contract": ["ranked_candidates", "risks"],
                    },
                }
            ]

    repo = Repo()
    result = stage_skill_store_assessment(
        "last 3 months market analysis",
        repo=repo,
        feature_enabled=True,
    )

    assert result is not None
    assert repo.retrieval_events
    assert repo.retrieval_events[0]["reviewer_decision"]["decision"] == "select"

    failing_repo = Repo(fail=True)
    result = stage_skill_store_assessment(
        "last 3 months market analysis",
        repo=failing_repo,
        feature_enabled=True,
    )
    assert result is not None
