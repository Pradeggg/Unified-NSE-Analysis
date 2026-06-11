from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


DEFAULT_TOP_N = 10
DEFAULT_ABSTAIN_THRESHOLD = 0.25
RRF_K = 60


@dataclass(frozen=True)
class RerankedSkillCandidate:
    skill_id: str
    version: int
    status: str
    domain: str
    score: float
    confidence: float
    vector_score: float = 0.0
    tag_score: float = 0.0
    intent_score: float = 0.0
    evidence_score: float = 0.0
    output_contract_score: float = 0.0
    runtime_success_score: float = 0.0
    status_boost: float = 0.0
    rrf_score: float = 0.0
    matched_tags: tuple[str, ...] = ()
    title: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "version": self.version,
            "status": self.status,
            "domain": self.domain,
            "score": round(self.score, 6),
            "confidence": round(self.confidence, 6),
            "vector_score": round(self.vector_score, 6),
            "tag_score": round(self.tag_score, 6),
            "intent_score": round(self.intent_score, 6),
            "evidence_score": round(self.evidence_score, 6),
            "output_contract_score": round(self.output_contract_score, 6),
            "runtime_success_score": round(self.runtime_success_score, 6),
            "status_boost": round(self.status_boost, 6),
            "rrf_score": round(self.rrf_score, 6),
            "matched_tags": list(self.matched_tags),
            "title": self.title,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class SkillRerankResult:
    candidates: tuple[RerankedSkillCandidate, ...]
    abstain: bool
    reason: str = ""

    @property
    def selected(self) -> RerankedSkillCandidate | None:
        return None if self.abstain or not self.candidates else self.candidates[0]

    def to_dict(self) -> dict[str, Any]:
        return {
            "abstain": self.abstain,
            "reason": self.reason,
            "selected": None if self.selected is None else self.selected.to_dict(),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }


def rerank_skill_candidates(
    candidates: Iterable[Any],
    *,
    top_n: int = DEFAULT_TOP_N,
    abstain_threshold: float = DEFAULT_ABSTAIN_THRESHOLD,
    required_output_contract: Iterable[str] | None = None,
    required_evidence: Iterable[str] | None = None,
) -> SkillRerankResult:
    normalized = [_normalize_candidate(candidate) for candidate in candidates]
    if not normalized:
        return SkillRerankResult(candidates=(), abstain=True, reason="no_candidates")

    rrf_by_key = reciprocal_rank_fusion(
        [
            _ranked_keys(normalized, "vector_score"),
            _ranked_keys(normalized, "tag_score"),
            _ranked_keys(normalized, "intent_score"),
        ]
    )
    ranked = [
        _score_candidate(
            candidate,
            rrf_by_key.get(_candidate_key(candidate), 0.0),
            required_output_contract=required_output_contract,
            required_evidence=required_evidence,
        )
        for candidate in normalized
    ]
    ranked.sort(
        key=lambda item: (
            item.score,
            item.intent_score,
            item.tag_score,
            item.vector_score,
            item.status_boost,
            item.skill_id,
        ),
        reverse=True,
    )
    top = tuple(ranked[: max(1, int(top_n))])
    best = top[0]
    if best.score < abstain_threshold:
        return SkillRerankResult(candidates=top, abstain=True, reason="low_confidence")
    return SkillRerankResult(candidates=top, abstain=False, reason="selected")


def reciprocal_rank_fusion(rankings: Iterable[Iterable[Any]], *, k: int = RRF_K) -> dict[Any, float]:
    scores: dict[Any, float] = {}
    for ranking in rankings:
        for rank, key in enumerate(ranking, start=1):
            scores[key] = scores.get(key, 0.0) + (1.0 / (k + rank))
    if not scores:
        return {}
    max_score = max(scores.values()) or 1.0
    return {key: value / max_score for key, value in scores.items()}


def _score_candidate(
    candidate: dict[str, Any],
    rrf_score: float,
    *,
    required_output_contract: Iterable[str] | None,
    required_evidence: Iterable[str] | None,
) -> RerankedSkillCandidate:
    metadata = dict(candidate.get("metadata") or {})
    vector_score = _bounded(candidate.get("vector_score"))
    tag_score = _bounded(candidate.get("tag_score"))
    intent_score = _bounded(metadata.get("intent_score", candidate.get("intent_score")))
    evidence_score = _evidence_score(candidate, required_evidence)
    output_contract_score = _output_contract_score(candidate, required_output_contract)
    runtime_success_score = _bounded(metadata.get("runtime_success_rate", candidate.get("runtime_success_rate")))
    status_boost = 0.04 if str(candidate.get("status")) == "production" else 0.0
    score = min(
        1.0,
        (0.25 * vector_score)
        + (0.22 * tag_score)
        + (0.18 * intent_score)
        + (0.12 * evidence_score)
        + (0.10 * output_contract_score)
        + (0.08 * runtime_success_score)
        + (0.05 * _bounded(rrf_score))
        + status_boost,
    )
    return RerankedSkillCandidate(
        skill_id=str(candidate["skill_id"]),
        version=int(candidate.get("version") or 1),
        status=str(candidate.get("status") or ""),
        domain=str(candidate.get("domain") or ""),
        score=score,
        confidence=score,
        vector_score=vector_score,
        tag_score=tag_score,
        intent_score=intent_score,
        evidence_score=evidence_score,
        output_contract_score=output_contract_score,
        runtime_success_score=runtime_success_score,
        status_boost=status_boost,
        rrf_score=_bounded(rrf_score),
        matched_tags=tuple(str(item) for item in candidate.get("matched_tags") or ()),
        title=candidate.get("title"),
        metadata=metadata,
    )


def _normalize_candidate(candidate: Any) -> dict[str, Any]:
    if hasattr(candidate, "to_dict"):
        value = candidate.to_dict()
    elif isinstance(candidate, Mapping):
        value = dict(candidate)
    else:
        value = dict(candidate)
    if "skill_id" not in value and "id" in value:
        value["skill_id"] = value["id"]
    if "skill_id" not in value:
        raise ValueError("candidate skill_id is required")
    value["version"] = int(value.get("version") or value.get("skill_version") or 1)
    value["metadata"] = dict(value.get("metadata") or {})
    return value


def _ranked_keys(candidates: list[dict[str, Any]], field_name: str) -> list[tuple[str, int]]:
    ranked = [
        (_candidate_key(candidate), _bounded(candidate.get(field_name)))
        for candidate in candidates
        if _bounded(candidate.get(field_name)) > 0
    ]
    ranked.sort(key=lambda item: (item[1], item[0][0]), reverse=True)
    return [key for key, _ in ranked]


def _candidate_key(candidate: dict[str, Any]) -> tuple[str, int]:
    return str(candidate["skill_id"]), int(candidate.get("version") or 1)


def _evidence_score(candidate: dict[str, Any], required_evidence: Iterable[str] | None) -> float:
    metadata = dict(candidate.get("metadata") or {})
    explicit = metadata.get("evidence_score", candidate.get("evidence_score"))
    if explicit is not None:
        return _bounded(explicit)
    available = set(_strings(metadata.get("available_evidence") or candidate.get("available_evidence")))
    required = set(_strings(required_evidence))
    if required:
        return len(available & required) / len(required)
    return 1.0 if metadata.get("evidence_available") is True or candidate.get("evidence_available") is True else 0.0


def _output_contract_score(candidate: dict[str, Any], required_output_contract: Iterable[str] | None) -> float:
    metadata = dict(candidate.get("metadata") or {})
    explicit = metadata.get("output_contract_score", candidate.get("output_contract_score"))
    if explicit is not None:
        return _bounded(explicit)
    available = set(_strings(metadata.get("output_contract") or candidate.get("output_contract")))
    required = set(_strings(required_output_contract))
    if required:
        return len(available & required) / len(required)
    return 0.0


def _strings(values: Iterable[Any] | Any | None) -> list[str]:
    if values in (None, "", [], {}):
        return []
    if isinstance(values, str):
        items = [values]
    elif isinstance(values, Iterable):
        items = list(values)
    else:
        items = [values]
    return [str(item).strip().lower() for item in items if str(item).strip()]


def _bounded(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))
