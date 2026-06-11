"""Local JSON task memory for Agent Adda copilot workflows."""

from __future__ import annotations

import json
import os
import time
from copy import deepcopy
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1


def default_memory_path() -> Path:
    override = os.environ.get("AGENT_ADDA_TASK_MEMORY_PATH")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".agent_adda" / "task_memory.json"


def empty_memory() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "current_objective": "",
        "recent_commands": [],
        "recent_artifacts": [],
        "open_issues": [],
        "latest_quality_breakouts": {},
        "latest_reports": [],
        "latest_report_validation": {},
        "updated_at": "",
    }


class TaskMemoryStore:
    """Small JSON-backed store with safe recovery for corrupt state."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path).expanduser() if path is not None else default_memory_path()

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return empty_memory()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            backup = self.path.with_name(f"{self.path.name}.corrupt-{int(time.time())}")
            try:
                self.path.rename(backup)
            except Exception:
                pass
            return empty_memory()
        state = empty_memory()
        if isinstance(raw, dict):
            state.update(raw)
        state["schema_version"] = SCHEMA_VERSION
        for key in ("recent_commands", "recent_artifacts", "open_issues", "latest_reports"):
            if not isinstance(state.get(key), list):
                state[key] = []
        for key in ("latest_quality_breakouts", "latest_report_validation"):
            if not isinstance(state.get(key), dict):
                state[key] = {}
        return state

    def save(self, state: dict[str, Any]) -> dict[str, Any]:
        next_state = empty_memory()
        next_state.update(deepcopy(state or {}))
        next_state["schema_version"] = SCHEMA_VERSION
        next_state["updated_at"] = _now()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(next_state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return next_state

    def clear(self) -> dict[str, Any]:
        return self.save(empty_memory())

    def set_objective(self, objective: str) -> dict[str, Any]:
        state = self.load()
        state["current_objective"] = (objective or "").strip()
        return self.save(state)

    def record_command(self, command: str) -> dict[str, Any]:
        state = self.load()
        _prepend_limited(state, "recent_commands", {"command": command, "timestamp": _now()})
        return self.save(state)

    def record_artifact(self, kind: str, path: str, *, title: str = "") -> dict[str, Any]:
        state = self.load()
        _prepend_limited(
            state,
            "recent_artifacts",
            {"kind": kind, "path": path, "title": title, "timestamp": _now()},
        )
        if kind in {"report", "report_validation"}:
            _prepend_limited(state, "latest_reports", {"kind": kind, "path": path, "title": title, "timestamp": _now()})
        return self.save(state)

    def record_quality_breakouts(self, symbols: list[str], *, source: str = "") -> dict[str, Any]:
        state = self.load()
        state["latest_quality_breakouts"] = {
            "symbols": list(symbols or []),
            "source": source,
            "timestamp": _now(),
        }
        return self.save(state)

    def record_report_validation(self, artifact: str, *, summary: dict[str, int] | None = None) -> dict[str, Any]:
        state = self.load()
        state["latest_report_validation"] = {
            "artifact": artifact,
            "summary": dict(summary or {}),
            "timestamp": _now(),
        }
        _prepend_limited(
            state,
            "recent_artifacts",
            {"kind": "report_validation", "path": artifact, "title": "Report validation", "timestamp": _now()},
        )
        return self.save(state)

    def add_issue(self, issue: str) -> dict[str, Any]:
        state = self.load()
        clean = (issue or "").strip()
        if clean:
            _prepend_limited(state, "open_issues", {"issue": clean, "timestamp": _now()})
        return self.save(state)


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _prepend_limited(state: dict[str, Any], key: str, item: dict[str, Any], limit: int = 20) -> None:
    values = state.get(key)
    if not isinstance(values, list):
        values = []
    values.insert(0, item)
    state[key] = values[:limit]
