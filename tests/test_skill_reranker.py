from __future__ import annotations


def _candidate(skill_id, **overrides):
    value = {
        "skill_id": skill_id,
        "version": 1,
        "status": "validated",
        "domain": "screening",
        "title": skill_id,
        "vector_score": 0.0,
        "tag_score": 0.0,
        "matched_tags": [],
        "metadata": {},
    }
    value.update(overrides)
    return value


def test_strong_tag_and_intent_match_can_outrank_weak_vector_match():
    from terminal.skills.reranker import rerank_skill_candidates

    result = rerank_skill_candidates(
        [
            _candidate("weak_vector", vector_score=0.68, tag_score=0.0, metadata={"intent_score": 0.0}),
            _candidate(
                "strong_intent",
                vector_score=0.32,
                tag_score=1.0,
                matched_tags=["breakout", "stage 2"],
                metadata={
                    "intent_score": 1.0,
                    "evidence_available": True,
                    "output_contract": ["ranked_candidates"],
                    "runtime_success_rate": 0.8,
                },
            ),
        ],
        required_output_contract=["ranked_candidates"],
    )

    assert result.abstain is False
    assert result.selected is not None
    assert result.selected.skill_id == "strong_intent"
    assert result.selected.score > result.candidates[1].score


def test_low_confidence_candidate_set_abstains():
    from terminal.skills.reranker import rerank_skill_candidates

    result = rerank_skill_candidates(
        [
            _candidate("vague", vector_score=0.05, tag_score=0.05, metadata={"intent_score": 0.05}),
        ],
        abstain_threshold=0.35,
    )

    assert result.abstain is True
    assert result.reason == "low_confidence"
    assert result.selected is None


def test_default_threshold_selects_relevant_tag_only_candidate():
    from terminal.skills.reranker import rerank_skill_candidates

    result = rerank_skill_candidates(
        [
            _candidate("stage2_breakout", vector_score=0.0, tag_score=0.5, metadata={"intent_score": 0.5}),
        ]
    )

    assert result.abstain is False
    assert result.selected is not None
    assert result.selected.skill_id == "stage2_breakout"


def test_production_status_gets_modest_boost_not_automatic_win():
    from terminal.skills.reranker import rerank_skill_candidates

    result = rerank_skill_candidates(
        [
            _candidate("production_generic", status="production", vector_score=0.45, tag_score=0.2),
            _candidate("validated_specific", status="validated", vector_score=0.5, tag_score=0.8, metadata={"intent_score": 0.8}),
        ],
        abstain_threshold=0.1,
    )

    assert result.selected is not None
    assert result.selected.skill_id == "validated_specific"
    assert result.candidates[1].skill_id == "production_generic"
    assert 0 < result.candidates[1].status_boost < 0.1


def test_reciprocal_rank_fusion_normalizes_rank_lists():
    from terminal.skills.reranker import reciprocal_rank_fusion

    scores = reciprocal_rank_fusion(
        [
            ["a", "b", "c"],
            ["b", "a", "c"],
        ],
        k=10,
    )

    assert scores["a"] == scores["b"]
    assert scores["a"] > scores["c"]
    assert max(scores.values()) == 1.0


def test_reranker_returns_top_10_by_default():
    from terminal.skills.reranker import rerank_skill_candidates

    candidates = [_candidate(f"skill_{index}", vector_score=0.9 - (index / 100)) for index in range(12)]

    result = rerank_skill_candidates(candidates, abstain_threshold=0.1)

    assert len(result.candidates) == 10
    assert result.selected is not None
    assert result.selected.skill_id == "skill_0"
