from datetime import datetime

from terminal.research_council.schemas import CouncilState, CriticFinding, CriticReview
from terminal.research_council.states import critic_review


class PassingCritic:
    name = "passing"

    def review(self, state):
        assert state.decision is not None
        return CriticReview(review_id="passing_run_1_0", critic=self.name, run_id=state.run_id, iteration=0)


class BlockingCritic:
    name = "blocking"

    def review(self, state):
        return CriticReview(
            review_id="blocking_run_1_0",
            critic=self.name,
            run_id=state.run_id,
            iteration=0,
            severity_max="block",
            findings=[
                CriticFinding(
                    finding_id="block_1",
                    severity="block",
                    target={"kind": "decision", "id": "x"},
                    description="blocked",
                    recommendation="fix",
                )
            ],
        )


def _state(flags=None):
    return CouncilState(
        run_id="run_1",
        session_id="s1",
        created_at=datetime(2026, 5, 27, 10, 0),
        mode="market_council",
        stage="critic_review",
        objective="today",
        horizon="swing",
        risk_budget="moderate",
        universe_filter="liquid",
        flags=flags or {},
    )


def test_critic_review_state_runs_parallel_critics_and_persists(monkeypatch):
    saved = []
    monkeypatch.setattr(critic_review, "DEFAULT_CRITICS", (PassingCritic(), BlockingCritic()))
    monkeypatch.setattr(critic_review, "save_critic_reviews", lambda reviews, **_: saved.extend(reviews))

    updated = critic_review.run(_state())

    assert len(updated.critic_reviews) == 1
    assert {review.critic for review in updated.critic_reviews[0]} == {"passing", "blocking"}
    assert len(saved) == 2


def test_critic_review_state_skips_in_dry_run(monkeypatch):
    monkeypatch.setattr(critic_review, "save_critic_reviews", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("called")))

    state = _state(flags={"dry_run": True})

    assert critic_review.run(state) == state


def test_critic_review_state_supplies_provisional_decision_to_critics(monkeypatch):
    saved = []
    monkeypatch.setattr(critic_review, "DEFAULT_CRITICS", (PassingCritic(),))
    monkeypatch.setattr(critic_review, "save_critic_reviews", lambda reviews, **_: saved.extend(reviews))

    state = _state()
    assert state.decision is None

    updated = critic_review.run(state)

    assert updated.decision is None
    assert saved[0].summary == ""
