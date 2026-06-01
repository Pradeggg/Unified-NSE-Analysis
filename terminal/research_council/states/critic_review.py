"""Run deterministic Research Council critics."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace

from terminal.research_council.agents.hedge_fund_owner import DEFAULT_CHAIR
from terminal.research_council.critics.data_quality import DataQualityCritic
from terminal.research_council.critics.evidence import EvidenceCritic
from terminal.research_council.critics.leakage import LeakageCritic
from terminal.research_council.critics.overfit import OverfitCritic
from terminal.research_council.critics.risk import RiskCritic
from terminal.research_council.mode_profiles import load_mode_profile
from terminal.research_council.persistence import save_critic_reviews

DEFAULT_CRITICS = (
    DataQualityCritic(),
    LeakageCritic(),
    OverfitCritic(),
    RiskCritic(),
    EvidenceCritic(),
)


def run(state):
    if state.flags.get("dry_run"):
        return state
    reviews = []
    failures = []
    critics = _critics_for_mode(state.mode)
    review_state = _state_with_review_decision(state)
    with ThreadPoolExecutor(max_workers=len(critics) or 1) as pool:
        future_to_critic = {pool.submit(critic.review, review_state): critic for critic in critics}
        for future in as_completed(future_to_critic):
            critic = future_to_critic[future]
            try:
                reviews.append(future.result())
            except Exception as exc:
                failures.append({"critic": getattr(critic, "name", "unknown"), "error": str(exc)})
    reviews = sorted(reviews, key=lambda review: review.critic)
    if reviews:
        save_critic_reviews(reviews)
    flags = dict(state.flags)
    if failures:
        flags["critic_failures"] = failures
    return replace(state, flags=flags, critic_reviews=[*state.critic_reviews, reviews])


def _state_with_review_decision(state):
    if getattr(state, "decision", None) is not None:
        return state
    return replace(state, decision=DEFAULT_CHAIR.synthesize_decision(state))


def _critics_for_mode(mode: str):
    profile = load_mode_profile(mode)
    critic_by_name = {critic.name: critic for critic in DEFAULT_CRITICS}
    selected = [critic_by_name[name] for name in profile.critics if name in critic_by_name]
    return tuple(selected) or DEFAULT_CRITICS
