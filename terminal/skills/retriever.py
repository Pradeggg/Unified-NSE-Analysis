from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol

from .embedding_provider import EmbeddingProvider
from .store_repo import RUNTIME_STATUSES, SkillStoreRepository


DEFAULT_TOP_N = 30
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "a",
    "an",
    "analysis",
    "and",
    "are",
    "for",
    "from",
    "how",
    "in",
    "is",
    "latest",
    "me",
    "of",
    "on",
    "or",
    "over",
    "review",
    "show",
    "the",
    "today",
    "to",
    "what",
    "why",
    "with",
}


class SkillCandidateRepository(Protocol):
    def list_runtime_eligible(self, domain: str | None = None) -> list[dict[str, Any]]:
        ...

    def search_vector_candidates(
        self,
        vector: Iterable[float],
        model: str,
        *,
        limit: int = DEFAULT_TOP_N,
        statuses: tuple[str, ...] = RUNTIME_STATUSES,
    ) -> list[dict[str, Any]]:
        ...

    def log_retrieval(self, event: dict[str, Any]) -> int | None:
        ...


@dataclass(frozen=True)
class RetrievedSkillCandidate:
    skill_id: str
    version: int
    status: str
    domain: str
    score: float
    vector_score: float | None = None
    tag_score: float = 0.0
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
            "vector_score": None if self.vector_score is None else round(self.vector_score, 6),
            "tag_score": round(self.tag_score, 6),
            "matched_tags": list(self.matched_tags),
            "title": self.title,
            "metadata": dict(self.metadata),
        }


def retrieve_skill_candidates(
    query: str,
    *,
    top_n: int = DEFAULT_TOP_N,
    repo: SkillCandidateRepository | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    embedding_model: str | None = None,
    domain: str | None = None,
    log_event: bool = True,
) -> list[RetrievedSkillCandidate]:
    normalized_query = _normalize_query(query)
    if not normalized_query:
        return []
    repo = repo or SkillStoreRepository()
    top_n = max(1, int(top_n))
    started = time.perf_counter()

    vector_rows: list[dict[str, Any]] = []
    vector_error: str | None = None
    if embedding_provider is not None:
        try:
            embedding = embedding_provider.embed_texts([normalized_query], model=embedding_model)
            vector_rows = repo.search_vector_candidates(
                embedding.vectors[0],
                embedding.model,
                limit=top_n,
                statuses=RUNTIME_STATUSES,
            )
        except Exception as exc:  # Retrieval must still work from tags when embeddings are unavailable.
            vector_error = f"{type(exc).__name__}: {exc}"

    try:
        tag_rows = repo.list_runtime_eligible(domain=domain)
    except Exception as exc:
        if vector_error:
            vector_error = f"{vector_error}; tag_list_error={type(exc).__name__}: {exc}"
        else:
            vector_error = f"tag_list_error={type(exc).__name__}: {exc}"
        tag_rows = []
    candidates = _merge_candidates(normalized_query, vector_rows, tag_rows, top_n, domain=domain)

    if log_event:
        _log_retrieval(repo, normalized_query, candidates, started, vector_error)

    return candidates


def _merge_candidates(
    normalized_query: str,
    vector_rows: list[dict[str, Any]],
    tag_rows: list[dict[str, Any]],
    top_n: int,
    *,
    domain: str | None = None,
) -> list[RetrievedSkillCandidate]:
    query_terms = _query_terms(normalized_query)
    merged: dict[tuple[str, int], dict[str, Any]] = {}

    for row in vector_rows:
        key = _candidate_key(row)
        if key is None or not _runtime_status(row) or not _domain_matches(row, domain):
            continue
        item = merged.setdefault(key, _base_candidate(row))
        item["vector_score"] = _float_value(row.get("vector_score"))

    for row in tag_rows:
        key = _candidate_key(row)
        if key is None or not _runtime_status(row) or not _domain_matches(row, domain):
            continue
        matched_tags = _matched_tags(row, query_terms)
        input_hits = _input_pattern_hits(row, normalized_query, query_terms)
        tag_score = _tag_score(matched_tags, input_hits, query_terms)
        if tag_score <= 0 and key not in merged:
            continue
        item = merged.setdefault(key, _base_candidate(row))
        if key in merged:
            _merge_metadata(item, row)
        item["tag_score"] = max(float(item.get("tag_score") or 0.0), tag_score)
        item["matched_tags"] = sorted(set(item.get("matched_tags") or []) | set(matched_tags))

    candidates = [_to_candidate(item) for item in merged.values()]
    candidates.sort(key=lambda item: (item.score, item.vector_score or 0.0, item.tag_score, item.skill_id), reverse=True)
    return candidates[:top_n]


def _base_candidate(row: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(row.get("metadata") or {})
    card_payload = row.get("card_payload")
    if isinstance(card_payload, dict):
        metadata.update({key: value for key, value in card_payload.items() if key not in metadata})
    return {
        "skill_id": row.get("skill_id") or row.get("id"),
        "version": int(row.get("version") or row.get("skill_version") or 1),
        "status": str(row.get("status") or ""),
        "domain": str(row.get("domain") or ""),
        "title": row.get("title"),
        "vector_score": None,
        "tag_score": 0.0,
        "matched_tags": [],
        "metadata": metadata,
    }


def _merge_metadata(item: dict[str, Any], row: dict[str, Any]) -> None:
    incoming = _base_candidate(row)
    item["metadata"] = {
        **dict(incoming.get("metadata") or {}),
        **dict(item.get("metadata") or {}),
    }
    for key in ("title", "status", "domain"):
        if not item.get(key) and incoming.get(key):
            item[key] = incoming[key]


def _to_candidate(item: dict[str, Any]) -> RetrievedSkillCandidate:
    vector_score = item.get("vector_score")
    tag_score = float(item.get("tag_score") or 0.0)
    score = _combined_score(vector_score, tag_score, str(item.get("status") or ""))
    return RetrievedSkillCandidate(
        skill_id=str(item["skill_id"]),
        version=int(item["version"]),
        status=str(item["status"]),
        domain=str(item["domain"]),
        score=score,
        vector_score=None if vector_score is None else float(vector_score),
        tag_score=tag_score,
        matched_tags=tuple(item.get("matched_tags") or ()),
        title=item.get("title"),
        metadata={**dict(item.get("metadata") or {}), "source": _source_label(vector_score, tag_score)},
    )


def _combined_score(vector_score: Any, tag_score: float, status: str) -> float:
    vector_component = max(0.0, min(1.0, float(vector_score))) if vector_score is not None else 0.0
    tag_component = max(0.0, min(1.0, tag_score))
    status_boost = 0.05 if status == "production" else 0.0
    return min(1.0, (vector_component * 0.7) + (tag_component * 0.3) + status_boost)


def _source_label(vector_score: Any, tag_score: float) -> str:
    if vector_score is not None and tag_score > 0:
        return "vector+tag"
    if vector_score is not None:
        return "vector"
    return "tag"


def _log_retrieval(
    repo: SkillCandidateRepository,
    normalized_query: str,
    candidates: list[RetrievedSkillCandidate],
    started: float,
    vector_error: str | None,
) -> None:
    metadata: dict[str, Any] = {"candidate_count": len(candidates)}
    if vector_error:
        metadata["vector_error"] = vector_error
    repo.log_retrieval(
        {
            "query_hash": hashlib.sha256(normalized_query.encode("utf-8")).hexdigest(),
            "normalized_query": normalized_query,
            "selected_skill_id": None,
            "selected_version": None,
            "candidates": [item.to_dict() for item in candidates],
            "reviewer_decision": {},
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "metadata": metadata,
        }
    )


def _candidate_key(row: dict[str, Any]) -> tuple[str, int] | None:
    skill_id = row.get("skill_id") or row.get("id")
    if not skill_id:
        return None
    return str(skill_id), int(row.get("version") or row.get("skill_version") or 1)


def _runtime_status(row: dict[str, Any]) -> bool:
    return str(row.get("status") or "") in RUNTIME_STATUSES


def _domain_matches(row: dict[str, Any], domain: str | None) -> bool:
    return domain is None or str(row.get("domain") or "") == domain


def _matched_tags(row: dict[str, Any], query_terms: set[str]) -> list[str]:
    tags = _string_list(row.get("tags"))
    matches = []
    for tag in tags:
        tag_terms = _query_terms(tag)
        overlap = tag_terms & query_terms
        if overlap:
            matches.append(tag)
    return sorted(set(matches))


def _input_pattern_hits(row: dict[str, Any], normalized_query: str, query_terms: set[str]) -> float:
    hits = 0.0
    for pattern in _string_list(row.get("input_patterns")):
        normalized_pattern = _normalize_query(pattern)
        pattern_terms = _query_terms(normalized_pattern)
        if normalized_pattern and normalized_pattern in normalized_query:
            hits += 2
            continue
        overlap_count = len(pattern_terms & query_terms)
        if overlap_count >= 2:
            hits += min(1.0, overlap_count / max(2, len(pattern_terms)))
    return hits


def _tag_score(matched_tags: list[str], input_hits: float, query_terms: set[str]) -> float:
    if not query_terms:
        return 0.0
    signal_count = len(matched_tags) + input_hits
    return min(1.0, signal_count / max(3, len(query_terms)))


def _query_terms(value: str) -> set[str]:
    normalized = str(value).lower().replace("_", " ").replace("-", " ").replace("+", " ")
    return {token for token in _TOKEN_RE.findall(normalized) if token not in _STOPWORDS and len(token) > 1}


def _normalize_query(query: str) -> str:
    return " ".join(str(query or "").lower().split())


def _string_list(value: Any) -> list[str]:
    if value in (None, "", [], {}):
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set, frozenset)):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)]


def _float_value(value: Any) -> float:
    if value is None:
        return 0.0
    return float(value)
