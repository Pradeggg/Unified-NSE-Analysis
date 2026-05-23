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

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "raw_event_count": self.raw_event_count,
            "raw_events": [event.to_dict() for event in self.raw_events[-50:]],
            "entities": {key: value.to_dict() for key, value in self.entities.items()},
            "report_paths": list(self.report_paths),
            "last_focus_symbols": list(self.last_focus_symbols),
            "last_focus_summary": self.last_focus_summary,
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
