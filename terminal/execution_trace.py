"""Structured execution trace events for Agent Adda workflows."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TraceEvent:
    event_type: str
    label: str
    status: str | None = None
    detail: str | None = None
    tool_name: str | None = None
    row_count: int | None = None
    before_count: int | None = None
    after_count: int | None = None
    artifact_type: str | None = None
    artifact_path: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        data = {
            "event_type": self.event_type,
            "label": self.label,
            "status": self.status,
            "detail": self.detail,
            "tool_name": self.tool_name,
            "row_count": self.row_count,
            "before_count": self.before_count,
            "after_count": self.after_count,
            "artifact_type": self.artifact_type,
            "artifact_path": self.artifact_path,
            "error": self.error,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }
        return {k: v for k, v in data.items() if v not in (None, {}, [])}


@dataclass
class ExecutionTrace:
    workflow_kind: str
    command: str | None = None
    workflow_id: str = field(default_factory=lambda: uuid4().hex[:12])
    profile_snapshot: dict[str, Any] = field(default_factory=dict)
    started_at: str = field(default_factory=_now_iso)
    completed_at: str | None = None
    status: str = "running"
    events: list[TraceEvent] = field(default_factory=list)
    source_trail: list[str] = field(default_factory=list)

    @classmethod
    def start(
        cls,
        workflow_kind: str,
        *,
        command: str | None = None,
        profile_snapshot: dict[str, Any] | None = None,
    ) -> "ExecutionTrace":
        trace = cls(
            workflow_kind=workflow_kind,
            command=command,
            profile_snapshot=profile_snapshot or {},
        )
        trace.events.append(TraceEvent("workflow_started", workflow_kind, status="running", detail=command))
        return trace

    def add_step(self, label: str, *, detail: str | None = None, status: str = "ok") -> TraceEvent:
        event = TraceEvent("step_started", label, status=status, detail=detail)
        self.events.append(event)
        return event

    def add_tool_result(
        self,
        tool_name: str,
        *,
        status: str,
        row_count: int | None = None,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TraceEvent:
        event_type = "tool_failed" if status in {"failed", "error"} or error else "tool_succeeded"
        event = TraceEvent(
            event_type,
            tool_name,
            status=status,
            tool_name=tool_name,
            row_count=row_count,
            error=error,
            metadata=metadata or {},
        )
        self.events.append(event)
        if tool_name not in self.source_trail:
            self.source_trail.append(tool_name)
        return event

    def add_filter_count(self, label: str, *, before: int, after: int, detail: str | None = None) -> TraceEvent:
        event = TraceEvent(
            "filter_applied",
            label,
            status="ok",
            detail=detail,
            before_count=before,
            after_count=after,
        )
        self.events.append(event)
        return event

    def add_artifact(self, artifact_type: str, path: str, *, label: str | None = None) -> TraceEvent:
        event = TraceEvent(
            "artifact_written",
            label or artifact_type,
            status="ok",
            artifact_type=artifact_type,
            artifact_path=path,
        )
        self.events.append(event)
        return event

    def add_verification(self, label: str, status: str, detail: str | None = None) -> TraceEvent:
        event = TraceEvent("verification", label, status=status, detail=detail)
        self.events.append(event)
        return event

    def complete(self, *, status: str = "ok") -> None:
        self.status = status
        self.completed_at = _now_iso()
        self.events.append(TraceEvent("workflow_completed", self.workflow_kind, status=status))

    def summary_counts(self) -> dict[str, int]:
        return {
            "tools_ok": sum(1 for e in self.events if e.event_type == "tool_succeeded"),
            "tools_failed": sum(1 for e in self.events if e.event_type == "tool_failed"),
            "filters": sum(1 for e in self.events if e.event_type == "filter_applied"),
            "artifacts": sum(1 for e in self.events if e.event_type == "artifact_written"),
            "verification_pass": sum(1 for e in self.events if e.event_type == "verification" and e.status == "pass"),
            "verification_fail": sum(1 for e in self.events if e.event_type == "verification" and e.status == "fail"),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "workflow_kind": self.workflow_kind,
            "command": self.command,
            "profile_snapshot": self.profile_snapshot,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "events": [e.to_dict() for e in self.events],
            "source_trail": list(self.source_trail),
            "summary": self.summary_counts(),
        }

