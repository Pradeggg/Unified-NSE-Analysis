"""Deterministic /review workflow."""

from __future__ import annotations

from pathlib import Path

from .common import command_arg, existing_path


def _artifact_observation(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return [f"- Could not read `{path}`: {exc}"]
    observations = [
        f"- Artifact exists: `{path}`",
        f"- Size: {path.stat().st_size} bytes",
        f"- Lines: {text.count(chr(10)) + 1 if text else 0}",
    ]
    if "href=\"#" in text or "href='#" in text:
        observations.append("- Contains anchor-style links that need target validation.")
    if "No data" in text or "undefined" in text or "null" in text:
        observations.append("- Contains possible missing-data markers.")
    return observations


def render_review(target: str, *, cwd: Path | None = None) -> str:
    target = (target or "").strip() or "unspecified target"
    path = existing_path(target, cwd=cwd)
    findings = _artifact_observation(path) if path else [
        "- No local artifact path was resolved; review is limited to checklist mode.",
    ]
    return "\n".join([
        "# Review",
        "",
        "**Findings First**",
        *findings,
        "",
        "**Evidence Gaps**",
        "- Confirm data freshness and source timestamps.",
        "- Confirm every material claim maps to a tool result, database row, or source artifact.",
        "- Confirm links open and underlying stock/detail pages contain populated data.",
        "",
        "**Risks**",
        "- Stale generated files can look current if latest symlinks or copies were not refreshed.",
        "- Report links can render correctly while pointing to empty or missing underlying pages.",
        "",
        "**Suggested Next Checks**",
        "- Run `/debug <issue>` for any broken behavior found.",
        "- Run `/verify reports` after regenerating report artifacts.",
    ])


def handle_review_command(command: str) -> str:
    return render_review(command_arg(command, "review"))
