from __future__ import annotations


class FakeFeedbackRepo:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.feedback_events = []

    def save_feedback(self, event):
        if self.fail:
            raise RuntimeError("db unavailable")
        self.feedback_events.append(dict(event))
        return 31

    def get_feedback_summary(self, skill_id=None):
        if self.fail:
            raise RuntimeError("db unavailable")
        rows = {
            "useful_skill_v1": {
                "skill_id": "useful_skill_v1",
                "total": 10,
                "positive": 8,
                "negative": 2,
                "runtime_success_rate": 0.8,
            },
            "weak_skill_v1": {
                "skill_id": "weak_skill_v1",
                "total": 10,
                "positive": 2,
                "negative": 8,
                "runtime_success_rate": 0.2,
            },
        }
        if skill_id:
            return [rows[skill_id]] if skill_id in rows else []
        return list(rows.values())


def test_capture_skill_feedback_persists_supported_feedback_types():
    from terminal.skills.feedback import capture_skill_feedback

    repo = FakeFeedbackRepo()

    result = capture_skill_feedback(
        repository=repo,
        skill_id="market_3m_rotation_swing_v1",
        skill_version=1,
        feedback_type="useful",
        retrieval_id=11,
        execution_id=22,
        reason="grounded and actionable",
        created_by="tester",
        payload={"screen": "trace"},
    )

    assert result.ok is True
    assert result.feedback_id == 31
    assert repo.feedback_events[0]["feedback_type"] == "useful"
    assert repo.feedback_events[0]["feedback_payload"]["sentiment"] == "positive"
    assert repo.feedback_events[0]["feedback_payload"]["reason"] == "grounded and actionable"
    assert repo.feedback_events[0]["retrieval_id"] == 11
    assert repo.feedback_events[0]["execution_id"] == 22


def test_capture_skill_feedback_rejects_unknown_feedback_type_without_persisting():
    from terminal.skills.feedback import capture_skill_feedback

    repo = FakeFeedbackRepo()

    result = capture_skill_feedback(
        repository=repo,
        skill_id="market_3m_rotation_swing_v1",
        feedback_type="amazing",
    )

    assert result.ok is False
    assert "unsupported feedback type" in result.message
    assert repo.feedback_events == []


def test_capture_skill_feedback_failure_does_not_break_response():
    from terminal.skills.feedback import capture_skill_feedback

    result = capture_skill_feedback(
        repository=FakeFeedbackRepo(fail=True),
        skill_id="market_3m_rotation_swing_v1",
        feedback_type="missing_evidence",
    )

    assert result.ok is False
    assert "db unavailable" in result.message


def test_feedback_summary_returns_safe_aggregate_rates():
    from terminal.skills.feedback import get_skill_feedback_summary

    summary = get_skill_feedback_summary(FakeFeedbackRepo(), "useful_skill_v1")

    assert summary["skill_id"] == "useful_skill_v1"
    assert summary["runtime_success_rate"] == 0.8
    assert get_skill_feedback_summary(FakeFeedbackRepo(fail=True), "useful_skill_v1") == {}


def test_apply_feedback_to_candidates_updates_metadata_for_reranker():
    from terminal.skills.feedback import apply_feedback_to_candidates
    from terminal.skills.reranker import rerank_skill_candidates

    candidates = [
        {
            "skill_id": "useful_skill_v1",
            "version": 1,
            "status": "validated",
            "domain": "screening",
            "vector_score": 0.5,
            "tag_score": 0.8,
            "metadata": {"intent_score": 0.7},
        },
        {
            "skill_id": "weak_skill_v1",
            "version": 1,
            "status": "validated",
            "domain": "screening",
            "vector_score": 0.5,
            "tag_score": 0.8,
            "metadata": {"intent_score": 0.7},
        },
    ]

    enriched = apply_feedback_to_candidates(candidates, FakeFeedbackRepo())
    result = rerank_skill_candidates(enriched, abstain_threshold=0.1)

    assert enriched[0]["metadata"]["runtime_success_rate"] == 0.8
    assert enriched[1]["metadata"]["runtime_success_rate"] == 0.2
    assert result.candidates[0].skill_id == "useful_skill_v1"


def test_supported_feedback_types_cover_backlog_categories():
    from terminal.skills.feedback import SUPPORTED_FEEDBACK_TYPES

    assert {
        "useful",
        "not_useful",
        "wrong_skill",
        "stale_data",
        "missing_evidence",
    }.issubset(SUPPORTED_FEEDBACK_TYPES)
