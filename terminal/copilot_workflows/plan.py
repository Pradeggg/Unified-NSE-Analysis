"""Deterministic /plan workflow."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from .common import command_arg, slugify, strip_flags


def render_plan(objective: str) -> str:
    objective = (objective or "").strip() or "unspecified objective"
    return "\n".join([
        "# Implementation Plan",
        "",
        f"**Objective:** {objective}",
        "",
        "**Files To Inspect**",
        "- `nse_agent.py` command routing and terminal output path.",
        "- `terminal/` modules related to the target workflow.",
        "- `tests/` files covering command dispatch, routing, and rendering.",
        "",
        "**Files To Modify Or Create**",
        "- Add the smallest workflow module that owns the new behavior.",
        "- Wire a thin slash-command handler in `nse_agent.py`.",
        "- Update `terminal/help.py` and slash-command autocomplete entries.",
        "",
        "**Tests To Add**",
        "- Unit tests for deterministic output and parsing.",
        "- Command registry tests for handler presence and routing.",
        "- Help smoke coverage for visible commands.",
        "",
        "**Verification Commands**",
        "- `.venv/bin/python -m pytest <focused tests> -q`",
        "- `.venv/bin/python -m py_compile <touched modules>`",
        "- Run one CLI smoke for the public command if applicable.",
        "",
        "**Risks And Rollback**",
        "- Risk: command prefix collision with existing slash commands.",
        "- Risk: workflow claims completion without verification.",
        "- Rollback: remove the new handler registration and workflow module.",
        "",
        "**Approval Gate**",
        "This plan does not execute implementation. Approve before code changes.",
    ])


def write_plan(objective: str, plans_dir: Path | None = None, today: date | None = None) -> Path:
    objective = (objective or "").strip() or "unspecified objective"
    plans_dir = plans_dir or Path("docs/superpowers/plans")
    today = today or date.today()
    plans_dir.mkdir(parents=True, exist_ok=True)
    path = plans_dir / f"{today.isoformat()}-{slugify(objective)}.md"
    if path.exists():
        raise FileExistsError(f"plan already exists: {path}")
    path.write_text(render_plan(objective) + "\n", encoding="utf-8")
    return path


def handle_plan_command(
    command: str,
    *,
    plans_dir: Path | None = None,
    today: date | None = None,
) -> str:
    objective, flags = strip_flags(command_arg(command, "plan"), ("--write",))
    output = render_plan(objective)
    if "--write" not in flags:
        return output
    path = write_plan(objective, plans_dir=plans_dir, today=today)
    return output + f"\n\n**Saved Plan:** `{path}`"
