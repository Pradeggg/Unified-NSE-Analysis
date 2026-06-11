from __future__ import annotations

import shlex
from collections import Counter
from typing import Any

from .store_repo import RUNTIME_STATUSES, SkillStoreRepository


def _repo(repo: Any | None = None) -> Any:
    return repo if repo is not None else SkillStoreRepository()


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item)]
    return [str(value)] if str(value) else []


def _matches_query(row: dict[str, Any], query: str) -> bool:
    haystack = " ".join(
        [
            str(row.get("id") or ""),
            str(row.get("title") or ""),
            str(row.get("description") or ""),
            " ".join(_as_list(row.get("tags"))),
            " ".join(_as_list(row.get("input_patterns"))),
            " ".join(_as_list(row.get("output_contract"))),
        ]
    ).lower()
    terms = [term for term in query.lower().split() if term]
    return all(term in haystack for term in terms)


def _fmt_list(values: Any, *, empty: str = "-") -> str:
    items = _as_list(values)
    return ", ".join(items) if items else empty


def _status_counts(rows: list[dict[str, Any]]) -> str:
    counts = Counter(str(row.get("status") or "unknown") for row in rows)
    ordered = ["production", "validated", "review_pending", "generated", "test_failed", "deprecated", "unknown"]
    parts = [f"{status}: {counts[status]}" for status in ordered if counts.get(status)]
    return " | ".join(parts) if parts else "none"


def _render_summary(repo: Any) -> str:
    rows = list(repo.list_skill_cards())
    runtime = [row for row in rows if str(row.get("status") or "") in RUNTIME_STATUSES]
    lines = [
        "## Skill Store",
        "",
        f"- Status counts: {_status_counts(rows)}",
        f"- Runtime eligible: {len(runtime)}",
        "",
        "### Runtime Eligible Skills",
    ]
    if not runtime:
        lines.append("- No validated or production skills found.")
    for row in runtime[:15]:
        lines.append(
            f"- `{row.get('id')}` v{row.get('version', 1)} "
            f"({row.get('status')} / {row.get('domain')}) — {row.get('title') or '-'}"
        )
    lines.extend(
        [
            "",
            "Commands: `/skills search QUERY`, `/skills show SKILL_ID`, `/skills recent`.",
            "Generated skills are untrusted and are not runtime eligible until validated or promoted.",
        ]
    )
    return "\n".join(lines)


def _render_search(repo: Any, query: str) -> str:
    if not query.strip():
        return "## Skill Store Search\n\nUsage: `/skills search QUERY`"
    rows = [row for row in repo.list_runtime_eligible() if _matches_query(row, query)]
    lines = [f"## Skill Store Search — {query}", ""]
    if not rows:
        lines.append("- No runtime-eligible skill matched.")
    for row in rows[:10]:
        lines.append(
            f"- `{row.get('id')}` v{row.get('version', 1)} "
            f"({row.get('status')} / {row.get('domain')}) — {row.get('title') or '-'}"
        )
        lines.append(f"  Tags: {_fmt_list(row.get('tags'))}")
        lines.append(f"  Patterns: {_fmt_list(row.get('input_patterns'))}")
    return "\n".join(lines)


def _render_show(repo: Any, skill_id: str) -> str:
    if not skill_id.strip():
        return "## Skill Store Show\n\nUsage: `/skills show SKILL_ID`"
    row = repo.get_skill_card(skill_id.strip())
    if not row:
        return f"## Skill Store Show\n\nNo skill found for `{skill_id}`."
    payload = row.get("card_payload") if isinstance(row.get("card_payload"), dict) else {}
    output_contract = row.get("output_contract") or payload.get("output_contract")
    validation_rules = row.get("validation_rules") or payload.get("validation_rules")
    evidence = row.get("evidence_required") or payload.get("evidence_required") or {}
    if isinstance(evidence, dict):
        evidence_text = ", ".join(f"{key}: {_fmt_list(value)}" for key, value in evidence.items()) or "-"
    else:
        evidence_text = _fmt_list(evidence)
    lines = [
        f"## Skill Store Skill — {row.get('id')}",
        "",
        f"- Version: {row.get('version', 1)}",
        f"- Status: {row.get('status')}",
        f"- Domain: {row.get('domain')}",
        f"- Title: {row.get('title') or '-'}",
        f"- Updated: {row.get('updated_at') or row.get('created_at') or '-'}",
        f"- Tags: {_fmt_list(row.get('tags'))}",
        "",
        "### Input Patterns",
        *[f"- {item}" for item in (_as_list(row.get("input_patterns")) or ["-"])],
        "",
        "### Evidence Required",
        f"- {evidence_text}",
        "",
        "### Output contract",
        *[f"- {item}" for item in (_as_list(output_contract) or ["-"])],
        "",
        "### Validation rules",
        *[f"- {item}" for item in (_as_list(validation_rules) or ["-"])],
        "",
        "Generated skills are untrusted until validation and promotion gates pass.",
    ]
    return "\n".join(lines)


def _render_recent(repo: Any) -> str:
    if hasattr(repo, "recent_activity"):
        rows = list(repo.recent_activity(limit=10))
    elif hasattr(repo, "get_recent_activity"):
        rows = list(repo.get_recent_activity(limit=10))
    else:
        rows = []
    lines = ["## Recent Skill Store Activity", ""]
    if not rows:
        lines.append("- No recent retrieval or execution logs found.")
        return "\n".join(lines)
    for row in rows:
        status = row.get("validation_status") or row.get("reviewer_decision") or "-"
        lines.append(
            f"- {row.get('created_at') or '-'} | {row.get('kind') or '-'} | "
            f"`{row.get('skill_id') or row.get('selected_skill_id') or '-'}` | "
            f"status: {status} | elapsed_ms: {row.get('elapsed_ms') or '-'}"
        )
    return "\n".join(lines)


def handle_skills_command(text: str, *, repo: Any | None = None) -> str:
    """Render read-only Skill Store inspection commands."""
    repository = _repo(repo)
    parts = shlex.split(text or "")
    if parts and parts[0].lower() == "/skills":
        parts = parts[1:]
    if not parts:
        return _render_summary(repository)
    subcommand = parts[0].lower()
    if subcommand == "search":
        return _render_search(repository, " ".join(parts[1:]))
    if subcommand == "show":
        return _render_show(repository, parts[1] if len(parts) > 1 else "")
    if subcommand == "recent":
        return _render_recent(repository)
    return "\n".join(
        [
            "## Skill Store",
            "",
            "Usage:",
            "- `/skills`",
            "- `/skills search QUERY`",
            "- `/skills show SKILL_ID`",
            "- `/skills recent`",
        ]
    )
