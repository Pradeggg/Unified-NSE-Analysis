from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Mapping

from terminal.learning.repository import LearningRepository


@dataclass(frozen=True)
class LearningPattern:
    pattern_key: str
    pattern_type: str
    label: str
    frequency: int
    score: int
    priority: str
    candidate_type: str
    start_date: date
    end_date: date
    failure_severity: int = 1
    manual_effort_saved: int = 1
    automation_potential: int = 1
    evidence_event_ids: tuple[int, ...] = ()
    evidence_chain_ids: tuple[int, ...] = ()
    examples: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        return {
            "pattern_key": self.pattern_key,
            "status": "observed",
            "pattern_payload": {
                "pattern_key": self.pattern_key,
                "pattern_type": self.pattern_type,
                "label": self.label,
                "frequency": self.frequency,
                "score": self.score,
                "priority": self.priority,
                "candidate_type": self.candidate_type,
                "start_date": self.start_date.isoformat(),
                "end_date": self.end_date.isoformat(),
                "failure_severity": self.failure_severity,
                "manual_effort_saved": self.manual_effort_saved,
                "automation_potential": self.automation_potential,
                "evidence_event_ids": list(self.evidence_event_ids),
                "evidence_chain_ids": list(self.evidence_chain_ids),
                "examples": list(self.examples),
                **dict(self.metadata or {}),
            },
        }


@dataclass(frozen=True)
class PatternMiningResult:
    start_date: date
    end_date: date
    window_days: int
    patterns: list[LearningPattern]
    saved_pattern_ids: list[int] = field(default_factory=list)


def mine_learning_patterns(
    *,
    events: Iterable[Mapping[str, Any]],
    workflow_chains: Iterable[Mapping[str, Any]],
    start_date: str | date | datetime,
    end_date: str | date | datetime,
) -> PatternMiningResult:
    start = _to_date(start_date)
    end = _to_date(end_date)
    event_rows = [_normalize_event(row) for row in events]
    chain_rows = [_normalize_chain(row) for row in workflow_chains]

    patterns: list[LearningPattern] = []
    patterns.extend(_query_patterns(event_rows, start, end))
    patterns.extend(_workflow_patterns(chain_rows, start, end))
    patterns.extend(_fallback_failure_patterns(event_rows, start, end))
    patterns.extend(_report_issue_patterns(event_rows, start, end))
    patterns.extend(_manual_fix_patterns(event_rows, start, end))

    deduped = _dedupe_patterns(patterns)
    ordered = sorted(deduped, key=lambda pattern: (-pattern.score, pattern.pattern_key))
    return PatternMiningResult(
        start_date=start,
        end_date=end,
        window_days=(end - start).days + 1,
        patterns=ordered,
    )


def analyze_learning_patterns(
    *,
    repository: Any | None = None,
    end_date: str | date | datetime | None = None,
    window: str = "14d",
    save: bool = True,
) -> PatternMiningResult:
    repo = repository or LearningRepository()
    days = _parse_window_days(window)
    end = _to_date(end_date or date.today())
    start = end - timedelta(days=days - 1)
    events = repo.list_interaction_events(start_date=start, end_date=end)
    chains = repo.list_workflow_chains(start_date=start, end_date=end)
    result = mine_learning_patterns(events=events, workflow_chains=chains, start_date=start, end_date=end)
    if not save:
        return result
    saved_ids = [int(repo.save_pattern(pattern.to_record())) for pattern in result.patterns]
    return PatternMiningResult(
        start_date=result.start_date,
        end_date=result.end_date,
        window_days=result.window_days,
        patterns=result.patterns,
        saved_pattern_ids=saved_ids,
    )


def _query_patterns(events: list[dict[str, Any]], start: date, end: date) -> list[LearningPattern]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        if event["query"]:
            grouped[event["query"]].append(event)
    patterns = []
    for query, rows in grouped.items():
        if len(rows) < 2:
            continue
        patterns.append(
            _build_pattern(
                key=f"query:{query}",
                pattern_type="repeated_user_phrasing",
                label=query,
                rows=rows,
                start=start,
                end=end,
                candidate_type="route_or_prompt_proposal",
                failure_severity=1,
                manual_effort_saved=1,
                automation_potential=2,
                examples=tuple(_first_values([row["raw_query"] for row in rows])),
            )
        )
    return patterns


def _workflow_patterns(chains: list[dict[str, Any]], start: date, end: date) -> list[LearningPattern]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for chain in chains:
        if chain["chain_type"]:
            grouped[chain["chain_type"]].append(chain)
    patterns = []
    for chain_type, rows in grouped.items():
        if len(rows) < 2:
            continue
        manual_effort = 3 if chain_type in {"daily_refresh_report_review_email", "portfolio_review_debug"} else 2
        candidate_type = "workflow_proposal"
        if chain_type == "fallback_failure_recovery":
            candidate_type = "route_tool_skill_candidate"
        patterns.append(
            _build_pattern(
                key=f"workflow:{chain_type}",
                pattern_type="recurring_workflow_chain",
                label=chain_type,
                rows=rows,
                start=start,
                end=end,
                candidate_type=candidate_type,
                failure_severity=3 if chain_type == "fallback_failure_recovery" else 1,
                manual_effort_saved=manual_effort,
                automation_potential=3,
            )
        )
    return patterns


def _fallback_failure_patterns(events: list[dict[str, Any]], start: date, end: date) -> list[LearningPattern]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        if event["intent"] != "llm_driven_fallback":
            continue
        for error in event["errors"]:
            grouped[error].append(event)
    patterns = []
    for error, rows in grouped.items():
        if len(rows) < 2:
            continue
        patterns.append(
            _build_pattern(
                key=f"fallback_failure:{error}",
                pattern_type="repeated_llm_fallback_failure",
                label=error,
                rows=rows,
                start=start,
                end=end,
                candidate_type="route_tool_skill_candidate",
                failure_severity=3,
                manual_effort_saved=3,
                automation_potential=3,
                examples=tuple(_first_values([row["query"] for row in rows])),
                metadata={"missing_evidence": _first_values([item for row in rows for item in row["missing_evidence"]])},
            )
        )
    return patterns


def _report_issue_patterns(events: list[dict[str, Any]], start: date, end: date) -> list[LearningPattern]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        for error in event["errors"]:
            if _is_report_issue(error, event):
                grouped[error].append(event)
    patterns = []
    for issue, rows in grouped.items():
        if len(rows) < 2:
            continue
        patterns.append(
            _build_pattern(
                key=f"report_issue:{issue}",
                pattern_type="repeated_report_validation_issue",
                label=issue,
                rows=rows,
                start=start,
                end=end,
                candidate_type="report_validation_proposal",
                failure_severity=2,
                manual_effort_saved=2,
                automation_potential=2,
                examples=tuple(_first_values([row["query"] for row in rows])),
                metadata={"artifacts": _first_values([item for row in rows for item in row["artifacts"]])},
            )
        )
    return patterns


def _manual_fix_patterns(events: list[dict[str, Any]], start: date, end: date) -> list[LearningPattern]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        if event["intent"] in {"code_report_fix", "report_debug"}:
            grouped[event["intent"]].append(event)
    patterns = []
    for intent, rows in grouped.items():
        if len(rows) < 2:
            continue
        patterns.append(
            _build_pattern(
                key=f"manual_fix:{intent}",
                pattern_type="repeated_manual_fix",
                label=intent,
                rows=rows,
                start=start,
                end=end,
                candidate_type="workflow_proposal",
                failure_severity=2,
                manual_effort_saved=3,
                automation_potential=2,
                examples=tuple(_first_values([row["query"] for row in rows])),
            )
        )
    return patterns


def _build_pattern(
    *,
    key: str,
    pattern_type: str,
    label: str,
    rows: list[dict[str, Any]],
    start: date,
    end: date,
    candidate_type: str,
    failure_severity: int,
    manual_effort_saved: int,
    automation_potential: int,
    examples: tuple[str, ...] = (),
    metadata: Mapping[str, Any] | None = None,
) -> LearningPattern:
    frequency = len(rows)
    recency = _recency_score(rows, end)
    score = frequency * 10 + recency + failure_severity * 5 + manual_effort_saved * 3 + automation_potential * 4
    return LearningPattern(
        pattern_key=key,
        pattern_type=pattern_type,
        label=label,
        frequency=frequency,
        score=int(score),
        priority=_priority(score),
        candidate_type=candidate_type,
        start_date=start,
        end_date=end,
        failure_severity=failure_severity,
        manual_effort_saved=manual_effort_saved,
        automation_potential=automation_potential,
        evidence_event_ids=tuple(_first_ints([row["event_id"] for row in rows])),
        evidence_chain_ids=tuple(_first_ints([row["chain_id"] for row in rows])),
        examples=examples,
        metadata=dict(metadata or {}),
    )


def _dedupe_patterns(patterns: list[LearningPattern]) -> list[LearningPattern]:
    by_key: dict[str, LearningPattern] = {}
    for pattern in patterns:
        current = by_key.get(pattern.pattern_key)
        if current is None or pattern.score > current.score:
            by_key[pattern.pattern_key] = pattern
    return list(by_key.values())


def _normalize_event(event: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "event_id": int(event.get("event_id") or 0),
        "chain_id": 0,
        "ts": _parse_ts(event.get("event_ts") or event.get("timestamp")),
        "query": _normalize_query(event.get("normalized_query") or event.get("raw_query") or ""),
        "raw_query": str(event.get("raw_query") or ""),
        "intent": str(event.get("selected_intent") or event.get("intent") or "").strip(),
        "route_type": str(event.get("route_type") or "").strip(),
        "entities": _strings(event.get("detected_entities") or event.get("entities")),
        "tools": _strings(event.get("tools_executed") or event.get("tools")),
        "artifacts": _strings(event.get("artifacts")),
        "errors": _strings(event.get("errors")),
        "missing_evidence": _strings(event.get("missing_evidence")),
    }


def _normalize_chain(chain: Mapping[str, Any]) -> dict[str, Any]:
    payload = chain.get("chain_payload") if isinstance(chain.get("chain_payload"), Mapping) else {}
    return {
        "event_id": 0,
        "chain_id": int(chain.get("chain_id") or payload.get("chain_id") or 0),
        "ts": _parse_ts(chain.get("started_at") or payload.get("started_at")),
        "chain_type": str(payload.get("chain_type") or chain.get("chain_type") or "").strip(),
        "errors": _strings(payload.get("errors") or chain.get("errors")),
    }


def _recency_score(rows: list[dict[str, Any]], end: date) -> int:
    latest = max((row["ts"].date() for row in rows), default=end)
    age_days = max((end - latest).days, 0)
    if age_days <= 1:
        return 5
    if age_days <= 3:
        return 4
    if age_days <= 7:
        return 3
    return 1


def _priority(score: int) -> str:
    if score >= 50:
        return "high"
    if score >= 25:
        return "medium"
    return "low"


def _is_report_issue(error: str, event: Mapping[str, Any]) -> bool:
    text = f"{error} {' '.join(event.get('artifacts') or [])} {event.get('query') or ''}".lower()
    return "report" in text or "html" in text or "link" in text or "percentage" in text


def _parse_window_days(window: str) -> int:
    text = str(window or "14d").strip().lower()
    if not text.endswith("d"):
        raise ValueError(f"unsupported learning window: {window}")
    days = int(text[:-1])
    if days < 1:
        raise ValueError(f"learning window must be positive: {window}")
    return days


def _to_date(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def _parse_ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return datetime.combine(date.today(), datetime.min.time())


def _normalize_query(value: Any) -> str:
    return " ".join(str(value or "").lower().split())


def _strings(value: Any) -> list[str]:
    if value in (None, "", [], {}):
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [str(value)]
    if isinstance(value, (list, tuple, set, frozenset)):
        return [str(item) for item in value if str(item)]
    return [str(value)]


def _first_values(values: Iterable[str], *, limit: int = 5) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _first_ints(values: Iterable[int], *, limit: int = 10) -> list[int]:
    result: list[int] = []
    for value in values:
        item = int(value or 0)
        if item and item not in result:
            result.append(item)
        if len(result) >= limit:
            break
    return result
