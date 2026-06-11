"""Safe telemetry helpers for Skill Store retrieval and execution events."""
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any


SENSITIVE_KEYS = {"embedding", "vector", "vectors", "raw_query", "raw_text"}


def build_retrieval_event(
    query: str,
    *,
    candidates: Any,
    reviewer_decision: Any,
    elapsed_ms: int | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_query = normalize_query(query)
    review = _plain_dict(reviewer_decision)
    return {
        "query_hash": hashlib.sha256(normalized_query.encode("utf-8")).hexdigest(),
        "normalized_query": normalized_query,
        "selected_skill_id": review.get("selected_skill_id"),
        "selected_version": review.get("selected_version"),
        "candidates": [_sanitize_candidate(item) for item in _list(candidates)],
        "reviewer_decision": _sanitize(review),
        "elapsed_ms": 0 if elapsed_ms is None else int(elapsed_ms),
        "metadata": _sanitize(dict(metadata or {})),
    }


def log_retrieval_event(repository: Any | None, event: Mapping[str, Any]) -> int | None:
    if repository is None:
        return None
    log_fn = getattr(repository, "log_retrieval", None)
    if not callable(log_fn):
        return None
    try:
        value = log_fn(dict(event))
    except Exception:
        return None
    return int(value) if value is not None else None


def build_execution_event(
    *,
    skill_id: str,
    skill_version: int = 1,
    steps: Any,
    validation_status: str,
    validation_findings: Any,
    final_intent: str | None = None,
    retrieval_id: int | None = None,
    elapsed_ms: int | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    event_metadata = dict(metadata or {})
    if final_intent:
        event_metadata["final_intent"] = final_intent
    return {
        "retrieval_id": retrieval_id,
        "skill_id": str(skill_id),
        "skill_version": int(skill_version or 1),
        "steps": [_sanitize_step(item) for item in _list(steps)],
        "validation_status": str(validation_status),
        "validation_findings": _sanitize(_list(validation_findings)),
        "elapsed_ms": 0 if elapsed_ms is None else int(elapsed_ms),
        "metadata": _sanitize(event_metadata),
    }


def log_execution_event(repository: Any | None, event: Mapping[str, Any]) -> int | None:
    if repository is None:
        return None
    log_fn = getattr(repository, "log_execution", None)
    if not callable(log_fn):
        return None
    try:
        value = log_fn(dict(event))
    except Exception:
        return None
    return int(value) if value is not None else None


def query_logs_by_skill(repository: Any | None, skill_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
    if repository is None:
        return []
    if getattr(repository, "fail", False):
        return []
    query_fn = getattr(repository, "query_logs_by_skill", None)
    if not callable(query_fn):
        return []
    try:
        rows = query_fn(skill_id, limit=limit)
    except Exception:
        return []
    return [dict(row) for row in rows or [] if isinstance(row, Mapping)]


def normalize_query(query: str) -> str:
    return " ".join(str(query or "").lower().split())


def _sanitize_candidate(value: Any) -> dict[str, Any]:
    item = _plain_dict(value)
    allowed = {
        "skill_id",
        "id",
        "version",
        "skill_version",
        "status",
        "domain",
        "title",
        "score",
        "confidence",
        "vector_score",
        "tag_score",
        "intent_score",
        "matched_tags",
        "metadata",
    }
    return {key: _sanitize(item[key]) for key in allowed if key in item}


def _sanitize_step(value: Any) -> dict[str, Any]:
    item = _plain_dict(value)
    allowed = {
        "step_id",
        "step_type",
        "name",
        "target",
        "status",
        "row_count",
        "error",
    }
    return {key: _sanitize(item[key]) for key in allowed if key in item}


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _sanitize(item)
            for key, item in value.items()
            if str(key).lower() not in SENSITIVE_KEYS
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_sanitize(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _plain_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "to_dict"):
        return dict(value.to_dict())
    if isinstance(value, Mapping):
        return dict(value)
    return dict(value)


def _list(value: Any) -> list[Any]:
    if value in (None, "", {}, ()):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, (set, frozenset)):
        return list(value)
    return [value]
