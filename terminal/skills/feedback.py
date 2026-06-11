"""User feedback capture and feedback-derived reranker signals."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from terminal.skills.store_repo import SkillStoreRepository


SUPPORTED_FEEDBACK_TYPES = frozenset(
    {
        "useful",
        "not_useful",
        "wrong_skill",
        "stale_data",
        "missing_evidence",
    }
)
POSITIVE_FEEDBACK_TYPES = frozenset({"useful"})
NEGATIVE_FEEDBACK_TYPES = SUPPORTED_FEEDBACK_TYPES - POSITIVE_FEEDBACK_TYPES


@dataclass(frozen=True)
class SkillFeedbackResult:
    ok: bool
    feedback_id: int | None = None
    message: str = ""


def capture_skill_feedback(
    *,
    repository: Any | None = None,
    skill_id: str,
    feedback_type: str,
    skill_version: int = 1,
    retrieval_id: int | None = None,
    execution_id: int | None = None,
    reason: str = "",
    payload: Mapping[str, Any] | None = None,
    created_by: str = "agent_adda",
) -> SkillFeedbackResult:
    feedback_type = str(feedback_type or "").strip()
    if feedback_type not in SUPPORTED_FEEDBACK_TYPES:
        return SkillFeedbackResult(ok=False, message=f"unsupported feedback type: {feedback_type}")

    repo = repository or SkillStoreRepository()
    event = {
        "retrieval_id": retrieval_id,
        "execution_id": execution_id,
        "skill_id": str(skill_id),
        "skill_version": int(skill_version or 1),
        "feedback_type": feedback_type,
        "feedback_payload": _feedback_payload(feedback_type, reason=reason, payload=payload),
        "created_by": created_by,
    }
    try:
        feedback_id = repo.save_feedback(event)
    except Exception as exc:
        return SkillFeedbackResult(ok=False, message=f"{type(exc).__name__}: {exc}")
    return SkillFeedbackResult(
        ok=True,
        feedback_id=int(feedback_id) if feedback_id is not None else None,
        message="feedback recorded",
    )


def get_skill_feedback_summary(repository: Any | None, skill_id: str) -> dict[str, Any]:
    repo = repository or SkillStoreRepository()
    summary_fn = getattr(repo, "get_feedback_summary", None)
    if not callable(summary_fn):
        return {}
    try:
        rows = summary_fn(skill_id)
    except Exception:
        return {}
    if not rows:
        return {}
    row = dict(rows[0])
    return _normalize_summary(row)


def apply_feedback_to_candidates(candidates: Any, repository: Any | None) -> list[dict[str, Any]]:
    repo = repository or SkillStoreRepository()
    summaries = _feedback_summary_by_skill(repo)
    enriched: list[dict[str, Any]] = []
    for candidate in list(candidates or []):
        item = candidate.to_dict() if hasattr(candidate, "to_dict") else dict(candidate)
        skill_id = str(item.get("skill_id") or item.get("id") or "")
        summary = summaries.get(skill_id)
        if summary:
            metadata = dict(item.get("metadata") or {})
            metadata["runtime_success_rate"] = summary["runtime_success_rate"]
            metadata["feedback_total"] = summary["total"]
            metadata["feedback_positive"] = summary["positive"]
            metadata["feedback_negative"] = summary["negative"]
            item["metadata"] = metadata
        enriched.append(item)
    return enriched


def _feedback_payload(
    feedback_type: str,
    *,
    reason: str,
    payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    value = _sanitize(dict(payload or {}))
    value["sentiment"] = "positive" if feedback_type in POSITIVE_FEEDBACK_TYPES else "negative"
    if reason:
        value["reason"] = str(reason)
    return value


def _feedback_summary_by_skill(repo: Any) -> dict[str, dict[str, Any]]:
    summary_fn = getattr(repo, "get_feedback_summary", None)
    if not callable(summary_fn):
        return {}
    try:
        rows = summary_fn()
    except Exception:
        return {}
    summaries: dict[str, dict[str, Any]] = {}
    for row in rows or []:
        normalized = _normalize_summary(dict(row))
        if normalized.get("skill_id"):
            summaries[str(normalized["skill_id"])] = normalized
    return summaries


def _normalize_summary(row: dict[str, Any]) -> dict[str, Any]:
    total = int(row.get("total") or 0)
    positive = int(row.get("positive") or 0)
    negative = int(row.get("negative") or 0)
    rate = row.get("runtime_success_rate")
    if rate is None:
        rate = positive / total if total else 0.0
    return {
        "skill_id": str(row.get("skill_id") or ""),
        "total": total,
        "positive": positive,
        "negative": negative,
        "runtime_success_rate": _bounded(rate),
    }


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_sanitize(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _bounded(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))
