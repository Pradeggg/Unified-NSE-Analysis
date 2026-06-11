from __future__ import annotations

import html
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from terminal.learning.repository import LearningRepository


DEFAULT_AUDIT_DIR = Path("reports") / "learning"


@dataclass(frozen=True)
class LearningAuditResult:
    window: str
    markdown: str
    markdown_path: Path
    html_path: Path
    audit_payload: dict[str, Any]
    audit_id: int | None = None


def generate_learning_audit(
    *,
    repository: Any | None = None,
    window: str = "14d",
    output_dir: str | Path = DEFAULT_AUDIT_DIR,
    save: bool = True,
) -> LearningAuditResult:
    repo = repository or LearningRepository()
    patterns = repo.list_patterns(limit=50)
    proposals = repo.list_proposals(status=None)
    promotions = _call_or_empty(repo, "list_promotion_runs", limit=50)
    payload = _build_audit_payload(window=window, patterns=patterns, proposals=proposals, promotions=promotions)
    markdown = _render_markdown(payload)
    output = Path(output_dir or DEFAULT_AUDIT_DIR)
    output.mkdir(parents=True, exist_ok=True)
    slug = window.replace("/", "_")
    markdown_path = output / f"learning_audit_{slug}.md"
    html_path = output / f"learning_audit_{slug}.html"
    markdown_path.write_text(markdown, encoding="utf-8")
    html_path.write_text(_render_html(markdown, payload), encoding="utf-8")
    audit_id = None
    if save:
        audit_id = int(repo.record_learning_audit({"audit_type": "fortnightly_learning", "audit_payload": payload}))
    return LearningAuditResult(
        window=window,
        markdown=markdown,
        markdown_path=markdown_path,
        html_path=html_path,
        audit_payload=payload,
        audit_id=audit_id,
    )


def _build_audit_payload(
    *,
    window: str,
    patterns: list[Mapping[str, Any]],
    proposals: list[Mapping[str, Any]],
    promotions: list[Mapping[str, Any]],
) -> dict[str, Any]:
    pattern_rows = [_pattern_payload(row) for row in patterns]
    proposal_rows = [_proposal_payload(row) for row in proposals]
    promoted = [row for row in proposal_rows if row["status"] in {"validated", "production"}]
    rejected = [row for row in proposal_rows if row["status"] in {"deprecated", "test_failed"}]
    return {
        "window": window,
        "top_repeated_workflows": [row for row in pattern_rows if "workflow" in row["pattern_key"]][:10],
        "recurring_failures": [row for row in pattern_rows if "failure" in row["pattern_key"] or "fallback" in row["pattern_key"]][:10],
        "generated_proposals": proposal_rows,
        "promoted_proposals": promoted,
        "rejected_proposals": rejected,
        "promotion_runs": [_promotion_payload(row) for row in promotions],
        "stale_deprecated_skills": [row for row in proposal_rows if row["proposal_type"] == "deprecation_proposal"],
        "recommended_next_backlog_tasks": _recommended_tasks(pattern_rows, proposal_rows),
    }


def _render_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        f"# Agent Adda Fortnightly Learning Audit ({payload['window']})",
        "",
        "This audit summarizes captured usage patterns, generated proposals, promotion outcomes, and next implementation tasks.",
        "",
        "## Top Repeated Workflows",
        *_pattern_lines(payload.get("top_repeated_workflows")),
        "",
        "## Recurring Failures",
        *_pattern_lines(payload.get("recurring_failures")),
        "",
        "## Generated Proposals",
        *_proposal_lines(payload.get("generated_proposals")),
        "",
        "## Promoted Proposals",
        *_proposal_lines(payload.get("promoted_proposals")),
        "",
        "## Rejected Proposals",
        *_proposal_lines(payload.get("rejected_proposals")),
        "",
        "## Promotion Runs",
        *_promotion_lines(payload.get("promotion_runs")),
        "",
        "## Stale Deprecated Skills",
        *_proposal_lines(payload.get("stale_deprecated_skills")),
        "",
        "## Recommended Next Backlog Tasks",
        *_task_lines(payload.get("recommended_next_backlog_tasks")),
        "",
    ]
    return "\n".join(lines)


def _render_html(markdown: str, payload: Mapping[str, Any]) -> str:
    sections = []
    current_title = ""
    current_lines: list[str] = []
    for line in markdown.splitlines():
        if line.startswith("## "):
            if current_title:
                sections.append((current_title, current_lines))
            current_title = line[3:]
            current_lines = []
        elif line.startswith("# "):
            continue
        else:
            current_lines.append(line)
    if current_title:
        sections.append((current_title, current_lines))

    section_html = "\n".join(
        f"<section><h2>{html.escape(title)}</h2><pre>{html.escape(chr(10).join(lines).strip() or 'None')}</pre></section>"
        for title, lines in sections
    )
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <title>Agent Adda Learning Audit</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 32px; color: #17202a; background: #f7f9fb; }}
    h1 {{ font-size: 28px; margin-bottom: 4px; }}
    section {{ background: #fff; border: 1px solid #d9e2ec; border-radius: 8px; padding: 18px; margin: 14px 0; }}
    h2 {{ font-size: 18px; margin: 0 0 10px; }}
    pre {{ white-space: pre-wrap; font: 13px/1.45 ui-monospace, SFMono-Regular, Menlo, monospace; margin: 0; }}
  </style>
</head>
<body>
  <h1>Agent Adda Fortnightly Learning Audit ({html.escape(str(payload['window']))})</h1>
  {section_html}
</body>
</html>
"""


def _recommended_tasks(patterns: list[dict[str, Any]], proposals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for proposal in proposals:
        if proposal["status"] == "review_pending":
            tasks.append({"title": f"Validate and promote proposal {proposal['proposal_id']}: {proposal['title']}", "source": "proposal"})
    for pattern in patterns:
        if pattern["priority"] == "high":
            tasks.append({"title": f"Create proposal for high-priority pattern {pattern['pattern_key']}", "source": "pattern"})
    return tasks[:10]


def _pattern_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    payload = row.get("pattern_payload") if isinstance(row.get("pattern_payload"), Mapping) else {}
    return {
        "pattern_id": int(row.get("pattern_id") or payload.get("pattern_id") or 0),
        "pattern_key": str(payload.get("pattern_key") or row.get("pattern_key") or ""),
        "pattern_type": str(payload.get("pattern_type") or ""),
        "label": str(payload.get("label") or ""),
        "frequency": int(payload.get("frequency") or 0),
        "score": int(payload.get("score") or 0),
        "priority": str(payload.get("priority") or ""),
    }


def _proposal_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    payload = row.get("proposal_payload") if isinstance(row.get("proposal_payload"), Mapping) else {}
    observed = payload.get("observed_pattern") if isinstance(payload.get("observed_pattern"), Mapping) else {}
    return {
        "proposal_id": int(row.get("proposal_id") or 0),
        "proposal_type": str(row.get("proposal_type") or payload.get("proposal_type") or ""),
        "title": str(row.get("title") or payload.get("title") or ""),
        "status": str(row.get("status") or ""),
        "source_pattern_id": row.get("source_pattern_id"),
        "pattern_key": str(observed.get("pattern_key") or ""),
    }


def _promotion_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    payload = row.get("promotion_payload") if isinstance(row.get("promotion_payload"), Mapping) else {}
    return {
        "promotion_run_id": int(row.get("promotion_run_id") or 0),
        "proposal_id": row.get("proposal_id"),
        "status": str(row.get("status") or ""),
        "artifact_path": str(payload.get("artifact_path") or ""),
        "reason": str(payload.get("reason") or ""),
    }


def _pattern_lines(rows: Any) -> list[str]:
    items = list(rows or [])
    if not items:
        return ["- None"]
    return [f"- {row['pattern_key']} | freq={row['frequency']} | score={row['score']} | priority={row['priority']}" for row in items]


def _proposal_lines(rows: Any) -> list[str]:
    items = list(rows or [])
    if not items:
        return ["- None"]
    return [f"- #{row['proposal_id']} {row['proposal_type']} [{row['status']}] {row['title']} ({row['pattern_key']})" for row in items]


def _promotion_lines(rows: Any) -> list[str]:
    items = list(rows or [])
    if not items:
        return ["- None"]
    return [
        f"- run #{row['promotion_run_id']} proposal #{row['proposal_id']} -> {row['status']} {row['artifact_path'] or row['reason']}"
        for row in items
    ]


def _task_lines(rows: Any) -> list[str]:
    items = list(rows or [])
    if not items:
        return ["- None"]
    return [f"- {row['title']}" for row in items]


def _call_or_empty(repo: Any, name: str, **kwargs: Any) -> list[dict[str, Any]]:
    method = getattr(repo, name, None)
    if not callable(method):
        return []
    return list(method(**kwargs))
