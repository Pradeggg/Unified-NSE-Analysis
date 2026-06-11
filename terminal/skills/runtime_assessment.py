from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from terminal.skills.config import skill_store_enabled
from terminal.skills.reranker import rerank_skill_candidates
from terminal.skills.retriever import retrieve_skill_candidates
from terminal.skills.reviewer import ReviewDecision, review_skill_candidates
from terminal.skills.telemetry import build_retrieval_event, log_retrieval_event


RetrieverFn = Callable[..., Any]
RerankerFn = Callable[..., Any]
ReviewerFn = Callable[..., ReviewDecision]


@dataclass(frozen=True)
class SkillStoreRuntimeAssessment:
    applies: bool
    decision: str
    selected_skill_id: str | None = None
    selected_version: int | None = None
    confidence: float = 0.0
    missing_inputs: tuple[str, ...] = ()
    clarification_question: str = ""
    plan_preview: tuple[str, ...] = ()
    trace: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "missing_inputs", tuple(str(item) for item in self.missing_inputs))
        object.__setattr__(self, "plan_preview", tuple(str(item) for item in self.plan_preview))
        object.__setattr__(self, "trace", dict(self.trace or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "applies": self.applies,
            "decision": self.decision,
            "selected_skill_id": self.selected_skill_id,
            "selected_version": self.selected_version,
            "confidence": self.confidence,
            "missing_inputs": list(self.missing_inputs),
            "clarification_question": self.clarification_question,
            "plan_preview": list(self.plan_preview),
            "trace": dict(self.trace),
        }


def stage_skill_store_assessment(
    user_input: str,
    *,
    repo: Any | None = None,
    embedding_provider: Any | None = None,
    feature_enabled: bool | None = None,
    unified_router_result: Any | None = None,
    deterministic_intent: str | None = None,
    deterministic_confidence: float = 0.0,
    plan_mode: bool = False,
    retriever_fn: RetrieverFn = retrieve_skill_candidates,
    reranker_fn: RerankerFn = rerank_skill_candidates,
    reviewer_fn: ReviewerFn = review_skill_candidates,
) -> SkillStoreRuntimeAssessment | None:
    query = (user_input or "").strip()
    if not query:
        return None
    if not skill_store_enabled(enabled=feature_enabled):
        return None
    if query.startswith("/"):
        return None
    if _router_already_handled(unified_router_result):
        return None
    if deterministic_intent and deterministic_confidence >= 0.90:
        return None

    candidates = retriever_fn(
        query,
        repo=repo,
        embedding_provider=embedding_provider,
        log_event=False,
    )
    if not candidates:
        return None
    reranked = reranker_fn(candidates)
    decision = reviewer_fn(
        query,
        reranked,
        deterministic_intent=deterministic_intent,
        deterministic_confidence=deterministic_confidence,
    )
    trace = _trace(query, candidates, reranked, decision)
    retrieval_id = log_retrieval_event(
        repo,
        build_retrieval_event(
            query,
            candidates=candidates,
            reviewer_decision=decision,
            metadata={"stage": "runtime_assessment"},
        ),
    )
    if retrieval_id is not None:
        trace["retrieval_id"] = retrieval_id
    if decision.decision == "select":
        return SkillStoreRuntimeAssessment(
            applies=True,
            decision="select",
            selected_skill_id=decision.selected_skill_id,
            selected_version=decision.selected_version,
            confidence=decision.confidence,
            plan_preview=_plan_preview(query, decision) if plan_mode else (),
            trace=trace,
        )
    if decision.decision == "merge":
        return SkillStoreRuntimeAssessment(
            applies=True,
            decision="merge",
            selected_skill_id=None,
            selected_version=None,
            confidence=decision.confidence,
            plan_preview=_plan_preview(query, decision) if plan_mode else (),
            trace=trace,
        )
    if decision.decision == "ask_clarification":
        return SkillStoreRuntimeAssessment(
            applies=True,
            decision="ask_clarification",
            confidence=decision.confidence,
            missing_inputs=decision.missing_inputs,
            clarification_question=_clarification_question(decision.missing_inputs),
            plan_preview=_plan_preview(query, decision) if plan_mode else (),
            trace=trace,
        )
    return None


def _router_already_handled(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, Mapping):
        intent = str(value.get("intent") or value.get("decision") or "")
        return bool(intent and intent not in {"fallback", "fallback_llm", "unknown"})
    intent = str(getattr(value, "intent", "") or getattr(value, "decision", ""))
    return bool(intent and intent not in {"fallback", "fallback_llm", "unknown"})


def _trace(query: str, candidates: Any, reranked: Any, decision: ReviewDecision) -> dict[str, Any]:
    candidate_list = [item.to_dict() if hasattr(item, "to_dict") else dict(item) for item in list(candidates or [])]
    rerank_payload = reranked.to_dict() if hasattr(reranked, "to_dict") else {}
    return {
        "feature_flag_enabled": True,
        "query": query,
        "retrieved_count": len(candidate_list),
        "retrieved_candidates": candidate_list[:10],
        "rerank": rerank_payload,
        "reviewer_decision": decision.to_dict(),
    }


def _clarification_question(missing_inputs: tuple[str, ...]) -> str:
    if not missing_inputs:
        return "What extra input should I use for the skill-store assessment?"
    joined = ", ".join(missing_inputs)
    return f"What {joined} should I use for the skill-store assessment?"


def _plan_preview(query: str, decision: ReviewDecision) -> tuple[str, ...]:
    selected = decision.selected_skill_id or ", ".join(decision.candidate_ids) or "reviewer-selected skill"
    return (
        f"Retrieve skill candidates for: {query}",
        "Rerank candidates using vector, tag, intent, evidence, and output-contract signals.",
        f"Review selected candidate and prepare dry-run skill plan for {selected}.",
    )
