"""Deterministic /status workflow backed by task memory."""

from __future__ import annotations

from terminal.task_memory import TaskMemoryStore


def render_status(store: TaskMemoryStore | None = None) -> str:
    store = store or TaskMemoryStore()
    state = store.load()
    if _is_empty(state):
        return "\n".join([
            "# Agent Adda Status",
            "",
            "No active task memory yet.",
            "",
            "**Useful Start Commands**",
            "- `/brainstorm <topic>` to structure the next change.",
            "- `/plan <objective>` to create an implementation-ready plan.",
            "- `/screen quality-breakouts --explain --tv` to produce a watchlist.",
            "- `/verify reports` to validate latest report artifacts.",
        ])

    lines = [
        "# Agent Adda Status",
        "",
        f"**Current Objective:** {state.get('current_objective') or 'not set'}",
        f"**Updated:** {state.get('updated_at') or 'unknown'}",
        "",
    ]

    qb = state.get("latest_quality_breakouts") or {}
    if qb.get("symbols"):
        lines.extend([
            "**Latest Quality Breakouts**",
            "- " + ", ".join(qb.get("symbols", [])[:20]),
            "",
        ])

    artifacts = state.get("recent_artifacts") or []
    if artifacts:
        lines.append("**Recent Artifacts**")
        for item in artifacts[:5]:
            lines.append(f"- {item.get('kind', 'artifact')}: `{item.get('path', '')}`")
        lines.append("")

    validation = state.get("latest_report_validation") or {}
    if validation:
        lines.extend([
            "**Latest Report Validation**",
            f"- Artifact: `{validation.get('artifact', '')}`",
            f"- Summary: {validation.get('summary', {})}",
            "",
        ])

    issues = state.get("open_issues") or []
    if issues:
        lines.append("**Open Issues**")
        for item in issues[:5]:
            lines.append(f"- {item.get('issue', '')}")
        lines.append("")

    commands = state.get("recent_commands") or []
    if commands:
        lines.append("**Recent Commands**")
        for item in commands[:5]:
            lines.append(f"- `{item.get('command', '')}`")
        lines.append("")

    lines.extend([
        "**Next Useful Commands**",
        "- `/verify reports`",
        "- `/status clear`",
    ])
    return "\n".join(lines)


def handle_status_command(command: str, *, store: TaskMemoryStore | None = None) -> str:
    store = store or TaskMemoryStore()
    if (command or "").strip().lower() == "/status clear":
        store.clear()
        return "# Agent Adda Status\n\nTask memory cleared."
    return render_status(store)


def _is_empty(state: dict) -> bool:
    return not any([
        state.get("current_objective"),
        state.get("recent_commands"),
        state.get("recent_artifacts"),
        state.get("open_issues"),
        state.get("latest_quality_breakouts"),
        state.get("latest_report_validation"),
    ])
