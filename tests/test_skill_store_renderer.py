from __future__ import annotations

from rich.console import Console

from terminal.skills.runtime_assessment import SkillStoreRuntimeAssessment


def _render_to_text(assessment, *, expanded: bool = False) -> str:
    from terminal.renderers.skill_store import render_skill_store_trace

    console = Console(record=True, width=120)
    render_skill_store_trace(console, assessment, expanded=expanded)
    return console.export_text()


def _selected_assessment(**overrides):
    trace = {
        "retrieved_count": 2,
        "retrieved_candidates": [
            {
                "skill_id": "market_3m_rotation_swing_v1",
                "version": 1,
                "status": "validated",
                "domain": "market_analysis",
                "title": "3M Market Rotation Swing",
                "confidence": 0.86,
                "vector_score": 0.91,
                "tag_score": 0.76,
                "matched_tags": ["market_regime", "swing"],
                "metadata": {
                    "embedding": [0.1, 0.2, 0.3],
                    "output_contract": ["ranked_candidates", "risks"],
                    "available_tables": ["market.index_eod"],
                },
            },
            {
                "skill_id": "vcp_breakouts_with_fundamentals_v1",
                "version": 1,
                "status": "validated",
                "domain": "screening",
                "confidence": 0.61,
                "matched_tags": ["vcp", "breakout"],
            },
        ],
        "reviewer_decision": {
            "decision": "select",
            "selected_skill_id": "market_3m_rotation_swing_v1",
            "selected_version": 1,
            "reason": "selected_reviewable_candidate",
            "findings": ["selected"],
            "confidence": 0.86,
        },
    }
    value = {
        "applies": True,
        "decision": "select",
        "selected_skill_id": "market_3m_rotation_swing_v1",
        "selected_version": 1,
        "confidence": 0.86,
        "plan_preview": (
            "Retrieve skill candidates for: last 3 months market analysis",
            "Rerank candidates using vector, tag, intent, evidence, and output-contract signals.",
            "Review selected candidate and prepare dry-run skill plan for market_3m_rotation_swing_v1.",
        ),
        "trace": trace,
    }
    value.update(overrides)
    return SkillStoreRuntimeAssessment(**value)


def test_renderer_shows_selected_skill_reason_and_evidence_plan():
    text = _render_to_text(_selected_assessment())

    assert "Skill Store Trace" in text
    assert "select" in text
    assert "market_3m_rotation_swing_v1" in text
    assert "v1" in text
    assert "86%" in text
    assert "selected_reviewable_candidate" in text
    assert "Retrieve skill candidates" in text
    assert "market.index_eod" in text
    assert "ranked_candidates" in text


def test_renderer_shows_missing_inputs_for_clarification():
    assessment = SkillStoreRuntimeAssessment(
        applies=True,
        decision="ask_clarification",
        confidence=0.74,
        missing_inputs=("timeframe", "portfolio"),
        clarification_question="What timeframe, portfolio should I use for the skill-store assessment?",
        trace={
            "retrieved_count": 1,
            "reviewer_decision": {
                "decision": "ask_clarification",
                "reason": "candidate_requires_more_input",
                "findings": ["missing_input:timeframe", "missing_input:portfolio"],
                "missing_inputs": ["timeframe", "portfolio"],
            },
        },
    )

    text = _render_to_text(assessment)

    assert "ask_clarification" in text
    assert "timeframe" in text
    assert "portfolio" in text
    assert "candidate_requires_more_input" in text
    assert "What timeframe" in text


def test_renderer_shows_validation_failure_and_missing_evidence_from_dict_payload():
    payload = {
        "applies": True,
        "decision": "reject",
        "confidence": 0.44,
        "trace": {
            "retrieved_count": 1,
            "reviewer_decision": {
                "decision": "reject",
                "reason": "no_reviewable_candidate",
                "findings": [
                    "missing_table:market.index_eod",
                    "candidate_has_validation_errors",
                    "missing_output_contract:ranked_candidates",
                ],
                "confidence": 0.44,
            },
        },
    }

    text = _render_to_text(payload)

    assert "reject" in text
    assert "Validation" in text
    assert "candidate_has_validation_errors" in text
    assert "Missing evidence" in text
    assert "market.index_eod" in text
    assert "Missing outputs" in text
    assert "ranked_candidates" in text


def test_renderer_omits_raw_embeddings_and_private_reasoning():
    text = _render_to_text(_selected_assessment())

    assert "embedding" not in text.lower()
    assert "[0.1" not in text
    assert "chain-of-thought" not in text.lower()
    assert "private reasoning" not in text.lower()
