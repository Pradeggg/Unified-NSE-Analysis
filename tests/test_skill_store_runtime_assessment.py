from __future__ import annotations


def _candidate(skill_id: str, **overrides):
    value = {
        "skill_id": skill_id,
        "version": 1,
        "status": "validated",
        "domain": "market_analysis",
        "title": "3M Market Rotation Swing",
        "score": 0.82,
        "confidence": 0.82,
        "vector_score": 0.0,
        "tag_score": 1.0,
        "intent_score": 0.8,
        "evidence_score": 1.0,
        "output_contract_score": 1.0,
        "matched_tags": ["market_regime", "swing", "3m"],
        "metadata": {
            "tags": ["market_regime", "swing", "3m"],
            "available_tables": ["market.index_eod", "scores.stage_snapshots"],
            "output_contract": ["ranked_candidates", "risks"],
            "validation_rules": ["required_tables_exist"],
        },
    }
    metadata = dict(value["metadata"])
    metadata.update(overrides.pop("metadata", {}) or {})
    value.update(overrides)
    value["metadata"] = metadata
    return value


class FakeRepo:
    def __init__(self):
        self.calls = []

    def list_runtime_eligible(self, domain=None):
        self.calls.append(("list_runtime_eligible", domain))
        return [
            {
                "id": "market_3m_rotation_swing_v1",
                "version": 1,
                "status": "validated",
                "domain": "market_analysis",
                "title": "3M Market Rotation Swing",
                "tags": ["market_regime", "sector_rotation", "swing", "last_3_months"],
                "input_patterns": ["last 3 months market analysis and swing candidates"],
                "metadata": {"intent_score": 0.8, "output_contract": ["ranked_candidates", "risks"]},
            }
        ]

    def log_retrieval(self, event):
        self.calls.append(("log_retrieval", event))
        return 101


def test_runtime_assessment_skips_when_feature_flag_disabled(monkeypatch):
    from terminal.skills.runtime_assessment import stage_skill_store_assessment

    repo = FakeRepo()
    monkeypatch.setenv("AGENT_ADDA_SKILL_STORE", "0")

    result = stage_skill_store_assessment(
        "last 3 months market analysis and swing candidates",
        repo=repo,
    )

    assert result is None
    assert repo.calls == []


def test_runtime_assessment_does_not_intercept_slash_command(monkeypatch):
    from terminal.skills.runtime_assessment import stage_skill_store_assessment

    repo = FakeRepo()
    monkeypatch.setenv("AGENT_ADDA_SKILL_STORE", "1")

    result = stage_skill_store_assessment("/screen stage2", repo=repo)

    assert result is None
    assert repo.calls == []


def test_runtime_assessment_selects_market_skill_when_enabled(monkeypatch):
    from terminal.skills.runtime_assessment import stage_skill_store_assessment

    monkeypatch.setenv("AGENT_ADDA_SKILL_STORE", "1")

    result = stage_skill_store_assessment(
        "last 3 months market analysis and swing candidates",
        repo=FakeRepo(),
    )

    assert result is not None
    assert result.decision == "select"
    assert result.selected_skill_id == "market_3m_rotation_swing_v1"
    assert result.confidence > 0
    assert result.trace["feature_flag_enabled"] is True
    assert result.trace["retrieved_count"] >= 1
    assert result.to_dict()["selected_skill_id"] == "market_3m_rotation_swing_v1"


def test_runtime_assessment_returns_none_when_reviewer_rejects(monkeypatch):
    from terminal.skills.runtime_assessment import stage_skill_store_assessment

    monkeypatch.setenv("AGENT_ADDA_SKILL_STORE", "1")

    result = stage_skill_store_assessment(
        "latest quarterly results analysis",
        repo=FakeRepo(),
        reviewer_fn=lambda query, ranked, **kwargs: _review_decision("reject", findings=("candidate_does_not_answer_query",)),
    )

    assert result is None


def test_runtime_assessment_returns_clarification_when_reviewer_asks(monkeypatch):
    from terminal.skills.runtime_assessment import stage_skill_store_assessment

    monkeypatch.setenv("AGENT_ADDA_SKILL_STORE", "1")

    result = stage_skill_store_assessment(
        "find swing candidates",
        repo=FakeRepo(),
        reviewer_fn=lambda query, ranked, **kwargs: _review_decision(
            "ask_clarification",
            missing_inputs=("timeframe",),
            reason="candidate_requires_more_input",
        ),
    )

    assert result is not None
    assert result.decision == "ask_clarification"
    assert result.missing_inputs == ("timeframe",)
    assert "timeframe" in result.clarification_question.lower()


def test_runtime_assessment_returns_plan_preview_in_plan_mode(monkeypatch):
    from terminal.skills.runtime_assessment import stage_skill_store_assessment

    monkeypatch.setenv("AGENT_ADDA_SKILL_STORE", "1")

    result = stage_skill_store_assessment(
        "last 3 months market analysis and swing candidates",
        repo=FakeRepo(),
        plan_mode=True,
    )

    assert result is not None
    assert result.plan_preview
    assert "Retrieve skill candidates" in result.plan_preview[0]
    assert "market_3m_rotation_swing_v1" in result.plan_preview[-1]


def test_agent_wrapper_delegates_to_runtime_assessment(monkeypatch):
    import terminal.agent as agent_mod

    monkeypatch.setenv("AGENT_ADDA_SKILL_STORE", "1")
    called = {}

    def fake_stage(query, **kwargs):
        called["query"] = query
        return "assessment"

    monkeypatch.setattr(agent_mod, "stage_skill_store_assessment", fake_stage)

    assert agent_mod._stage_skill_store_assessment("market swing") == "assessment"
    assert called == {"query": "market swing"}


def _review_decision(decision: str, **overrides):
    from terminal.skills.reviewer import ReviewDecision

    value = {
        "decision": decision,
        "selected_skill_id": "market_3m_rotation_swing_v1" if decision == "select" else None,
        "selected_version": 1 if decision == "select" else None,
        "candidate_ids": ("market_3m_rotation_swing_v1",),
        "reason": decision,
        "confidence": 0.8,
    }
    value.update(overrides)
    return ReviewDecision(**value)
