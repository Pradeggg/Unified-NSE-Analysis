"""AA-UR-2 Context Pack — structured per-session context for the router.

The :class:`ContextPack` is the lossless view of what the agent knows
about the current session at a single point in time:

* recent_turns       — last N user/assistant turns (depth 5 by default)
* active_symbols     — symbols the user has been operating on
* active_indices     — indices the session is anchored to
* active_sectors     — sectors the session is anchored to
* active_reports     — generated reports addressable by (path, type, symbol)
* active_workflow    — multi-step "Sherlock" workflow with evidence per step
* pending_options    — NEXT OPTIONS waiting to be consumed by label
* source_trails      — observed (source_label, freshness) pairs
* freshness          — current freshness label for routing

The router consumes a ContextPack instead of the raw
:class:`terminal.conversation_memory.ConversationMemory`, so providers
can reason about structured facts rather than prose. Per AA-UR-2
acceptance: *no evidence should be sourced only from a prose summary*.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class ActiveReport:
    """A generated report addressable by path, type, and optional symbol."""

    path: str
    report_type: str = ""
    symbol: str = ""
    created_at: str = field(default_factory=_utcnow_iso)

    def __post_init__(self) -> None:
        if not self.path:
            raise ValueError("ActiveReport.path must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "report_type": self.report_type,
            "symbol": self.symbol,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ActiveReport":
        return cls(
            path=str(data.get("path") or ""),
            report_type=str(data.get("report_type") or ""),
            symbol=str(data.get("symbol") or "").upper(),
            created_at=str(data.get("created_at") or _utcnow_iso()),
        )


@dataclass(frozen=True)
class WorkflowStep:
    """One step of a Sherlock-style multi-step workflow.

    ``evidence`` is a list of structured fact dicts (NOT free prose).
    Each fact carries its own ``source_label`` and ``freshness`` so the
    final synthesis can audit provenance per step.
    """

    step_id: str
    kind: str
    summary: str = ""
    evidence: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    source_label: str = ""
    freshness: str = ""
    created_at: str = field(default_factory=_utcnow_iso)

    def __post_init__(self) -> None:
        if not self.step_id:
            raise ValueError("WorkflowStep.step_id must be non-empty")
        if not self.kind:
            raise ValueError("WorkflowStep.kind must be non-empty")
        # Normalize evidence to a tuple of frozen dict copies.
        object.__setattr__(
            self,
            "evidence",
            tuple(dict(item) for item in (self.evidence or ()) if isinstance(item, dict)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "kind": self.kind,
            "summary": self.summary,
            "evidence": [dict(item) for item in self.evidence],
            "source_label": self.source_label,
            "freshness": self.freshness,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowStep":
        return cls(
            step_id=str(data.get("step_id") or ""),
            kind=str(data.get("kind") or ""),
            summary=str(data.get("summary") or ""),
            evidence=tuple(
                dict(item) for item in (data.get("evidence") or []) if isinstance(item, dict)
            ),
            source_label=str(data.get("source_label") or ""),
            freshness=str(data.get("freshness") or ""),
            created_at=str(data.get("created_at") or _utcnow_iso()),
        )


@dataclass(frozen=True)
class ActiveWorkflow:
    """A multi-step workflow currently in flight for the session."""

    workflow_id: str
    kind: str
    status: str = "open"  # open | closed | abandoned
    steps: tuple[WorkflowStep, ...] = field(default_factory=tuple)
    started_at: str = field(default_factory=_utcnow_iso)
    updated_at: str = field(default_factory=_utcnow_iso)

    def __post_init__(self) -> None:
        if not self.workflow_id:
            raise ValueError("ActiveWorkflow.workflow_id must be non-empty")
        if not self.kind:
            raise ValueError("ActiveWorkflow.kind must be non-empty")

    @property
    def symbols(self) -> tuple[str, ...]:
        out: list[str] = []
        for step in self.steps:
            for fact in step.evidence:
                sym = str(fact.get("symbol") or "").upper()
                if sym and sym not in out:
                    out.append(sym)
        return tuple(out)

    @property
    def all_evidence(self) -> tuple[dict[str, Any], ...]:
        merged: list[dict[str, Any]] = []
        for step in self.steps:
            merged.extend(dict(item) for item in step.evidence)
        return tuple(merged)

    def append_step(self, step: WorkflowStep) -> "ActiveWorkflow":
        return ActiveWorkflow(
            workflow_id=self.workflow_id,
            kind=self.kind,
            status=self.status,
            steps=(*self.steps, step),
            started_at=self.started_at,
            updated_at=_utcnow_iso(),
        )

    def close(self) -> "ActiveWorkflow":
        return ActiveWorkflow(
            workflow_id=self.workflow_id,
            kind=self.kind,
            status="closed",
            steps=self.steps,
            started_at=self.started_at,
            updated_at=_utcnow_iso(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "kind": self.kind,
            "status": self.status,
            "steps": [step.to_dict() for step in self.steps],
            "started_at": self.started_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ActiveWorkflow":
        return cls(
            workflow_id=str(data.get("workflow_id") or ""),
            kind=str(data.get("kind") or ""),
            status=str(data.get("status") or "open"),
            steps=tuple(
                WorkflowStep.from_dict(item)
                for item in (data.get("steps") or [])
                if isinstance(item, dict)
            ),
            started_at=str(data.get("started_at") or _utcnow_iso()),
            updated_at=str(data.get("updated_at") or _utcnow_iso()),
        )


@dataclass(frozen=True)
class PendingOption:
    """A NEXT OPTION currently waiting to be executed by label (e.g. ``A``, ``1``)."""

    label: str
    text: str
    bound_action: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utcnow_iso)
    expires_at: str = ""

    def __post_init__(self) -> None:
        if not self.label:
            raise ValueError("PendingOption.label must be non-empty")
        if not self.text:
            raise ValueError("PendingOption.text must be non-empty")
        object.__setattr__(self, "bound_action", dict(self.bound_action or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "text": self.text,
            "bound_action": dict(self.bound_action),
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PendingOption":
        return cls(
            label=str(data.get("label") or ""),
            text=str(data.get("text") or ""),
            bound_action=dict(data.get("bound_action") or {}),
            created_at=str(data.get("created_at") or _utcnow_iso()),
            expires_at=str(data.get("expires_at") or ""),
        )


@dataclass(frozen=True)
class RecentTurn:
    """A compact view of one prior turn used for routing decisions."""

    turn_index: int
    user_input: str
    intent: str = ""
    symbols: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    result_type: str = ""
    source_label: str = ""
    freshness: str = ""
    report_paths: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_index": self.turn_index,
            "user_input": self.user_input,
            "intent": self.intent,
            "symbols": list(self.symbols),
            "tools": list(self.tools),
            "result_type": self.result_type,
            "source_label": self.source_label,
            "freshness": self.freshness,
            "report_paths": list(self.report_paths),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RecentTurn":
        return cls(
            turn_index=int(data.get("turn_index") or 0),
            user_input=str(data.get("user_input") or ""),
            intent=str(data.get("intent") or ""),
            symbols=tuple(str(s).upper() for s in (data.get("symbols") or [])),
            tools=tuple(str(t) for t in (data.get("tools") or [])),
            result_type=str(data.get("result_type") or ""),
            source_label=str(data.get("source_label") or ""),
            freshness=str(data.get("freshness") or ""),
            report_paths=tuple(str(p) for p in (data.get("report_paths") or [])),
        )


@dataclass(frozen=True)
class ContextPack:
    """Structured per-session context handed to the unified router."""

    session_id: str
    recent_turns: tuple[RecentTurn, ...] = ()
    active_symbols: tuple[str, ...] = ()
    active_indices: tuple[str, ...] = ()
    active_sectors: tuple[str, ...] = ()
    active_reports: tuple[ActiveReport, ...] = ()
    active_workflow: ActiveWorkflow | None = None
    pending_options: tuple[PendingOption, ...] = ()
    source_trails: tuple[dict[str, Any], ...] = ()
    freshness: str = ""

    def __post_init__(self) -> None:
        if not self.session_id:
            raise ValueError("ContextPack.session_id must be non-empty")

    @property
    def has_active_workflow(self) -> bool:
        return self.active_workflow is not None and self.active_workflow.status == "open"

    def report_for(
        self,
        *,
        path: str | None = None,
        report_type: str | None = None,
        symbol: str | None = None,
    ) -> ActiveReport | None:
        """Look up a report by any combination of (path, type, symbol).

        Returns the first match in insertion order, or ``None``. Matching
        is case-insensitive for symbol and report_type.
        """
        sym_q = (symbol or "").strip().upper() or None
        type_q = (report_type or "").strip().lower() or None
        for report in self.active_reports:
            if path and report.path != path:
                continue
            if type_q and report.report_type.lower() != type_q:
                continue
            if sym_q and report.symbol.upper() != sym_q:
                continue
            return report
        return None

    def find_pending_option(self, label: str) -> PendingOption | None:
        target = (label or "").strip().lower()
        if not target:
            return None
        for opt in self.pending_options:
            if opt.label.strip().lower() == target:
                return opt
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "recent_turns": [turn.to_dict() for turn in self.recent_turns],
            "active_symbols": list(self.active_symbols),
            "active_indices": list(self.active_indices),
            "active_sectors": list(self.active_sectors),
            "active_reports": [report.to_dict() for report in self.active_reports],
            "active_workflow": self.active_workflow.to_dict() if self.active_workflow else None,
            "pending_options": [opt.to_dict() for opt in self.pending_options],
            "source_trails": [dict(item) for item in self.source_trails],
            "freshness": self.freshness,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContextPack":
        return cls(
            session_id=str(data.get("session_id") or ""),
            recent_turns=tuple(
                RecentTurn.from_dict(item)
                for item in (data.get("recent_turns") or [])
                if isinstance(item, dict)
            ),
            active_symbols=tuple(str(s).upper() for s in (data.get("active_symbols") or [])),
            active_indices=tuple(str(s).upper() for s in (data.get("active_indices") or [])),
            active_sectors=tuple(str(s).upper() for s in (data.get("active_sectors") or [])),
            active_reports=tuple(
                ActiveReport.from_dict(item)
                for item in (data.get("active_reports") or [])
                if isinstance(item, dict)
            ),
            active_workflow=(
                ActiveWorkflow.from_dict(data["active_workflow"])
                if isinstance(data.get("active_workflow"), dict)
                else None
            ),
            pending_options=tuple(
                PendingOption.from_dict(item)
                for item in (data.get("pending_options") or [])
                if isinstance(item, dict)
            ),
            source_trails=tuple(
                dict(item) for item in (data.get("source_trails") or []) if isinstance(item, dict)
            ),
            freshness=str(data.get("freshness") or ""),
        )


__all__ = [
    "ActiveReport",
    "ActiveWorkflow",
    "ContextPack",
    "PendingOption",
    "RecentTurn",
    "WorkflowStep",
]
