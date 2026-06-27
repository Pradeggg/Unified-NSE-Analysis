from __future__ import annotations

from terminal.governance.models import GovernanceReport


def render_markdown(report: GovernanceReport) -> str:
    lines = [
        f"# Governance Evaluation - {report.symbol}",
        "",
        f"As of: {report.as_of.isoformat()}",
        f"Score: {report.score:.2f} | Rating: {report.rating} | Confidence: {report.confidence}",
        "",
        "## Component Scores",
        "",
        "| Component | Score | Status | Notes | Sources |",
        "| --- | ---: | --- | --- | --- |",
    ]

    for component in report.component_scores:
        notes = _table_cell("; ".join(component.notes) if component.notes else "-")
        sources = _table_cell(", ".join(component.source_names) if component.source_names else "-")
        lines.append(
            f"| {_table_cell(component.name)} | {component.score:.2f}/{component.max_score:.2f} | "
            f"{_table_cell(component.status)} | {notes} | {sources} |"
        )

    lines.extend(["", "## Flags"])
    if report.flags:
        lines.extend(f"- {_list_text(flag)}" for flag in report.flags)
    else:
        lines.append("- None")

    lines.extend(["", "## Missing Evidence"])
    if report.missing_evidence:
        for item in report.missing_evidence:
            reason = f" - {item.reason}" if item.reason else ""
            lines.append(f"- {_list_text(f'{item.severity}: {item.scope}/{item.subject}/{item.field}{reason}')}")
    else:
        lines.append("- None")

    lines.extend(["", "## Source Trail"])
    if report.source_trail:
        for source in report.source_trail:
            details = []
            if source.rows is not None:
                details.append(f"rows={source.rows}")
            if source.latest_date is not None:
                details.append(f"latest={source.latest_date.isoformat()}")
            if source.fallback:
                details.append("fallback")
            if source.error:
                details.append(f"error={source.error}")
            suffix = f" ({', '.join(details)})" if details else ""
            lines.append(f"- {_list_text(f'{source.name}: {source.status}{suffix}')}")
    else:
        lines.append("- None")

    if report.llm_opinion:
        lines.extend(["", "## LLM Opinion"])
        label = report.llm_opinion.get("opinion_label")
        summary = report.llm_opinion.get("summary")
        if label:
            lines.append(f"Label: {_list_text(label)}")
        if summary:
            lines.append(_list_text(summary))

    lines.extend(["", "Research-only governance evaluation. Not investment advice."])
    return "\n".join(lines)


def _single_line(value) -> str:
    return " ".join(str(value).split())


def _table_cell(value) -> str:
    return _single_line(value).replace("|", "\\|")


def _list_text(value) -> str:
    text = _single_line(value).replace("|", "\\|")
    return text.lstrip("#-* ")
