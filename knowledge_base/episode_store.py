"""Real episode logging for Agent Adda.

This records *actual executions* (tools/commands) as append-only JSONL events.
It is safe-by-default:
- writes only to repo `data/knowledge_base/episodes/`
- does not capture stdout/stderr by default (can be added explicitly later)

Episode = a workflow run (e.g., "build midday report", "validate report", "deploy").
Event  = a single log record inside an episode (step/validator/artifact/status).
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._common import DATA_DIR, now_iso, safe_filename


EPISODES_DIR = DATA_DIR / "knowledge_base" / "episodes"
EVENTS_JSONL = EPISODES_DIR / "events.jsonl"


def _env_snapshot(keys: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k in keys:
        v = os.environ.get(k)
        if v:
            out[k] = "[set]" if "KEY" in k or "TOKEN" in k or "PASSWORD" in k else v
    return out


@dataclass(frozen=True)
class EpisodeHandle:
    episode_id: str

    @staticmethod
    def from_env() -> "EpisodeHandle | None":
        eid = (os.environ.get("AGENT_ADDA_EPISODE_ID") or "").strip()
        return EpisodeHandle(episode_id=eid) if eid else None


def active_episode_id() -> str:
    return (os.environ.get("AGENT_ADDA_EPISODE_ID") or "").strip()


class EpisodeStore:
    def __init__(self, *, events_path: Path | None = None) -> None:
        self._path = events_path or EVENTS_JSONL
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _append(self, event: dict[str, Any]) -> None:
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")

    def start_episode(
        self,
        *,
        goal: str,
        caller: str,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EpisodeHandle:
        eid = str(uuid.uuid4())
        self._append(
            {
                "ts": now_iso(),
                "type": "episode_start",
                "episode_id": eid,
                "goal": goal[:500],
                "caller": caller[:80],
                "tags": tags or [],
                "metadata": metadata or {},
                "env": _env_snapshot(["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "KB_EMBED_BACKEND"]),
            }
        )
        return EpisodeHandle(episode_id=eid)

    def log_step(
        self,
        handle: EpisodeHandle,
        *,
        step: str,
        tool_name: str = "",
        tool_args: dict[str, Any] | None = None,
        status: str = "info",
        result: dict[str, Any] | None = None,
    ) -> None:
        self._append(
            {
                "ts": now_iso(),
                "type": "step",
                "episode_id": handle.episode_id,
                "step": step[:800],
                "tool_name": tool_name[:120],
                "tool_args": tool_args or {},
                "status": status,
                "result": result or {},
            }
        )

    def log_validator(
        self,
        handle: EpisodeHandle,
        *,
        name: str,
        ok: bool,
        details: dict[str, Any] | None = None,
    ) -> None:
        self._append(
            {
                "ts": now_iso(),
                "type": "validator",
                "episode_id": handle.episode_id,
                "name": name[:120],
                "ok": bool(ok),
                "details": details or {},
            }
        )

    def log_artifact(
        self,
        handle: EpisodeHandle,
        *,
        artifact_type: str,
        locator: str,
        meta: dict[str, Any] | None = None,
    ) -> None:
        self._append(
            {
                "ts": now_iso(),
                "type": "artifact",
                "episode_id": handle.episode_id,
                "artifact_type": artifact_type[:80],
                "locator": locator[:2000],
                "meta": meta or {},
            }
        )

    def end_episode(
        self,
        handle: EpisodeHandle,
        *,
        status: str,
        summary: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._append(
            {
                "ts": now_iso(),
                "type": "episode_end",
                "episode_id": handle.episode_id,
                "status": status,
                "summary": summary[:1500],
                "metadata": metadata or {},
            }
        )


def episode_log_path() -> str:
    return str(EVENTS_JSONL)


def episode_export_path(name: str) -> Path:
    """Return a safe JSONL export path under episodes/exports."""
    exports = EPISODES_DIR / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    return exports / f"{safe_filename(name)}.jsonl"


__all__ = ["EpisodeStore", "EpisodeHandle", "episode_log_path", "episode_export_path"]
