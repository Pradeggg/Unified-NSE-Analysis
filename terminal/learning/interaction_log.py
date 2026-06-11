from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from terminal.learning.repository import LearningRepository


LEARNING_CAPTURE_ENV = "AGENT_ADDA_LEARNING_CAPTURE"
FALSEY_VALUES = {"0", "false", "no", "off", "disabled"}
SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "bcc",
    "body",
    "cc",
    "cookie",
    "email_body",
    "password",
    "recipients",
    "secret",
    "to",
    "token",
}
OVERSIZED_KEYS = {"attachment_bytes", "html", "raw_tool_payload"}
EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")


@dataclass(frozen=True)
class InteractionEvent:
    raw_query: str
    normalized_query: str = ""
    selected_intent: str = ""
    route_type: str = ""
    detected_entities: tuple[str, ...] = ()
    tools_executed: tuple[str, ...] = ()
    reports: tuple[str, ...] = ()
    artifacts: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    clarification_requested: bool = False
    user_marker: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "normalized_query", self.normalized_query or normalize_query(self.raw_query))
        for field_name in (
            "detected_entities",
            "tools_executed",
            "reports",
            "artifacts",
            "errors",
            "missing_evidence",
        ):
            object.__setattr__(self, field_name, tuple(str(item) for item in getattr(self, field_name) or ()))
        object.__setattr__(self, "payload", dict(self.payload or {}))
        if not self.timestamp:
            object.__setattr__(self, "timestamp", datetime.now(timezone.utc).isoformat())

    def to_record(self) -> dict[str, Any]:
        artifacts = list(dict.fromkeys([*self.reports, *self.artifacts]))
        return {
            "event_ts": self.timestamp,
            "raw_query": redact_query(self.raw_query),
            "normalized_query": normalize_query(redact_query(self.normalized_query)),
            "selected_intent": self.selected_intent,
            "route_type": self.route_type,
            "detected_entities": list(self.detected_entities),
            "tools_executed": list(self.tools_executed),
            "artifacts": artifacts,
            "errors": list(self.errors),
            "missing_evidence": list(self.missing_evidence),
            "payload": sanitize_payload(
                {
                    **self.payload,
                    "clarification_requested": self.clarification_requested,
                    "user_marker": self.user_marker,
                }
            ),
        }


def capture_interaction_event(
    event: InteractionEvent,
    *,
    repository: Any | None = None,
    env: Mapping[str, str] | None = None,
) -> int | None:
    if not learning_capture_enabled(env=env):
        return None
    repo = repository or LearningRepository()
    try:
        return repo.record_interaction_event(event.to_record())
    except Exception:
        return None


def build_agent_turn_event(user_input: str, result: Mapping[str, Any]) -> InteractionEvent:
    trace = list(result.get("trace") or [])
    tools = []
    entities = []
    errors = []
    missing = []
    artifacts = []
    for item in trace:
        if not isinstance(item, Mapping):
            continue
        if item.get("tool"):
            tools.append(str(item["tool"]))
        args = item.get("args") if isinstance(item.get("args"), Mapping) else {}
        res = item.get("result") if isinstance(item.get("result"), Mapping) else {}
        for source in (args, res):
            symbol = source.get("symbol")
            if symbol:
                entities.append(str(symbol).upper())
            path = source.get("path") or source.get("report_path") or source.get("html_path")
            if path:
                artifacts.append(str(path))
        if item.get("error"):
            errors.append(str(item["error"]))
        if res.get("error"):
            errors.append(str(res["error"]))
        for key in ("missing_evidence", "missing_inputs"):
            if isinstance(res.get(key), list):
                missing.extend(str(value) for value in res[key])

    return InteractionEvent(
        raw_query=user_input,
        selected_intent=str(result.get("intent") or ""),
        route_type="agent_query",
        detected_entities=tuple(dict.fromkeys(entities)),
        tools_executed=tuple(dict.fromkeys(tools)),
        artifacts=tuple(dict.fromkeys(artifacts)),
        errors=tuple(errors),
        missing_evidence=tuple(missing),
        clarification_requested=str(result.get("intent") or "") == "ask_clarification",
        payload={
            "backend": result.get("backend"),
            "usage": result.get("usage") or {},
        },
    )


def build_command_action_event(
    raw_query: str,
    *,
    action: str,
    report: str | None = None,
    recipient_list_key: str | None = None,
    payload: Mapping[str, Any] | None = None,
) -> InteractionEvent:
    artifacts = (str(report),) if report else ()
    clean_payload = dict(payload or {})
    if recipient_list_key:
        clean_payload["recipient_list_key"] = recipient_list_key
    return InteractionEvent(
        raw_query=raw_query,
        selected_intent=action,
        route_type="command_action",
        reports=artifacts,
        artifacts=artifacts,
        payload=clean_payload,
    )


def learning_capture_enabled(*, env: Mapping[str, str] | None = None) -> bool:
    source = os.environ if env is None else env
    return str(source.get(LEARNING_CAPTURE_ENV, "1")).strip().lower() not in FALSEY_VALUES


def normalize_query(query: str) -> str:
    return " ".join(str(query or "").lower().split())


def redact_query(query: str) -> str:
    redacted = EMAIL_RE.sub("[email]", str(query or ""))
    redacted = re.sub(r"(?i)(--to|--cc|--bcc)\s+\S+", r"\1 [redacted]", redacted)
    return redacted


def sanitize_payload(value: Any) -> Any:
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            lowered = key_text.lower()
            if lowered in SENSITIVE_KEYS or any(token in lowered for token in SENSITIVE_KEYS):
                continue
            if lowered in OVERSIZED_KEYS:
                continue
            sanitized[key_text] = sanitize_payload(item)
        return sanitized
    if isinstance(value, (list, tuple, set, frozenset)):
        return [sanitize_payload(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
