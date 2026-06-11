"""Deterministic /debug workflow."""

from __future__ import annotations

from .common import command_arg, strip_flags


def render_debug(issue: str, *, apply_requested: bool = False) -> str:
    issue = (issue or "").strip() or "unspecified issue"
    apply_note = (
        "The `--apply` flag was requested, but this MVP only produces an investigation plan."
        if apply_requested
        else "No files will be modified by this command."
    )
    return "\n".join([
        "# Debug Plan",
        "",
        f"**Issue:** {issue}",
        "",
        "**Investigation Steps**",
        "1. Reproduce the issue with the smallest command or artifact path.",
        "2. Inspect the rendered artifact and the source data feeding it.",
        "3. Trace command routing, renderer selection, and generated links.",
        "4. Isolate whether the fault is data absence, path generation, stale artifact, or renderer logic.",
        "5. Propose the smallest fix and its regression test.",
        "6. Run focused tests and one smoke command before claiming fixed.",
        "",
        "**Candidate Files And Commands**",
        "- `nse_agent.py` for command dispatch.",
        "- `terminal/renderers/` for terminal/report rendering.",
        "- `reports/latest/` for generated artifacts.",
        "- `rg -n \"<broken text or link>\" reports terminal tests`",
        "- `.venv/bin/python -m pytest <focused test> -q`",
        "",
        "**Guardrail**",
        apply_note,
    ])


def handle_debug_command(command: str) -> str:
    issue, flags = strip_flags(command_arg(command, "debug"), ("--apply",))
    return render_debug(issue, apply_requested="--apply" in flags)
