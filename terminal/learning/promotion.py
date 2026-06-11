from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from terminal.learning.proposal_validator import validate_learning_proposal
from terminal.learning.repository import LearningRepository


DEFAULT_BACKLOG_DIR = Path("reports") / "learning" / "backlog"


@dataclass(frozen=True)
class LearningPromotionResult:
    proposal_id: int
    proposal_type: str
    ok: bool
    status_before: str
    status_after: str
    message: str
    promotion_kind: str = ""
    artifact_path: Path | None = None
    promotion_run_id: int | None = None


def list_learning_proposals(*, repository: Any | None = None, status: str | None = None) -> list[dict[str, Any]]:
    repo = repository or LearningRepository()
    return repo.list_proposals(status=status)


def get_learning_proposal(proposal_id: int, *, repository: Any | None = None) -> dict[str, Any] | None:
    repo = repository or LearningRepository()
    get = getattr(repo, "get_proposal", None)
    if callable(get):
        return get(proposal_id)
    for row in repo.list_proposals(status=None):
        if int(row.get("proposal_id") or 0) == int(proposal_id):
            return row
    return None


def promote_learning_proposal(
    proposal_id: int,
    *,
    repository: Any | None = None,
    target_status: str = "validated",
    approve_production: bool = False,
    output_dir: str | Path = DEFAULT_BACKLOG_DIR,
) -> LearningPromotionResult:
    repo = repository or LearningRepository()
    proposal = get_learning_proposal(proposal_id, repository=repo)
    if proposal is None:
        return _blocked(proposal_id, "", "", f"proposal {proposal_id} not found")

    status_before = str(proposal.get("status") or "")
    proposal_type = str(proposal.get("proposal_type") or "")
    if status_before != "review_pending":
        return _blocked(proposal_id, proposal_type, status_before, "proposal must be review_pending before promotion")
    if target_status == "production" and not approve_production:
        return _blocked(proposal_id, proposal_type, status_before, "production promotion requires explicit approval")
    if target_status not in {"validated", "production"}:
        return _blocked(proposal_id, proposal_type, status_before, f"unsupported target status: {target_status}")

    validation = validate_learning_proposal(proposal)
    if not validation.ok:
        return _blocked(proposal_id, proposal_type, status_before, "proposal validation failed before promotion")

    promotion_kind = _promotion_kind(proposal_type)
    artifact_path = _write_promotion_artifact(
        proposal,
        validation.backlog_snippet,
        promotion_kind,
        output_dir=output_dir or DEFAULT_BACKLOG_DIR,
    )
    repo.update_proposal_status(proposal_id, target_status)
    run_id = int(
        repo.record_promotion_run(
            {
                "proposal_id": proposal_id,
                "status": target_status,
                "promotion_payload": {
                    "promotion_kind": promotion_kind,
                    "artifact_path": str(artifact_path),
                    "target_status": target_status,
                    "backlog_snippet": validation.backlog_snippet,
                },
            }
        )
    )
    return LearningPromotionResult(
        proposal_id=proposal_id,
        proposal_type=proposal_type,
        ok=True,
        status_before=status_before,
        status_after=target_status,
        message=f"promoted proposal {proposal_id} to {target_status}",
        promotion_kind=promotion_kind,
        artifact_path=artifact_path,
        promotion_run_id=run_id,
    )


def reject_learning_proposal(
    proposal_id: int,
    *,
    repository: Any | None = None,
    reason: str = "",
) -> LearningPromotionResult:
    repo = repository or LearningRepository()
    proposal = get_learning_proposal(proposal_id, repository=repo)
    if proposal is None:
        return _blocked(proposal_id, "", "", f"proposal {proposal_id} not found")
    status_before = str(proposal.get("status") or "")
    proposal_type = str(proposal.get("proposal_type") or "")
    repo.update_proposal_status(proposal_id, "deprecated")
    run_id = int(
        repo.record_promotion_run(
            {
                "proposal_id": proposal_id,
                "status": "deprecated",
                "promotion_payload": {
                    "promotion_kind": "rejection",
                    "reason": reason,
                    "from_status": status_before,
                },
            }
        )
    )
    return LearningPromotionResult(
        proposal_id=proposal_id,
        proposal_type=proposal_type,
        ok=True,
        status_before=status_before,
        status_after="deprecated",
        message=f"rejected proposal {proposal_id}",
        promotion_kind="rejection",
        promotion_run_id=run_id,
    )


def _write_promotion_artifact(
    proposal: Mapping[str, Any],
    backlog_snippet: Mapping[str, Any],
    promotion_kind: str,
    *,
    output_dir: str | Path,
) -> Path:
    proposal_id = int(proposal.get("proposal_id") or 0)
    proposal_type = str(proposal.get("proposal_type") or "")
    path = Path(output_dir) / f"proposal_{proposal_id}_{proposal_type}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = proposal.get("proposal_payload") if isinstance(proposal.get("proposal_payload"), Mapping) else {}
    lines = [
        f"# {proposal.get('title') or proposal_type}",
        "",
        f"- Proposal ID: {proposal_id}",
        f"- Proposal Type: {proposal_type}",
        f"- Promotion Kind: {promotion_kind}",
        "",
        "## Proposed Behavior",
        str((payload.get("proposed_behavior") or {}).get("summary") or ""),
        "",
        "## Files To Edit",
        *_bullets(backlog_snippet.get("files_to_edit")),
        "",
        "## Tests To Add",
        *_bullets(backlog_snippet.get("tests_to_add")),
        "",
        "## Expected Tool Calls",
        *_bullets(backlog_snippet.get("expected_tool_calls")),
        "",
        "## Must Not Call Rules",
        *_bullets(backlog_snippet.get("must_not_call_rules")),
        "",
        "## Acceptance Criteria",
        *_bullets(backlog_snippet.get("acceptance_criteria")),
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _promotion_kind(proposal_type: str) -> str:
    mapping = {
        "skill_proposal": "skill_lifecycle_handoff",
        "route_proposal": "implementation_backlog_artifact",
        "tool_proposal": "implementation_backlog_artifact",
        "workflow_proposal": "implementation_backlog_artifact",
        "prompt_proposal": "prompt_review_artifact",
        "report_validation_proposal": "report_validation_task",
        "deprecation_proposal": "deprecation_task",
    }
    return mapping.get(proposal_type, "implementation_backlog_artifact")


def _blocked(proposal_id: int, proposal_type: str, status_before: str, message: str) -> LearningPromotionResult:
    return LearningPromotionResult(
        proposal_id=proposal_id,
        proposal_type=proposal_type,
        ok=False,
        status_before=status_before,
        status_after=status_before,
        message=message,
    )


def _bullets(values: Any) -> list[str]:
    items = _list(values)
    if not items:
        return ["- None"]
    return [f"- {item}" for item in items]


def _list(value: Any) -> list[Any]:
    if value in (None, "", [], {}):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set, frozenset)):
        return list(value)
    return [value]
