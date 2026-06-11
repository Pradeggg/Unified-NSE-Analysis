from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from terminal.learning.repository import LearningRepository


DEFAULT_WINDOW_MINUTES = 45


@dataclass(frozen=True)
class WorkflowChain:
    chain_type: str
    event_ids: tuple[int, ...]
    intents: tuple[str, ...]
    artifacts: tuple[str, ...] = ()
    entities: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    started_at: str = ""
    ended_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def chain_key(self) -> str:
        return f"{self.chain_type}:{self.event_ids[0]}-{self.event_ids[-1]}"

    def to_record(self) -> dict[str, Any]:
        return {
            "chain_key": self.chain_key,
            "ended_at": self.ended_at or None,
            "event_ids": list(self.event_ids),
            "chain_payload": {
                "chain_type": self.chain_type,
                "event_ids": list(self.event_ids),
                "intents": list(self.intents),
                "artifacts": list(self.artifacts),
                "entities": list(self.entities),
                "tools": list(self.tools),
                "errors": list(self.errors),
                "started_at": self.started_at,
                "ended_at": self.ended_at,
                **dict(self.metadata or {}),
            },
        }


def detect_workflow_chains(
    events: Iterable[Mapping[str, Any]],
    *,
    window_minutes: int = DEFAULT_WINDOW_MINUTES,
) -> list[WorkflowChain]:
    normalized = sorted((_normalize_event(event) for event in events), key=lambda item: item["ts"])
    groups = _group_related_events(normalized, window_minutes=window_minutes)
    chains: list[WorkflowChain] = []
    for group in groups:
        chain_type = _classify_group(group)
        if chain_type:
            chains.append(_chain_from_group(chain_type, group))
    return chains


def store_workflow_chains(chains: Iterable[WorkflowChain], *, repository: Any | None = None) -> list[int]:
    repo = repository or LearningRepository()
    ids: list[int] = []
    for chain in chains:
        try:
            ids.append(int(repo.record_workflow_chain(chain.to_record())))
        except Exception:
            continue
    return ids


def _group_related_events(events: list[dict[str, Any]], *, window_minutes: int) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for event in events:
        if not current:
            current = [event]
            continue
        previous = current[-1]
        if _related(previous, event, current, window_minutes=window_minutes):
            current.append(event)
        else:
            if len(current) >= 2:
                groups.append(current)
            current = [event]
    if len(current) >= 2:
        groups.append(current)
    return groups


def _related(previous: dict[str, Any], event: dict[str, Any], group: list[dict[str, Any]], *, window_minutes: int) -> bool:
    delta_minutes = (event["ts"] - previous["ts"]).total_seconds() / 60
    if delta_minutes > window_minutes:
        return False
    intents = {item["intent"] for item in [*group, event]}
    if _known_sequence_signal(intents):
        return True
    if set(event["artifacts"]) & set(_flatten(group, "artifacts")):
        return True
    if set(event["entities"]) & set(_flatten(group, "entities")):
        return True
    if _explicit_followup(event):
        return True
    return False


def _known_sequence_signal(intents: set[str]) -> bool:
    known_sets = [
        {"daily_refresh", "report_open", "report_email"},
        {"report_debug", "code_report_fix", "report_generate", "report_validation", "report_open"},
        {"symbol_quick_analysis", "company_360_research_report", "report_open"},
        {"quality_breakouts", "watchlist_export"},
        {"portfolio_review", "code_report_fix"},
        {"llm_driven_fallback", "route_failure_diagnostics"},
    ]
    return any(len(intents & known) >= 2 for known in known_sets)


def _classify_group(group: list[dict[str, Any]]) -> str:
    intents = [event["intent"] for event in group]
    intent_set = set(intents)
    text = " ".join(event["query"] for event in group)
    if {"daily_refresh", "report_open", "report_email"}.issubset(intent_set):
        return "daily_refresh_report_review_email"
    if (
        {"code_report_fix", "report_generate", "report_validation"} & intent_set
        and ("report_debug" in intent_set or "links not working" in text or "missing data" in text)
    ):
        return "report_debug_regenerate_validate"
    if (
        "company_360_research_report" in intent_set
        or ("research" in text and len(set(_flatten(group, "entities"))) > 0)
    ) and ("symbol_quick_analysis" in intent_set or "report_open" in intent_set):
        return "stock_research_deep_dive"
    if ("portfolio_review" in intent_set or "portfolio" in text) and (
        "code_report_fix" in intent_set or "report_debug" in intent_set or "fix" in text
    ):
        return "portfolio_review_debug"
    if ("quality_breakouts" in intent_set or "screen" in text or "scanner" in text) and (
        "watchlist_export" in intent_set or "tradingview" in text or "watchlist" in text
    ):
        return "scanner_to_watchlist"
    if ("llm_driven_fallback" in intent_set or any(event["errors"] for event in group)) and (
        "route_failure_diagnostics" in intent_set or "off rails" in text or "missing tool" in text
    ):
        return "fallback_failure_recovery"
    return ""


def _chain_from_group(chain_type: str, group: list[dict[str, Any]]) -> WorkflowChain:
    return WorkflowChain(
        chain_type=chain_type,
        event_ids=tuple(event["event_id"] for event in group),
        intents=tuple(event["intent"] for event in group),
        artifacts=tuple(dict.fromkeys(_flatten(group, "artifacts"))),
        entities=tuple(dict.fromkeys(_flatten(group, "entities"))),
        tools=tuple(dict.fromkeys(_flatten(group, "tools"))),
        errors=tuple(dict.fromkeys(_flatten(group, "errors"))),
        started_at=_format_ts(group[0]["ts"]),
        ended_at=_format_ts(group[-1]["ts"]),
        metadata={"event_count": len(group)},
    )


def _normalize_event(event: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "event_id": int(event.get("event_id") or event.get("id") or 0),
        "ts": _parse_ts(event.get("event_ts") or event.get("timestamp")),
        "query": str(event.get("normalized_query") or event.get("raw_query") or "").lower(),
        "intent": str(event.get("selected_intent") or event.get("intent") or ""),
        "artifacts": _strings(event.get("artifacts")),
        "entities": _strings(event.get("detected_entities") or event.get("entities")),
        "tools": _strings(event.get("tools_executed") or event.get("tools")),
        "errors": _strings(event.get("errors")),
        "payload": dict(event.get("payload") or {}) if isinstance(event.get("payload"), Mapping) else {},
    }


def _parse_ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value or "").strip()
    if not text:
        return datetime.now(timezone.utc)
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime.now(timezone.utc)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _format_ts(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _strings(value: Any) -> list[str]:
    if value in (None, "", {}, []):
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set, frozenset)):
        return [str(item) for item in value if str(item)]
    return [str(value)]


def _flatten(group: list[dict[str, Any]], key: str) -> list[str]:
    values: list[str] = []
    for event in group:
        values.extend(event.get(key) or [])
    return values


def _explicit_followup(event: dict[str, Any]) -> bool:
    return str(event.get("payload", {}).get("followup") or "").lower() in {"1", "true", "yes"}
