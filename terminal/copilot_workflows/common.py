"""Shared helpers for deterministic copilot workflow commands."""

from __future__ import annotations

import re
from pathlib import Path


def command_arg(command: str, verb: str) -> str:
    text = (command or "").strip()
    prefix = f"/{verb}"
    if text.lower().startswith(prefix):
        return text[len(prefix):].strip()
    return text


def strip_flags(text: str, flags: tuple[str, ...]) -> tuple[str, set[str]]:
    found: set[str] = set()
    cleaned = text or ""
    for flag in flags:
        pattern = rf"(?<!\S){re.escape(flag)}(?!\S)"
        if re.search(pattern, cleaned):
            found.add(flag)
            cleaned = re.sub(pattern, " ", cleaned)
    return " ".join(cleaned.split()), found


def slugify(text: str, fallback: str = "plan") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug[:80] or fallback


def existing_path(raw: str, cwd: Path | None = None) -> Path | None:
    if not raw:
        return None
    cwd = cwd or Path.cwd()
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = cwd / candidate
    return candidate if candidate.exists() else None
