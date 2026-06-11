"""Promotion and deprecation controls for Skill Store cards."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from terminal.skills.store_repo import SkillStoreRepository


@dataclass(frozen=True)
class SkillPromotionResult:
    ok: bool
    skill_id: str
    version: int
    from_status: str
    to_status: str
    message: str


def list_skills(
    *,
    repository: Any | None = None,
    status: str | None = None,
    domain: str | None = None,
) -> list[dict[str, Any]]:
    repo = repository or SkillStoreRepository()
    if hasattr(repo, "list_skill_cards"):
        return [dict(row) for row in repo.list_skill_cards(status=status, domain=domain)]
    if status in (None, "validated", "production"):
        return [dict(row) for row in repo.list_runtime_eligible(domain=domain)]
    return []


def promote_skill(
    skill_id: str,
    *,
    target_status: str = "validated",
    repository: Any | None = None,
    version: int | None = None,
    actor: str = "agent_adda_cli",
) -> SkillPromotionResult:
    repo = repository or SkillStoreRepository()
    card = _load_card(repo, skill_id, version=version)
    if not card:
        return _result(False, skill_id, version or 1, "", target_status, "skill not found", repo, actor)

    from_status = str(card.get("status") or "")
    card_version = int(card.get("version") or version or 1)
    allowed, message = _promotion_allowed(card, target_status)
    if not allowed:
        return _result(False, skill_id, card_version, from_status, target_status, message, repo, actor)

    updated = dict(card)
    updated["status"] = target_status
    updated.setdefault("promotion_history", [])
    if isinstance(updated["promotion_history"], list):
        updated["promotion_history"].append(
            {"from_status": from_status, "to_status": target_status, "actor": actor}
        )
    repo.upsert_skill_card(updated)
    return _result(
        True,
        skill_id,
        card_version,
        from_status,
        target_status,
        f"promoted {skill_id} from {from_status} to {target_status}",
        repo,
        actor,
    )


def deprecate_skill(
    skill_id: str,
    *,
    repository: Any | None = None,
    version: int | None = None,
    reason: str = "",
    actor: str = "agent_adda_cli",
) -> SkillPromotionResult:
    repo = repository or SkillStoreRepository()
    card = _load_card(repo, skill_id, version=version)
    if not card:
        return _result(False, skill_id, version or 1, "", "deprecated", "skill not found", repo, actor)

    from_status = str(card.get("status") or "")
    card_version = int(card.get("version") or version or 1)
    updated = dict(card)
    updated["status"] = "deprecated"
    updated["deprecation_reason"] = reason
    repo.upsert_skill_card(updated)
    return _result(
        True,
        skill_id,
        card_version,
        from_status,
        "deprecated",
        f"deprecated {skill_id}",
        repo,
        actor,
        extra_payload={"reason": reason},
    )


def _load_card(repo: Any, skill_id: str, *, version: int | None) -> dict[str, Any]:
    row = repo.get_skill_card(skill_id, version=version)
    if not row:
        return {}
    if isinstance(row.get("card_payload"), dict):
        payload = dict(row["card_payload"])
        payload.setdefault("id", row.get("id") or skill_id)
        payload.setdefault("version", row.get("version") or version or 1)
        payload.setdefault("status", row.get("status") or payload.get("status"))
        return payload
    return dict(row)


def _promotion_allowed(card: dict[str, Any], target_status: str) -> tuple[bool, str]:
    current = str(card.get("status") or "")
    if target_status == "production":
        if current != "validated":
            return False, f"cannot promote {current or 'unknown'} directly to production"
        return True, "ok"
    if target_status == "validated":
        if current != "review_pending":
            return False, f"cannot promote {current or 'unknown'} to validated"
        if not _has_validation_pass(card):
            return False, "validation pass is required before promotion"
        return True, "ok"
    return False, f"unsupported target status {target_status}"


def _has_validation_pass(card: dict[str, Any]) -> bool:
    review = card.get("review") if isinstance(card.get("review"), dict) else {}
    return review.get("status") == "pass" and not card.get("validation_errors")


def _result(
    ok: bool,
    skill_id: str,
    version: int,
    from_status: str,
    to_status: str,
    message: str,
    repo: Any,
    actor: str,
    *,
    extra_payload: dict[str, Any] | None = None,
) -> SkillPromotionResult:
    result = SkillPromotionResult(
        ok=ok,
        skill_id=skill_id,
        version=version,
        from_status=from_status,
        to_status=to_status,
        message=message,
    )
    _log_decision(repo, result, actor=actor, extra_payload=extra_payload)
    return result


def _log_decision(
    repo: Any,
    result: SkillPromotionResult,
    *,
    actor: str,
    extra_payload: dict[str, Any] | None = None,
) -> None:
    payload = {
        "ok": result.ok,
        "from_status": result.from_status,
        "to_status": result.to_status,
        "message": result.message,
        **(extra_payload or {}),
    }
    if hasattr(repo, "log_promotion"):
        repo.log_promotion(
            {
                "skill_id": result.skill_id,
                "skill_version": result.version,
                "actor": actor,
                "payload": payload,
            }
        )
    elif hasattr(repo, "save_feedback"):
        repo.save_feedback(
            {
                "skill_id": result.skill_id,
                "skill_version": result.version,
                "feedback_type": "skill_promotion",
                "feedback_payload": payload,
                "created_by": actor,
            }
        )
