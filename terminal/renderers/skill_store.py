"""Visible renderer for Skill Store runtime assessment traces."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


def render_skill_store_trace(
    console: Console,
    assessment: Any,
    *,
    expanded: bool = False,
) -> None:
    """Render an operational Skill Store trace without exposing private reasoning."""
    payload = _payload(assessment)
    trace = _mapping(payload.get("trace"))
    reviewer = _mapping(trace.get("reviewer_decision"))
    findings = _strings(reviewer.get("findings"))
    missing_inputs = _strings(payload.get("missing_inputs") or reviewer.get("missing_inputs"))
    candidates = [_mapping(item) for item in _list(trace.get("retrieved_candidates"))]

    selected_skill_id = _text(payload.get("selected_skill_id") or reviewer.get("selected_skill_id"))
    selected_version = payload.get("selected_version") or reviewer.get("selected_version")
    decision = _text(payload.get("decision") or reviewer.get("decision") or "-")
    confidence = _float(payload.get("confidence", reviewer.get("confidence")))
    reason = _text(reviewer.get("reason") or "-")

    summary = Table.grid(padding=(0, 2))
    summary.add_column(style="bold cyan", no_wrap=True)
    summary.add_column()
    summary.add_row("Decision", decision)
    summary.add_row("Confidence", _pct(confidence))
    if selected_skill_id:
        summary.add_row("Selected", f"{selected_skill_id} v{selected_version or 1}")
    summary.add_row("Why selected", reason)
    summary.add_row("Retrieved", str(trace.get("retrieved_count") or len(candidates) or 0))
    summary.add_row("Validation", _validation_status(findings))

    sections: list[Any] = [summary]
    if missing_inputs:
        sections.append(_lines_block("Missing inputs", missing_inputs))
    if payload.get("clarification_question"):
        sections.append(Text(f"Clarification: {_text(payload.get('clarification_question'))}", style="yellow"))

    missing_evidence = _missing_evidence(findings)
    if missing_evidence:
        sections.append(_lines_block("Missing evidence", missing_evidence))

    missing_outputs = _missing_outputs(findings)
    if missing_outputs:
        sections.append(_lines_block("Missing outputs", missing_outputs))

    validation_findings = _validation_findings(findings)
    if validation_findings:
        sections.append(_lines_block("Validation findings", validation_findings))

    sections.append(_lines_block("Source trail", _source_trail(trace, reviewer)))

    evidence_plan = _evidence_plan(candidates, selected_skill_id)
    if evidence_plan:
        sections.append(_lines_block("Evidence plan", evidence_plan))

    plan_preview = _strings(payload.get("plan_preview"))
    if plan_preview:
        sections.append(_numbered_block("Plan preview", plan_preview))

    if candidates and (expanded or len(candidates) > 1):
        sections.append(_candidate_table(candidates, expanded=expanded))

    console.print(
        Panel(
            Group(*sections),
            title="[bold cyan]Skill Store Trace[/bold cyan]",
            border_style="cyan",
            box=box.ROUNDED,
        )
    )


def _payload(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "to_dict"):
        return dict(value.to_dict())
    if isinstance(value, Mapping):
        return dict(value)
    return dict(value)


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _list(value: Any) -> list[Any]:
    if value in (None, "", {}, ()):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _strings(value: Any) -> list[str]:
    return [_text(item) for item in _list(value) if _text(item)]


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _float(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))


def _pct(value: float) -> str:
    return f"{round(value * 100):.0f}%"


def _validation_status(findings: list[str]) -> str:
    actionable = [item for item in findings if item not in {"selected", "merge_close_complementary_candidates"}]
    if any("validation" in item or "unsafe_sql" in item or "contract_invalid" in item for item in actionable):
        return "failed"
    if actionable:
        return "attention"
    return "pass"


def _source_trail(trace: dict[str, Any], reviewer: dict[str, Any]) -> list[str]:
    retrieved = trace.get("retrieved_count") or 0
    rerank = _mapping(trace.get("rerank"))
    rerank_reason = _text(rerank.get("reason") or "completed")
    review_decision = _text(reviewer.get("decision") or "-")
    return [
        f"skill_store.retrieve: {retrieved} candidate(s)",
        f"skill_store.rerank: {rerank_reason}",
        f"skill_store.review: {review_decision}",
    ]


def _missing_evidence(findings: list[str]) -> list[str]:
    prefixes = ("missing_table:", "missing_tool:")
    return [item.split(":", 1)[1] for item in findings if item.startswith(prefixes)]


def _missing_outputs(findings: list[str]) -> list[str]:
    return [item.split(":", 1)[1] for item in findings if item.startswith("missing_output_contract:")]


def _validation_findings(findings: list[str]) -> list[str]:
    return [
        item
        for item in findings
        if "validation" in item or "unsafe_sql" in item or "contract_invalid" in item
    ]


def _evidence_plan(candidates: list[dict[str, Any]], selected_skill_id: str) -> list[str]:
    candidate = _selected_candidate(candidates, selected_skill_id)
    if not candidate:
        return []
    metadata = _mapping(candidate.get("metadata"))
    tables = _strings(metadata.get("available_tables") or candidate.get("available_tables"))
    tools = _strings(metadata.get("available_tools") or candidate.get("available_tools"))
    outputs = _strings(metadata.get("output_contract") or candidate.get("output_contract"))
    plan: list[str] = []
    if tables:
        plan.append(f"Tables: {', '.join(tables[:6])}")
    if tools:
        plan.append(f"Tools: {', '.join(tools[:6])}")
    if outputs:
        plan.append(f"Outputs: {', '.join(outputs[:6])}")
    return plan


def _selected_candidate(candidates: list[dict[str, Any]], selected_skill_id: str) -> dict[str, Any]:
    if selected_skill_id:
        for candidate in candidates:
            if _text(candidate.get("skill_id")) == selected_skill_id:
                return candidate
    return candidates[0] if candidates else {}


def _lines_block(title: str, lines: list[str]) -> Text:
    text = Text(f"\n{title}\n", style="bold")
    for item in lines:
        text.append(f"  - {item}\n")
    return text


def _numbered_block(title: str, lines: list[str]) -> Text:
    text = Text(f"\n{title}\n", style="bold")
    for index, item in enumerate(lines, start=1):
        text.append(f"  {index}. {item}\n")
    return text


def _candidate_table(candidates: list[dict[str, Any]], *, expanded: bool) -> Table:
    table = Table(title="Top candidates", box=box.SIMPLE_HEAD, show_header=True, header_style="bold cyan")
    table.add_column("Skill", min_width=30)
    table.add_column("Status", min_width=10)
    table.add_column("Confidence", justify="right", min_width=10)
    table.add_column("Tags", min_width=20)
    if expanded:
        table.add_column("Domain", min_width=16)

    for candidate in candidates[:10 if expanded else 3]:
        tags = _strings(candidate.get("matched_tags"))
        table.add_row(
            f"{_text(candidate.get('skill_id'))} v{candidate.get('version') or 1}",
            _text(candidate.get("status") or "-"),
            _pct(_float(candidate.get("confidence", candidate.get("score")))),
            ", ".join(tags[:5]) if tags else "-",
            *([_text(candidate.get("domain") or "-")] if expanded else []),
        )
    return table
