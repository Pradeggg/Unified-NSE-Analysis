from datetime import datetime

from terminal.research_council.schemas import CouncilState, CriticFinding, CriticReview, RevisionResult
from terminal.research_council.states import revision


def _block_review():
    return CriticReview(
        review_id="risk_run_1_0",
        critic="risk",
        run_id="run_1",
        iteration=0,
        severity_max="block",
        findings=[
            CriticFinding(
                finding_id="risk_1",
                severity="block",
                target={"kind": "candidate", "id": "AAA"},
                description="blocked",
                recommendation="fix",
            )
        ],
    )


def _state(**overrides):
    base = {
        "run_id": "run_1",
        "session_id": "s1",
        "created_at": datetime(2026, 5, 27, 10, 0),
        "mode": "market_council",
        "stage": "revision",
        "objective": "today",
        "horizon": "swing",
        "risk_budget": "moderate",
        "universe_filter": "liquid",
    }
    base.update(overrides)
    return CouncilState(**base)


def test_revision_converges_in_one_round_without_blocks_or_new_hypothesis():
    state = _state(
        flags={"max_confidence_shift": 0.02},
        critic_reviews=[[CriticReview(review_id="risk_run_1_0", critic="risk", run_id="run_1", iteration=0)]],
    )

    updated = revision.run(state)

    assert updated.revision_history[-1].converged is True
    assert updated.revision_history[-1].unresolved_blocks == []
    assert updated.flags["converged"] is True


def test_revision_cap_hit_with_blocks_escalates_manual_review():
    state = _state(
        flags={"revision_cap": 1},
        critic_reviews=[[_block_review()]],
        revision_history=[RevisionResult(iteration=0, converged=False)],
    )

    updated = revision.run(state)

    assert updated.revision_history[-1].converged is False
    assert updated.flags["revision_cap_hit"] is True
    assert updated.flags["requires_manual_review"] is True
    assert updated.flags["decision_pressure"] == "downgrade"


def test_revision_cap_hit_without_blocks_converges_with_note():
    state = _state(
        flags={"revision_cap": 1},
        critic_reviews=[[CriticReview(review_id="risk_run_1_0", critic="risk", run_id="run_1", iteration=0)]],
        revision_history=[RevisionResult(iteration=0, converged=False)],
    )

    updated = revision.run(state)

    assert updated.revision_history[-1].converged is True
    assert updated.flags["revision_cap_hit"] is True
    assert "cap reached without unresolved blocks" in updated.revision_history[-1].notes


def test_revision_does_not_converge_when_new_hypothesis_introduced():
    state = _state(
        flags={"new_testable_hypothesis": "breakout confirmation"},
        critic_reviews=[[CriticReview(review_id="risk_run_1_0", critic="risk", run_id="run_1", iteration=0)]],
    )

    updated = revision.run(state)

    assert updated.revision_history[-1].converged is False
    assert updated.flags["new_testable_hypothesis"] == "breakout confirmation"


def test_revision_treats_resolved_blocks_as_converged():
    state = _state(
        flags={"resolved_critic_blocks": ["risk_1"], "max_confidence_shift": 0.01},
        critic_reviews=[[_block_review()]],
    )

    updated = revision.run(state)

    assert updated.revision_history[-1].converged is True
    assert updated.revision_history[-1].unresolved_blocks == []
