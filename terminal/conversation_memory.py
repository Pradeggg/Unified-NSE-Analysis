"""PostgreSQL-backed conversation memory for Agent Adda.

The memory has two layers:
1. raw_events: lossless per-turn archive payloads suitable for audit/recovery.
2. entities/snapshot: compact deterministic working memory for context binding.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from psycopg2.extras import Json

from .router.context import (
    ActiveReport,
    ActiveWorkflow,
    ContextPack,
    PendingOption,
    RecentTurn,
    WorkflowStep,
)
from .situation_assessment import TurnContext


DEFAULT_DSN = os.environ.get("AGENT_ADDA_PG_DSN") or os.environ.get("PG_DSN") or "dbname=nse_market user=nse_admin host=/tmp"
DEFAULT_SESSION_ID = os.environ.get("AGENT_ADDA_MEMORY_SESSION_ID", "agent_adda_default")


SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS agent_memory;

CREATE TABLE IF NOT EXISTS agent_memory.turn_events (
    id             BIGSERIAL PRIMARY KEY,
    session_id     TEXT NOT NULL,
    turn_index     INTEGER NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_input     TEXT NOT NULL,
    answer         TEXT NOT NULL,
    intent         TEXT,
    mode           TEXT,
    source_label   TEXT,
    freshness      TEXT,
    result_type    TEXT,
    result_summary TEXT,
    symbols        TEXT[] NOT NULL DEFAULT '{}',
    result_items   TEXT[] NOT NULL DEFAULT '{}',
    tool_names     TEXT[] NOT NULL DEFAULT '{}',
    tool_results   JSONB NOT NULL DEFAULT '[]'::jsonb,
    turn_context   JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (session_id, turn_index)
);

CREATE TABLE IF NOT EXISTS agent_memory.session_snapshots (
    session_id  TEXT PRIMARY KEY,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    turn_count  INTEGER NOT NULL DEFAULT 0,
    memory_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_agent_memory_turn_events_session_turn
    ON agent_memory.turn_events (session_id, turn_index DESC);
CREATE INDEX IF NOT EXISTS idx_agent_memory_turn_events_symbols
    ON agent_memory.turn_events USING GIN (symbols);
"""


@dataclass
class MemoryEvent:
    turn_index: int
    user_input: str
    answer: str
    intent: str = ""
    mode: str = ""
    source_label: str = ""
    freshness: str = ""
    result_type: str = ""
    result_summary: str = ""
    symbols: list[str] = field(default_factory=list)
    result_items: list[str] = field(default_factory=list)
    tool_names: list[str] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_index": self.turn_index,
            "user_input": self.user_input,
            "answer": self.answer,
            "intent": self.intent,
            "mode": self.mode,
            "source_label": self.source_label,
            "freshness": self.freshness,
            "result_type": self.result_type,
            "result_summary": self.result_summary,
            "symbols": list(self.symbols),
            "result_items": list(self.result_items),
            "tool_names": list(self.tool_names),
            "tool_results": _jsonable(self.tool_results),
        }


@dataclass
class EntityMemory:
    symbol: str
    latest_stance: str = "unknown"
    evidence: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    source_label: str = ""
    freshness: str = ""
    last_summary: str = ""
    report_paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "latest_stance": self.latest_stance,
            "evidence": list(self.evidence),
            "contradictions": list(self.contradictions),
            "source_label": self.source_label,
            "freshness": self.freshness,
            "last_summary": self.last_summary,
            "report_paths": list(self.report_paths),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EntityMemory":
        return cls(
            symbol=str(data.get("symbol") or "").upper(),
            latest_stance=str(data.get("latest_stance") or "unknown"),
            evidence=[str(v) for v in data.get("evidence") or []],
            contradictions=[str(v) for v in data.get("contradictions") or []],
            source_label=str(data.get("source_label") or ""),
            freshness=str(data.get("freshness") or ""),
            last_summary=str(data.get("last_summary") or ""),
            report_paths=[str(v) for v in data.get("report_paths") or []],
        )


@dataclass
class ConversationMemory:
    session_id: str = DEFAULT_SESSION_ID
    raw_events: list[MemoryEvent] = field(default_factory=list)
    raw_event_count: int = 0
    entities: dict[str, EntityMemory] = field(default_factory=dict)
    report_paths: list[str] = field(default_factory=list)
    last_focus_symbols: list[str] = field(default_factory=list)
    last_focus_summary: str = ""
    # AA-UR-2: lossless structured context for the unified router.
    active_indices: list[str] = field(default_factory=list)
    active_sectors: list[str] = field(default_factory=list)
    active_reports: list[ActiveReport] = field(default_factory=list)
    active_workflows: dict[str, ActiveWorkflow] = field(default_factory=dict)
    pending_options: list[PendingOption] = field(default_factory=list)
    source_trails: list[dict[str, Any]] = field(default_factory=list)
    current_workflow_id: str = ""

    def record_turn(
        self,
        user_input: str,
        answer: str,
        tool_results: list[dict[str, Any]],
        turn_context: TurnContext | None = None,
    ) -> MemoryEvent:
        turn_index = self.raw_event_count + 1
        ctx = turn_context
        tool_names = [str(item.get("tool") or "") for item in tool_results if item.get("tool")]
        event = MemoryEvent(
            turn_index=turn_index,
            user_input=user_input,
            answer=answer,
            intent=ctx.intent if ctx else "",
            mode=ctx.mode if ctx else "",
            source_label=ctx.source_label if ctx else "",
            freshness=ctx.freshness or "" if ctx else "",
            result_type=ctx.result_type or "" if ctx else "",
            result_summary=ctx.result_summary or "" if ctx else "",
            symbols=list(ctx.symbols) if ctx else _symbols_from_tool_results(tool_results),
            result_items=list(ctx.result_items) if ctx else [],
            tool_names=list(ctx.tools) if ctx and ctx.tools else tool_names,
            tool_results=_jsonable(tool_results),
        )
        self.raw_events.append(event)
        self.raw_event_count = turn_index
        if len(self.raw_events) > 200:
            self.raw_events = self.raw_events[-200:]

        if ctx:
            self._merge_turn_context(ctx)
        return event

    def _merge_turn_context(self, ctx: TurnContext) -> None:
        if ctx.symbols:
            self.last_focus_symbols = _dedupe(ctx.symbols)
        if ctx.result_summary:
            self.last_focus_summary = ctx.result_summary
        for path in _report_paths(ctx.result_items):
            if path not in self.report_paths:
                self.report_paths.append(path)

        for symbol in ctx.symbols:
            sym = str(symbol).upper()
            entity = self.entities.get(sym) or EntityMemory(symbol=sym)
            entity.source_label = ctx.source_label or entity.source_label
            entity.freshness = ctx.freshness or entity.freshness
            entity.last_summary = ctx.result_summary or entity.last_summary
            entity.latest_stance = _infer_stance(ctx.result_summary)
            for item in _extract_evidence(ctx.result_summary):
                if item not in entity.evidence:
                    entity.evidence.append(item)
            for item in _extract_contradictions(ctx.result_summary):
                if item not in entity.contradictions:
                    entity.contradictions.append(item)
            for path in _report_paths(ctx.result_items):
                if path not in entity.report_paths:
                    entity.report_paths.append(path)
            self.entities[sym] = entity

    def compressed_summary(self, max_symbols: int = 8) -> str:
        pieces: list[str] = []
        if self.last_focus_symbols:
            pieces.append(f"Last focus: {', '.join(self.last_focus_symbols)}.")
        for entity in list(self.entities.values())[:max_symbols]:
            bits = [entity.symbol]
            if entity.latest_stance and entity.latest_stance != "unknown":
                bits.append(f"stance={entity.latest_stance}")
            if entity.evidence:
                bits.append("evidence=" + ", ".join(entity.evidence[:6]))
            if entity.contradictions:
                bits.append("conflicts=" + ", ".join(entity.contradictions[:3]))
            if entity.freshness:
                bits.append(f"freshness={entity.freshness}")
            pieces.append("; ".join(bits) + ".")
        if self.report_paths:
            pieces.append("Reports: " + ", ".join(self.report_paths[-5:]) + ".")
        return " ".join(pieces) or "No compressed memory yet."

    def context_for_query(self, query: str, *, mode: str, source_label: str) -> TurnContext | None:
        symbols = _symbols_for_query(query, self)
        if not symbols:
            return None
        summaries = []
        tools: list[str] = []
        result_items: list[str] = []
        for symbol in symbols:
            entity = self.entities.get(symbol)
            if not entity:
                continue
            summaries.append(entity.last_summary or f"Memory for {symbol}.")
            result_items.extend(entity.report_paths)
        result_items.extend(self.report_paths[-5:])
        return TurnContext(
            user_input="compressed conversation memory",
            intent="conversation_memory",
            mode=mode,
            tools=tools,
            source_label=source_label,
            result_type="conversation_memory",
            result_summary=" ".join(summaries) or self.compressed_summary(),
            symbols=symbols,
            result_items=_dedupe(result_items),
        )

    # ------------------------------------------------------------------
    # AA-UR-2 — Structured context (workflows / reports / pending options)
    # ------------------------------------------------------------------
    def register_active_indices(self, indices: list[str]) -> None:
        for idx in indices:
            value = str(idx).upper().strip()
            if value and value not in self.active_indices:
                self.active_indices.append(value)

    def register_active_sectors(self, sectors: list[str]) -> None:
        for sec in sectors:
            value = str(sec).upper().strip()
            if value and value not in self.active_sectors:
                self.active_sectors.append(value)

    def register_report(
        self,
        path: str,
        *,
        report_type: str = "",
        symbol: str = "",
    ) -> ActiveReport:
        """Register a generated report addressable by (path, type, symbol)."""
        if not path:
            raise ValueError("register_report requires a non-empty path")
        sym = (symbol or "").upper().strip()
        # Idempotent on path: replace prior row for the same path.
        self.active_reports = [r for r in self.active_reports if r.path != path]
        report = ActiveReport(path=path, report_type=report_type, symbol=sym)
        self.active_reports.append(report)
        if path not in self.report_paths:
            self.report_paths.append(path)
        return report

    def start_workflow(self, workflow_id: str, kind: str) -> ActiveWorkflow:
        if workflow_id in self.active_workflows:
            return self.active_workflows[workflow_id]
        wf = ActiveWorkflow(workflow_id=workflow_id, kind=kind)
        self.active_workflows[workflow_id] = wf
        self.current_workflow_id = workflow_id
        return wf

    def append_workflow_step(
        self,
        workflow_id: str,
        step: WorkflowStep,
    ) -> ActiveWorkflow:
        wf = self.active_workflows.get(workflow_id)
        if wf is None:
            raise KeyError(f"workflow {workflow_id!r} is not active")
        updated = wf.append_step(step)
        self.active_workflows[workflow_id] = updated
        return updated

    def close_workflow(self, workflow_id: str) -> ActiveWorkflow:
        wf = self.active_workflows.get(workflow_id)
        if wf is None:
            raise KeyError(f"workflow {workflow_id!r} is not active")
        closed = wf.close()
        self.active_workflows[workflow_id] = closed
        if self.current_workflow_id == workflow_id:
            self.current_workflow_id = ""
        return closed

    def register_pending_options(self, options: list[PendingOption]) -> None:
        """Replace the pending NEXT OPTIONS for this session."""
        seen: set[str] = set()
        deduped: list[PendingOption] = []
        for opt in options:
            key = opt.label.strip().lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(opt)
        self.pending_options = deduped

    def consume_pending_option(self, label: str) -> PendingOption | None:
        target = (label or "").strip().lower()
        if not target:
            return None
        for idx, opt in enumerate(self.pending_options):
            if opt.label.strip().lower() == target:
                self.pending_options.pop(idx)
                return opt
        return None

    def record_source_trail(
        self,
        source_label: str,
        freshness: str = "",
        *,
        meta: dict[str, Any] | None = None,
    ) -> None:
        if not source_label:
            return
        entry: dict[str, Any] = {
            "source_label": source_label,
            "freshness": freshness,
        }
        if meta:
            entry["meta"] = dict(meta)
        self.source_trails.append(entry)
        if len(self.source_trails) > 200:
            self.source_trails = self.source_trails[-200:]

    def build_context_pack(self, *, depth: int = 5) -> ContextPack:
        """Project the current memory state into a router-friendly ContextPack."""
        if depth < 0:
            depth = 0
        recent_events = self.raw_events[-depth:] if depth else []
        recent_turns = tuple(
            RecentTurn(
                turn_index=event.turn_index,
                user_input=event.user_input,
                intent=event.intent,
                symbols=tuple(str(s).upper() for s in event.symbols),
                tools=tuple(event.tool_names),
                result_type=event.result_type,
                source_label=event.source_label,
                freshness=event.freshness,
                report_paths=tuple(_report_paths(event.result_items)),
            )
            for event in recent_events
        )

        active_symbols: list[str] = []
        for sym in self.last_focus_symbols:
            value = str(sym).upper().strip()
            if value and value not in active_symbols:
                active_symbols.append(value)
        for entity_sym in self.entities.keys():
            if entity_sym not in active_symbols:
                active_symbols.append(entity_sym)

        workflow_id = self.current_workflow_id
        active_workflow: ActiveWorkflow | None = None
        if workflow_id and workflow_id in self.active_workflows:
            active_workflow = self.active_workflows[workflow_id]
        elif self.active_workflows:
            # Fall back to the most recently updated OPEN workflow.
            open_workflows = [
                wf for wf in self.active_workflows.values() if wf.status == "open"
            ]
            if open_workflows:
                active_workflow = max(open_workflows, key=lambda wf: wf.updated_at)

        latest_freshness = ""
        if recent_events:
            for event in reversed(recent_events):
                if event.freshness:
                    latest_freshness = event.freshness
                    break

        return ContextPack(
            session_id=self.session_id,
            recent_turns=recent_turns,
            active_symbols=tuple(active_symbols),
            active_indices=tuple(self.active_indices),
            active_sectors=tuple(self.active_sectors),
            active_reports=tuple(self.active_reports),
            active_workflow=active_workflow,
            pending_options=tuple(self.pending_options),
            source_trails=tuple(dict(item) for item in self.source_trails[-50:]),
            freshness=latest_freshness,
        )

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "raw_event_count": self.raw_event_count,
            "raw_events": [event.to_dict() for event in self.raw_events[-50:]],
            "entities": {key: value.to_dict() for key, value in self.entities.items()},
            "report_paths": list(self.report_paths),
            "last_focus_symbols": list(self.last_focus_symbols),
            "last_focus_summary": self.last_focus_summary,
            "active_indices": list(self.active_indices),
            "active_sectors": list(self.active_sectors),
            "active_reports": [r.to_dict() for r in self.active_reports],
            "active_workflows": {wid: wf.to_dict() for wid, wf in self.active_workflows.items()},
            "pending_options": [opt.to_dict() for opt in self.pending_options],
            "source_trails": [dict(item) for item in self.source_trails],
            "current_workflow_id": self.current_workflow_id,
        }

    @classmethod
    def from_snapshot(cls, session_id: str, snapshot: dict[str, Any] | None) -> "ConversationMemory":
        data = snapshot or {}
        memory = cls(session_id=session_id)
        memory.raw_event_count = int(data.get("raw_event_count") or 0)
        memory.raw_events = [
            MemoryEvent(**event)
            for event in data.get("raw_events") or []
            if isinstance(event, dict)
        ]
        memory.entities = {
            str(key).upper(): EntityMemory.from_dict(value)
            for key, value in (data.get("entities") or {}).items()
            if isinstance(value, dict)
        }
        memory.report_paths = [str(v) for v in data.get("report_paths") or []]
        memory.last_focus_symbols = [str(v).upper() for v in data.get("last_focus_symbols") or []]
        memory.last_focus_summary = str(data.get("last_focus_summary") or "")
        memory.active_indices = [str(v).upper() for v in data.get("active_indices") or []]
        memory.active_sectors = [str(v).upper() for v in data.get("active_sectors") or []]
        memory.active_reports = [
            ActiveReport.from_dict(item)
            for item in data.get("active_reports") or []
            if isinstance(item, dict)
        ]
        memory.active_workflows = {
            str(wid): ActiveWorkflow.from_dict(payload)
            for wid, payload in (data.get("active_workflows") or {}).items()
            if isinstance(payload, dict)
        }
        memory.pending_options = [
            PendingOption.from_dict(item)
            for item in data.get("pending_options") or []
            if isinstance(item, dict)
        ]
        memory.source_trails = [
            dict(item) for item in data.get("source_trails") or [] if isinstance(item, dict)
        ]
        memory.current_workflow_id = str(data.get("current_workflow_id") or "")
        return memory

    def save_to_postgres(self, dsn: str | None = None) -> dict[str, Any]:
        conn = connect(dsn)
        ensure_memory_schema(conn, commit=False)
        event = self.raw_events[-1] if self.raw_events else None
        with conn.cursor() as cur:
            if event:
                cur.execute(
                    """
                    INSERT INTO agent_memory.turn_events (
                        session_id, turn_index, user_input, answer, intent, mode,
                        source_label, freshness, result_type, result_summary,
                        symbols, result_items, tool_names, tool_results, turn_context
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (session_id, turn_index) DO UPDATE SET
                        user_input=EXCLUDED.user_input,
                        answer=EXCLUDED.answer,
                        intent=EXCLUDED.intent,
                        mode=EXCLUDED.mode,
                        source_label=EXCLUDED.source_label,
                        freshness=EXCLUDED.freshness,
                        result_type=EXCLUDED.result_type,
                        result_summary=EXCLUDED.result_summary,
                        symbols=EXCLUDED.symbols,
                        result_items=EXCLUDED.result_items,
                        tool_names=EXCLUDED.tool_names,
                        tool_results=EXCLUDED.tool_results,
                        turn_context=EXCLUDED.turn_context
                    """,
                    (
                        self.session_id,
                        event.turn_index,
                        event.user_input,
                        event.answer,
                        event.intent,
                        event.mode,
                        event.source_label,
                        event.freshness,
                        event.result_type,
                        event.result_summary,
                        event.symbols,
                        event.result_items,
                        event.tool_names,
                        Json(event.tool_results),
                        Json(event.to_dict()),
                    ),
                )
            cur.execute(
                """
                INSERT INTO agent_memory.session_snapshots (session_id, turn_count, memory_json)
                VALUES (%s, %s, %s)
                ON CONFLICT (session_id) DO UPDATE SET
                    updated_at=now(),
                    turn_count=EXCLUDED.turn_count,
                    memory_json=EXCLUDED.memory_json
                """,
                (self.session_id, self.raw_event_count, Json(self.to_snapshot())),
            )
        conn.commit()
        return {"ok": True, "rows_inserted": 1 if event else 0, "schema": "agent_memory"}

    @classmethod
    def load_from_postgres(cls, session_id: str = DEFAULT_SESSION_ID, dsn: str | None = None) -> "ConversationMemory":
        conn = connect(dsn)
        ensure_memory_schema(conn, commit=False)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT memory_json FROM agent_memory.session_snapshots WHERE session_id=%s",
                (session_id,),
            )
            row = cur.fetchone()
        if not row:
            return cls(session_id=session_id)
        return cls.from_snapshot(session_id, row[0])


def connect(dsn: str | None = None):
    import psycopg2

    return psycopg2.connect(dsn or DEFAULT_DSN)


def ensure_memory_schema(conn, *, commit: bool = True) -> None:
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)
    if commit:
        conn.commit()


def load_memory_fail_open(session_id: str = DEFAULT_SESSION_ID) -> ConversationMemory:
    try:
        return ConversationMemory.load_from_postgres(session_id)
    except Exception:
        return ConversationMemory(session_id=session_id)


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _dedupe(values: Any) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value).strip().upper()
        if text and text not in seen:
            out.append(text)
            seen.add(text)
    return out


def _symbols_from_tool_results(tool_results: list[dict[str, Any]]) -> list[str]:
    symbols: list[str] = []
    for item in tool_results:
        for source in (item.get("args") or {}, item.get("result") or {}):
            symbol = source.get("symbol")
            if symbol:
                symbols.append(str(symbol).upper())
    return _dedupe(symbols)


def _report_paths(items: list[str]) -> list[str]:
    return [
        str(item)
        for item in items or []
        if "/" in str(item) or "\\" in str(item) or re.search(r"\.(?:html|md|pdf|json|csv)$", str(item), re.I)
    ]


def _extract_evidence(summary: str) -> list[str]:
    text = summary or ""
    evidence: list[str] = []
    for pattern in (
        r"\bSELL\b",
        r"\bBUY\b",
        r"\bHOLD\b",
        r"\bSTAGE_[1-4]\b",
        r"\bRS\s*-?\d+(?:\.\d+)?\b",
        r"\bMACD\s+(?:bearish|bullish|neutral)\b",
        r"\bsupertrend\s+(?:SELL|BUY|HOLD)\b",
        r"low interest coverage",
        r"margin[s]? compressed",
    ):
        for match in re.finditer(pattern, text, flags=re.I):
            evidence.append(match.group(0))
    return _dedupe(evidence)


def _extract_contradictions(summary: str) -> list[str]:
    text = summary or ""
    out: list[str] = []
    match = re.search(
        r"RSI\s+snapshot\s+(\d+(?:\.\d+)?).*?technical\s+RSI\s+(\d+(?:\.\d+)?)",
        text,
        flags=re.I,
    )
    if match and match.group(1) != match.group(2):
        out.append(f"snapshot RSI {match.group(1)} vs technical RSI {match.group(2)}")
    return out


def _infer_stance(summary: str) -> str:
    lower = (summary or "").lower()
    if any(term in lower for term in ("sell", "stage_4", "weak", "bearish", "low interest coverage")):
        return "cautious_avoid_fresh_entry"
    if any(term in lower for term in ("buy", "stage_2", "bullish", "strong")):
        return "constructive_with_confirmation"
    return "neutral_watchlist"


def _symbols_for_query(query: str, memory: ConversationMemory) -> list[str]:
    q = (query or "").upper()
    explicit = [symbol for symbol in memory.entities if re.search(rf"\b{re.escape(symbol)}\b", q)]
    if explicit:
        return explicit[:5]
    if any(term in (query or "").lower() for term in ("above", "previous", "prior", "this", "that", "it", "recommendation", "approach")):
        return memory.last_focus_symbols[:5]
    return []
