from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from terminal.learning.repository import LearningRepository


DEFAULT_OUTPUT_DIR = Path("reports") / "learning" / "daily"


@dataclass(frozen=True)
class DailyLearningSummary:
    summary_date: date
    event_count: int
    top_intents: list[dict[str, Any]]
    top_entities: list[dict[str, Any]]
    commands_run: list[dict[str, Any]]
    tools_used: list[dict[str, Any]]
    artifacts_created: list[dict[str, Any]]
    failures: list[dict[str, Any]]
    report_issues: list[dict[str, Any]]
    missing_evidence: list[dict[str, Any]]
    workflow_counts: list[dict[str, Any]]
    successful_workflows: list[dict[str, Any]]
    failed_workflows: list[dict[str, Any]]
    markdown: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "summary_date": self.summary_date.isoformat(),
            "activity_status": "active" if self.event_count else "no_activity",
            "event_count": self.event_count,
            "top_intents": self.top_intents,
            "top_entities": self.top_entities,
            "commands_run": self.commands_run,
            "tools_used": self.tools_used,
            "artifacts_created": self.artifacts_created,
            "failures": self.failures,
            "report_issues": self.report_issues,
            "missing_evidence": self.missing_evidence,
            "workflow_counts": self.workflow_counts,
            "successful_workflows": self.successful_workflows,
            "failed_workflows": self.failed_workflows,
            "markdown": self.markdown,
        }


@dataclass(frozen=True)
class DailyLearningSummaryResult:
    summary: DailyLearningSummary
    summary_id: int | None = None
    markdown_path: Path | None = None


def build_daily_learning_summary(
    summary_date: str | date | datetime,
    *,
    events: Iterable[Mapping[str, Any]],
    workflow_chains: Iterable[Mapping[str, Any]],
) -> DailyLearningSummary:
    target_date = _to_date(summary_date)
    event_rows = [dict(event) for event in events]
    chain_rows = [dict(chain) for chain in workflow_chains]

    intent_counts: Counter[str] = Counter()
    entity_counts: Counter[str] = Counter()
    command_counts: Counter[str] = Counter()
    tool_counts: Counter[str] = Counter()
    artifact_counts: Counter[str] = Counter()
    failure_counts: Counter[str] = Counter()
    report_issue_counts: Counter[str] = Counter()
    missing_counts: Counter[str] = Counter()

    for event in event_rows:
        intent = str(event.get("selected_intent") or event.get("intent") or "").strip()
        route_type = str(event.get("route_type") or "").strip()
        if intent:
            intent_counts[intent] += 1
            if route_type == "command_action":
                command_counts[intent] += 1
        for entity in _strings(event.get("detected_entities") or event.get("entities")):
            entity_counts[entity.upper()] += 1
        for tool in _strings(event.get("tools_executed") or event.get("tools")):
            tool_counts[tool] += 1
        for artifact in _strings(event.get("artifacts")):
            artifact_counts[artifact] += 1
        for missing in _strings(event.get("missing_evidence")):
            missing_counts[missing] += 1
        for error in _strings(event.get("errors")):
            if _is_report_issue(error, event):
                report_issue_counts[error] += 1
            else:
                failure_counts[error] += 1

    workflow_counts: Counter[str] = Counter()
    successful_workflows: list[dict[str, Any]] = []
    failed_workflows: list[dict[str, Any]] = []
    for chain in chain_rows:
        chain_id, chain_type, errors = _chain_identity(chain)
        if not chain_type:
            continue
        workflow_counts[chain_type] += 1
        item = {"chain_id": chain_id, "chain_type": chain_type}
        if errors or chain_type == "fallback_failure_recovery":
            failed_workflows.append(item)
        else:
            successful_workflows.append(item)

    successful_workflows = sorted(successful_workflows, key=lambda item: (str(item["chain_type"]), int(item["chain_id"] or 0)))
    failed_workflows = sorted(failed_workflows, key=lambda item: (str(item["chain_type"]), int(item["chain_id"] or 0)))

    payload_parts = {
        "top_intents": _counter_rows(intent_counts),
        "top_entities": _counter_rows(entity_counts),
        "commands_run": _counter_rows(command_counts),
        "tools_used": _counter_rows(tool_counts),
        "artifacts_created": _counter_rows(artifact_counts),
        "failures": _counter_rows(failure_counts),
        "report_issues": _counter_rows(report_issue_counts),
        "missing_evidence": _counter_rows(missing_counts),
        "workflow_counts": _counter_rows(workflow_counts),
        "successful_workflows": successful_workflows,
        "failed_workflows": failed_workflows,
    }
    markdown = _render_markdown(target_date, len(event_rows), payload_parts)

    return DailyLearningSummary(
        summary_date=target_date,
        event_count=len(event_rows),
        markdown=markdown,
        **payload_parts,
    )


def load_daily_learning_summary(
    summary_date: str | date | datetime,
    *,
    repository: Any | None = None,
) -> DailyLearningSummary:
    target_date = _to_date(summary_date)
    repo = repository or LearningRepository()
    events = repo.list_interaction_events(start_date=target_date, end_date=target_date)
    chains = repo.list_workflow_chains(start_date=target_date, end_date=target_date)
    return build_daily_learning_summary(target_date, events=events, workflow_chains=chains)


def save_daily_learning_summary(summary: DailyLearningSummary, *, repository: Any | None = None) -> int:
    repo = repository or LearningRepository()
    return int(
        repo.save_daily_summary(
            {
                "summary_date": summary.summary_date,
                "summary_payload": summary.to_payload(),
            }
        )
    )


def write_daily_learning_markdown(
    summary: DailyLearningSummary,
    *,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> Path:
    path = Path(output_dir) / f"learning_summary_{summary.summary_date.isoformat()}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(summary.markdown, encoding="utf-8")
    return path


def summarize_daily_learning(
    summary_date: str | date | datetime,
    *,
    repository: Any | None = None,
    save: bool = True,
    write_markdown: bool = False,
    output_dir: str | Path | None = None,
) -> DailyLearningSummaryResult:
    summary = load_daily_learning_summary(summary_date, repository=repository)
    summary_id = save_daily_learning_summary(summary, repository=repository) if save else None
    markdown_path = (
        write_daily_learning_markdown(summary, output_dir=output_dir or DEFAULT_OUTPUT_DIR)
        if write_markdown
        else None
    )
    return DailyLearningSummaryResult(summary=summary, summary_id=summary_id, markdown_path=markdown_path)


def _counter_rows(counter: Counter[str], *, limit: int = 10) -> list[dict[str, Any]]:
    return [
        {"value": value, "count": count}
        for value, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:limit]
        if value
    ]


def _render_markdown(summary_date: date, event_count: int, payload: Mapping[str, Any]) -> str:
    lines = [
        f"# Agent Adda Daily Learning Summary - {summary_date.isoformat()}",
        "",
    ]
    if event_count == 0:
        lines.append(f"No learning activity was logged for {summary_date.isoformat()}.")
        lines.append("")
        return "\n".join(lines)

    lines.extend([f"Events logged: {event_count}", ""])
    for title, key in [
        ("Top Intents", "top_intents"),
        ("Top Entities", "top_entities"),
        ("Commands Run", "commands_run"),
        ("Tools Used", "tools_used"),
        ("Artifacts Created", "artifacts_created"),
        ("Failures", "failures"),
        ("Report Issues", "report_issues"),
        ("Missing Evidence", "missing_evidence"),
        ("Workflow Chains", "workflow_counts"),
    ]:
        lines.append(f"## {title}")
        rows = list(payload.get(key) or [])
        if rows:
            lines.extend(f"- {row['value']}: {row['count']}" for row in rows)
        else:
            lines.append("- None")
        lines.append("")

    lines.append("## Successful Workflows")
    lines.extend(_workflow_lines(payload.get("successful_workflows") or []))
    lines.append("")
    lines.append("## Failed Workflows")
    lines.extend(_workflow_lines(payload.get("failed_workflows") or []))
    lines.append("")
    return "\n".join(lines)


def _workflow_lines(workflows: list[Mapping[str, Any]]) -> list[str]:
    if not workflows:
        return ["- None"]
    return [f"- {workflow.get('chain_type')} ({workflow.get('chain_id')})" for workflow in workflows]


def _chain_identity(chain: Mapping[str, Any]) -> tuple[int, str, list[str]]:
    payload = chain.get("chain_payload") if isinstance(chain.get("chain_payload"), Mapping) else {}
    chain_id = int(chain.get("chain_id") or payload.get("chain_id") or 0)
    chain_type = str(payload.get("chain_type") or chain.get("chain_type") or "").strip()
    errors = _strings(payload.get("errors") or chain.get("errors"))
    return chain_id, chain_type, errors


def _is_report_issue(error: str, event: Mapping[str, Any]) -> bool:
    text = f"{error} {' '.join(_strings(event.get('artifacts')))} {event.get('raw_query') or ''}".lower()
    return "report" in text or "html" in text or "percentage" in text or "link" in text


def _strings(value: Any) -> list[str]:
    if value in (None, "", {}, []):
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [str(value)]
    if isinstance(value, (list, tuple, set, frozenset)):
        return [str(item) for item in value if str(item)]
    return [str(value)]


def _to_date(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value), "%Y-%m-%d").date()
