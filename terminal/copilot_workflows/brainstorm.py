"""Deterministic /brainstorm workflow."""

from __future__ import annotations

from .common import command_arg


def render_brainstorm(topic: str) -> str:
    topic = (topic or "").strip() or "unspecified topic"
    return "\n".join([
        "# Brainstorm",
        "",
        f"**Understood Topic:** {topic}",
        "",
        "**Known Context**",
        "- Treat this as design discussion, not implementation.",
        "- Preserve existing Agent Adda behavior unless the change is explicitly approved.",
        "- Prefer deterministic workflows first; use an LLM only for synthesis or wording.",
        "",
        "**Assumptions**",
        "- The goal is to clarify intent, risks, and tradeoffs before code or data changes.",
        "- Any action that mutates files, reports, data, or portfolio state needs a later approval step.",
        "",
        "**Approaches**",
        "1. Minimal: add a narrow command or behavior only for the named workflow.",
        "2. Structured: add a reusable workflow primitive with tests and help entries.",
        "3. Full copilot: add state, execution trace, verification, and resumable task memory.",
        "",
        "**Recommendation**",
        "Use the structured approach first, then promote it to the full copilot path once it proves useful.",
        "",
        "**Approval Gate**",
        "Reply with `approved` or ask for changes before implementation starts.",
    ])


def handle_brainstorm_command(command: str) -> str:
    return render_brainstorm(command_arg(command, "brainstorm"))
